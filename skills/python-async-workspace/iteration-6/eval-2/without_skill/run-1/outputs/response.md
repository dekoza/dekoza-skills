What is broken:

- Your worker is wrong. Catching `asyncio.CancelledError`, logging it, and then continuing the loop defeats shutdown. The task stays alive, so anything awaiting task completion can hang forever.
- That also breaks asyncio’s structured-concurrency machinery. `TaskGroup` and `asyncio.timeout()` use cancellation internally; swallowing `CancelledError` can make them misbehave.
- `asyncio.shield()` is commonly misunderstood. It does not make the caller “not cancelled”. It only prevents the inner awaitable from being cancelled by that caller’s cancellation. The outer `await` still raises `CancelledError`.
- So `await asyncio.shield(close())` during shutdown often creates the worst mix: the shutdown task is cancelled, but `close()` keeps running in the background. If you do not keep and await that task explicitly, shutdown can become racy, detached, or hang elsewhere.
- If you truly suppress cancellation in pure asyncio, suppressing the exception is not enough. The task remains in a cancelled state unless you also call `Task.uncancel()`. That escape hatch is real, but it should be rare and tightly scoped.

Safer patterns:

```python
import asyncio
import logging

log = logging.getLogger(__name__)


async def worker(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            await do_one_iteration()
    except asyncio.CancelledError:
        log.info("Worker cancelled; exiting")
        raise
    finally:
        await release_worker_resources()
```

If you need cleanup on cancellation, do it and then re-raise:

```python
async def worker() -> None:
    try:
        while True:
            await do_one_iteration()
    except asyncio.CancelledError:
        log.info("Worker cancelled; cleaning up")
        await cleanup()
        raise
```

For shutdown close logic, bound it instead of shielding forever:

```python
async def shutdown_resource(resource) -> None:
    try:
        async with asyncio.timeout(5):
            await resource.aclose()
    except TimeoutError:
        log.error("Timed out closing resource")
```

If you must let the close continue even after the caller is cancelled, keep the task and finish it deliberately:

```python
async def shutdown_resource(resource) -> None:
    close_task = asyncio.create_task(resource.aclose())
    try:
        await asyncio.shield(close_task)
    except asyncio.CancelledError:
        log.warning("Shutdown cancelled; waiting briefly for close")
        try:
            async with asyncio.timeout(5):
                await close_task
        except TimeoutError:
            log.error("Resource close still not finished")
        raise
```

For the special asyncio-only audit flush that intentionally ignores cancellation, scope it narrowly and clear the cancellation state explicitly:

```python
async def flush_audit_even_if_cancelled() -> None:
    task = asyncio.current_task()
    if task is None:
        await audit_flush()
        return

    try:
        await audit_flush()
    except asyncio.CancelledError:
        log.warning("Cancellation delayed until audit flush completes")
        task.uncancel()          # asyncio-only escape hatch
        await audit_flush()      # finish the critical flush
```

The rule of thumb:

- `CancelledError` in normal tasks: clean up, then `raise`
- `shield()`: use only when you also keep the inner task and decide who awaits it
- suppression: only in a tiny, leaf-level asyncio-only path, with `uncancel()`, and never as the default worker-loop behavior

If you want, I can also rewrite your current shutdown code into one consistent pattern using `TaskGroup` and bounded shutdown phases.
