This is `asyncio-specific`.

References used: `skills/python-async/SKILL.md`, `skills/python-async/references/cancellation-timeouts.md`, `skills/python-async/references/structured-concurrency.md`, `skills/python-async/references/backend-asyncio.md`.

The highest-risk issue is broken cancellation semantics.

Your worker is broken because it catches `CancelledError`, logs it, and then keeps looping. That is not defensive code. It is a shutdown bug. In `asyncio`, cancellation is how the runtime tells a task to stop. If you swallow `CancelledError`, the task stays alive, task-group or timeout behavior can misfire, and process shutdown can hang because the worker never exits.

The rule is blunt: catch cancellation only to do minimal cleanup, then re-raise it.

Broken pattern:

```python
import asyncio


async def worker() -> None:
    while True:
        try:
            await do_one_iteration()
        except asyncio.CancelledError:
            logger.info("worker cancelled")
            continue
```

Safer pattern:

```python
import asyncio
import logging

logger = logging.getLogger(__name__)


async def worker() -> None:
    try:
        while True:
            await do_one_iteration()
    except asyncio.CancelledError:
        logger.info("worker cancelled; stopping")
        await cleanup_on_cancel()
        raise
```

The `asyncio.shield()` cleanup is also a footgun. Raw `shield()` does not make shutdown safe. It only prevents the inner awaitable from being cancelled by the outer awaiter, while the outer task is still cancelled immediately. That makes it easy to orphan cleanup work or let teardown run forever with no bound. Using raw `asyncio.shield()` as the default fix is the wrong pattern.

What you want instead is bounded cleanup plus cancellation propagation.

Portable AnyIO version:

```python
import anyio


async def worker() -> None:
    try:
        while True:
            await do_one_iteration()
    except anyio.get_cancelled_exc_class():
        with anyio.move_on_after(5, shield=True) as scope:
            await resource.aclose()
        if scope.cancel_called:
            logger.warning("Timed out while closing resource during shutdown")
        raise
```

Plain `asyncio` version:

```python
import asyncio
import contextlib


async def worker() -> None:
    try:
        while True:
            await do_one_iteration()
    except asyncio.CancelledError:
        logger.info("worker cancelled; closing resource")
        close_task = asyncio.create_task(resource.aclose())
        try:
            await asyncio.wait_for(asyncio.shield(close_task), timeout=5)
        except TimeoutError:
            logger.warning("Timed out while closing resource during shutdown")
            close_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await close_task
        raise
```

Why this is safer:

- cancellation still means "stop"
- cleanup gets a short, explicit window
- shutdown cannot hang forever on cleanup
- the task actually terminates instead of looping forever

Minimum verification step: add a shutdown test that cancels the worker and asserts two things: the worker task finishes with `CancelledError`, and cleanup either completes within the bound or logs the timeout path.
