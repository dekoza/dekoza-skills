The right move is not “replace `asyncio` imports with AnyIO and declare victory.” That would be false portability.

This is `AnyIO-portable` for the core, with an explicit `asyncio-only` boundary around the vendor SDK.

- `asyncio.create_task()` -> `anyio.create_task_group()`
- `asyncio.Queue()` -> `anyio.create_memory_object_stream()`
- `asyncio.wait_for()` -> `anyio.fail_after()` or `anyio.move_on_after()`
- asyncio-native vendor SDK -> isolate behind an adapter that is clearly not Trio-portable

A sane redesign looks like this:

```python
import anyio
from typing import Protocol

class BackendAdapter(Protocol):
    async def open(self) -> None: ...
    async def send(self, item: bytes) -> None: ...
    async def receive(self) -> bytes: ...
    async def close(self) -> None: ...

class Client:
    def __init__(self, adapter: BackendAdapter) -> None:
        self._adapter = adapter

    async def run(self) -> None:
        send_stream, recv_stream = anyio.create_memory_object_stream[bytes](100)

        async with anyio.create_task_group() as tg:
            await tg.start(self._run_reader, send_stream.clone())
            tg.start_soon(self._run_writer, recv_stream)

    async def _run_reader(self, task_status, stream) -> None:
        await self._adapter.open()
        task_status.started()
        async with stream:
            while True:
                item = await self._adapter.receive()
                await stream.send(item)

    async def _run_writer(self, stream) -> None:
        async with stream:
            async for item in stream:
                await self._adapter.send(item)
```

What changes in design:

- Use task groups so spawned work has an owner, shutdown path, and sibling-cancellation semantics.
- Use memory object streams so backpressure is part of the contract instead of an accidental queue detail.
- Make timeout policy explicit; reusable library code usually should let the caller own deadlines.
- Keep public types backend-neutral; no `asyncio.Task`, `Future`, `Queue`, loop objects, or vendor SDK handles leaking out.

Where native backend details still matter:

- The vendor SDK is the big lie detector. If it is asyncio-native and spawns its own tasks, that part is not Trio-portable.
- Even on the asyncio backend, SDK-spawned raw tasks are outside your AnyIO task tree unless the SDK gives you a real shutdown/join API.
- If the SDK exposes asyncio-only objects or assumes a running asyncio loop, quarantine that in an adapter and mark it `asyncio-only`.
- Under Trio, do one of two honest things:
  1. disable that adapter with a clear runtime error, or
  2. move the SDK behind a process/thread/service boundary and talk to it through a portable transport

Do not do this:

- call the asyncio SDK directly from code you market as backend-neutral
- expose raw asyncio primitives in your public API
- use fire-and-forget tasks in library code
- swallow cancellation and keep going

Timeout/cancellation mapping matters too:

- `wait_for()` is not a drop-in mental model; in AnyIO use `fail_after()` when timeout is an error, `move_on_after()` when timeout is just a stop condition
- Trio-style cancellation is stricter than asyncio; code that “sort of survives” asyncio cancellation often breaks under Trio
- cleanup that must await should be shielded briefly and then re-raise cancellation

The honest architecture is:

- portable core orchestration in AnyIO
- backend-specific adapters at the edges
- vendor-SDK features either `asyncio-only` or isolated out of process

Minimum test bar if you want to claim portability:

- run core tests on both `asyncio` and Trio
- run vendor-adapter tests on `asyncio` only
- add shutdown/cancellation tests, not just happy-path I/O
- if you mention `uvloop`, test it as an asyncio runtime option only

Highest-risk issue: the vendor SDK’s self-spawned tasks. If you cannot stop and await them deterministically, your shutdown story is brittle no matter how pretty the AnyIO refactor looks.

References used: `decision-matrix.md`, `structured-concurrency.md`, `cancellation-timeouts.md`, `streams-synchronization.md`, `testing.md`, `backend-asyncio.md`, `backend-trio.md`.

If you want, I can turn this into a concrete migration recipe for your library API surface, including an adapter interface and test matrix.
