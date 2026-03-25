`asyncio.run()` inside wrapper methods is the wrong boundary. It creates a fresh loop per call, explodes if a framework loop is already running, and bypasses AnyIO’s thread/cancellation model.

The AnyIO-first boundary is:

- async code owns the client and the event loop
- sync code crosses that boundary with `anyio.from_thread.*` or a `BlockingPortal`
- blocking sync work runs under `anyio.to_thread.run_sync(...)`

A sane split looks like this:

```python
import time
from threading import Thread

import anyio
from anyio import Event, from_thread, to_thread
from anyio.from_thread import BlockingPortal
from anyio.lowlevel import current_token


class AsyncClient:
    async def fetch(self, value: str) -> str:
        await anyio.sleep(0.1)
        return value.upper()


class SyncClient:
    def __init__(self, async_client: AsyncClient, portal: BlockingPortal) -> None:
        self._async_client = async_client
        self._portal = portal

    def fetch(self, value: str) -> str:
        return self._portal.call(self._async_client.fetch, value)


def worker_thread_callback(event: Event) -> None:
    # This is correct for an AnyIO worker thread.
    from_thread.run_sync(event.set)


def foreign_thread_callback(event: Event, token) -> None:
    # This is correct for a non-AnyIO thread.
    from_thread.run_sync(event.set, token=token)


def long_running_sync_function() -> None:
    while True:
        from_thread.check_cancelled()
        time.sleep(0.1)  # keep blocking chunks short if you want prompt stop


def legacy_sync_entrypoint(sync_client: SyncClient, event: Event) -> str:
    worker_thread_callback(event)
    return sync_client.fetch("hello")


async def main() -> None:
    event = Event()
    async_client = AsyncClient()

    async with BlockingPortal() as portal:
        sync_client = SyncClient(async_client, portal)

        result = await to_thread.run_sync(legacy_sync_entrypoint, sync_client, event)
        await event.wait()
        print(result)

        thread = Thread(
            target=foreign_thread_callback,
            args=(event, current_token()),
        )
        thread.start()
        await event.wait()

        with anyio.move_on_after(1):
            await to_thread.run_sync(long_running_sync_function)


anyio.run(main)
```

What to use when:

- `to_thread.run_sync(...)`
  - run blocking sync code from async code
  - this is the correct async -> sync boundary

- `from_thread.run(...)`
  - call an async function from an AnyIO worker thread
  - only works if that thread came from `to_thread.run_sync(...)`

- `from_thread.run_sync(...)`
  - schedule thread-unsafe sync work back onto the loop thread
  - perfect for `event.set()`, stream sends, etc.

- `from_thread.check_cancelled()`
  - use inside long-running sync code running in an AnyIO worker thread
  - this is cooperative cancellation; Python cannot kill the thread for you

When `BlockingPortal` is the right tool:

- your sync wrapper must call async methods repeatedly from sync code
- calls may come from foreign threads, not just AnyIO worker threads
- you need more than one-off calls:
  - spawn async tasks
  - use async context managers
  - keep a long-lived bridge open

When `BlockingPortal` is not the right tool:

- a one-off callback from an AnyIO worker thread just needs `event.set()`
- use `from_thread.run_sync(event.set)` instead
- a one-off call from a foreign thread can often use a passed `token` instead of a full portal

The key rule is simple:

- don’t hide loop creation inside methods
- create one explicit boundary
- if the app already has a loop, bridge into that loop
- if sync code needs a durable bridge, use a portal
- if sync code only needs a tiny one-shot hop, use `from_thread.run()` / `run_sync()` with the right thread context

One subtlety: `check_cancelled()` is only prompt if your sync function returns to Python regularly. If it sits in a single long blocking syscall, cancellation will wait for that call to unblock. Use short polling timeouts or interruptible blocking APIs if prompt stop actually matters.
