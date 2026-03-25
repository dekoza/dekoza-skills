# Execution Transcript

## Eval Prompt

Review this pattern: a request handler uses `asyncio.gather()` for three child calls, one branch starts a background `create_task()` with no stored reference, and the response returns before that task finishes because we 'do not care if it completes later'. That detached task currently closes over the `request` object, a DB session, and a tracing span. Another teammate wants to enable the eager task factory or `eager_start` to shave scheduler overhead. During traffic spikes and deploy drain, this path can also queue a burst of post-response work, so we need an explicit policy for whether to buffer, reject, drain on shutdown, or hand off durably. Explain the lifecycle problems and show a safer design.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: read
- Tool use: read
- Tool use: skill:court-jester
- Tool use: read
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

This pattern is broken in exactly the place it pretends to be convenient: it smuggles request-scoped state into work that outlives the request, then calls that "fire-and-forget".

- `asyncio.gather()` is fine for "run 3 things and collect results", but it is not a lifecycle boundary; if one child raises, the others are not automatically cancelled the way a `TaskGroup` gives you.
- Bare `asyncio.create_task()` with no stored reference is a footgun; asyncio only keeps weak references to tasks, so the task can be lost before completion.
- "We do not care if it completes later" is sloppy framing. You must care about ownership, shutdown, overload, and failure visibility even if the HTTP caller does not wait for the result.
- Closing over `request`, a DB session, and a tracing span is the worst part. Those are request-bound resources. After the response returns, they may already be closed, ended, cancelled, or otherwise invalid.
- Enabling eager task factory / `eager_start` here is not a free speedup. It changes execution timing and ordering. That can surface hidden reentrancy and lifetime bugs sooner, not fix them.

**Lifecycle Problems**

- **Request lifetime violation**: the detached task uses objects whose validity ends with the request. Expect closed sessions, ended spans, cancelled context, and accidental retention of large request data.
- **No owner**: the handler spawns work, but nothing defines who tracks it, limits it, drains it, or reports failures.
- **Shutdown races**: during deploy drain, those tasks may be cancelled mid-flight, silently abandoned, or continue against partially torn-down app state.
- **Burst amplification**: post-response work can pile up faster than it drains. Without a bound, memory becomes the queue.
- **Invisible failure**: if the detached task errors after the response, the user already got `200 OK`; unless you explicitly report it, the failure vanishes into logs or worse.
- **Eager-start hazard**: if task execution begins immediately at creation time, code that assumed "schedule now, run later" semantics can start touching request state before the handler finishes its own cleanup path.

**What To Do Instead**

Split the problem into two lifetimes:

1. **Request-coupled fanout**
- Use `asyncio.TaskGroup` for the three child calls if their lifetime is part of serving the request.
- That gives one owner, one exit point, and sibling cancellation on failure.

2. **Post-response work**
- Do not spawn it directly from the handler.
- Hand off a plain data snapshot to an app-owned background boundary: bounded queue, worker pool, or durable outbox.

The detached unit of work should contain only serializable, durable inputs like:
- IDs
- timestamps
- correlation / trace IDs
- small immutable payload needed for processing

It should not contain:
- `request`
- ORM / DB session objects
- open sockets / file handles
- live tracing span objects

**Policy You Need To Choose Explicitly**

"Best effort" is not a policy. Pick one:

- **Buffer and drain**: bounded in-memory queue; accept until full; on shutdown stop admission and drain for a fixed deadline.
- **Reject when full**: if the work is important to the caller, return `503` or `429` instead of pretending success.
- **Drop when full**: only for truly optional side effects; count and log drops.
- **Durable handoff**: if the work must survive process crash or deploy, put it in a broker / DB outbox and let a separate worker own it.

Rule of thumb:
- If losing the work is acceptable -> bounded in-memory queue.
- If losing the work is not acceptable -> durable handoff.
- If you cannot articulate which of those is true, the design is unfinished.

**Safer asyncio Design**

```python
import asyncio
from dataclasses import dataclass
from contextlib import suppress

@dataclass(frozen=True)
class PostResponseJob:
    user_id: str
    order_id: str
    trace_id: str

class BackgroundDispatcher:
    def __init__(self, *, queue_size: int = 1000, workers: int = 4) -> None:
        self._queue: asyncio.Queue[PostResponseJob] = asyncio.Queue(maxsize=queue_size)
        self._workers = workers
        self._worker_tasks: set[asyncio.Task[None]] = set()
        self._accepting = True

    async def start(self) -> None:
        for index in range(self._workers):
            task = asyncio.create_task(self._worker(index), name=f"post-response-worker-{index}")
            self._worker_tasks.add(task)
            task.add_done_callback(self._worker_tasks.discard)

    async def submit(self, job: PostResponseJob) -> bool:
        if not self._accepting:
            return False
        try:
            self._queue.put_nowait(job)
            return True
        except asyncio.QueueFull:
            return False

    async def shutdown(self, *, drain_timeout: float = 10.0) -> None:
        self._accepting = False
        try:
            await asyncio.wait_for(self._queue.join(), timeout=drain_timeout)
        except asyncio.TimeoutError:
            pass

        for task in list(self._worker_tasks):
            task.cancel()

        for task in list(self._worker_tasks):
            with suppress(asyncio.CancelledError):
                await task

    async def _worker(self, worker_index: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            except Exception:
                # report to logs / metrics / error tracking
                pass
            finally:
                self._queue.task_done()

    async def _process(self, job: PostResponseJob) -> None:
        # Create fresh per-job resources here.
        # New DB session, new trace/span from trace_id, new client handles if needed.
        await asyncio.sleep(0.01)
```

Handler sketch:

```python
async def handler(request, dispatcher: BackgroundDispatcher):
    async with asyncio.TaskGroup() as tg:
        a_task = tg.create_task(call_a(request))
        b_task = tg.create_task(call_b(request))
        c_task = tg.create_task(call_c(request))

    response = make_response(
        a_task.result(),
        b_task.result(),
        c_task.result(),
    )

    job = PostResponseJob(
        user_id=request.user.id,
        order_id=request.path_params["order_id"],
        trace_id=request.headers.get("x-trace-id", ""),
    )

    accepted = await dispatcher.submit(job)
    if not accepted:
        # choose policy:
        # - log and drop if optional
        # - or fail request if enqueue is required
        pass

    return response
```

**Why This Is Safer**

- The request fanout stays inside structured concurrency.
- Post-response work has an owner: `BackgroundDispatcher`.
- The queue is bounded, so overload behavior is explicit.
- Workers hold strong task references and are shut down deliberately.
- Each job creates fresh DB/tracing resources instead of reusing dead request ones.
- Shutdown can stop admission, drain for a deadline, then cancel.

**About eager task factory / `eager_start`**

Do not turn that on as a band-aid.

- It does not solve lost ownership.
- It does not solve request-lifetime capture.
- It does not solve overload or shutdown policy.
- It can change execution order enough to expose hidden bugs in code that assumed deferred scheduling.

Only consider it after:
- task ownership is explicit,
- post-response work is isolated from request resources,
- overload policy is defined,
- shutdown behavior is tested,
- and you have a benchmark showing scheduler overhead is actually material.

**Recommended policy**

For most services:
- Use `TaskGroup` for request-time fanout.
- Use a bounded app queue only for optional, losable side effects.
- Use durable handoff for anything that must survive crash, drain, or restart.

The highest-risk issue is the detached task capturing request-scoped objects. That is not "background processing"; it is use-after-lifetime with good marketing.

References used: `structured-concurrency.md`, `backend-asyncio.md`, `cancellation-timeouts.md`, `streams-synchronization.md`, `backend-uvloop.md`. Classification: `asyncio-specific`.

Natural next steps:
1. I can turn this into a concrete pattern for your framework (`aiohttp`, FastAPI/Starlette, Litestar, etc.).
2. I can sketch the shutdown and overload tests you should add before changing this path.
3. I can show the durable outbox variant if this work must survive deploys and crashes.
