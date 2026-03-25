That pattern is brittle. “We do not care if it completes later” usually means the ownership model is undefined, and undefined ownership is how async code turns into ghost work.

- `asyncio.gather()` is already a weak spot for request fan-out: if one child fails, `gather()` propagates the first exception, but the other children are not automatically cancelled and may keep running unless you manage them explicitly.
- A naked `create_task()` inside one branch is worse: Python documents that the event loop keeps only weak references to tasks, so an unreferenced task may disappear mid-execution.
- Returning the HTTP response does not give that task a safe lifetime. The request task is done, but the spawned task may still depend on request-scoped state that is about to die: DB session, transaction, auth context, tracing span, timeout scope, cancellation budget, open client objects.
- Unobserved exceptions become operational garbage. Best case: they get logged late as “Task exception was never retrieved”. Worst case: they vanish into noisy logs nobody correlates to the original request.
- Shutdown is undefined. Worker restart, deploy, process crash, or event-loop cancellation can kill that task halfway through. If the work matters, you just lost it. If it mutates state, you may have half-applied side effects.
- Backpressure is absent. Under load, each request can leak more detached tasks and you have invented an unbounded in-process queue by accident.

The highest-risk issue is simple: you have work with no clear owner. If no one owns completion, error handling, cancellation, and shutdown, the work is not reliable.

A safer split is:

1. Request-critical concurrent work: use `TaskGroup` and finish it before responding.
2. Post-response work:
   - if it must happen reliably, enqueue it to a real background system;
   - if it is only best-effort, run it under an application-level supervisor that stores references, logs failures, and drains on shutdown.

Bad shape:

```python
async def handler(request):
    result_a, result_b, result_c = await asyncio.gather(
        call_a(),
        call_b_that_spawns_background_work(),
        call_c(),
    )
    return {"ok": True}
```

Safer request-scoped concurrency:

```python
import asyncio

async def handler(request):
    async with asyncio.TaskGroup() as tg:
        task_a = tg.create_task(call_a())
        task_b = tg.create_task(call_b())
        task_c = tg.create_task(call_c())

    return {
        "a": task_a.result(),
        "b": task_b.result(),
        "c": task_c.result(),
    }
```

Safer best-effort in-process background supervision:

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

class BackgroundSupervisor:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def spawn(self, coro: asyncio.coroutines) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_failure)

    def _log_failure(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("Background task cancelled")
        except Exception:
            logger.exception("Background task failed")

    async def shutdown(self) -> None:
        if not self._tasks:
            return
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
```

Handler using it:

```python
async def handler(request, background: BackgroundSupervisor):
    async with asyncio.TaskGroup() as tg:
        task_a = tg.create_task(call_a())
        task_b = tg.create_task(call_b())
        task_c = tg.create_task(call_c())

    background.spawn(send_audit_event(task_b.result()))

    return {
        "a": task_a.result(),
        "b": task_b.result(),
        "c": task_c.result(),
    }
```

If the post-response task actually matters, the in-process supervisor is still not enough. Use a durable queue/outbox instead:

```python
async def handler(request):
    async with asyncio.TaskGroup() as tg:
        task_a = tg.create_task(call_a())
        task_b = tg.create_task(call_b())
        task_c = tg.create_task(call_c())

    await jobs.enqueue("send_audit_event", payload={"b": task_b.result()})
    return {"ok": True}
```

Decision rule:

- If the result affects the response or correctness, await it in the request.
- If it must eventually happen, use a durable background job.
- If it is truly disposable, supervise it explicitly and accept loss.

What is not acceptable is the current middle ground: “important enough to start, not important enough to own.” That is how systems become flaky.

If you want, I can also show this pattern applied concretely in `aiohttp`, `FastAPI`, or a generic ASGI lifespan setup.
