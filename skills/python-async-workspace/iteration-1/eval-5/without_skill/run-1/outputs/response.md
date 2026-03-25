This pattern is wrong for one reason above all: task lifetime is undefined.

`asyncio.gather()` only manages the three awaitables you pass to it. It is not a lifecycle manager for extra tasks spawned inside one branch. If one branch does this:

```python
async def branch():
    asyncio.create_task(write_audit_log())
    return "scheduled"
```

then `gather()` waits only for `branch()` to finish scheduling the child task. It does not wait for `write_audit_log()`.

That creates several concrete failures:

- The detached task has no explicit owner. Request completion is not ownership.
- The task has no strong reference. Python's `asyncio.create_task()` docs explicitly warn that the event loop keeps only weak references, so an unreferenced task may disappear mid-execution.
- Exceptions from the detached task are now easy to miss or log too late.
- Request cancellation or server shutdown can kill the task halfway through, leaving partial side effects.
- The claim "we do not care if it completes later" is usually sloppy. If the work truly does not matter, do not start it. If it does matter even a little, it needs an owner, error handling, and shutdown behavior.

Safer design 1: if the work belongs to the request, keep it in structured concurrency and wait for it.

```python
import asyncio


async def handle_request() -> dict:
    async with asyncio.TaskGroup() as task_group:
        user_task = task_group.create_task(fetch_user())
        orders_task = task_group.create_task(fetch_orders())
        audit_task = task_group.create_task(write_audit_log())

    return {
        "user": user_task.result(),
        "orders": orders_task.result(),
        "audit": audit_task.result(),
    }
```

Why this is safer:

- The handler owns all child tasks.
- Failure and cancellation propagate predictably.
- Shutdown semantics are clear: the request is not done until its work is done.

Safer design 2: if the work is truly background work, move it behind an explicit background boundary instead of smuggling it through a request branch.

```python
import asyncio
import logging


logger = logging.getLogger(__name__)


class BackgroundWorker:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()
        self._closing = False

    def submit(self, coro: "asyncio.coroutines") -> None:
        if self._closing:
            raise RuntimeError("background worker is shutting down")
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._finalize)

    def _finalize(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        try:
            task.result()
        except Exception:
            logger.exception("background task failed")

    async def aclose(self) -> None:
        self._closing = True
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


async def handle_request(worker: BackgroundWorker) -> dict:
    user, orders, recommendations = await asyncio.gather(
        fetch_user(),
        fetch_orders(),
        fetch_recommendations(),
    )
    worker.submit(write_audit_log(user_id=user["id"]))
    return {
        "user": user,
        "orders": orders,
        "recommendations": recommendations,
    }
```

That version is still in-process, but at least the ownership is explicit:

- the app-level worker keeps a strong reference,
- failures are observed,
- shutdown can drain outstanding tasks,
- the request handler is no longer pretending that `gather()` owns detached work.

If the background job must survive process restarts or must reliably complete, an in-memory task is still not enough. Put it on a real queue and return a response that reflects that boundary, often `202 Accepted` rather than pretending the request fully handled it.

Reference used:

- Python `asyncio` task docs: `https://docs.python.org/3/library/asyncio-task.html`

Verification notes:

- Verified against the official Python docs that `create_task()` requires saving a reference because the loop keeps weak references.
- Verified against the official Python docs that `TaskGroup` is the safer alternative when related subtasks need structured ownership.
- Verified against the official Python docs that `gather()` runs only the awaitables passed to it and is not the safety boundary for nested detached tasks.
