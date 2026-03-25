# Execution Transcript

## Eval Prompt

I need a synchronous wrapper around an async client for legacy code. Right now it calls `asyncio.run()` inside methods, sometimes from AnyIO worker threads, sometimes from foreign threads, and sometimes while an app framework already has a running loop. One worker-thread callback only needs to set an AnyIO `Event`, and another long-running sync function should stop promptly when the host task is cancelled. Show the correct AnyIO-first boundary and explain when `BlockingPortal` is the right tool.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

`asyncio.run()` inside library methods is the wrong boundary. It only works at a top-level sync entry point in a thread with no running loop. In your cases it is brittle by construction:

- AnyIO worker thread: use `anyio.from_thread.*`, not `asyncio.run()`
- foreign thread: use an AnyIO token or a `BlockingPortal`
- current thread already has a running loop: do not call the sync wrapper there; use the async client directly

A sane AnyIO-first shape looks like this:

```python
from __future__ import annotations

import time
from typing import Any

import anyio
from anyio import from_thread, to_thread
from anyio.from_thread import BlockingPortalProvider


class AsyncClient:
    async def fetch(self, value: str) -> str:
        await anyio.sleep(0.1)
        return value.upper()


class SyncClient:
    def __init__(self, async_client: AsyncClient) -> None:
        self._async_client = async_client
        self._portal_provider = BlockingPortalProvider()

    def fetch(self, value: str) -> str:
        # Safe for normal sync callers, including foreign threads.
        # Not for calling from the event-loop thread in async code.
        with self._portal_provider as portal:
            return portal.call(self._async_client.fetch, value)
```

Use these boundaries instead:

- Async code calls `await async_client.fetch(...)`
- Sync code calls `sync_client.fetch(...)`
- Async code that must invoke blocking legacy sync code uses `await to_thread.run_sync(...)`

For your two thread callbacks:

```python
def worker_callback_set_event(event: anyio.Event) -> None:
    # This is correct from an AnyIO worker thread.
    from_thread.run_sync(event.set)


def long_running_sync_work() -> None:
    while True:
        from_thread.check_cancelled()  # cooperative cancellation
        do_one_chunk_of_blocking_work()
        time.sleep(0.05)
```

And from async code:

```python
async def run_blocking_legacy_code() -> None:
    await to_thread.run_sync(long_running_sync_work)
```

Important cancellation detail:

- `from_thread.check_cancelled()` is how a worker-thread function stops promptly when the host task is cancelled
- `abandon_on_cancel=True` is different: it lets the async side stop waiting, but the thread keeps running unchecked
- so for “stop promptly”, use `check_cancelled()` inside the sync loop; do not rely on `abandon_on_cancel=True`

When `BlockingPortal` is the right tool:

- You are in a foreign thread, not an AnyIO worker thread
- You need repeated sync->async calls, not a one-off callback
- You need to spawn async tasks from sync code
- You need to use async context managers from sync code

When it is not the right tool:

- A one-off signal into the loop from a worker thread; use `from_thread.run()` / `from_thread.run_sync()`
- Async code already running on the loop thread; just `await`
- A sync wrapper being called from inside async code on the loop thread; that blocks the loop and is a design bug even if a portal can technically bridge it

For foreign threads, the lighter one-off option is an event loop token:

```python
from threading import Thread

from anyio import Event, from_thread
from anyio.lowlevel import current_token


def foreign_thread_callback(event: Event, token) -> None:
    from_thread.run_sync(event.set, token=token)


async def main() -> None:
    event = Event()
    token = current_token()
    Thread(target=foreign_thread_callback, args=(event, token)).start()
    await event.wait()
```

The rule of thumb is simple:

- worker thread created by AnyIO -> `from_thread.*`
- foreign thread, one-shot -> `token + from_thread.*`
- foreign thread, repeated/richer interaction -> `BlockingPortal`
- already async -> stay async, do not route through a sync wrapper

If you want, I can turn this into a small production-ready wrapper class with shutdown handling and error translation.
