# Execution Transcript

## Eval Prompt

I start a TCP listener in an AnyIO task group and then sleep for 0.1 seconds before connecting, because that usually gives it time to bind. Sometimes CI flakes. One code path even forgets to call `task_status.started()` after binding. Show the correct readiness pattern and tell me the exact failure behavior that `start()` gives me when the child never signals readiness.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: bash
- Tool use: bash
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: grep
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

Sleeping `0.1` is the wrong pattern. It guesses. `TaskGroup.start()` gives you an actual readiness handshake.

```python
from anyio import TASK_STATUS_IGNORED, create_task_group, create_tcp_listener, connect_tcp
from anyio.abc import TaskStatus

async def run_listener(
    port: int,
    *,
    task_status: TaskStatus[None] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(local_host="127.0.0.1", local_port=port) as listener:
        task_status.started()  # signal only after bind/listen succeeded
        await listener.serve(handler)

async def main() -> None:
    async with create_task_group() as tg:
        await tg.start(run_listener, 5000)
        async with await connect_tcp("127.0.0.1", 5000) as stream:
            ...
```

- Use `await tg.start(...)`, not `start_soon(...); await sleep(0.1)`.
- Call `task_status.started()` immediately after the listener is successfully created and before `serve()`.

Exact `start()` behavior when readiness is never signaled:

- If the child raises before calling `started()`, `await tg.start(...)` raises that original exception.
- If the child exits normally without calling `started()`, `await tg.start(...)` raises:
  - `RuntimeError("Child exited without calling task_status.started()")`
- If the child keeps running forever and never calls `started()`, `await tg.start(...)` waits forever. There is no automatic timeout.
- If the waiting parent gets cancelled while blocked in `start()`, AnyIO cancels the child task and re-raises the cancellation.

So your buggy path is not just “a bit flaky”:
- with `sleep(0.1)`, connection races the bind and CI flakes;
- with `start()` but missing `started()`, you either get that exact `RuntimeError` on child exit or a hang if the child never exits.

Natural next steps:
1. Replace every `start_soon(...); sleep(...)` listener startup with `await tg.start(...)`
2. Add a test that proves the broken path raises `RuntimeError("Child exited without calling task_status.started()")`
