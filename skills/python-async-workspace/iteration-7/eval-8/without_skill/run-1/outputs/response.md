Use `TaskGroup.start()`, not `start_soon()` + `sleep()`.

```python
from anyio import (
    TASK_STATUS_IGNORED,
    create_task_group,
    create_tcp_listener,
    connect_tcp,
)
from anyio.abc import TaskStatus


async def handle_client(stream) -> None:
    ...


async def run_server(
    port: int,
    *,
    task_status: TaskStatus[None] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(
        local_host="127.0.0.1",
        local_port=port,
    ) as listener:
        task_status.started()  # signal only after bind succeeds
        await listener.serve(handle_client)


async def main() -> None:
    async with create_task_group() as tg:
        await tg.start(run_server, 5000)
        async with await connect_tcp("127.0.0.1", 5000) as stream:
            ...
```

- This fixes the race: the parent does not continue until the child has actually bound and explicitly signaled readiness.
- If bind fails before `started()`, that exception propagates directly out of `await tg.start(...)`.
- If the child exits without ever calling `task_status.started()`, `await tg.start(...)` raises `RuntimeError`.
- Important nuance: if the child forgets `started()` and then keeps running forever, `start()` does not magically detect that; it just waits forever. The `RuntimeError` happens when the child finishes without signaling readiness, not while it is still alive and silent.

So your broken path is worse than “flaky”:
- `sleep(0.1)` gives a timing race.
- forgetting `task_status.started()` can turn `await tg.start(...)` into an indefinite hang if that task stays alive.