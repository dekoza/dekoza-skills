Answer mode: `AnyIO-portable`

References used: `skills/python-async/SKILL.md`, `skills/python-async/references/decision-matrix.md`, `skills/python-async/references/threads-boundaries.md`, `skills/python-async/references/testing.md`, and the official AnyIO thread docs at `https://anyio.readthedocs.io/en/stable/threads.html`.

Your current design is wrong. `asyncio.run()` inside wrapper methods is only valid at a top-level program boundary. Python's docs are explicit: it cannot run while another event loop is already running in the same thread, and it is not a safe per-method bridge under a framework-owned loop.

The correct boundary is this:

- keep the real client async
- expose a separate sync facade for legacy callers
- make that facade cross into async code through one owned AnyIO boundary
- never call the sync facade from code that is already async on the same thread

Good shape:

```python
from __future__ import annotations

from anyio.from_thread import BlockingPortalProvider


class AsyncClient:
    async def fetch_user(self, user_id: str) -> dict[str, str]:
        ...

    async def aclose(self) -> None:
        ...


class SyncClient:
    def __init__(self, async_client: AsyncClient) -> None:
        self._async_client = async_client
        self._portal_provider = BlockingPortalProvider()

    def fetch_user(self, user_id: str) -> dict[str, str]:
        with self._portal_provider as portal:
            return portal.call(self._async_client.fetch_user, user_id)

    def close(self) -> None:
        with self._portal_provider as portal:
            portal.call(self._async_client.aclose)
```

Why this boundary is correct:

- the sync API does not create a fresh event loop per method call
- repeated calls reuse one portal instead of nesting runners
- multiple legacy threads can share the same bridge safely
- async work stays owned by AnyIO rather than ad-hoc `asyncio.run()` calls

Worker-thread vs foreign-thread rule:

- If a thread was spawned by `anyio.to_thread.run_sync()`, it is an AnyIO worker thread. That thread may call `anyio.from_thread.run()` or `anyio.from_thread.run_sync()` directly.
- If it is some other thread created outside AnyIO, it is a foreign thread. That thread cannot assume `from_thread.run()` works by magic.

For a foreign thread, use one of these:

1. `current_token()` plus `from_thread.run()` / `from_thread.run_sync()` for a one-off call.
2. `BlockingPortal` for repeated calls, task spawning, or async context-manager bridging.

One-off foreign-thread bridge:

```python
from threading import Thread

from anyio import Event, from_thread, run
from anyio.lowlevel import current_token


def notify_loop(event: Event, token) -> None:
    from_thread.run_sync(event.set, token=token)


async def main() -> None:
    event = Event()
    thread = Thread(target=notify_loop, args=(event, current_token()))
    thread.start()
    await event.wait()
    thread.join()


run(main)
```

When `BlockingPortal` is the right tool:

- you are building a real synchronous facade over async internals
- synchronous callers will make repeated calls, possibly from several threads
- you need to spawn async tasks from sync code
- you need to wrap an async context manager for synchronous use

When it is not the right tool:

- you only need one one-off foreign-thread callback; a token is simpler
- the caller is already running on the app's event-loop thread; use the async client directly instead of blocking back into the same loop

Do not promise fake cancellation behavior. Cancelling the async task that is waiting on `to_thread.run_sync()` does not stop arbitrary Python code already running in the worker thread. AnyIO can abandon the wait or let thread code cooperatively check `from_thread.check_cancelled()`, but Python still does not provide forced thread cancellation.

The highest-risk footgun is trying to hide loop ownership. A sync wrapper is for sync callers. If framework code already has a running loop in that thread, do not route back through the sync wrapper; call the async API.

Minimum verification step:

- add one test that calls the sync wrapper from plain synchronous code and confirms repeated calls succeed
- add one test that calls the bridge from a foreign thread and proves token-or-portal access works
- add one test that cancellation of a waiting async task does not claim to kill the underlying worker thread
