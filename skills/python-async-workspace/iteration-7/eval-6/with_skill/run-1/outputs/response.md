Your current pattern is wrong. `asyncio.run()` inside library methods is a boundary bug, not a wrapper strategy.

- It is illegal in a thread that already has a running loop.
- It creates a fresh loop per call, which shreds lifecycle, cancellation, and connection ownership.
- It is the wrong abstraction for AnyIO worker threads and foreign threads.

This should be `AnyIO-portable`.

```python
import anyio
from anyio import from_thread, to_thread
from anyio.from_thread import BlockingPortal


class AsyncClient:
    async def fetch(self, key: str) -> str:
        await anyio.sleep(0.1)
        return f"value:{key}"


class SyncClient:
    def __init__(self, async_client: AsyncClient, portal: BlockingPortal) -> None:
        self._async_client = async_client
        self._portal = portal

    def fetch(self, key: str) -> str:
        return self._portal.call(self._async_client.fetch, key)
```

The correct boundary is:

- async code owns the real client and its lifetime
- sync code gets a thin adapter
- cross-thread hops use AnyIO thread APIs, not nested runners

Example when an async app/framework already owns the loop:

```python
import anyio
from anyio.from_thread import BlockingPortal

async def main() -> None:
    async_client = AsyncClient()

    async with BlockingPortal() as portal:
        sync_client = SyncClient(async_client, portal)
        await anyio.to_thread.run_sync(legacy_sync_entrypoint, sync_client)
```

That is the right shape when legacy sync code must call async internals while the app loop already exists.

Worker-thread callback that only needs to set an AnyIO `Event`:

```python
def worker_callback(done: anyio.Event) -> None:
    # blocking work...
    from_thread.run_sync(done.set)
```

Use `from_thread.run_sync()` there, not `from_thread.run()`, because `event.set` is a sync loop-thread callback.

Worker-thread callback that needs to call async client code once:

```python
def worker_fetch(sync_client: SyncClient) -> str:
    return sync_client.fetch("abc")
```

Or directly from an AnyIO worker thread:

```python
def worker_fetch_direct(async_client: AsyncClient) -> str:
    return from_thread.run(async_client.fetch, "abc")
```

Use `from_thread.run()` only for async callables.

Long-running sync function that must stop when the host task is cancelled:

```python
import time
from anyio import from_thread

def long_sync_job() -> None:
    while True:
        from_thread.check_cancelled()
        do_one_chunk()
        time.sleep(0.05)
```

Run it with:

```python
await to_thread.run_sync(long_sync_job)
```

The footgun here is important:

- `abandon_on_cancel=True` does not stop the thread
- it only stops waiting for the result
- prompt stopping requires cooperative polling with `from_thread.check_cancelled()`

For foreign threads, use a token for one-off hops, or a portal for repeated structured access:

```python
from threading import Thread
from anyio.lowlevel import current_token

def foreign_thread_set(done: anyio.Event, token) -> None:
    from_thread.run_sync(done.set, token=token)

async def main() -> None:
    done = anyio.Event()
    token = current_token()
    Thread(target=foreign_thread_set, args=(done, token)).start()
    await done.wait()
```

When `BlockingPortal` is the right tool:

- sync facade over an async client
- repeated sync-to-async calls from threads
- foreign threads that need more than a one-shot callback
- wrapping async context managers or spawning managed tasks from sync code

When it is not:

- a one-off call from an AnyIO worker thread
- a worker-thread callback that only needs `event.set()`
- trying to make a blocking sync API safe to call from the loop thread itself

That last case is still wrong. If code is already on the event-loop thread, call the async API directly. A synchronous wrapper does not become safe just because it uses a portal.

Minimum verification:

- test under both AnyIO backends you claim to support: `asyncio` and `trio`
- one test for worker-thread `Event.set()`
- one test for foreign-thread token hop
- one cancellation test proving `from_thread.check_cancelled()` stops the sync function promptly

References used: AnyIO thread docs, `threads-boundaries.md`, `cancellation-timeouts.md`, `decision-matrix.md`, and Python `asyncio.run()` docs.