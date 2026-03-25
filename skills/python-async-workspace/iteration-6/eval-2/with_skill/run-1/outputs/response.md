This is `asyncio-specific`.

What is broken:

- Catching `CancelledError`, logging it, and then continuing the loop is a shutdown bug. Cancellation is the stop signal. If the worker keeps looping, the service never quiesces.
- `asyncio.shield()` does not make the outer task uncancelled. It only prevents the inner awaitable from being cancelled by that await. The caller still receives `CancelledError`, so you can easily end up with half-aborted shutdown logic or orphaned cleanup work.
- Intentionally suppressing `CancelledError` in raw `asyncio` is also broken unless you clear the task's cancellation state with `uncancel()`. Otherwise the task stays poisoned and later awaits can misbehave.
- An unbounded shielded close/flush is another hang source. You traded "cancellation interrupted cleanup" for "cleanup can block shutdown forever."

Safer pattern:

```python
import asyncio
import logging

log = logging.getLogger(__name__)


async def worker(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            await do_one_iteration()
    except asyncio.CancelledError:
        log.info("Worker cancelled; cleaning up")
        try:
            await asyncio.wait_for(asyncio.shield(close_resources()), timeout=5)
        finally:
            raise
```

Why this is safer:

- It treats cancellation as terminal.
- It allows async cleanup.
- It bounds cleanup time.
- It always re-raises cancellation so shutdown can finish.

For the "audit flush must survive cancellation" case, the least bad `asyncio` pattern is explicit and narrow:

```python
async def flush_audit_even_if_cancelled() -> None:
    task = asyncio.current_task()
    if task is None:
        await asyncio.wait_for(audit_flush(), timeout=2)
        return

    try:
        await asyncio.wait_for(audit_flush(), timeout=2)
    except asyncio.CancelledError:
        log.warning("Cancelled during audit flush; finishing bounded flush")
        task.uncancel()
        try:
            await asyncio.wait_for(audit_flush(), timeout=2)
        finally:
            raise
```

But this is still a sharp tool. Better design:

- move audit flushing into a supervisor-owned shutdown phase
- give it its own deadline
- wait for it explicitly before the process exits
- do not let normal worker loops decide to ignore cancellation

The rule is simple: catch cancellation only to clean up, then re-raise. Shield only bounded finalization. If code catches cancellation and keeps running, assume it is wrong.

Minimum verification:

- add a shutdown test that cancels the worker and asserts the task finishes
- add a test where `close_resources()` stalls and assert shutdown times out cleanly instead of hanging

References used: `cancellation-timeouts.md`, `backend-asyncio.md`.
