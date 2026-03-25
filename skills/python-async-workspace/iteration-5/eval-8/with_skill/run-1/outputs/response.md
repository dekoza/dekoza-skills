The `sleep(0.1)` pattern is wrong. It is a race, so your CI flakes are expected.

Use the readiness handshake AnyIO already gives you:

```python
from anyio import TASK_STATUS_IGNORED, create_task_group, create_tcp_listener, connect_tcp
from anyio.abc import TaskStatus


async def serve_tcp(
    port: int,
    *,
    task_status: TaskStatus[None] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(local_host="127.0.0.1", local_port=port) as listener:
        task_status.started()
        await listener.serve(handler)


async def main() -> None:
    async with create_task_group() as tg:
        await tg.start(serve_tcp, 5000)
        async with await connect_tcp("127.0.0.1", 5000) as stream:
            ...
```

If you need to return bound info, signal it through `started()`:

```python
from anyio import TASK_STATUS_IGNORED, create_task_group, create_tcp_listener
from anyio.abc import TaskStatus


async def serve_ephemeral(
    *,
    task_status: TaskStatus[int] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(local_host="127.0.0.1", local_port=0) as listener:
        port = listener.extra("sockname")[1]
        task_status.started(port)
        await listener.serve(handler)


async def main() -> None:
    async with create_task_group() as tg:
        port = await tg.start(serve_ephemeral)
        ...
```

Exact failure behavior for `TaskGroup.start()`:

- If the child raises before calling `task_status.started()`, `await tg.start(...)` raises that original exception.
- If the child exits normally without ever calling `task_status.started()`, `await tg.start(...)` raises `RuntimeError("Child exited without calling task_status.started()")` on the asyncio backend.
- If the child never calls `task_status.started()` and also never exits, `await tg.start(...)` does not fail fast; it just waits forever until something cancels it.

That last case is the footgun in your “bind, forget `started()`, then `serve()` forever” path: `start()` hangs, it does not magically detect the omission.

Verified from:
- AnyIO docs for `TaskGroup.start()`
- AnyIO asyncio backend source, where task completion without readiness sets `RuntimeError("Child exited without calling task_status.started()")`

Natural next steps:
1. Replace every “start task + sleep + connect” call site with `await tg.start(...)`
2. Add a test that proves missing `task_status.started()` either raises on early exit or hangs until timeout/cancellation in the long-running case
