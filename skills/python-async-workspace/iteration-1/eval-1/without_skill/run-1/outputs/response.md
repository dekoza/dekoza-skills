`AnyIO-portable`

The right redesign is to stop exposing raw `asyncio` primitives from your core library and move the core concurrency model to AnyIO's structured APIs.

- Replace owned background work built with `asyncio.create_task()` with `anyio.create_task_group()` and `tg.start_soon()`; use `tg.start()` when the caller must wait for child readiness.
- Replace new queue-style producer/consumer flows built on `asyncio.Queue()` with `anyio.create_memory_object_stream()`; it gives explicit send/receive ends, natural close semantics, async iteration, and safer multi-producer shutdown behavior.
- Replace `asyncio.wait_for()` with `anyio.fail_after()` when timeout is an error, or `anyio.move_on_after()` when timeout is a normal control-flow branch; use shielded cancel scopes for bounded cleanup.

Minimal redesign direction:

```python
from collections.abc import AsyncIterator

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream


class WorkerPool:
    def __init__(self, buffer_size: int = 0) -> None:
        self._buffer_size = buffer_size

    async def run(self, items: AsyncIterator[str]) -> list[str]:
        send, receive = anyio.create_memory_object_stream[str](self._buffer_size)
        results: list[str] = []

        async def producer() -> None:
            async with send:
                async for item in items:
                    await send.send(item)

        async def consumer(stream: MemoryObjectReceiveStream[str]) -> None:
            async with stream:
                async for item in stream:
                    with anyio.fail_after(5):
                        results.append(await self._handle(item))

        async with anyio.create_task_group() as tg:
            tg.start_soon(producer)
            tg.start_soon(consumer, receive)

        return results

    async def _handle(self, item: str) -> str:
        return item.upper()
```

What should stay portable in the library core:

- Task ownership, cancellation, deadlines, and in-process message passing.
- Network/file/thread subprocess work when you stay on AnyIO APIs.
- Test surface and fixtures by running the same async tests under both backends.

Where native backend details still matter:

- Cancellation semantics are not identical under the hood. AnyIO gives Trio-style cancel scopes, but raw asyncio code you still call may behave with asyncio's edge-cancellation quirks. Portability fails if your design depends on those quirks.
- Backend-native objects are still backend-native: `asyncio.Task`, `asyncio.Future`, event-loop handles, and Trio-specific low-level primitives should not leak into your public API.
- Integration boundaries remain specific: asyncio-only dependencies, loop policies, uvloop tuning, task introspection, and direct loop APIs are not portable just because the surrounding code uses AnyIO.
- Timeout and cleanup behavior should be designed around cancel scopes, not around exact asyncio exception timing.
- Signal handling, debugging hooks, and low-level scheduling/instrumentation can still differ by backend and may need backend-specific adapters.

Practical migration rule:

- Keep the core library `AnyIO-portable`.
- Push backend-specific code to thin adapters at startup/integration boundaries.
- Refuse to promise portability for APIs that accept or return native asyncio objects.

Verification step:

- Run the async test suite on both backends with the AnyIO pytest plugin, at minimum once with `anyio_backend = "asyncio"` and once with `anyio_backend = "trio"`.

References used:

- AnyIO docs: `Creating and managing tasks`
- AnyIO docs: `Streams`
- AnyIO docs: `Cancellation and timeouts`
- AnyIO docs: `Testing with AnyIO`
- AnyIO docs: `Why you should be using AnyIO APIs instead of asyncio APIs`
