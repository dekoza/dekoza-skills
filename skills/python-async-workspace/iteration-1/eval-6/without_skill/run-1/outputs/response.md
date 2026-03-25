The current design is wrong because `asyncio.run()` is only a top-level program entrypoint. Python documents that it cannot be called while another asyncio event loop is already running in the same thread, so putting it inside per-method sync wrappers is invalid under frameworks that already own the loop.

Use an AnyIO-first boundary instead: keep the real client async, and make the sync facade cross the boundary through AnyIO thread/portal APIs rather than starting fresh event loops ad hoc.

```python
from __future__ import annotations

from anyio.from_thread import BlockingPortal, BlockingPortalProvider


class AsyncClient:
    async def fetch_user(self, user_id: str) -> dict[str, str]:
        return {"user_id": user_id}

    async def aclose(self) -> None:
        return None


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

- The async client stays async; no hidden loop creation is scattered across methods.
- The sync wrapper uses one AnyIO-managed blocking portal boundary instead of `asyncio.run()`.
- `BlockingPortalProvider` is the right wrapper for a reusable sync API because concurrent calls from multiple sync threads can share the same portal instead of spawning a new loop per call.

When `BlockingPortal` is the right tool:

- Use it when synchronous code from one or more non-async threads needs repeated access to async code.
- Use it when the sync side needs more than one-off calls: spawning tasks, wrapping async context managers, or keeping async state alive across many sync method calls.
- Use `start_blocking_portal()` when the sync layer owns the lifetime and can dedicate a thread to the async loop.
- Use `async with BlockingPortal()` inside an already-running async app when that app owns the loop and needs to expose a portal to synchronous worker code.

Do not overuse it. There are two distinct thread cases in AnyIO:

1. AnyIO worker thread

If the synchronous function is already running in a thread created by `anyio.to_thread.run_sync()`, it can call back into the loop with `anyio.from_thread.run()` / `run_sync()` directly. AnyIO documents that this works only for worker threads spawned by `to_thread.run_sync()`.

2. Foreign thread

If the thread was created outside AnyIO, direct `from_thread.run()` is not enough by itself. AnyIO documents two valid bridges:

- pass an event-loop token from `anyio.lowlevel.current_token()` for one-off access
- expose a `BlockingPortal` for richer or repeated sync-to-async bridging

That means the rule is simple:

- AnyIO worker thread -> `from_thread.run()` / `from_thread.run_sync()`
- Foreign thread, one-off callback -> token-based access
- Foreign thread, repeated calls or task spawning -> `BlockingPortal`

Example inside an async app that must call legacy sync code in a worker thread:

```python
from anyio import from_thread, to_thread


class AsyncClient:
    async def fetch_user(self, user_id: str) -> dict[str, str]:
        return {"user_id": user_id}


def legacy_sync_function(client: AsyncClient) -> dict[str, str]:
    return from_thread.run(client.fetch_user, "42")


async def handler(client: AsyncClient) -> dict[str, str]:
    return await to_thread.run_sync(legacy_sync_function, client)
```

That path is lighter than a portal because the sync code is already in an AnyIO worker thread.

Cancellation caveat:

- Do not promise that cancelling the async caller stops arbitrary code already running in a worker thread. AnyIO documents that even with `abandon_on_cancel=True`, the thread keeps running; only the waiting task stops caring about the result.
- If you need cooperative cancellation inside thread code, the thread code must explicitly call `anyio.from_thread.check_cancelled()`.

What to avoid:

- Do not call `asyncio.run()` inside library methods.
- Do not call `portal.call()` from the event-loop thread itself; the portal is for crossing in from other threads.
- Do not wrap every sync method with its own brand-new event loop unless the process is truly a one-shot top-level sync script.

References used:

- Python docs, `asyncio.run()`: `https://docs.python.org/3/library/asyncio-runner.html#running-an-asyncio-program`
- AnyIO docs, working with threads: `https://anyio.readthedocs.io/en/stable/threads.html`

Verification step:

- I verified the `asyncio.run()` restriction against the Python docs.
- I verified the AnyIO worker-thread vs foreign-thread distinction, token-based access, `BlockingPortal`, `BlockingPortalProvider`, and cancellation notes against the AnyIO thread docs.
- I did not claim local runtime verification here because this repository's `pyproject.toml` does not declare `anyio`, so execution in this repo would have been invented rather than verified.
