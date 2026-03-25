# Execution Transcript

## Eval Prompt

I start a TCP listener in an AnyIO task group and then sleep for 0.1 seconds before connecting, because that usually gives it time to bind. Sometimes CI flakes. Show the correct readiness pattern and tell me what mistake this sleep-based pattern is hiding.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: bash
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

Use `TaskGroup.start()` and have the server task call `task_status.started(...)` only after the listener is actually bound.

```python
from anyio import TASK_STATUS_IGNORED, connect_tcp, create_task_group, create_tcp_listener
from anyio.abc import TaskStatus


async def handle_client(stream):
    async with stream:
        await stream.send(b"ok")


async def serve(
    *,
    task_status: TaskStatus[int] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(local_host="127.0.0.1", local_port=0) as listener:
        port = listener.extra("socket").getsockname()[1]
        task_status.started(port)
        await listener.serve(handle_client)


async def main() -> None:
    async with create_task_group() as tg:
        port = await tg.start(serve)
        async with await connect_tcp("127.0.0.1", port) as stream:
            data = await stream.receive()
            assert data == b"ok"
```

What your `sleep(0.1)` is hiding:

- It is not a readiness signal; it is a timing guess.
- The real bug is missing synchronization between "task spawned" and "listener bound and accepting".
- It also hides startup failures: if bind/listener setup raises, `start()` propagates that immediately, while the sleep pattern often turns it into flaky `ConnectionRefusedError` noise.
- In other words, you are treating scheduling latency as if it were readiness, which is wrong.
