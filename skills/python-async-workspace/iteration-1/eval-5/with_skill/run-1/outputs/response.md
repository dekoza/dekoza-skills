Answer mode: `asyncio-specific`

References used: `references/decision-matrix.md`, `references/structured-concurrency.md`, `references/cancellation-timeouts.md`, `references/backend-asyncio.md`, `references/code-review-checklist.md`

The primary risk is task lifetime.

That pattern is not harmless fire-and-forget. It is broken ownership.

- `asyncio.gather()` is not a lifecycle manager. It is only an aggregate await. If one child raises, the others are not automatically cancelled just because sibling lifetime should be coupled.
- A bare `asyncio.create_task()` with no stored reference is worse. Python documents that the event loop keeps only weak references to tasks, so a detached task can be garbage-collected before it finishes.
- Returning the response before that task finishes means the task now outlives the request that created it. That is a design claim, not a free optimization. You need explicit ownership for shutdown, cancellation, error reporting, and resource lifetime.
- Request-scoped resources may already be gone when the detached task runs: DB session, transaction, tracing span, auth context, deadline, or request logger.
- If the detached task fails, the exception is usually observed late, logged poorly, or effectively lost. Tests also become flaky because work continues after the handler already returned.

Bad pattern:

```python
import asyncio


async def handler(request):
    async def branch_c():
        asyncio.create_task(send_audit_event(request.user_id))
        return {"scheduled": True}

    a, b, c = await asyncio.gather(
        fetch_profile(request.user_id),
        fetch_permissions(request.user_id),
        branch_c(),
    )
    return {"profile": a, "permissions": b, "extra": c}
```

If the work must finish as part of the request, keep it inside structured concurrency and wait for it.

```python
import asyncio


async def handler(request):
    async with asyncio.TaskGroup() as tg:
        profile_task = tg.create_task(fetch_profile(request.user_id))
        permissions_task = tg.create_task(fetch_permissions(request.user_id))
        audit_task = tg.create_task(send_audit_event(request.user_id))

    return {
        "profile": profile_task.result(),
        "permissions": permissions_task.result(),
        "audit": audit_task.result(),
    }
```

If you truly do not care whether it finishes before the response, do not spawn it from the handler as an unowned task. Hand it to an explicit application-owned worker boundary.

```python
import asyncio
from collections.abc import Awaitable


class AuditDispatcher:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker is not None:
            raise RuntimeError("dispatcher already started")
        self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        await self._queue.put("__shutdown__")
        if self._worker is not None:
            await self._worker
            self._worker = None

    async def submit(self, user_id: str) -> None:
        await self._queue.put(user_id)

    async def _run(self) -> None:
        while True:
            user_id = await self._queue.get()
            try:
                if user_id == "__shutdown__":
                    return
                await send_audit_event(user_id)
            finally:
                self._queue.task_done()


async def handler(request, audit_dispatcher: AuditDispatcher):
    profile, permissions = await asyncio.gather(
        fetch_profile(request.user_id),
        fetch_permissions(request.user_id),
    )
    await audit_dispatcher.submit(request.user_id)
    return {"profile": profile, "permissions": permissions, "audit": "queued"}
```

Why this is safer:

- the request no longer lies about ownership
- the background work has a strong reference and a defined shutdown path
- failures have one place to be logged and monitored
- backpressure policy can be made explicit at the queue boundary

Minimum verification step:

- add a test where the request returns and then app shutdown runs immediately
- assert the owned worker either drains queued work or stops according to policy
- assert detached ad-hoc tasks are no longer created from request handlers

The highest-risk footgun is the orphaned `create_task()`: no strong reference, no shutdown owner, and no guarantee that request-scoped state is still valid when it runs.
