This pattern is brittle. The claim "we do not care if it completes later" is false the moment that detached task closes over request-scoped state.

- `asyncio.gather()` is only a result combiner; it is not a lifecycle boundary. If one child fails, the others are not automatically cancelled the way a `TaskGroup` would handle sibling failure.
- A bare `create_task()` with no stored reference is a classic asyncio footgun. The loop keeps weak references to tasks, so "fire-and-forget" is not even reliable fire-and-forget.
- Returning the response before that task finishes means the task can outlive the request while still touching the `request`, DB session, and tracing span. Those objects are usually request-owned, so now you have use-after-lifetime bugs.
- If the task fails, you have no structured place to observe, retry, or report that failure. At best you get a late log like "Task exception was never retrieved". At worst you lose work silently.
- Shutdown behavior is undefined. If the process stops, deployment rolls, or the server cancels outstanding tasks, that detached work is cut off mid-flight.

The ugliest bug is the resource capture:

- `request`: may hold cancellation context, auth, transport state, or lazily accessed bodies that are invalid after the handler returns.
- DB session: request-scoped sessions are commonly closed/committed/rolled back in middleware immediately after the response.
- tracing span: child work may emit into a span that is already ended, producing broken traces or exporter errors.

The eager-task idea makes this worse, not safer.

- Eager execution is a semantic change, not a free micro-optimization.
- The new task may start running immediately during `create_task(...)`, before your handler reaches the next line.
- That changes ordering assumptions, error timing, and teardown races. Code that "usually" started after the response path may now run partly inline before response construction finishes.
- If your design is already wrong because ownership is unclear, eager start just lets the bug happen sooner and less predictably.

A safer design is to split work by ownership.

If the work is part of the request, keep it inside structured concurrency and await it:

```python
import asyncio

async def handle_request(request, db_session, tracer):
    async with asyncio.TaskGroup() as tg:
        user_task = tg.create_task(load_user(request))
        prefs_task = tg.create_task(load_preferences(request))
        stats_task = tg.create_task(load_stats(request))

    return {
        "user": user_task.result(),
        "preferences": prefs_task.result(),
        "stats": stats_task.result(),
    }
```

If the work truly may outlive the request, do not spawn it from the handler as an unowned task. Hand off plain data to an app-owned worker that has its own shutdown policy and acquires its own resources:

```python
import asyncio
from dataclasses import dataclass

@dataclass(frozen=True)
class AuditJob:
    request_id: str
    user_id: str
    action: str

class BackgroundDispatcher:
    def __init__(self, db_session_factory, tracer):
        self._queue: asyncio.Queue[AuditJob] = asyncio.Queue(maxsize=1000)
        self._db_session_factory = db_session_factory
        self._tracer = tracer
        self._worker_task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._worker_task = asyncio.create_task(self._run())

    async def submit(self, job: AuditJob) -> None:
        await self._queue.put(job)

    async def stop(self) -> None:
        self._stopping.set()
        await self._queue.put(AuditJob("", "", "__shutdown__"))
        if self._worker_task is not None:
            await self._worker_task

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if self._stopping.is_set() and job.action == "__shutdown__":
                    return

                async with self._db_session_factory() as db_session:
                    with self._tracer.start_as_current_span("process_audit_job"):
                        await write_audit_record(db_session, job)
            finally:
                self._queue.task_done()
```

Handler:

```python
async def handle_request(request, dispatcher):
    async with asyncio.TaskGroup() as tg:
        user_task = tg.create_task(load_user(request))
        prefs_task = tg.create_task(load_preferences(request))
        stats_task = tg.create_task(load_stats(request))

    await dispatcher.submit(
        AuditJob(
            request_id=request.headers["x-request-id"],
            user_id=str(request.user.id),
            action="view_dashboard",
        )
    )

    return {
        "user": user_task.result(),
        "preferences": prefs_task.result(),
        "stats": stats_task.result(),
    }
```

Why this is safer:

- The request handler owns request-bound work and waits for it.
- The background worker is app-owned, not request-owned.
- The handoff uses a data snapshot, not live request/session/span objects.
- The worker creates its own DB session and tracing span.
- Shutdown is explicit: reject, buffer, or drain queued jobs. That is an actual policy; "best effort" is not.

If the work must survive process crashes or deploys, an in-process queue is still not enough. Then the correct design is an external durable boundary: job table, broker, or task system. "We do not care if it finishes later" often really means "we do care, just not on the request latency path."

Highest-risk issue: the detached task closes over request-scoped resources after the request lifetime ends. That is the design bug. `gather()` and eager start are secondary hazards piled on top.

References used: `structured-concurrency.md`, `backend-asyncio.md`, `cancellation-timeouts.md`.

Natural next steps:
1. Replace request-local `gather()` + stray `create_task()` with `asyncio.TaskGroup` for request-owned work.
2. Move post-response work behind an app-owned queue/worker with explicit startup and shutdown.
3. If reliability matters across restarts, replace the in-process worker with a durable job system.
