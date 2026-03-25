# Execution Transcript

## Eval Prompt

I need a synchronous wrapper around an async client for legacy code. Right now it calls `asyncio.run()` inside methods, sometimes from AnyIO worker threads, sometimes from foreign threads, and sometimes while an app framework already has a running loop. One worker-thread callback only needs to set an AnyIO `Event`, and another long-running sync function should stop promptly when the host task is cancelled. Show the correct AnyIO-first boundary and explain when `BlockingPortal` is the right tool.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

Use an AnyIO-owned boundary once, not `asyncio.run()` per method. The current design is wrong because `asyncio.run()` cannot be nested under an already-running loop, and even where it “works” it creates a fresh runner per call and hides ownership.

- Mode: `AnyIO-portable`
- Sources used: `python-async` references `threads-boundaries.md`, `cancellation-timeouts.md`, `decision-matrix.md`; AnyIO thread docs; Python `asyncio.run()` docs
- Main footgun: calling a sync wrapper from the event-loop thread itself is still broken; fail fast there or use the async API directly

**Correct Boundary**

Expose two APIs:
- async code uses the real async client directly
- legacy sync code uses one shared `BlockingPortal`, not `asyncio.run()`

```python
from __future__ import annotations

from anyio.from_thread import BlockingPortalProvider

class SyncClient:
    def __init__(self, async_client) -> None:
        self._async_client = async_client
        self._portal_provider = BlockingPortalProvider()

    def fetch_user(self, user_id: str):
        with self._portal_provider as portal:
            return portal.call(self._async_client.fetch_user, user_id)

    def close(self) -> None:
        with self._portal_provider as portal:
            portal.call(self._async_client.aclose)
```

Why this is the right boundary:
- repeated sync calls reuse one portal instead of spinning up a runner each time
- calls can come from ordinary sync threads safely
- the async side stays owned by AnyIO, not by ad hoc nested runners

**Worker Thread Callback That Only Sets An Event**

Do not open a portal for this. If the thread came from `anyio.to_thread.run_sync()`, use `from_thread.run_sync()`:

```python
import time

from anyio import Event, from_thread, to_thread

def worker(event: Event) -> None:
    time.sleep(0.1)
    from_thread.run_sync(event.set)

async def do_work() -> None:
    event = Event()
    await to_thread.run_sync(worker, event)
    await event.wait()
```

That is the direct AnyIO-first path for “set an `Event` from a worker thread”.

If it is a foreign thread, use a token for a one-off callback:

```python
from threading import Thread

from anyio import Event, from_thread
from anyio.lowlevel import current_token

def foreign_callback(event: Event, token) -> None:
    from_thread.run_sync(event.set, token=token)

async def main() -> None:
    event = Event()
    thread = Thread(target=foreign_callback, args=(event, current_token()))
    thread.start()
    await event.wait()
    thread.join()
```

**Long-Running Sync Function That Must Stop On Host Cancellation**

`to_thread.run_sync()` does not magically kill threads. By default, waiting on it is cancellation-shielded. If you need prompt stop, the sync code must poll `from_thread.check_cancelled()`.

```python
import time

from anyio import from_thread, to_thread

def blocking_job() -> None:
    while True:
        from_thread.check_cancelled()
        do_one_small_chunk()
        time.sleep(0.05)

async def run_blocking_job() -> None:
    await to_thread.run_sync(blocking_job, abandon_on_cancel=True)
```

Important distinction:
- `abandon_on_cancel=True` lets the async caller stop waiting
- it does not stop the thread by itself
- prompt stop requires `from_thread.check_cancelled()` inside the blocking function

If the sync job never polls, it can keep running forever in the background. That is the bug.

**When `BlockingPortal` Is The Right Tool**

Use `BlockingPortal` when sync code needs structured, repeated access to async internals:
- sync facade over an async client
- many sync calls over time, possibly from multiple threads
- wrapping async context managers
- spawning async tasks from sync code

Do not use it for:
- one-off calls from an AnyIO worker thread; use `from_thread.run()` / `from_thread.run_sync()`
- papering over a bad boundary where sync code is running on the event-loop thread itself

**Practical Rule Set**

- `async` caller already in app/framework loop -> call async client directly
- AnyIO worker thread -> `from_thread.run()` / `from_thread.run_sync()`
- foreign thread, one-off hop -> `current_token()` + `from_thread.run()` / `run_sync()`
- foreign/sync code with repeated async calls -> shared `BlockingPortal` / `BlockingPortalProvider`
- never put `asyncio.run()` inside library methods

**Verification**

Test these cases explicitly on both AnyIO backends if you claim portability:
1. sync facade from a plain thread
2. one-off callback from `to_thread.run_sync()`
3. one-off callback from a foreign thread using `current_token()`
4. cancellation of the long-running sync function, proving it exits promptly

If you want, I can turn this into a minimal production-ready wrapper class plus pytest examples.
