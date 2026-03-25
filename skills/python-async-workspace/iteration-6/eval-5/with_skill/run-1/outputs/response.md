This pattern is brittle. It mixes request-scoped concurrency with detached work and then pretends lifecycle no longer matters. It does.

- `asyncio.gather()` is not a lifecycle boundary. If one of the three child calls raises, `gather()` does not cancel the others by default; they can keep running while the handler is already unwinding.
- The untracked `create_task()` is worse: `asyncio` keeps only weak references to tasks, so a truly fire-and-forget task can be garbage-collected before completion.
- “We do not care if it completes later” is usually false. If it writes to a DB, emits telemetry, mutates state, or calls another service, then you absolutely care whether it runs, fails, duplicates, or gets cut off at shutdown.
- Closing over `request`, a DB session, and a tracing span is a request-lifetime violation. After the response returns, those objects are commonly invalid, closing, or already closed.
- Enabling eager task execution is not a free speedup. `eager_start` / eager task factories change semantics: the coroutine may run immediately during task creation, changing ordering, error timing, and context/lifetime assumptions.

The concrete failure modes:

- `request`: framework may recycle or tear down request state after the handler returns.
- DB session: transaction/session may be closed; detached code can hit “session closed”, use stale transaction state, or race cleanup.
- tracing span: the request span usually ends with the request; detached work may attach events to an ended span or silently lose correlation.
- exceptions: if the detached task fails, failure observation is often just a late loop log, or nothing useful.
- shutdown: process exit/redeploy can kill the task mid-side-effect.

The highest-risk lie is this one: “background work that outlives the request can safely keep request-owned resources.” It cannot.

A safer design splits the two lifetimes:

1. Request-bound concurrent work: use `TaskGroup`.
2. Post-response work: hand off plain data to an app-owned worker boundary.
3. Detached worker opens its own DB session and its own tracing span.
4. If the work must survive process death, do not use in-process tasks at all; use a durable job/outbox/queue.

Example, still `asyncio`-native:

```python
import asyncio
from dataclasses import dataclass

@dataclass(frozen=True)
class AuditJob:
    user_id: str
    request_id: str
    trace_id: str | None
    action: str


class BackgroundDispatcher:
    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[AuditJob] = asyncio.Queue(maxsize=maxsize)
        self._workers: asyncio.TaskGroup | None = None

    async def start(self) -> None:
        self._workers = asyncio.TaskGroup()
        await self._workers.__aenter__()
        self._workers.create_task(self._worker())

    async def stop(self) -> None:
        if self._workers is not None:
            await self._workers.__aexit__(None, None, None)

    def submit_nowait(self, job: AuditJob) -> None:
        self._queue.put_nowait(job)

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            except Exception:
                # Replace with real logging/metrics/reporting.
                report_background_failure(job)
            finally:
                self._queue.task_done()

    async def _process(self, job: AuditJob) -> None:
        with start_background_span("audit.write", parent_trace_id=job.trace_id):
            async with open_db_session() as session:
                await write_audit_record(
                    session=session,
                    user_id=job.user_id,
                    request_id=job.request_id,
                    action=job.action,
                )
                await session.commit()
```

Request handler:

```python
async def handle_request(request, dispatcher: BackgroundDispatcher):
    user_id = request.user.id
    request_id = request.request_id
    trace_id = current_trace_id()

    async with asyncio.TaskGroup() as tg:
        profile_t = tg.create_task(fetch_profile(user_id))
        flags_t = tg.create_task(fetch_flags(user_id))
        perms_t = tg.create_task(fetch_permissions(user_id))

    dispatcher.submit_nowait(
        AuditJob(
            user_id=user_id,
            request_id=request_id,
            trace_id=trace_id,
            action="view_dashboard",
        )
    )

    return {
        "profile": profile_t.result(),
        "flags": flags_t.result(),
        "permissions": perms_t.result(),
    }
```

Why this is safer:

- `TaskGroup` owns the three request child calls.
- The background boundary takes a data snapshot, not live request objects.
- The worker creates fresh resources inside its own lifetime.
- Failures become observable in one place.
- Shutdown can drain or cancel workers deliberately instead of “whatever happens happens”.

If the background action matters enough that dropping it is unacceptable, go one step further:

- write an outbox/job row in the request transaction,
- commit it,
- let a separate worker process it,
- return `202 Accepted` if the client should know the work is deferred.

On eager execution: do not enable it here as a blanket optimization.

- It changes execution order.
- It can run task code before your handler finishes setup.
- It makes bugs around context capture and exception timing nastier, not smaller.
- The scheduler overhead you save is usually trivial compared with network/DB latency.

Answer type: `asyncio-specific`
References used: `structured-concurrency.md`, `backend-asyncio.md`, `pre-mortem-analysis.md`

Natural next steps:
1. Replace request `gather()` usage with `TaskGroup` where sibling lifetime matters.
2. Introduce an app-owned background dispatcher or a durable outbox.
3. Add shutdown tests proving background work is drained, cancelled, or persisted intentionally.
