The pattern is brittle. “We do not care if it finishes later” is not the same as “it is safe to detach.”

- `asyncio.gather()` only covers the three awaited branches; the extra `create_task()` escapes that lifecycle entirely.
- A task with no stored reference is explicitly unsafe: asyncio keeps only weak references, so the task can disappear mid-flight.
- The detached task closes over request-scoped objects that are supposed to die with the handler:
  - `request`: often invalid once the response is sent
  - DB session: usually closed/returned to pool at end of request
  - tracing span: typically ended before the detached task finishes
- Exceptions become garbage-fire telemetry: either unobserved, logged as “Task exception was never retrieved”, or silently missed by the request path.
- Shutdown and cancellation get sloppy: request cancellation, server shutdown, and app draining no longer have a clear owner for that task.

The eager-task idea makes this worse, not better.

- `eager_start` / eager task factory is a semantic change, not a free optimization.
- The coroutine can start running immediately inside `create_task()`, before your handler finishes its current line of thought.
- That changes ordering, error timing, and side effects.
- If the detached coroutine touches `request`, session, or span immediately, eager start makes that happen sooner and more unpredictably.
- Shaving scheduler overhead is noise next to network/DB latency; it is the wrong place to get clever.

Safer rule:

- If work is part of handling the request, keep it structured and await it.
- If work may outlive the request, do not capture request-scoped objects. Pass only durable data and recreate resources inside the background job.
- If it truly matters, use a queue/worker. In-process fire-and-forget is best-effort only.

A safer in-process design looks like this:

```python
import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class BackgroundRunner:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background task failed")

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


async def request_handler(request, background_runner: BackgroundRunner, session_factory, tracer):
    user_id = request.user_id
    payload = dict(request.json_body)

    async with asyncio.TaskGroup() as tg:
        a_task = tg.create_task(fetch_a(user_id))
        b_task = tg.create_task(fetch_b(user_id))
        c_task = tg.create_task(fetch_c(user_id))

    response = make_response(
        a=a_task.result(),
        b=b_task.result(),
        c=c_task.result(),
    )

    # Detached work gets only durable inputs.
    background_runner.spawn(
        publish_audit_event(
            user_id=user_id,
            payload=payload,
            session_factory=session_factory,
            tracer=tracer,
        )
    )

    return response


async def publish_audit_event(*, user_id, payload, session_factory, tracer) -> None:
    with tracer.start_as_current_span("publish_audit_event"):
        async with session_factory() as session:
            await write_audit_record(session, user_id=user_id, payload=payload)
            await send_webhook(user_id=user_id, payload=payload)
```

Why this is safer:

- `TaskGroup` gives the request-owned fan-out/fan-in proper structure.
- The background task is owned by an app-level runner, so it has a strong reference, logging, and shutdown handling.
- The background job receives snapshots (`user_id`, `payload`), not live request/session/span objects.
- It creates its own DB session and tracing span inside its own lifetime.

If the background work must be reliable across crashes/restarts, stop pretending `create_task()` is a job system and use a real queue.

Highest-risk issue: the detached task captures a request-scoped DB session and tracing span after the request has logically ended. That is a use-after-lifetime bug, not an optimization opportunity.

Natural next steps:
1. Replace request-owned `gather()` fan-out with `TaskGroup`.
2. Move detached work behind an app-owned supervisor or job queue.
3. Ban passing `request`, request DB sessions, and live spans into detached tasks.
4. Do not enable eager task factory for this code path.
