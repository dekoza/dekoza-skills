This pattern is brittle. "`We do not care if it completes later`" is usually code for "`we have not assigned ownership`."

- `asyncio.gather()` is only a result aggregator. It is not a lifecycle boundary. If one child raises, `gather(..., return_exceptions=False)` propagates that error, but the other children keep running.
- The naked `create_task()` is worse: `asyncio` only keeps weak references to tasks. If you do not keep a strong reference, the task can disappear before finishing.
- Returning the response ends the request's logical lifetime, but your detached task may still be using request-scoped state: DB session, tracing span, auth context, open socket, cancellation context, etc.
- Exceptions in that detached task are now unowned. Best case: noisy logs. Worst case: silent data loss or partial side effects.
- Shutdown becomes undefined. On process stop, reload, timeout, or worker recycle, that task may be cut off mid-write.

The highest-risk bug is not "it might finish later." It is "it might finish half-way, or never, and nobody will know."

A safer split is:

1. Request-coupled concurrent work: use `TaskGroup` and await it.
2. Work allowed to outlive the request: hand it to an app-owned background worker or external queue.

Bad shape:

```python
async def handler(request):
    a, b, c = await asyncio.gather(
        call_a(),
        call_b(),
        call_c_and_spawn_side_task(),  # internally does create_task(...)
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

Safer fire-later design: explicit background ownership.

```python
import asyncio
from contextlib import suppress

class BackgroundDispatcher:
    def __init__(self, maxsize: int = 1000) -> None:
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=maxsize)
        self.worker_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self.worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        self._stop.set()
        await self.queue.put({"type": "_shutdown"})
        if self.worker_task is not None:
            with suppress(asyncio.CancelledError):
                await self.worker_task

    async def submit(self, job: dict) -> bool:
        try:
            self.queue.put_nowait(job)
            return True
        except asyncio.QueueFull:
            return False

    async def _worker(self) -> None:
        while not self._stop.is_set():
            job = await self.queue.get()
            try:
                if job["type"] == "_shutdown":
                    return
                await process_job(job)
            except Exception:
                logger.exception("Background job failed", extra={"job": job})
            finally:
                self.queue.task_done()


async def handler(request, dispatcher: BackgroundDispatcher):
    async with asyncio.TaskGroup() as tg:
        task_a = tg.create_task(call_a())
        task_b = tg.create_task(call_b())
        task_c = tg.create_task(call_c())

    accepted = await dispatcher.submit(
        {"type": "post_response_work", "request_id": request.id}
    )

    return {
        "a": task_a.result(),
        "b": task_b.result(),
        "c": task_c.result(),
        "background_accepted": accepted,
    }
```

Why this is safer:

- The request path has structured concurrency.
- Background work has explicit owner: the application, not the request handler.
- The worker task has a strong reference.
- You can define shutdown behavior: drain, stop, or reject new jobs.
- Queue capacity gives you backpressure instead of infinite hidden task growth.
- Failures are observed and logged in one place.

If the work actually matters, do not background it. Await it.
If it truly does not matter, do not spawn it ad hoc from the handler; make it best-effort and explicitly supervised.
If it really must survive process restarts, in-process tasks are the wrong tool; use a durable external job queue.

This is `asyncio`-specific guidance, based on the documented behavior of `asyncio.gather()`, `asyncio.create_task()`, and `asyncio.TaskGroup`.

Natural next steps:
1. I can rewrite your current pattern into an app-owned dispatcher for your framework.
2. I can show the same design in AnyIO for a more portable structured-concurrency model.
3. I can review your actual handler code and point out the exact lifecycle leaks.
