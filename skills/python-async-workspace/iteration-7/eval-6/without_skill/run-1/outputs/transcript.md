# Execution Transcript

## Eval Prompt

I need a synchronous wrapper around an async client for legacy code. Right now it calls `asyncio.run()` inside methods, sometimes from AnyIO worker threads, sometimes from foreign threads, and sometimes while an app framework already has a running loop. One worker-thread callback only needs to set an AnyIO `Event`, and another long-running sync function should stop promptly when the host task is cancelled. Show the correct AnyIO-first boundary and explain when `BlockingPortal` is the right tool.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:court-jester
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

`asyncio.run()` inside wrapper methods is the wrong design. It only works when that method happens to be the top-level entry point for a fresh thread with no running loop. In your cases it is actively broken: it explodes in a framework loop thread, creates detached runtimes in worker/foreign threads, and ignores AnyIO’s cancellation/thread bridge.

The correct boundary is: async owns the real implementation; sync crosses that boundary with AnyIO’s thread APIs.

```python
from anyio import Event, to_thread
from anyio.from_thread import BlockingPortal, run_sync, check_cancelled
from anyio.lowlevel import current_token
from threading import Thread


class AsyncClient:
    async def fetch(self, key: str) -> str:
        ...

    async def aclose(self) -> None:
        ...


class SyncClient:
    def __init__(self, async_client: AsyncClient, portal: BlockingPortal) -> None:
        self._async_client = async_client
        self._portal = portal

    def fetch(self, key: str) -> str:
        return self._portal.call(self._async_client.fetch, key)

    def close(self) -> None:
        self._portal.call(self._async_client.aclose)


def worker_sets_event(event: Event) -> None:
    # Called from an AnyIO worker thread created by to_thread.run_sync()
    run_sync(event.set)


def long_running_sync() -> None:
    while True:
        check_cancelled()  # cooperatively stop when the host task is cancelled
        do_one_blocking_step()


def foreign_thread_sets_event(event: Event, token) -> None:
    # Called from a plain threading.Thread, not an AnyIO worker thread
    run_sync(event.set, token=token)


async def app(async_client: AsyncClient) -> None:
    event = Event()

    async with BlockingPortal() as portal:
        sync_client = SyncClient(async_client, portal)

        await to_thread.run_sync(worker_sets_event, event)
        await to_thread.run_sync(long_running_sync)

        thread = Thread(
            target=foreign_thread_sets_event,
            args=(event, current_token()),
        )
        thread.start()
        await event.wait()

        await to_thread.run_sync(run_legacy_code, sync_client)
```

The rule set is simple:

- `anyio.run(...)` or `asyncio.run(...)`: only at the true top-level entry point, never in per-method wrappers.
- `await to_thread.run_sync(sync_fn, ...)`: async -> blocking sync work.
- `from_thread.run(...)` / `from_thread.run_sync(...)`: AnyIO worker thread -> event loop.
- `token=current_token()`: foreign thread -> one-off call back into the existing loop.
- `BlockingPortal`: foreign/sync side needs a durable bridge, not a one-off hop.

For your two special cases:

- Worker-thread callback only setting an `Event`:
  - use `from_thread.run_sync(event.set)`
  - not `asyncio.run()`
  - not a portal unless you already need one for other reasons

- Long-running sync function that should stop promptly:
  - run it with `await to_thread.run_sync(...)`
  - call `from_thread.check_cancelled()` inside its loop
  - do not rely on `abandon_on_cancel=True` for this; that abandons the thread instead of stopping it cleanly

When `BlockingPortal` is actually the right tool:

- A sync API must call async code repeatedly from sync code
- Calls may come from non-AnyIO threads
- You need more than one-shot calls:
  - spawning tasks
  - wrapping async context managers
  - reusing one bridge across many sync calls

When it is not the right tool:

- One worker-thread callback just needs `event.set()`
- A foreign thread only needs an occasional one-off callback; a loop token is simpler
- You are trying to paper over bad wrapper design instead of defining one clear async/sync boundary

Practical decision tree:

1. Pure sync program entering async once -> `anyio.run(main)`
2. Async app calling blocking sync code -> `to_thread.run_sync`
3. AnyIO worker thread calling back into loop once -> `from_thread.run` / `run_sync`
4. Foreign thread calling back once -> `current_token()` + `from_thread.run` / `run_sync`
5. Sync side needs a long-lived bridge into async -> `BlockingPortal`

If you want, I can turn this into a production-ready `SyncClient` pattern with lifecycle management for either:
1. “portal inside an existing async app”, or
2. “self-owned shared portal for a pure sync facade.”
