Use `TaskGroup.start()`. Sleeping for `0.1` is a race, not a readiness protocol.

`AnyIO-portable`  
Sources used: AnyIO docs `tasks.html`, `python-async/references/structured-concurrency.md`, AnyIO asyncio backend source `src/anyio/_backends/_asyncio.py`

```python
from anyio import TASK_STATUS_IGNORED, create_task_group, create_tcp_listener, connect_tcp
from anyio.abc import TaskStatus, SocketStream


async def handle_client(stream: SocketStream) -> None:
    async with stream:
        await stream.send(b"hello\n")


async def serve_tcp(
    port: int,
    *,
    task_status: TaskStatus[None] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(local_host="127.0.0.1", local_port=port) as listener:
        task_status.started()  # signal only after bind/listen succeeded
        await listener.serve(handle_client)


async def main() -> None:
    async with create_task_group() as tg:
        await tg.start(serve_tcp, 5000)  # blocks until child signals readiness
        async with await connect_tcp("127.0.0.1", 5000) as stream:
            data = await stream.receive()
```

What `start()` buys you:

- If bind/listen fails before readiness, `await tg.start(...)` raises that real exception to the parent immediately.
- If the child exits without calling `task_status.started()`, `start()` raises `RuntimeError`.
- In the AnyIO asyncio backend, the exact error is:
  - `RuntimeError("Child exited without calling task_status.started()")`

The important footgun:

- If the child does not call `started()` and also does not exit, `start()` does not magically fail fast; it stays blocked until the task exits or you cancel/time out the wait.
- So the broken code path is worse than flaky: one version can hang forever, and another can raise that `RuntimeError`.

If you want, I can also show the minimal pytest pattern that proves all three cases:
1. ready path, 2. bind failure propagation, 3. missing `started()` failure.