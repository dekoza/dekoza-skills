That pattern is brittle. The “we do not care if it completes later” story is mostly fiction unless you give the task its own lifetime.

- `asyncio.gather()` only governs the three awaited branches. The extra `create_task()` escapes that structure, so its errors, cancellation, and shutdown behavior are now somebody else’s problem.
- A task created without a stored reference is explicitly unsafe in `asyncio`: the loop keeps weak references, so the task can disappear mid-execution.
- The detached task closes over `request`, a DB session, and a tracing span. Those are request-scoped resources. Once the handler returns, middleware/framework cleanup can invalidate all three:
  - `request` may no longer be safe to read
  - the DB session may be closed or returned to the pool
  - the span may already be ended, so child work is attached to dead tracing state
- If the client disconnects, the handler is cancelled, or the app shuts down, the detached task now has unclear semantics. It may keep running, get cancelled late, or die with an exception nobody observes.
- Enabling eager task execution here is not a harmless micro-optimization. It changes semantics. The coroutine can start running immediately inside `create_task()`, before your next line runs. That means:
  - execution order changes
  - synchronous exceptions can surface earlier
  - request-scoped state can be touched immediately and unpredictably
  - “fire it off for later” stops meaning “later”

The highest-risk issue is not scheduler overhead. It is lifetime mismatch: request-bound objects are being used by work that outlives the request.

A safer design is:

- keep the request’s concurrent work structured and awaited
- for post-response work, pass only immutable data
- create fresh resources inside the background job
- keep a strong reference to the task in an app-owned registry
- log/observe failures
- drain or cancel outstanding tasks on shutdown
- if completion truly matters across process restarts, use a real job queue instead of in-process tasks

Example:

```python
import asyncio
from collections.abc import Awaitable, Callable

background_tasks: set[asyncio.Task[None]] = set()

def spawn_background(job: Awaitable[None]) -> None:
    task = asyncio.create_task(job, name="audit-log")
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    task.add_done_callback(_log_task_failure)

def _log_task_failure(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Background task failed", extra={"task": task.get_name()})

async def handler(request: Request) -> Response:
    user_id = request.user.id
    request_id = request.headers["x-request-id"]
    trace_context = extract_trace_context(request.headers)

    async with asyncio.TaskGroup() as tg:
        profile_t = tg.create_task(fetch_profile(user_id))
        perms_t = tg.create_task(fetch_permissions(user_id))
        prefs_t = tg.create_task(fetch_preferences(user_id))

    spawn_background(
        write_audit_event(
            user_id=user_id,
            request_id=request_id,
            trace_context=trace_context,
        )
    )

    return Response(
        {
            "profile": profile_t.result(),
            "permissions": perms_t.result(),
            "preferences": prefs_t.result(),
        }
    )

async def write_audit_event(
    *,
    user_id: int,
    request_id: str,
    trace_context: TraceContext,
) -> None:
    with tracer.start_as_current_span(
        "write_audit_event",
        context=trace_context,
    ):
        async with db_session_factory() as session:
            await audit_repo(session).insert_event(
                user_id=user_id,
                request_id=request_id,
            )
```

Why this is better:

- `TaskGroup` gives the request-time fanout real structure; if one branch fails, siblings are cancelled.
- The background task gets plain data, not live request objects.
- The background task opens its own DB session and its own span.
- The app holds a strong reference, so the task is not lost.
- Exceptions are surfaced instead of becoming “Task exception was never retrieved”.

If you truly do not care about immediate completion, the stronger design is usually a queue:

```python
await audit_queue.publish({
    "user_id": user_id,
    "request_id": request_id,
    "trace_context": serialize_trace_context(request.headers),
})
return Response(...)
```

That beats detached in-process tasks because it survives handler return, worker restarts, and app shutdown.

About `eager_start` / eager task factory: your teammate is optimizing the wrong thing.

- It can help tiny coroutines that often complete synchronously from cache.
- It is a semantic change, not just a faster scheduler path.
- In this pattern it makes the lifecycle bug sharper, because the detached coroutine may start touching request-bound state immediately during task creation.

So the verdict is simple: don’t combine detached tasks, request-scoped captures, and eager execution. That is not clever concurrency; it is borrowed-state roulette.

Natural next steps:
1. Replace `gather()` with `TaskGroup` for the request-scoped branches.
2. Move detached work to an app-level background supervisor that accepts only primitive payloads.
3. If the work must survive shutdown or retries matter, push it onto a real job queue instead of `create_task()`.
