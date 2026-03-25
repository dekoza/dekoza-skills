The right direction is not “make everything portable.” That’s how libraries lie. The right direction is:

- make your core concurrency model AnyIO-native
- isolate backend-specific integrations behind explicit seams
- mark the asyncio-only vendor path as asyncio-only unless you truly move it out of the core runtime

**Steelmanned thesis**

You want one honest async API that works on both asyncio and Trio for the parts that can be portable, while refusing to pretend that an asyncio-native SDK with its own task model is somehow Trio-compatible.

**Redesign Direction**

- Replace ad-hoc task spawning with structured concurrency:
  - `asyncio.create_task(...)` -> `anyio.create_task_group()` + `tg.start_soon(...)`
  - if startup readiness matters, use `await tg.start(...)`
- Replace `asyncio.Queue()` with AnyIO memory object streams:
  - `send_stream, receive_stream = anyio.create_memory_object_stream[T](max_buffer_size)`
  - this is better than `Queue` for multi-producer / multi-consumer shutdown semantics
- Replace `asyncio.wait_for(...)` with cancel scopes:
  - `with anyio.fail_after(seconds): ...`
  - or `with anyio.move_on_after(seconds): ...` if timeout is not exceptional
- Push timeout policy outward:
  - reusable library methods usually should not hardcode `timeout=...` on every internal call
  - let callers wrap larger operations in `fail_after()` unless there is a true internal protocol deadline
- Treat cancellation as Trio/AnyIO-style, not asyncio-style:
  - catch `anyio.get_cancelled_exc_class()` only for cleanup
  - always re-raise
  - use `CancelScope(shield=True)` or `move_on_after(..., shield=True)` only for bounded cleanup

**What This Looks Like**

```python
import anyio
from anyio.abc import TaskStatus

class WorkerPool:
    def __init__(self, buffer_size: int = 100) -> None:
        self._send, self._receive = anyio.create_memory_object_stream[str](buffer_size)

    async def submit(self, item: str) -> None:
        await self._send.send(item)

    async def run(
        self,
        *,
        workers: int,
        task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        async with self._send, self._receive:
            async with anyio.create_task_group() as tg:
                for index in range(workers):
                    tg.start_soon(self._worker, self._receive.clone(), index)
                task_status.started()
                await anyio.sleep_forever()

    async def _worker(self, receive: anyio.abc.ObjectReceiveStream[str], index: int) -> None:
        async with receive:
            async for item in receive:
                with anyio.fail_after(5):
                    await self._handle(item, index)

    async def _handle(self, item: str, index: int) -> None:
        ...
```

That is the portable core shape: task group, object stream, cancel scopes.

**Where Native Backend Details Still Matter**

- `asyncio` task handles are not portable
  - if your API returns `asyncio.Task`, it is already asyncio-only
  - return your own handle abstraction, or better, keep task lifetime inside a context manager / service object
- direct event loop access is not portable
  - no `asyncio.get_running_loop()`, `loop.call_soon`, `Future`, `Event`, `Lock`, `Condition`, etc. in the core
- cancellation semantics still bite
  - AnyIO uses Trio-style level cancellation
  - asyncio-native code that swallows `CancelledError` or assumes one-shot cancellation can misbehave even on the asyncio backend when run under AnyIO task groups
- queue semantics differ
  - `asyncio.Queue` shutdown patterns do not map cleanly
  - memory object streams close cleanly and support async iteration; design around stream closure, not sentinel hacks
- startup coordination differs
  - if a child task must be “ready” before the caller proceeds, use `TaskGroup.start()`
  - `create_task()` plus polling flags is sloppy and race-prone
- low-level socket/transport/protocol APIs remain backend-shaped
  - stay at AnyIO stream/socket abstractions in the core
  - anything relying on asyncio transport/protocol internals is not portable

**The Vendor SDK Problem**

This is the hard stop.

If the vendor SDK is asyncio-native and spawns its own asyncio tasks, then it is not Trio-compatible just because your outer API uses AnyIO. That integration is backend-specific.

Your honest options are:

1. Keep that feature asyncio-only
   - document it clearly
   - fail fast under Trio with a precise error
2. Isolate it behind a separate boundary
   - dedicated thread/process/service running asyncio
   - communicate with your portable core over streams/messages/RPC
3. Replace the SDK
   - if true Trio portability is a product requirement, this is often the only clean answer

What you should not do:

- claim “supports Trio” while a code path still awaits an asyncio-only SDK
- bury backend detection deep in business logic
- mix `asyncio.create_task()` inside an AnyIO/Trio-facing core and hope for the best

**Recommended Architecture**

- `core/`
  - AnyIO only
  - task groups, memory object streams, cancel scopes, AnyIO locks/events/semaphores
- `adapters/portable/`
  - AnyIO-compatible transports and services
- `adapters/asyncio_vendor/`
  - explicit asyncio-only adapter for the vendor SDK
- `api/`
  - backend-neutral entrypoints
  - feature gating / capability checks
- `tests/`
  - run core tests under both `asyncio` and `trio`
  - run vendor adapter tests under `asyncio` only

**A Clean Honesty Pattern**

```python
import sniffio

class UnsupportedBackendError(RuntimeError):
    pass

async def use_vendor_feature(...) -> ...:
    backend = sniffio.current_async_library()
    if backend != "asyncio":
        raise UnsupportedBackendError(
            "This feature requires the asyncio backend because the vendor SDK is asyncio-native."
        )

    return await _asyncio_vendor_adapter(...)
```

That is honest portability: the library is cross-backend where the implementation is cross-backend, and explicitly backend-bound where it is not.

**Highest-Risk Issue**

The vendor SDK is the real constraint, not your `create_task` / `Queue` / `wait_for` usage. Rewriting your code to AnyIO while leaving that SDK in the core just gives you a nicer-shaped lie.

**Next Steps**

1. Convert your internal concurrency primitives to AnyIO: task groups, memory object streams, cancel scopes.
2. Move the vendor SDK behind an adapter boundary and mark it `asyncio`-only first.
3. Run the core test suite under both AnyIO backends and keep adapter tests backend-specific.

If you want, I can sketch a concrete before/after migration plan for one of your current `create_task` + `Queue` flows.
