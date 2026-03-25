# Execution Transcript

## Eval Prompt

My service hangs on shutdown. A worker catches `CancelledError`, logs it, then keeps looping. Another cleanup path uses `asyncio.shield()` around an async close call because we did not want cancellation to interrupt it. There is also one asyncio-only path that intentionally suppresses cancellation to keep an audit flush alive. Explain what is broken and show the safer pattern.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:court-jester
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

What is broken:

- Catching `CancelledError` and then continuing the worker loop is a shutdown bug. Cancellation is the stop signal. If you log it and keep looping, the task ignores shutdown and the service hangs.
- `asyncio.shield()` is commonly misunderstood. It protects the inner awaitable from being cancelled, but the outer task still gets `CancelledError` immediately. So `await asyncio.shield(close())` does not mean "finish close before shutdown"; it often means "cleanup is now running off to the side while shutdown logic is already cancelled."
- Suppressing cancellation to keep an audit flush alive turns shutdown into unbounded I/O wait. If that flush blocks, your service never exits.
- If this code ever runs under structured concurrency helpers (`TaskGroup`, `asyncio.timeout()`, AnyIO/Trio), swallowing cancellation also breaks their control flow.

The safe rule is simple:

- treat cancellation as terminal for the current task
- do only bounded, explicit cleanup
- then re-raise `CancelledError`

A safer asyncio pattern looks like this:

```python
import asyncio
import contextlib
import logging

log = logging.getLogger(__name__)


async def close_with_deadline(resource, timeout: float = 5.0) -> None:
    close_task = asyncio.create_task(resource.aclose())
    try:
        await asyncio.wait_for(close_task, timeout)
    except asyncio.TimeoutError:
        log.warning("Timed out while closing resource")
        close_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await close_task


async def flush_audit_with_deadline(audit_sink, timeout: float = 2.0) -> None:
    flush_task = asyncio.create_task(audit_sink.flush())
    try:
        await asyncio.wait_for(flush_task, timeout)
    except asyncio.TimeoutError:
        log.error("Audit flush missed shutdown deadline")
        flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await flush_task


async def worker(queue, resource, audit_sink) -> None:
    try:
        while True:
            item = await queue.get()
            await handle(item)
    except asyncio.CancelledError:
        log.info("Worker cancelled; stopping")
        try:
            await flush_audit_with_deadline(audit_sink)
            await close_with_deadline(resource)
        finally:
            raise
```

Safer still: move cleanup out of the cancelled worker and into a shutdown coordinator:

```python
async def shutdown(workers, resource, audit_sink) -> None:
    for task in workers:
        task.cancel()

    await asyncio.gather(*workers, return_exceptions=True)

    await flush_audit_with_deadline(audit_sink, timeout=2.0)
    await close_with_deadline(resource, timeout=5.0)
```

Why this is better:

- workers stop when cancelled
- cleanup has a deadline, so shutdown cannot hang forever
- no silent cancellation suppression
- no `shield()`-based orphaned cleanup

The audit-flush path is the weak spot. If audit durability really matters, do not “win” by ignoring cancellation. Put audit writes behind a dedicated queue/spool and drain it during shutdown with a fixed deadline. If you need, I can show the same pattern for AnyIO/Trio too, because the failure mode is even harsher there.
