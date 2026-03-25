# Execution Transcript

## Eval Prompt

I start a TCP listener in an AnyIO task group and then sleep for 0.1 seconds before connecting, because that usually gives it time to bind. Sometimes CI flakes. Show the correct readiness pattern and tell me what mistake this sleep-based pattern is hiding.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Tool use: bash
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

Use an explicit startup handshake, not a timing guess.

```python
from anyio import (
    TASK_STATUS_IGNORED,
    connect_tcp,
    create_task_group,
    create_tcp_listener,
)
from anyio.abc import TaskStatus


async def handle_client(stream) -> None:
    async with stream:
        await stream.send(b"hello\n")


async def serve_tcp(
    port: int,
    *,
    task_status: TaskStatus[None] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(
        local_host="127.0.0.1",
        local_port=port,
    ) as listener:
        task_status.started()   # listener is bound and ready
        await listener.serve(handle_client)


async def main() -> None:
    async with create_task_group() as tg:
        await tg.start(serve_tcp, 5000)
        async with await connect_tcp("127.0.0.1", 5000) as stream:
            data = await stream.receive()
            assert data == b"hello\n"
```

What your `sleep(0.1)` pattern is hiding:
- It assumes "task was scheduled" means "socket is bound". That is false.
- You have no readiness signal, so parent and child race on scheduler timing and machine load.
- You also hide startup failures: with `tg.start()`, a bind error propagates immediately; with `start_soon() + sleep()`, you just hope the child got far enough before connect.
- The real bug is missing initialization coordination, not “CI is slow”.

The blunt version: sleeping is not synchronization. It is a flaky substitute for `TaskGroup.start()`.

References used: AnyIO task startup docs (`TaskGroup.start()`), AnyIO testing guidance on testing readiness handshakes instead of sleeping.
