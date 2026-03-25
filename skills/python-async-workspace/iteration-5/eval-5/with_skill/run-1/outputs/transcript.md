# Execution Transcript

## Eval Prompt

Review this pattern: a request handler uses `asyncio.gather()` for three child calls, one branch starts a background `create_task()` with no stored reference, and the response returns before that task finishes because we 'do not care if it completes later'. That detached task currently closes over the `request` object, a DB session, and a tracing span. Another teammate wants to enable the eager task factory or `eager_start` to shave scheduler overhead. Explain the lifecycle problems and show a safer design.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Tool use: skill:court-jester
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

This pattern is broken. It is pretending to be "fire-and-forget", but it is really "fire-and-hope".

- `asyncio.gather()` gives concurrency, not ownership. If one child raises, the others keep running unless the `gather()` itself is cancelled.
- A bare `create_task()` with no stored reference is unsafe. Python documents that the loop keeps only weak references, so the task can disappear mid-execution.
- Returning the response before that task finishes means the task outlives the request, but it still closes over request-scoped objects: `request`, DB session, tracing span. Those are exactly the objects that should die with the request.
- That gives you classic use-after-lifetime bugs: closed DB session, ended span, request body/cache objects torn down, framework context no longer valid.
- Failures become invisible. If the detached task raises after the response is sent, you usually get lousy observability at best and silent loss at worst.
- Shutdown is undefined. On deploy, worker restart, or cancellation, that task may be cut off halfway through side effects.

The eager-task idea makes this worse, not safer.

- `eager_start` / eager task factory is a semantic change, not a free optimization.
- The coroutine may start running immediately during `create_task(...)`, before your handler reaches the next line.
- That changes ordering, error timing, lock contention, and tracing behavior.
- If the coroutine touches request/session/span before the handler finishes setting up or before cleanup assumptions hold, you have even more brittle timing-dependent bugs.

The highest-risk issue is simple: you have detached work using request-owned resources after the request lifetime ends. That is invalid ownership.

A safer split is:

1. If the work is part of the request contract, keep it structured and await it.
2. If it may outlive the request, hand off plain data to an app-owned background worker that creates its own resources.

Example with `TaskGroup` for request-scoped work:

```python
import asyncio

async def handle_request(request, session_factory, tracer):
    async with asyncio.TaskGroup() as tg:
        user_task = tg.create_task(fetch_user(request.user_id))
        perms_task = tg.create_task(fetch_permissions(request.user_id))
        audit_task = tg.create_task(write_inline_audit(request.user_id))

    return {
        "user": user_task.result(),
        "permissions": perms_task.result(),
    }
```

Example for true post-response work: queue + supervised worker.

```python
import asyncio
from dataclasses import dataclass

@dataclass(frozen=True)
class AuditJob:
    user_id: str
    trace_id: str

class AuditDispatcher:
    def __init__(self, session_factory, tracer, maxsize: int = 1000) -> None:
        self._session_factory = session_factory
        self._tracer = tracer
        self._queue: asyncio.Queue[AuditJob] = asyncio.Queue(maxsize=maxsize)
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._worker_task = asyncio.create_task(self._worker(), name="audit-worker")

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        finally:
            self._worker_task = None

    def submit_nowait(self, job: AuditJob) -> None:
        self._queue.put_nowait(job)

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                async with self._session_factory() as session:
                    with self._tracer.start_as_current_span("background_audit"):
                        await write_audit_record(
                            session=session,
                            user_id=job.user_id,
                            trace_id=job.trace_id,
                        )
            except Exception:
                report_background_failure(job)
            finally:
                self._queue.task_done()
```

Handler:

```python
async def handle_request(request, audit_dispatcher):
    results = await asyncio.gather(
        fetch_user(request.user_id),
        fetch_permissions(request.user_id),
        fetch_settings(request.user_id),
    )

    audit_dispatcher.submit_nowait(
        AuditJob(
            user_id=request.user_id,
            trace_id=request.trace_id,
        )
    )

    return make_response(*results)
```

Why this is safer:

- The request handler passes a data snapshot, not live request objects.
- The background worker owns its own DB session and span.
- The app owns worker startup, shutdown, backpressure, and error reporting.
- No orphan task per request.
- If the work really matters, you can replace the in-process queue with a durable queue/outbox without changing handler ownership rules.

Decision rule:

- Use `TaskGroup` when sibling lifetime and failure coupling matter.
- Use `gather()` only when you want aggregate results and accept its weaker failure semantics.
- Do not detach tasks that capture request-scoped resources.
- Do not enable eager task execution to "optimize" already-brittle lifecycle code.

Minimum verification:

- Add a test that cancels the request and proves background work does not touch the request DB session/span afterward.
- Add a shutdown test proving the worker drains, rejects, or drops according to explicit policy.
- Benchmark eager mode before even considering it; do not turn it on speculatively.

Sources used: Python `asyncio` task docs and the `python-async` references on structured concurrency and asyncio task footguns.

If you want, I can also show the same redesign in `AnyIO` form, which is usually cleaner than raw `asyncio` for app-owned background services.
