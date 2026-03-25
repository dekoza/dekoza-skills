Your current approach is wrong. `asyncio.run()` inside per-method sync wrappers is brittle in all three places you named:

- inside a thread spawned by AnyIO, it bypasses AnyIO’s thread/loop bridge
- inside a foreign thread, it creates unrelated event loops per call
- inside a thread that already has a running loop, it just fails

The clean boundary is:

- async code owns the real client
- sync legacy code talks to that client through an AnyIO bridge
- worker-thread callbacks use `anyio.from_thread.*`
- long-running sync work runs under `anyio.to_thread.run_sync(...)` and cooperatively checks cancellation

A good shape looks like this:

```python
from __future__ import annotations

import time
from typing import Any

import anyio
from anyio import Event, from_thread, to_thread
from anyio.from_thread import BlockingPortalProvider


class AsyncClient:
    async def fetch(self, key: str) -> str:
        await anyio.sleep(0.1)
        return f"value:{key}"


class SyncClient:
    def __init__(self, async_client: AsyncClient) -> None:
        self._async_client = async_client
        self._portal_provider = BlockingPortalProvider()

    def fetch(self, key: str) -> str:
        with self._portal_provider as portal:
            return portal.call(self._async_client.fetch, key)
```

That is the AnyIO-first sync facade for legacy callers from normal synchronous code and foreign threads.

Use the lighter thread bridges when you are already inside AnyIO-managed threads:

```python
def worker_sets_event(event: Event) -> None:
    # Correct for an AnyIO worker thread
    from_thread.run_sync(event.set)
```

```python
def long_running_sync_job() -> None:
    while True:
        from_thread.check_cancelled()
        do_one_small_step()
        time.sleep(0.05)


async def run_job() -> None:
    await to_thread.run_sync(long_running_sync_job)
```

If the sync code needs to call an async function from an AnyIO worker thread, use:

```python
def worker_calls_async(client: AsyncClient, key: str) -> str:
    return from_thread.run(client.fetch, key)
```

The important boundary rules are:

- `to_thread.run_sync(...)`: async task -> blocking sync function in worker thread
- `from_thread.run(...)`: AnyIO worker thread -> coroutine on the event loop
- `from_thread.run_sync(...)`: AnyIO worker thread -> thread-unsafe sync callback on the event loop thread, like `event.set`
- `from_thread.check_cancelled()`: cooperative cancellation inside long-running sync code running in an AnyIO worker thread

When `BlockingPortal` is the right tool:

- a synchronous API must call async code from threads that are not AnyIO worker threads
- you need repeated sync->async calls, not a one-off handoff
- you need to spawn async tasks from sync code
- you need to wrap async context managers for sync code

When it is not the right tool:

- a worker thread only needs a one-off call back into the loop; use `from_thread.run()` / `from_thread.run_sync()`
- you are already in async code; just `await`
- you are trying to make a sync wrapper callable from the same thread that is already running the app’s event loop

That last case is the trap. If a framework already has a running loop on the current thread, a synchronous method cannot safely block that same thread waiting for async work. The fix is architectural:

- async callers use the async client directly
- sync callers use the sync wrapper
- if truly necessary, run the sync caller in another thread and let it use a portal there

For foreign threads, you have two choices:

- one-off callback into the loop: pass an AnyIO token and use `from_thread.run(..., token=token)` or `from_thread.run_sync(..., token=token)`
- long-lived/repeated bridge: use `BlockingPortal` / `BlockingPortalProvider`

The practical recommendation:

- keep one real async client
- expose one sync facade backed by `BlockingPortalProvider`
- never call that sync facade from async code
- use `from_thread.run_sync(event.set)` for the event callback
- use `from_thread.check_cancelled()` inside the long-running sync function

If you want, I can turn this into a small production-ready wrapper class with shutdown semantics and examples for both “foreign thread” and “framework already has a loop” cases.
