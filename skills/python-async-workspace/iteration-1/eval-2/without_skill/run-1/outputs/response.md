The highest-risk bug is broken cancellation semantics.

Your worker is catching `asyncio.CancelledError`, logging it, and then continuing the loop. That is not a style choice. It is a shutdown bug. In `asyncio`, cancellation is the mechanism the runtime uses to stop tasks. If you swallow `CancelledError`, the task stays alive, structured-concurrency helpers can misbehave, and shutdown can hang because the task never actually exits.

The rule is simple: if you catch `CancelledError` to do cleanup or logging, re-raise it when that work is finished.

Bad pattern:

```python
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

The `asyncio.shield()` part is also dangerous as a default fix. Raw `shield()` prevents the inner awaitable from being cancelled when the outer task is cancelled, but the outer task is still cancelled immediately. That means you can easily end up with cleanup still running in the background with no bound on how long it takes. On shutdown, that often turns into "we tried to be safe" and accidentally made teardown unbounded.

So the safer pattern is: bounded cleanup, then propagate cancellation.

If you use AnyIO, this is the clean version:

```python
import anyio


async def worker() -> None:
    try:
        while True:
            await do_one_iteration()
    except BaseException:
        with anyio.move_on_after(5, shield=True) as scope:
            await resource.aclose()
        if scope.cancel_called:
            logger.warning("Timed out while closing resource during shutdown")
        raise
```

If you stay in plain `asyncio`, use an explicit timeout around cleanup and do not turn `shield()` into an unbounded escape hatch:

```python
import asyncio


async def worker() -> None:
    try:
        while True:
            await do_one_iteration()
    except asyncio.CancelledError:
        logger.info("worker cancelled; closing resource")
        close_task = asyncio.create_task(resource.aclose())
        try:
            await asyncio.wait_for(close_task, timeout=5)
        except TimeoutError:
            logger.warning("Timed out while closing resource during shutdown")
        raise
```

Why this is safer:

- cancellation still means "stop now"
- cleanup gets a chance to run
- cleanup is bounded, so shutdown does not hang forever
- the task actually terminates instead of looping forever

If you truly suppress cancellation, you are changing task state semantics and usually fighting the runtime. That is rarely justified and is not the right default here.
