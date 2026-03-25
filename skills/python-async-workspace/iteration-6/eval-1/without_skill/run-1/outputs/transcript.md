# Execution Transcript

## Eval Prompt

I maintain a Python library that currently uses `asyncio.create_task()`, `asyncio.Queue()`, and `asyncio.wait_for()` directly. One part of the library also calls an asyncio-native vendor SDK that spawns its own tasks. I want the core API to run on both asyncio and Trio without lying about portability. Show the right redesign direction under AnyIO and call out the places where native backend details still matter.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:court-jester
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

The honest redesign direction is: make the core library AnyIO-native, and quarantine asyncio-native code behind an explicit adapter boundary. Anything else is fake portability.

- `asyncio.create_task()` -> `anyio.create_task_group()` with `tg.start_soon()` / `tg.start()`
- `asyncio.Queue()` -> `anyio.create_memory_object_stream()` or other AnyIO sync primitives
- `asyncio.wait_for()` -> `anyio.fail_after()` / `anyio.move_on_after()`

The deeper change is not just API swaps. It is moving from unstructured asyncio habits to structured concurrency.

**What to redesign**

- Make long-lived background activity live inside an owned service object:
  - `await service.start()`
  - `await service.request(...)`
  - `await service.aclose()`
- Internally, keep one task group per service/component instead of scattering detached tasks.
- Do not return raw task objects from public APIs. That bakes in asyncio semantics immediately.
- Model producer/consumer work with streams, not hidden queues plus orphan tasks.
- Put timeout policy at call boundaries with cancel scopes, not ad hoc `wait_for()` around random awaits.

A sane shape looks like this:

```python
import anyio

class Client:
    def __init__(self) -> None:
        self._send = None
        self._tg = None

    async def __aenter__(self) -> "Client":
        self._send, receive = anyio.create_memory_object_stream(100)
        self._exit_stack = anyio.create_task_group()
        self._tg = await self._exit_stack.__aenter__()
        self._tg.start_soon(self._worker, receive)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._send.aclose()
        await self._exit_stack.__aexit__(exc_type, exc, tb)

    async def submit(self, item: object) -> None:
        await self._send.send(item)

    async def _worker(self, receive) -> None:
        async with receive:
            async for item in receive:
                with anyio.fail_after(5):
                    await self._process(item)

    async def _process(self, item: object) -> None:
        ...
```

That design works on asyncio and Trio because the core primitives are AnyIO-owned.

**Where your current assumptions break**

- `create_task()` assumes detached task handles are normal; Trio/AnyIO wants tasks scoped to a parent.
- `Queue()` encourages hidden infinite lifetimes and vague shutdown; memory object streams have explicit close semantics.
- `wait_for()` assumes asyncio cancellation behavior; AnyIO uses cancel scopes with Trio-style semantics.

The cancellation point matters a lot. This is the trap most ports miss.

- Asyncio uses edge cancellation: one `CancelledError`, and code can suppress it.
- AnyIO task groups/cancel scopes use level cancellation: if code stays in a cancelled scope, cancellation keeps hitting at yield points.

So code that "kind of works" under asyncio by swallowing cancellation can become broken or spin badly under Trio-style semantics. If your code catches cancellation, it must clean up and re-raise.

**The vendor asyncio SDK is the real portability boundary**

This is the part you should not lie about.

If the vendor SDK is asyncio-native and spawns its own asyncio tasks:

- it is not Trio-native
- it cannot be claimed as backend-portable
- even on AnyIO+asyncio, its internally spawned tasks are still native asyncio tasks with asyncio semantics

AnyIO’s own docs are explicit: native libraries only work on their own backend, and native tasks are not governed by AnyIO’s cancellation rules the same way.

So your support matrix should probably be:

- core library: asyncio + Trio
- vendor integration: asyncio only

That is the honest version.

**If you must expose the vendor feature on Trio**

You have only two real options, both with costs:

1. Keep it asyncio-only
- Best design honesty
- Cleanest docs and failure modes

2. Isolate it behind a bridge
- Run the vendor SDK inside a dedicated asyncio thread/process
- Talk to it through message passing
- Accept weaker cancellation, more serialization, more shutdown complexity, and different error behavior

That bridge is not "native Trio support". It is an interoperability shim.

**Good boundary design**

Split your package into layers:

- `core/`
  - AnyIO-native orchestration
  - streams, task groups, cancel scopes
  - no `asyncio` imports
- `adapters/asyncio_vendor.py`
  - wraps the vendor SDK
  - marked asyncio-only
- `interfaces.py`
  - protocol/ABC used by core

For example:

```python
from typing import Protocol

class VendorTransport(Protocol):
    async def send(self, payload: bytes) -> bytes: ...
    async def aclose(self) -> None: ...
```

Then provide:

- `AnyIOCoreClient(transport: VendorTransport)`
- `AsyncioVendorTransport(...)` for the vendor SDK

On Trio, either:
- no vendor transport, raise a clear configuration error, or
- provide `ThreadedAsyncioVendorTransport(...)` and document the degraded semantics

**Native backend details that still matter**

Even after an AnyIO redesign, these are still backend-sensitive:

- `cancelled` behavior  
  Trio-style level cancellation is stricter than asyncio’s edge cancellation.
- third-party task spawning  
  Native asyncio tasks created by vendor code are outside your structured task tree.
- task identity / loop APIs  
  Anything using `get_running_loop()`, `current_task()`, loop callbacks, or task handles is backend-specific.
- synchronization semantics  
  Replacing a queue with a stream changes shutdown and backpressure behavior; that is usually good, but it is a semantic change.
- thread handoff  
  Crossing into threads or back from threads is backend/tooling-sensitive and should stay at the edges.
- testing  
  You need backend-parametrized tests, because "works on AnyIO" without running both backends is wishful thinking.

**Practical migration rule**

- Replace raw asyncio primitives in core code first.
- Refuse backend-specific imports in core modules.
- Move vendor SDK use into one adapter file.
- Document the support matrix explicitly.
- Run the same contract tests on both `asyncio` and `trio`.
- Add separate adapter tests for the vendor path on asyncio only.

**Highest-risk false assumption**

The bad assumption is: "If I swap `asyncio.*` for `anyio.*`, the whole library becomes portable."

No. Your vendor SDK and your cancellation assumptions can still pin you to asyncio.

If you want, I can turn this into a concrete migration checklist or show a before/after refactor for a `create_task` + `Queue` worker pattern.
