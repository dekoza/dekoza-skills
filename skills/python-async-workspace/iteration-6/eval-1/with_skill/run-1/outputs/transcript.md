# Execution Transcript

## Eval Prompt

I maintain a Python library that currently uses `asyncio.create_task()`, `asyncio.Queue()`, and `asyncio.wait_for()` directly. One part of the library also calls an asyncio-native vendor SDK that spawns its own tasks. I want the core API to run on both asyncio and Trio without lying about portability. Show the right redesign direction under AnyIO and call out the places where native backend details still matter.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Tool use: skill:court-jester
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: read
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

This should become an `AnyIO-portable` core with explicit backend-specific edges, not a fake "works everywhere" wrapper.

- Hard truth: the part that calls an asyncio-native vendor SDK is not Trio-portable just because the rest uses AnyIO. If that SDK spawns its own `asyncio` tasks, that path is asyncio-only unless you build a separate Trio implementation.
- The right split is: portable core logic in AnyIO, backend adapters at the edge, and capability flags or clear runtime errors for features that only exist on `asyncio`.

A sane redesign looks like this:

```python
import anyio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

JobHandler = Callable[[bytes], Awaitable[None]]

@dataclass
class BackendCapabilities:
    vendor_streaming: bool

class CoreClient:
    def __init__(self, vendor_adapter: "VendorAdapter | None") -> None:
        self._vendor = vendor_adapter

    async def run_worker(self, handler: JobHandler) -> None:
        send, receive = anyio.create_memory_object_stream[bytes](100)

        async with send, receive, anyio.create_task_group() as tg:
            tg.start_soon(self._produce_jobs, send)
            tg.start_soon(self._consume_jobs, receive, handler)

    async def _produce_jobs(self, send: anyio.abc.ObjectSendStream[bytes]) -> None:
        ...

    async def _consume_jobs(
        self,
        receive: anyio.abc.ObjectReceiveStream[bytes],
        handler: JobHandler,
    ) -> None:
        async for item in receive:
            await handler(item)
```

What to replace:

- `asyncio.create_task()` -> `anyio.create_task_group()`
  - This is the main redesign, not a cosmetic swap.
  - Stop spawning orphan tasks from library code.
  - The caller or enclosing service should own task lifetime through a task group.
- `asyncio.Queue()` -> `anyio.create_memory_object_stream()`
  - This gives explicit send/receive ends, better shutdown semantics, and deliberate backpressure.
  - Pick a bounded buffer on purpose; unbounded buffering is a design bug disguised as convenience.
- `asyncio.wait_for()` -> `anyio.fail_after()` or `anyio.move_on_after()`
  - Use `fail_after()` when timeout is part of the contract.
  - Use `move_on_after()` when timeout means "stop trying and continue."
  - In reusable libraries, timeout policy usually belongs to the caller.

**Redesign direction**

- **Portable core**
  - Put retries, fan-out/fan-in, coordination, pooling, and cancellation rules in AnyIO-only code.
  - Accept abstract callables or adapter objects instead of hard-coding backend-native clients into the core.
- **Explicit integration boundary**
  - Define a `VendorAdapter` protocol or interface.
  - Provide `AsyncioVendorAdapter` now.
  - Add `TrioVendorAdapter` only if the vendor ships one or you can implement one honestly.
- **Feature gating**
  - Expose capabilities like `supports_vendor_push` or fail fast with a precise error on Trio for asyncio-only features.
  - Do not silently degrade into half-working behavior.

Example timeout and cancellation style:

```python
import anyio

async def fetch_with_timeout(adapter: "VendorAdapter", key: str) -> bytes:
    try:
        with anyio.fail_after(5):
            return await adapter.fetch(key)
    except anyio.get_cancelled_exc_class():
        # cleanup if needed
        raise
```

Where native backend details still matter:

- **Asyncio-native vendor SDK**
  - This is the big one. AnyIO does not make an asyncio SDK Trio-compatible.
  - If the SDK creates its own tasks, those tasks are outside your structured-concurrency model unless the SDK itself gives lifecycle hooks.
- **Cancellation semantics**
  - Trio/AnyIO use level cancellation; asyncio uses edge cancellation.
  - Code written with asyncio assumptions can misbehave under Trio-style cancellation if it swallows cancellation or retries badly.
- **Task ownership**
  - Your AnyIO task group cannot magically supervise tasks the vendor SDK spawns internally.
  - Shutdown, error propagation, and cleanup may stay vendor-defined on that path.
- **Readiness handshakes**
  - AnyIO gives you `TaskGroup.start()`; raw asyncio has no equivalent built into `TaskGroup`.
  - If startup ordering matters, keep that logic in your AnyIO layer, not in ad-hoc vendor callbacks.
- **Testing claims**
  - "Portable" means tests pass on both asyncio and Trio.
  - The vendor-backed feature should be tested only on asyncio unless you have a real Trio adapter.

The strongest design is usually this synthesis:

- Keep one public API.
- Make the core implementation AnyIO-native.
- Treat vendor-specific functionality as pluggable adapters.
- Mark asyncio-only features as asyncio-only.

The weak design is pretending you can wrap an asyncio SDK in AnyIO and call the whole library Trio-compatible. That is false portability.

Highest-risk issue: the vendor SDK spawning its own tasks. That is where lifecycle control, cancellation, and shutdown correctness escape your abstraction.

Minimum verification:

- Run your library test suite on both AnyIO backends: `asyncio` and Trio.
- Run adapter-specific tests separately.
- Document a backend support matrix in the README.

References used: `decision-matrix.md`, `structured-concurrency.md`, `cancellation-timeouts.md`, `streams-synchronization.md`, `dialectic-synthesis.md`.

If you want, I can turn this into a concrete migration plan from your current `create_task`/`Queue`/`wait_for` usage, including adapter interfaces and test matrix layout.
