Your `sleep(0.1)` hack is the bug. It is not a readiness protocol; it is a race with wishful thinking.

Use `TaskGroup.start()` and have the child signal readiness only after the listener is bound:

```python
from anyio import (
    TASK_STATUS_IGNORED,
    connect_tcp,
    create_task_group,
    create_tcp_listener,
)
from anyio.abc import TaskStatus

async def handler(stream) -> None:
    ...

async def serve_tcp(
    host: str,
    port: int,
    *,
    task_status: TaskStatus[None] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(local_host=host, local_port=port) as listener:
        task_status.started()
        await listener.serve(handler)

async def main() -> None:
    async with create_task_group() as tg:
        await tg.start(serve_tcp, "127.0.0.1", 5000)
        async with await connect_tcp("127.0.0.1", 5000) as stream:
            ...
```

What `start()` gives you:

- If bind/init fails before readiness, `await tg.start(...)` raises that original exception in the parent.
- If the child exits without ever calling `task_status.started()`, `await tg.start(...)` raises exactly:
  - `RuntimeError("Child exited without calling task_status.started()")`
- If the child never calls `started()` and also never exits, `await tg.start(...)` does not magically fail fast; it waits forever until something cancels it.
- If the waiting parent is cancelled while blocked in `start()`, AnyIO cancels the child, waits for it to finish, then re-raises the cancellation.

So the precise rule is harsher than the docs shorthand: “never signals readiness” only becomes `RuntimeError` if the child actually exits first. A child that forgets `started()` and keeps running just deadlocks the startup path.

References used: `python-async` skill `references/structured-concurrency.md`, AnyIO task docs, AnyIO 4.13.0 `_backends/_asyncio.py`.

Natural next step:
1. Add a test that intentionally omits `task_status.started()` and asserts `RuntimeError("Child exited without calling task_status.started()")`.
2. Add a second test that proves `start()` propagates the bind failure directly.
