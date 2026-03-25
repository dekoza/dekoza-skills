This is `AnyIO-portable`.

Calling `asyncio.run()` inside wrapper methods is the wrong boundary. It fails under a running framework loop, creates a fresh loop per call, breaks client/resource ownership, and gives you fake cancellation semantics. It only "works" in trivial scripts.

The correct boundary is:

- async code stays async
- blocking sync code is offloaded with `anyio.to_thread.run_sync()`
- worker threads call back into the loop with `anyio.from_thread.run()` / `run_sync()`
- true sync callers use a `BlockingPortal`, not `asyncio.run()`

```python
from anyio import from_thread, to_thread
from anyio.from_thread import BlockingPortal


class SyncClient:
    def __init__(self, portal: BlockingPortal, async_client) -> None:
        self._portal = portal
        self._async_client = async_client

    def get_user(self, user_id: str) -> dict:
        return self._portal.call(self._async_client.get_user, user_id)

    def close(self) -> None:
        self._portal.call(self._async_client.aclose)


async def serve_legacy_code(async_client) -> None:
    async with BlockingPortal() as portal:
        sync_client = SyncClient(portal, async_client)
        await to_thread.run_sync(legacy_entrypoint, sync_client)
```

Why this is correct:

- `BlockingPortal` keeps async work on one owned loop
- sync code can call async methods repeatedly without nesting runners
- it still works when some framework already has a running loop, because the portal is the bridge, not `asyncio.run()`

For a sync API used from many threads, `BlockingPortalProvider` is usually the cleaner tool than creating a brand-new portal per method call.

For the worker-thread callback that only needs to set an AnyIO `Event`, do not open a portal:

```python
from anyio import Event, from_thread, to_thread

def worker(event: Event) -> None:
    from_thread.run_sync(event.set)

async def main() -> None:
    event = Event()
    await to_thread.run_sync(worker, event)
    await event.wait()
```

That is the cheap, correct path because the thread was spawned by `to_thread.run_sync()`. A portal would be unnecessary machinery.

For a foreign thread, `from_thread.run_sync()` only works if you pass an AnyIO token or give that thread a portal. One-off foreign-thread callback: use a token. Repeated calls or task spawning: use a portal.

For the long-running sync function that must stop promptly on host-task cancellation, thread cancellation does not exist. The function has to cooperate:

```python
import time

from anyio import from_thread, move_on_after, to_thread

def long_running_sync() -> None:
    while True:
        from_thread.check_cancelled()
        do_one_small_blocking_step()
        time.sleep(0.1)

async def run_it() -> None:
    with move_on_after(5):
        await to_thread.run_sync(long_running_sync)
```

Important part:

- `from_thread.check_cancelled()` is what makes the worker thread notice host-task cancellation
- `abandon_on_cancel=True` is not a substitute; it only stops waiting for the thread, it does not stop the thread

Use `BlockingPortal` when:

- you need a real sync facade over an async client
- sync callers may come from foreign threads
- you need repeated sync-to-async calls on one owned loop
- you need to wrap async context managers or spawn async tasks from sync code

Do not use `BlockingPortal` when:

- an AnyIO worker thread just needs a one-off callback like `event.set()` or sending to a memory stream
- a token or `from_thread.run_sync()` is enough

Highest-risk footgun: mixing all three models at once - `asyncio.run()` in methods, `to_thread.run_sync()` around them, and framework-owned loops above them. That is brittle garbage. Pick one AnyIO boundary and keep ownership explicit.

References used: `threads-boundaries.md`, `cancellation-timeouts.md`, `decision-matrix.md`, AnyIO thread docs, Python `asyncio.run()` docs.

Minimum verification:

1. test the sync wrapper from plain sync code
2. test it from an AnyIO worker thread
3. test it under an already-running framework loop
4. if you claim portability, run the tests on both asyncio and Trio backends
