The pattern is brittle. It mixes request-scoped work, detached work, and lifecycle-sensitive resources as if they all share the same lifetime. They do not.

**What Is Actually Happening**
- `asyncio.gather()` only manages the three awaited children; the extra `create_task()` is outside that structure, so the handler can finish while orphan work is still running.
- A task created with `asyncio.create_task()` must have a stored reference; the Python docs explicitly warn the event loop keeps only weak references, so an unreferenced task can disappear mid-execution.
- `gather()` is also the weaker primitive here: if one child raises, `gather()` propagates that exception but does not cancel the other children; `TaskGroup` does.

**Lifecycle Bugs**
- The detached task closes over `request`: after the response, middleware/request cleanup may already have run, body streams may be gone, and any mutable request state is now out of contract.
- It closes over a DB session: request-scoped sessions are commonly committed/rolled back/closed at request end. Reusing that session later is use-after-close dressed up as optimism.
- It closes over a tracing span: request spans should end with the request. A later task writing to that span is corrupt context, or just silently lost telemetry.
- During deploy drain/shutdown, in-process background work is not durable. It may be cancelled, abandoned, or never started before loop shutdown.
- During spikes, each request can enqueue more post-response work, so latency looks fine while memory, DB pressure, and shutdown time rot underneath.

**Why Eager Start Makes This Worse**
- `eager_start` / eager task factory is a semantic change, not a free optimization.
- The coroutine may start running synchronously inside `create_task()`. If it does CPU work, touches request/session/span, or raises before first `await`, that now happens inline on the request path.
- Task ordering changes. Code that accidentally relied on "scheduled later" behavior can break.
- If you have unsafe detached work now, eager start just helps it fail faster and in weirder places.

**Highest-Risk Issue**
- The real bug is not scheduler overhead. It is letting post-response work depend on request-scoped objects. That is a lifetime violation.

**Safer Design**
Use structured concurrency for request work, and a separately owned background subsystem for post-response work.

```python
import asyncio
from dataclasses import dataclass

@dataclass(frozen=True)
class PostResponseJob:
    user_id: str
    order_id: str
    traceparent: str | None

class BackgroundDispatcher:
    def __init__(self, *, max_queue_size: int = 1000, workers: int = 4):
        self._queue: asyncio.Queue[PostResponseJob] = asyncio.Queue(maxsize=max_queue_size)
        self._workers: set[asyncio.Task[None]] = set()
        self._accepting = True
        self._worker_count = workers

    async def start(self) -> None:
        for index in range(self._worker_count):
            task = asyncio.create_task(self._worker(index), name=f"post-response-worker-{index}")
            self._workers.add(task)
            task.add_done_callback(self._workers.discard)

    def submit_nowait(self, job: PostResponseJob) -> bool:
        if not self._accepting:
            return False
        try:
            self._queue.put_nowait(job)
            return True
        except asyncio.QueueFull:
            return False

    async def shutdown(self, *, drain_timeout: float = 5.0) -> None:
        self._accepting = False
        try:
            async with asyncio.timeout(drain_timeout):
                await self._queue.join()
        except TimeoutError:
            pass

        for task in list(self._workers):
            task.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)

    async def _worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            finally:
                self._queue.task_done()

    async def _process(self, job: PostResponseJob) -> None:
        # Open fresh resources inside worker lifetime.
        # Create a new DB session here.
        # Start a new trace/span here, optionally linked to job.traceparent.
        await do_post_response_work(
            user_id=job.user_id,
            order_id=job.order_id,
            traceparent=job.traceparent,
        )

async def handle_request(request, dispatcher: BackgroundDispatcher) -> dict:
    async with asyncio.TaskGroup() as tg:
        profile_t = tg.create_task(load_profile(request.user.id))
        settings_t = tg.create_task(load_settings(request.user.id))
        quota_t = tg.create_task(load_quota(request.user.id))

    response = {
        "profile": profile_t.result(),
        "settings": settings_t.result(),
        "quota": quota_t.result(),
    }

    job = PostResponseJob(
        user_id=request.user.id,
        order_id=request.headers["X-Order-ID"],
        traceparent=request.headers.get("traceparent"),
    )

    accepted = dispatcher.submit_nowait(job)
    if not accepted:
        # Explicit overload policy here.
        # Either fail, degrade, or persist durably.
        response["post_response_enqueued"] = False
    else:
        response["post_response_enqueued"] = True

    return response
```

**Why This Is Safer**
- Request-scoped fan-out uses `TaskGroup`, so failures cancel siblings and complete before response.
- Post-response work gets only immutable data, not live request/session/span objects.
- Background workers own their own lifetime, task references, cancellation, logging, and shutdown.
- Backpressure is explicit via a bounded queue.

**Policy You Need To Decide Explicitly**
- `best effort`: bounded in-memory queue; reject or drop when full; okay to lose on crash/deploy.
- `must happen before success`: do not detach it; keep it in the request path and await it.
- `important but can finish shortly after response`: bounded queue plus drain on shutdown with a hard timeout.
- `must survive crash/deploy`: durable handoff to a broker/job system before returning success.

**Decision Rule**
- If losing the work is acceptable, buffer in memory with a hard cap.
- If losing the work is not acceptable, in-process `create_task()` is the wrong tool; hand it off durably.
- If overload should surface to callers, reject enqueue when full instead of pretending success.
- If shutdown must be graceful, stop accepting new jobs, drain for a bounded time, then cancel leftovers.

**What Not To Do**
- Do not capture `request`, request DB sessions, or live spans in detached tasks.
- Do not use naked `create_task()` as a queue.
- Do not enable eager task factory globally unless you have benchmarks and have audited task-creation side effects.

If you want, I can also turn this into a concrete pattern for your stack: ASGI lifespan hooks, a shutdown-draining worker manager, and tracing/session examples.