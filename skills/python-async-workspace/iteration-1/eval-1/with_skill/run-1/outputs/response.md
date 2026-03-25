Answer mode: `AnyIO-portable`

References used: `skills/python-async/references/decision-matrix.md`, `skills/python-async/references/structured-concurrency.md`, `skills/python-async/references/cancellation-timeouts.md`, `skills/python-async/references/streams-synchronization.md`, `skills/python-async/references/backend-asyncio.md`, `skills/python-async/references/backend-trio.md`, `skills/python-async/references/testing.md`

Do not do a fake portability pass where you keep the same `asyncio` shape and swap a few imports. If the core library API exposes `asyncio.Task`, `asyncio.Queue`, loop ownership, or assumes `wait_for()` semantics, it is still `asyncio`-native.

The redesign direction is:

1. Replace ad-hoc task spawning with structured concurrency.
   - Old shape: library code calls `asyncio.create_task()` and hopes someone else stops it.
   - New shape: the library either owns an `anyio.create_task_group()` inside an async context manager, or it exposes a `run()`/`serve()` coroutine that the caller starts inside their own task group.
   - If startup ordering matters, use `TaskGroup.start()` instead of sleeps or polling.

2. Replace `asyncio.Queue()` with AnyIO memory object streams.
   - Use `send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer)`.
   - Pick buffer size deliberately; `0` gives backpressure, bounded sizes make overload behavior explicit.
   - This is a better portable contract than a raw queue because close semantics and producer/consumer cloning are explicit.

3. Stop baking timeout policy into low-level operations unless it is truly part of the contract.
   - `asyncio.wait_for()` is not just a timeout helper; it cancels the awaited task and may outlive the nominal timeout while cancellation finishes.
   - In portable code, prefer caller-owned timeouts.
   - When the library must enforce one, use `anyio.fail_after()` for hard timeout or `anyio.move_on_after()` for soft timeout.

4. Keep the public API backend-neutral.
   - Return plain results, async iterators, or library-owned abstractions.
   - Do not return raw task handles, loop objects, or backend-native synchronization primitives.

Minimal redesign sketch:

```python
from collections.abc import AsyncIterator

import anyio


class Worker:
    def __init__(self, buffer_size: int = 100) -> None:
        self._send, self._receive = anyio.create_memory_object_stream[str](buffer_size)

    async def submit(self, item: str) -> None:
        await self._send.send(item)

    async def run(self, *, task_status=anyio.TASK_STATUS_IGNORED) -> None:
        task_status.started()
        async with self._receive:
            async for item in self._receive:
                await self._handle(item)

    async def aclose(self) -> None:
        await self._send.aclose()

    async def _handle(self, item: str) -> None:
        ...


async def serve(worker: Worker) -> None:
    async with anyio.create_task_group() as tg:
        await tg.start(worker.run)
        ...
```

Native backend details still matter here:

- `asyncio` and Trio do not cancel the same way.
  - AnyIO adopts Trio-style level cancellation, not raw `asyncio` edge cancellation.
  - Code that swallows cancellation, busy-waits, or assumes one-shot `CancelledError` delivery is brittle under Trio/AnyIO semantics.

- Timeout semantics are not identical.
  - `asyncio.wait_for()` behavior is not a drop-in mental model for `fail_after()`.
  - Cleanup that awaits must be shielded deliberately and re-raise cancellation after cleanup.

- Detached background work is still backend-sensitive.
  - Raw `asyncio.create_task()` keeps only weak references unless you hold one.
  - Trio has no equivalent "fire-and-forget and maybe it lives" model; nurseries own task lifetime on purpose.
  - So portable library code should avoid detached tasks as part of its core contract.

- Backend-native dependencies break the portability claim.
  - If part of the core path depends on an `asyncio`-only client, transport, or queue, your library is not really Trio-portable.
  - AnyIO can sit at the boundary, but it cannot make native `asyncio` semantics disappear.

- Runtime/bootstrap remains native.
  - Top-level runner choice is still backend-specific: `anyio.run(..., backend="asyncio")` vs `backend="trio"`.
  - `uvloop` is only an `asyncio` runtime option; it does nothing for Trio compatibility.

- Backend-specific tests are still mandatory.
  - If you claim portability, run the async test suite on both `asyncio` and Trio.
  - Add an `asyncio+uvloop` axis only if you explicitly support or recommend that runtime.

The highest-risk footgun is pretending that replacing `create_task`, `Queue`, and `wait_for` with vaguely similar AnyIO calls is enough. It is not. The real redesign is about ownership of child tasks, explicit backpressure, caller-visible timeout policy, and refusing to expose backend-native objects in the library contract.

Minimum verification step:

```python
@pytest.fixture(
    params=[
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param(("trio", {}), id="trio"),
    ]
)
def anyio_backend(request):
    return request.param
```

Then run the same behavioral tests on both backends, especially task startup, cancellation, timeout, and producer-consumer backpressure paths.
