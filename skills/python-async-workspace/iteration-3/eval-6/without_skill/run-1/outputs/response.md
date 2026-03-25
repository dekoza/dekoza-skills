Your current design is wrong. `asyncio.run()` inside library methods is the bad boundary:
- it explodes if the current thread already has a running loop
- it ignores AnyIO’s thread/loop bridging APIs
- it creates a fresh loop per call, which is the wrong lifetime for most async clients
- it does not solve foreign-thread re-entry into an existing app loop

The AnyIO-first rule is simple:

- async code stays async
- sync code crosses the boundary exactly once, at the edge
- use `anyio.run()` only at a true top-level sync entrypoint
- use `anyio.from_thread.*` or a `BlockingPortal` when crossing between threads and an existing loop

A good shape looks like this:

```python
from __future__ import annotations

from anyio.from_thread import BlockingPortalProvider


class AsyncClient:
    async def fetch(self, key: str) -> str:
        return f"value:{key}"

    async def aclose(self) -> None:
        pass


class SyncClient:
    def __init__(self, async_client: AsyncClient) -> None:
        self._async_client = async_client
        self._portal_provider = BlockingPortalProvider()

    def fetch(self, key: str) -> str:
        with self._portal_provider as portal:
            return portal.call(self._async_client.fetch, key)

    def close(self) -> None:
        with self._portal_provider as portal:
            portal.call(self._async_client.aclose)
```

Why this is correct:
- the async client remains the source of truth
- the sync wrapper owns one reusable async boundary instead of creating a new loop per method call
- repeated calls from multiple sync threads reuse the same portal instead of spinning up a loop every time

When each tool is right:

- `anyio.run(...)`
  - use once at a top-level sync entrypoint like CLI `main()`
  - do not bury it inside methods

- `anyio.from_thread.run(...)`
  - use in an AnyIO worker thread created by `anyio.to_thread.run_sync(...)`
  - this re-enters the existing event loop directly

```python
from anyio import from_thread, to_thread

def legacy_sync_func(client: AsyncClient, key: str) -> str:
    return from_thread.run(client.fetch, key)

async def handler(client: AsyncClient) -> str:
    return await to_thread.run_sync(legacy_sync_func, client, "abc")
```

- `current_token()` + `from_thread.run(..., token=token)`
  - use for a one-off call from a foreign thread that was not created by AnyIO

- `BlockingPortal`
  - use when sync code in foreign thread(s) needs ongoing access to an existing async environment
  - also use when you need portal-only features: spawning tasks, wrapping async context managers, sharing one bridge for many calls

`BlockingPortal` is the right tool when:
- calls come from non-AnyIO threads
- calls are frequent, not one-shot
- you need one stable async runtime behind a sync facade
- you need `start_task_soon()`, `start_task()`, or `wrap_async_context_manager()`

It is not the right tool when:
- you are already in async code; just `await`
- you are in an AnyIO worker thread doing a simple call back into the loop; use `from_thread.run()`
- you only need a one-shot top-level sync entrypoint; use `anyio.run()`

The nastiest failure mode in your current setup is this:
- if a framework loop is already running and sync code is invoked on that same loop thread, a sync wrapper cannot safely block there
- the fix is not “find a smarter `run()`”
- the fix is: call the async client directly, or move the sync call off the loop thread with `await to_thread.run_sync(...)`

Decision table:
- sync top-level app entrypoint -> `anyio.run()`
- sync call from AnyIO worker thread -> `from_thread.run()`
- sync call from foreign thread, one-off -> token + `from_thread.run()`
- sync call from foreign thread, repeated/shared/needs task spawning -> `BlockingPortal` / `BlockingPortalProvider`

If you want, I can also sketch a production-grade wrapper with `close()`, context manager support, and separate patterns for “sync-first app” vs “async app with legacy sync callbacks.”
