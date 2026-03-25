This is `asyncio-specific`.

What is broken:

- The worker that catches `CancelledError` and keeps looping is wrong. Cancellation is the shutdown signal. If you log it and continue, the task stays alive and your service hangs waiting for it to die.
- In raw `asyncio`, cancellation is edge-triggered. You often get one injected `CancelledError`; if you swallow it, the task may just keep running forever.
- The `asyncio.shield()` cleanup is also wrong as a default pattern. `shield()` protects the inner awaitable, not the outer task. The caller still gets cancelled immediately, so your close can keep running in the background, become hard to observe, and hang shutdown if it has no time bound.
- The “intentionally suppress cancellation” path is especially sharp. In `asyncio`, if you truly suppress `CancelledError` and continue normal execution, you must also clear the task’s cancellation state with `uncancel()`. If you do not, the task stays poisoned and higher-level helpers like `TaskGroup` / `asyncio.timeout()` can misbehave.

Safer pattern:

- Catch cancellation only to do bounded cleanup.
- Make cleanup idempotent.
- Put a timeout around cleanup.
- Re-raise cancellation after cleanup.
- If some work must outlive the cancelled task, run it as a separately owned task, not by keeping the cancelled task alive.

Example:

```python
import asyncio
import logging

log = logging.getLogger(__name__)

async def worker(resource):
    try:
        while True:
            item = await resource.get()
            await resource.process(item)
    except asyncio.CancelledError:
        log.info("worker cancelled; shutting down")

        try:
            async with asyncio.timeout(5):
                await resource.aclose()
        finally:
            raise
```

If cleanup itself must resist interruption briefly, make it bounded and explicit:

```python
import asyncio
import contextlib

async def close_with_budget(resource, seconds=5):
    close_task = asyncio.create_task(resource.aclose())

    try:
        async with asyncio.timeout(seconds):
            await asyncio.shield(close_task)
    except TimeoutError:
        close_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await close_task
```

Used from cancellation handling:

```python
async def worker(resource):
    try:
        while True:
            await resource.run_once()
    except asyncio.CancelledError:
        try:
            await close_with_budget(resource, seconds=5)
        finally:
            raise
```

For the audit flush case:

- Best fix: move the flush into its own supervisor-owned task and await it with a shutdown budget.
- Bad fix: suppress cancellation in the cancelled task and keep doing ordinary work.

Only if you absolutely must suppress cancellation in that same task:

```python
import asyncio

async def flush_audit_even_during_shutdown(audit):
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("must run in a task")

    try:
        await audit.flush()
    except asyncio.CancelledError:
        await audit.flush()          # narrow, final flush only
        task.uncancel()             # asyncio-only; clears poisoned state
        return
```

That pattern is still risky. It should be tiny, final-only, and not loop. If it grows beyond a narrow flush, the design is wrong.

Highest-risk footgun:

- `except asyncio.CancelledError: ... continue` is a shutdown bug.
- `asyncio.shield()` without a timeout is a shutdown hang factory.

Minimum verification:

- Add a test that cancels the worker task and asserts it finishes within a short timeout.
- Add a test that makes `aclose()` block and confirms shutdown still completes because the cleanup budget expires.

Sources used: `cancellation-timeouts.md`, `backend-asyncio.md`.

If you want, I can turn this into a concrete before/after patch for your worker and shutdown paths.
