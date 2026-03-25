The fix is to stop spawning ad-hoc event loops. `asyncio.run()` inside wrapper methods is wrong in all three cases you named: it explodes under a running loop, it is the wrong bridge from AnyIO worker threads, and it is not the right primitive for foreign threads.

This is `AnyIO-portable`.

- Keep the async client as the real implementation.
- Choose one explicit sync/async boundary.
- Use AnyIO thread bridges at that boundary.
- Use `BlockingPortal` only when synchronous code needs repeated, structured access to async code.

Bad pattern:

```python
class LegacyClient:
    def get_user(self, user_id: str) -> User:
        return asyncio.run(self._async_client.get_user(user_id))
```

That wrapper is brittle by design.

Correct boundary for code already running under AnyIO or an async framework:

```python
import anyio
from anyio import from_thread

class AsyncClient:
    async def get_user(self, user_id: str) -> dict:
        ...

async def call_legacy(async_client: AsyncClient) -> None:
    event = anyio.Event()
    await anyio.to_thread.run_sync(legacy_sync_entrypoint, async_client, event)

def legacy_sync_entrypoint(async_client: AsyncClient, event: anyio.Event) -> None:
    user = from_thread.run(async_client.get_user, "123")
    from_thread.run_sync(event.set)
```

Why this is correct:

- `anyio.to_thread.run_sync()` creates an AnyIO-managed worker thread.
- Inside that worker thread, `from_thread.run()` calls async callables back on the loop.
- Inside that worker thread, `from_thread.run_sync()` is for loop-thread sync callbacks like `event.set`.
- Do not use `from_thread.run(event.set)`: `event.set` is synchronous.

For the long-running sync function that must stop when the host task is cancelled:

```python
import time
import anyio
from anyio import from_thread

def blocking_sync_job() -> None:
    while True:
        from_thread.check_cancelled()
        do_one_blocking_chunk()

def do_one_blocking_chunk() -> None:
    time.sleep(0.1)

async def run_job() -> None:
    await anyio.to_thread.run_sync(blocking_sync_job)
```

Key rule:

- Python cannot kill a worker thread.
- Prompt stop requires cooperative polling with `from_thread.check_cancelled()`.
- `abandon_on_cancel=True` only stops waiting on the thread result; it does not stop the thread.

For a foreign thread, worker-thread helpers are not enough. Use a token for one-off calls, or a portal for repeated calls:

```python
import threading
import anyio
from anyio import from_thread
from anyio.lowlevel import current_token

def foreign_thread_fn(token, event):
    from_thread.run_sync(event.set, token=token)

async def main() -> None:
    event = anyio.Event()
    token = current_token()
    thread = threading.Thread(target=foreign_thread_fn, args=(token, event))
    thread.start()
    await event.wait()
    thread.join()
```

`BlockingPortal` is the right tool when sync code needs more than a one-off hop:

- a real sync facade over an async client
- many repeated sync calls into async code
- wrapping async context managers/lifecycle safely
- long-lived access from foreign threads without passing tokens around everywhere

Typical portal-based wrapper:

```python
from anyio.from_thread import start_blocking_portal

class SyncClient:
    def __init__(self) -> None:
        self._portal_cm = start_blocking_portal()
        self._portal = self._portal_cm.__enter__()
        self._client = self._portal.call(self._open_client)

    async def _open_client(self):
        client = AsyncClient()
        return client

    def get_user(self, user_id: str) -> dict:
        return self._portal.call(self._client.get_user, user_id)

    def close(self) -> None:
        self._portal.call(self._client.aclose)
        self._portal_cm.__exit__(None, None, None)
```

Use the portal when the sync facade owns the async lifecycle. Do not use it for a trivial worker-thread callback that only needs `event.set`; `from_thread.run_sync(event.set)` is the correct tool there.

The highest-risk footgun is mixing up these cases:

- AnyIO worker thread -> `from_thread.run()` / `from_thread.run_sync()`
- foreign thread -> token or `BlockingPortal`
- running async app/framework loop -> never nested `asyncio.run()`

References used: `threads-boundaries.md`, `cancellation-timeouts.md`, `decision-matrix.md`. I could not do a local runtime smoke test because `anyio` is not installed in this environment.

If you want, I can turn this into a concrete wrapper template for your client API.
