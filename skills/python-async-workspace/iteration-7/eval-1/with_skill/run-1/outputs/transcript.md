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
- Tool use: read
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

The right redesign is to make your code portable, and make the vendor lock-in explicit instead of smearing `asyncio` across the whole library.

- Mode: `AnyIO-portable`
- References used: `decision-matrix.md`, `structured-concurrency.md`, `cancellation-timeouts.md`, `streams-synchronization.md`, `backend-asyncio.md`, `backend-trio.md`, `threads-boundaries.md`, `testing.md`

**Direction**

- Move all library-owned concurrency to AnyIO: task groups, streams, cancellation, thread offloading, tests.
- Isolate the asyncio-native vendor SDK behind a clearly labeled adapter like `integrations/vendor_asyncio.py`.
- Claim portability only for the core and for integrations that are actually backend-neutral.

A sane shape looks like this:

```python
import anyio
from collections.abc import AsyncIterator

class CoreClient:
    def __init__(self, transport):
        self._transport = transport

    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._transport.receive_loop)
            tg.start_soon(self._transport.send_loop)
```

**Replace the direct asyncio pieces**

- `asyncio.create_task()` -> `anyio.create_task_group()`
  - Better lifecycle, explicit ownership, sibling cancellation on failure.
  - If startup readiness matters, use `tg.start()` instead of sleeping and hoping.
- `asyncio.Queue()` -> `anyio.create_memory_object_stream()`
  - Pick a buffer size on purpose; unbounded buffering is cowardly design.
  - Streams also make shutdown clearer: closing send sides ends receive iteration.
- `asyncio.wait_for()` -> `anyio.fail_after()` or `anyio.move_on_after()`
  - Prefer caller-owned timeouts in reusable library code.
  - Use `fail_after()` when timeout is part of the contract; `move_on_after()` when timeout is just a local escape hatch.

Example:

```python
send_stream, recv_stream = anyio.create_memory_object_stream[Message](100)

async def producer() -> None:
    async with send_stream:
        await send_stream.send(Message(...))

async def consumer() -> None:
    async with recv_stream:
        async for message in recv_stream:
            await handle(message)

async def fetch_with_timeout() -> Response:
    with anyio.fail_after(5):
        return await do_fetch()
```

**Where native backend details still matter**

- Your asyncio-native vendor SDK is the big one.
  - If that SDK requires `asyncio` tasks, loop APIs, or spawns its own asyncio tasks, that integration is not Trio-portable.
  - AnyIO does not magically launder backend-native code into portable code.
- Cancellation semantics differ.
  - AnyIO/Trio use level-style cancellation; asyncio code often assumes one-shot cancellation.
  - Code written with asyncio instincts can misbehave under Trio-style semantics if it swallows cancellation or spins badly.
- Native tasks spawned by the vendor SDK are outside your structured-concurrency guarantees.
  - On non-Trio backends, AnyIO docs explicitly warn native-library-spawned tasks are not governed by AnyIO cancellation rules.
  - Translation: your task group exiting does not mean the vendor’s internal tasks are cleanly owned or stopped.
- Trio fairness/checkpoints are stricter.
  - Busy loops or code that “works” on asyncio because scheduling is forgiving may get exposed under Trio.
- Thread crossings still need care.
  - If the SDK uses foreign threads or callback threads, you cannot touch AnyIO primitives directly from them without the proper token or portal boundary.

**What to do with the vendor SDK**

Pick one of these and say it plainly in docs:

1. Core library is AnyIO-portable; vendor integration is `asyncio`-only.
2. If the vendor also has a sync API, wrap that with `anyio.to_thread.run_sync()` and keep the core portable.
3. If the vendor must stay asyncio-native and is central, stop claiming full Trio support for that feature set.

A good boundary is:

```python
class PortableTransport(Protocol):
    async def send(self, item: Item) -> None: ...
    async def receive(self) -> Item: ...
    async def aclose(self) -> None: ...
```

Then implement:

- `transport_anyio.py` -> portable
- `transport_vendor_asyncio.py` -> explicitly asyncio-only

**Steelmanned thesis**

You want one honest library surface: portable where you own the concurrency, explicit where a dependency drags in backend-specific behavior.

That is the right instinct.

**Strongest challenges**

- If the vendor SDK is part of the main happy path, saying “the library supports Trio” without qualification is false.
- Replacing `create_task()` with AnyIO alone is not enough; detached vendor tasks can still leak lifecycle and cancellation bugs.
- Replacing `Queue` mechanically misses the real design question: what is your overload policy and shutdown contract?
- Replacing `wait_for()` mechanically can also be wrong; timeout ownership belongs at the API boundary, not sprayed through internals.

**Highest-risk issue**

The highest-risk lie is “we are portable now” while an asyncio-native SDK still owns hidden tasks in the core execution path.

**Testing you need before claiming portability**

- Run core tests on both backends with AnyIO pytest:
  - `asyncio`
  - `trio`
- Run vendor integration tests separately as `asyncio`-only.
- Add cancellation tests and shutdown tests, not just happy-path result tests.

A minimal matrix is:

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

**Bottom line**

Redesign around:
- AnyIO for code you own
- structured concurrency instead of ad-hoc tasks
- streams instead of raw queues
- explicit timeout ownership
- explicit asyncio-only adapters for vendor code

If you want, I can turn this into a concrete migration plan with module boundaries and before/after code patterns.
