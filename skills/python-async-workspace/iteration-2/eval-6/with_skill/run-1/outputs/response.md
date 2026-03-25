The fix is not “find a safer `asyncio.run()` trick.” That model is wrong.

This is `AnyIO-portable`, based on AnyIO’s thread-boundary docs and Python’s `asyncio.run()` docs.

- `asyncio.run()` inside client methods is broken because it creates a new runner per call, it cannot run when an event loop is already running in the same thread, and it hides who actually owns async resources.
- There is no single sync method implementation that is correct for plain sync code, AnyIO worker threads, foreign threads, and framework loop threads at once.
- The correct boundary is: keep the async client truly async, and put one explicit sync/async bridge at the outer edge.

A good shape looks like this:

```python
import anyio
from anyio.from_thread import BlockingPortal

class AsyncClient:
    async def fetch(self, key: str) -> str:
        ...

    async def aclose(self) -> None:
        ...

class SyncClient:
    def __init__(self, portal: BlockingPortal, client: AsyncClient) -> None:
        self._portal = portal
        self._client = client

    def fetch(self, key: str) -> str:
        return self._portal.call(self._client.fetch, key)

    def close(self) -> None:
        self._portal.call(self._client.aclose)


def legacy_code(client: SyncClient) -> None:
    value = client.fetch("abc")
    ...


async def app_entrypoint() -> None:
    client = AsyncClient()

    async with BlockingPortal() as portal:
        sync_client = SyncClient(portal, client)
        await anyio.to_thread.run_sync(legacy_code, sync_client)
```

Why this boundary is correct:

- The app or top-level owner creates and owns the async client.
- Legacy synchronous code runs in a worker thread via `anyio.to_thread.run_sync()`.
- The sync wrapper does not start or nest event loops; it submits work back through the portal.
- Resource lifetime stays explicit.

When `BlockingPortal` is the right tool:

- You need a real sync facade over async internals.
- Calls may come from threads that are not guaranteed to be AnyIO worker threads.
- You need repeated sync calls, not just one callback.
- You need to spawn async tasks or wrap async context managers from sync code.

When `BlockingPortal` is not the tool:

- You are already on the event-loop thread. Then the sync wrapper is the wrong API; use `await client.fetch(...)`.
- You only need a one-off call from an AnyIO worker thread. Then `from_thread.run()` is narrower and simpler.
- You only need a one-off call from a foreign thread and you can safely pass an event-loop token. Then `current_token()` + `from_thread.run(..., token=token)` is enough.

Use this decision table:

- `AnyIO worker thread created by to_thread.run_sync()` -> `from_thread.run()` for one-offs
- `Foreign thread` -> token for one-offs, `BlockingPortal` for reusable access
- `Framework/request handler already on running loop` -> do not call sync wrapper; use async client directly
- `Pure sync application needing a long-lived sync API` -> own a portal for the wrapper lifetime, often with `start_blocking_portal()` or `BlockingPortalProvider`

The big footgun:

- Never call a sync wrapper from the same event-loop thread that must execute the async work. You block the loop and can deadlock or at least stall the app.

If you need a reusable sync API for non-async callers, use a long-lived portal instead of per-call runners. AnyIO even documents `BlockingPortalProvider` for sharing one portal across many sync calls/threads.

Minimal rule of thumb:

- `await` in async code
- `to_thread.run_sync()` for blocking legacy sync code
- `from_thread.run()` only from known AnyIO worker threads
- `BlockingPortal` for a real sync facade across thread boundaries
- never `asyncio.run()` inside methods

If you want, I can also show:
1. a standalone `SyncClient` that owns its own dedicated portal thread, or
2. a version that hard-fails when someone tries to use the sync facade from inside an asyncio framework loop.
