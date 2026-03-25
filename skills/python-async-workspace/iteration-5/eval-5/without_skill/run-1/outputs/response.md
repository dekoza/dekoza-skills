That pattern is not "fire-and-forget". It is "fire-and-hope the garbage collector, shutdown path, and dead request-scoped objects do not bite you."

- `asyncio.create_task()` with no stored reference is explicitly unreliable for background work; the docs warn the loop keeps only weak references, so an unreferenced task may disappear mid-execution.
- Returning the response before that task finishes means it now outlives the `request` lifecycle, but it still closes over `request`, a DB session, and a tracing span. Those are usually request-scoped resources. After the handler returns, they are often invalid, closed, ended, or reused.
- If that detached task raises, nobody awaits it, so failure handling is garbage: best case you get a late "Task exception was never retrieved" log, worst case the failure is effectively orphaned.
- `asyncio.gather()` is already weaker than it looks: if one child raises, `gather()` propagates the first exception, but the other children keep running unless you manage them yourself. Add a detached grandchild and now you have unstructured concurrency soup.
- Enabling the eager task factory or `eager_start` is not a harmless micro-optimization. It changes semantics: the coroutine starts running synchronously inside `create_task()`. Code before the first `await` now runs immediately, task ordering changes, and your "background" task may touch `request`/session/span before the handler even gets to return.

The highest-risk bug is simple: the task captures request-scoped state but is intentionally allowed to outlive the request.

A safer design is:

- use structured concurrency for request-owned work (`TaskGroup`, not loose `gather()`),
- make background work explicit,
- pass only immutable data into the background job,
- create fresh resources inside that job,
- keep a strong reference and observe failure,
- if completion actually matters, use a durable queue/outbox instead of in-process tasks.

Example:

```python
import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuditJob:
    user_id: int
    request_id: str
    traceparent: str | None


class BackgroundSupervisor:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(self, coro: Any, *, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_failure)

    @staticmethod
    def _log_failure(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background task failed", extra={"task": task.get_name()})

    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def handler(request) -> Response:
    job = AuditJob(
        user_id=request.user.id,
        request_id=request.headers["x-request-id"],
        traceparent=current_traceparent(),
    )

    async with asyncio.TaskGroup() as tg:
        user_task = tg.create_task(fetch_user_data(request.user.id))
        flags_task = tg.create_task(fetch_feature_flags(request.user.id))
        quota_task = tg.create_task(fetch_quota(request.user.id))

    response = build_response(
        user=user_task.result(),
        flags=flags_task.result(),
        quota=quota_task.result(),
    )

    request.app.background_supervisor.submit(
        run_audit_job(job),
        name="audit-job",
    )
    return response


async def run_audit_job(job: AuditJob) -> None:
    async with open_db_session() as session:
        with tracer.start_as_current_span(
            "audit-job",
            links=links_from_traceparent(job.traceparent),
        ):
            await write_audit_record(
                session=session,
                user_id=job.user_id,
                request_id=job.request_id,
            )
```

Why this is safer:

- `TaskGroup` gives the request-scoped children a real owner and cancellation boundary.
- The background job gets a snapshot, not the live `request`.
- The DB session is opened inside the background job, so its lifetime matches the job.
- The tracing span is also created inside the background job; if you want continuity, pass trace context, not the live span object.
- The supervisor holds strong references, logs failures, and can cancel/drain tasks on shutdown.

On eager execution:

- Do not enable eager task factory globally unless you have audited code for ordering assumptions. It is a semantic toggle, not just a speed knob.
- It is especially toxic around detached tasks, because pre-`await` side effects happen inline during `create_task()`.
- If you ever use `eager_start`, reserve it for tiny, self-contained coroutines that do not capture expiring resources and whose pre-`await` code is safe to run immediately.

Bluntly: "we do not care if it completes later" does not justify closing over objects whose lifetime ends now. If later is acceptable but loss is not, use a queue. If loss is acceptable, still isolate the task from request-scoped resources and supervise it.
