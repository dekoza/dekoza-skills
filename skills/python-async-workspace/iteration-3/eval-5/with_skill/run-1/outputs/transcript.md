# Execution Transcript

## Eval Prompt

Review this pattern: a request handler uses `asyncio.gather()` for three child calls, one branch starts a background `create_task()` with no stored reference, and the response returns before that task finishes because we 'do not care if it completes later'. Another teammate wants to enable the eager task factory or `eager_start` to shave scheduler overhead. Explain the lifecycle problems and show a safer design.

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
- Tool use: read
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

This pattern is brittle. It is mixing three different concerns - concurrent request work, detached background work, and runtime micro-optimization - as if they were equivalent. They are not.

- Steelmanned thesis: "Use `asyncio.gather()` for the three request subcalls, launch a best-effort side task with `create_task()`, ignore its completion, then maybe enable eager task execution for less scheduler overhead."
- Highest-risk issue: the detached task has no owner. Once you do that in a request handler, you no longer control completion, cancellation, error reporting, or shutdown behavior.

**Lifecycle Problems**
- `asyncio.gather()` is not a lifecycle boundary. If one child raises, the others are not automatically cancelled; they can keep running while the request is already failing or unwinding.
- `asyncio.create_task()` without a stored strong reference is a real footgun. `asyncio` only keeps weak references to tasks, so "fire-and-forget" can become "fire-and-maybe-garbage-collect."
- Returning the response before the detached task finishes does not mean you "do not care." It means you have silently accepted dropped work, unobserved exceptions, flaky tests, and shutdown races.
- Request-scoped resources are the usual corpse here: DB sessions, tracing spans, auth context, open clients, and temp files often disappear right after the handler returns.
- Enabling eager task factory or `eager_start` does not fix any of that. It changes scheduling semantics. The task may start running immediately during creation, reorder side effects, and surface exceptions earlier. That is a semantic change, not a free speedup.

**What To Do Instead**
- If the work is part of the request outcome, keep it inside a structured boundary and wait for it.
- If the work may outlive the request, do not spawn it ad hoc from the handler. Hand it to an app-owned background worker or, if it truly matters, an external durable queue.

**Safer Request-Coupled Design**
```python
import asyncio

async def handle_request(item_id: str) -> dict:
    async with asyncio.TaskGroup() as tg:
        a_task = tg.create_task(fetch_a(item_id))
        b_task = tg.create_task(fetch_b(item_id))
        c_task = tg.create_task(fetch_c(item_id))

    return {
        "a": a_task.result(),
        "b": b_task.result(),
        "c": c_task.result(),
    }
```

Why this is safer:
- the handler owns the child tasks;
- exit waits for all of them;
- one failure cancels siblings;
- no stray work escapes request lifetime.

**Safer Detached Work Design**
```python
import asyncio
import logging
from collections.abc import Awaitable

logger = logging.getLogger(__name__)


class BackgroundSupervisor:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()
        self._closing = False

    def start(self, coro: Awaitable[None]) -> None:
        if self._closing:
            raise RuntimeError("background supervisor is closing")

        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_failure)

    def _log_failure(self, task: asyncio.Task[None]) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return

        if exc is not None:
            logger.exception("Background task failed", exc_info=exc)

    async def shutdown(self) -> None:
        self._closing = True
        tasks = list(self._tasks)
        if not tasks:
            return

        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
```

```python
async def handle_request(item_id: str, supervisor: BackgroundSupervisor) -> dict:
    async with asyncio.TaskGroup() as tg:
        a_task = tg.create_task(fetch_a(item_id))
        b_task = tg.create_task(fetch_b(item_id))
        c_task = tg.create_task(fetch_c(item_id))

    response = {
        "a": a_task.result(),
        "b": b_task.result(),
        "c": c_task.result(),
    }

    audit_payload = {"item_id": item_id, "status": "served"}
    supervisor.start(send_audit_event(audit_payload))

    return response
```

Critical rule there:
- pass plain data into background work, not request objects or request-bound clients.

**About Eager Start**
- It may reduce scheduler overhead in narrow hot paths.
- It also changes execution order, which can expose hidden bugs or create new ones.
- If your lifecycle is already wrong, eager start just makes the wrong code fail faster or differently.
- Benchmark it only after task ownership and shutdown semantics are correct.

**Decision Rule**
- "Need result now?" -> `TaskGroup`
- "Need work later but still care whether it happens?" -> app-owned worker or durable queue
- "Truly do not care whether it runs, fails, or gets dropped?" -> do not start it at all

This answer is `asyncio-specific`, based on the `python-async` references for structured concurrency, asyncio task semantics, and runtime tuning. Minimum verification: add tests for sibling cancellation, supervisor shutdown draining/cancellation, and a benchmark before touching eager task execution.

If you want, I can also show the same design in AnyIO or adapt it to a framework request lifecycle like FastAPI or Litestar.
