# Execution Transcript

## Eval Prompt

Review this pattern: a request handler uses `asyncio.gather()` for three child calls, one branch starts a background `create_task()` with no stored reference, and the response returns before that task finishes because we 'do not care if it completes later'. Another teammate wants to enable the eager task factory or `eager_start` to shave scheduler overhead. Explain the lifecycle problems and show a safer design.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: skill:court-jester
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

This pattern is sloppy. It mixes structured request work with unstructured orphan work, then pretends lifecycle does not matter.

- `asyncio.gather()` only manages the awaitables you give it; the extra `create_task()` branch is outside that contract.
- A task created with `asyncio.create_task()` needs a strong reference; the docs explicitly warn the loop keeps only weak references, so an unreferenced task can disappear mid-execution.
- If that detached task raises, the exception is no longer part of the request flow; at best it lands in the loop exception handler, at worst it becomes noisy, late, or effectively ignored.
- Request cancellation and shutdown get muddy: the handler can finish, the client can disconnect, or the process can stop while that orphan task is still half-done.
- `gather()` is also a weaker fit than `TaskGroup` here: if one gathered child fails, `gather()` propagates the first exception but does not cancel the other submitted awaitables; `TaskGroup` does.

The eager-task idea is not a harmless micro-optimization either.

- `eager_start` / the eager task factory is a semantic change, not just a speed tweak.
- The coroutine can start running immediately during `create_task()`, before your next line stores it, registers callbacks, or updates bookkeeping.
- If it returns or raises before blocking, it may never even be scheduled on the loop; execution order changes, side effects move earlier, and debugging gets worse.
- That makes orphaned background work even less predictable, not safer.

The real design question is simple:

- If the work matters to the request, await it.
- If it does not matter to the request, do not hide it in a stray task; hand it to supervised app-level background machinery or a real job queue.

Safer request-scoped design:

```python
import asyncio

async def handler(request) -> dict:
    async with asyncio.TaskGroup() as tg:
        profile_task = tg.create_task(fetch_profile(request.user_id))
        orders_task = tg.create_task(fetch_orders(request.user_id))
        flags_task = tg.create_task(fetch_flags(request.user_id))

    return {
        "profile": profile_task.result(),
        "orders": orders_task.result(),
        "flags": flags_task.result(),
    }
```

If you truly need post-response best-effort work, supervise it explicitly:

```python
import asyncio
import logging

log = logging.getLogger(__name__)


class BackgroundSupervisor:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
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
            log.exception("Background task failed")

    async def shutdown(self) -> None:
        if not self._tasks:
            return
        await asyncio.gather(*self._tasks, return_exceptions=True)


background = BackgroundSupervisor()


async def handler(request) -> dict:
    async with asyncio.TaskGroup() as tg:
        profile_task = tg.create_task(fetch_profile(request.user_id))
        orders_task = tg.create_task(fetch_orders(request.user_id))
        flags_task = tg.create_task(fetch_flags(request.user_id))

    background.spawn(send_audit_event(request.user_id))

    return {
        "profile": profile_task.result(),
        "orders": orders_task.result(),
        "flags": flags_task.result(),
    }
```

Best design if completion actually matters: use a queue/outbox/job runner instead of in-process fire-and-forget.

Highest-risk issue: the detached task has no owner. No owner means no guarantee of completion, no reliable error reporting, and no clean shutdown story.

If you want, I can also show:
1. a version integrated with FastAPI/Starlette lifespan,
2. a pure `asyncio` shutdown pattern,
3. or a durable outbox/worker design.
