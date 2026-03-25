# Execution Transcript

## Eval Prompt

I start a TCP listener in an AnyIO task group and then sleep for 0.1 seconds before connecting, because that usually gives it time to bind. Sometimes CI flakes. One code path even forgets to call `task_status.started()` after binding. Show the correct readiness pattern and tell me the exact failure behavior that `start()` gives me when the child never signals readiness.

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

Use `TaskGroup.start()` plus `task_status.started()` right after the listener is successfully bound, not `sleep(0.1)`.

```python
from anyio import TASK_STATUS_IGNORED, create_task_group, create_tcp_listener, connect_tcp
from anyio.abc import TaskStatus


async def serve_tcp(
    port: int,
    *,
    task_status: TaskStatus[None] = TASK_STATUS_IGNORED,
) -> None:
    async with await create_tcp_listener(local_host="127.0.0.1", local_port=port) as listener:
        task_status.started()  # readiness signal: bind succeeded
        await listener.serve(handler)


async def main() -> None:
    async with create_task_group() as tg:
        await tg.start(serve_tcp, 5000)
        async with await connect_tcp("127.0.0.1", 5000) as stream:
            ...
```

What this buys you:

- If bind/startup fails before readiness, `await tg.start(...)` raises that real exception.
- If startup succeeds, `await tg.start(...)` returns only after the child explicitly signals readiness.
- No timing hack, no CI flake from racing the bind.

The failure behavior is more precise than people usually say:

- If the child exits without ever calling `task_status.started()`, `start()` raises:
  - `RuntimeError("Child exited without calling task_status.started()")`
- If the child raises an exception before calling `started()`, `start()` raises that exception instead.
- If the child keeps running forever and never calls `started()`, `start()` does not fail fast; it just waits forever until cancelled.

So your “forgot `started()` after binding” bug has two possible outcomes:

- if that code path enters the long-running serve loop: caller hangs on `await tg.start(...)`
- if that code path returns/exits: caller gets the exact `RuntimeError` above

If you want, I can also show the same pattern for ephemeral port `0`, where the child passes the bound port back via `task_status.started(port)`.
