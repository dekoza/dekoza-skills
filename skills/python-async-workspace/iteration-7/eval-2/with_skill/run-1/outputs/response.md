This is broken in three different ways.

- The worker that catches `CancelledError`, logs it, and keeps looping is defeating shutdown. In `asyncio`, cancellation is not a warning; it is the stop signal. If you swallow it, the task can keep running forever and the service hangs waiting for it to die.
- The `asyncio.shield()` cleanup is also suspect. `shield()` does not make shutdown safe; it only prevents the inner awaitable from being cancelled by the outer await. The caller is still cancelled. That means you can orphan cleanup work, hide failures, or hang shutdown if the close never finishes.
- The asyncio-only audit-flush path is wrong unless it is truly deliberate and it clears the task's cancellation state. In raw `asyncio`, suppressing `CancelledError` without `uncancel()` leaves the task poisoned, and later structured-concurrency helpers can misbehave.

Safer pattern:

```python
import asyncio
import logging

logger = logging.getLogger(__name__)


async def worker(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            await do_one_iteration()
    except asyncio.CancelledError:
        logger.info("Worker cancelled; shutting down")
        raise
    finally:
        try:
            await asyncio.wait_for(resource.aclose(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("Timed out closing resource during shutdown")
```

If cleanup must resist caller cancellation briefly, bound it and keep a strong reference:

```python
async def worker() -> None:
    close_task: asyncio.Task[None] | None = None
    try:
        while True:
            await do_one_iteration()
    except asyncio.CancelledError:
        logger.info("Worker cancelled")
        raise
    finally:
        close_task = asyncio.create_task(resource.aclose())
        try:
            await asyncio.wait_for(asyncio.shield(close_task), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("Resource close did not finish within 5s")
            close_task.cancel()
        except Exception:
            logger.exception("Resource close failed")
```

If you really must suppress cancellation for an audit flush in `asyncio`, do it as a tiny, explicit exception path and clear cancellation state:

```python
async def flush_audit_even_on_cancel() -> None:
    task = asyncio.current_task()
    if task is None:
        await audit.flush()
        return

    try:
        await audit.flush()
    except asyncio.CancelledError:
        logger.warning("Cancellation deferred until audit flush completes")
        task.uncancel()
        try:
            await asyncio.wait_for(asyncio.shield(audit.flush()), timeout=2)
        finally:
            raise
```

Rules that should replace the current design:

- Catch cancellation only to log or clean up, then re-raise it.
- Shield only short, bounded finalization.
- Never use `shield()` as a generic "ignore shutdown" switch.
- If raw `asyncio` code intentionally suppresses cancellation, call `uncancel()` and re-raise after the bounded critical section.

Highest-risk footgun: swallowing `CancelledError` and continuing the main loop. That is the classic shutdown hang.

References used: `cancellation-timeouts.md`, `backend-asyncio.md`
Type: `asyncio-specific`

Minimum verification:
- Add a shutdown test that cancels the worker and asserts it exits.
- Add a cleanup-timeout test where `aclose()` blocks.
- Add an audit-flush test proving cancellation is re-raised after the bounded flush.