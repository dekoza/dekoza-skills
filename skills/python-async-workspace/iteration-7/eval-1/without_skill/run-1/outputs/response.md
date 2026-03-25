The right direction is not “swap imports and declare victory.” That would be a lie.

Your strongest viable redesign is:

- make the library’s core logic speak only AnyIO primitives
- isolate backend-native integrations behind explicit adapters
- admit that an asyncio-native SDK which spawns its own tasks is asyncio-only unless you put it behind a real boundary

**What to redesign**

- Replace `asyncio.create_task()` with `anyio.create_task_group()` and `tg.start_soon()` / `tg.start()`
- Replace `asyncio.Queue()` with `anyio.create_memory_object_stream()`
- Replace `asyncio.wait_for()` with `anyio.fail_after()` or `anyio.move_on_after()`
- Replace “return a Task / let caller cancel a Task” APIs with structured async context managers, streams, or explicit cancel methods that act on an internal cancel scope

A good target shape is:

```python
class Client:
    async def __aenter__(self) -> "Client": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def request(self, ...) -> Response: ...
    async def events(self) -> AsyncIterator[Event]: ...
```

Internally:

- one task group owns background workers
- one or more memory object streams connect producers/consumers
- shutdown is “close streams / exit context / cancel scope”, not “hope stray tasks die”

**Why this is the right direction**

AnyIO gives you structured concurrency. That fixes the usual `create_task()` mess where background tasks outlive the thing that created them, error propagation is sloppy, and shutdown becomes guesswork.

Queues also need redesign, not just replacement:

- `asyncio.Queue` encourages unbounded buffering and awkward shutdown
- AnyIO memory object streams make producer/consumer lifetimes explicit
- closing the send side is the termination signal; `async for` on the receive side ends naturally

Timeouts also change meaning:

- `asyncio.wait_for()` wraps one awaitable
- `anyio.fail_after()` / `move_on_after()` define a cancellation scope for a block
- that is better, but it means your code must tolerate structured cancellation, not just one-off timeout wrappers

**The big uncomfortable truth**

If one part of the library calls an asyncio-native vendor SDK that spawns its own tasks, then that part is not honestly Trio-portable.

Not “hard to port.”
Not “portable with caveats.”
Not portable.

AnyIO’s own docs are explicit:

- you can only use native libraries for the backend you are running
- native tasks are not governed by AnyIO’s structured cancellation semantics the same way
- an asyncio-native SDK remains an asyncio-native dependency

So the redesign should split the library into two layers:

- `core/`: backend-agnostic AnyIO logic
- `adapters/asyncio_vendor.py`: asyncio-only integration

Then be explicit in your API/docs:

- core API is AnyIO-compatible
- vendor-backed features require asyncio
- Trio support exists only for features implemented with backend-neutral code or a Trio-native alternative

**What to do with the vendor SDK**

You have only three honest options:

1. `Asyncio-only adapter`
- Keep that feature available only on asyncio
- Detect backend and fail fast on Trio with a precise error

2. `Separate implementation`
- Find/build a Trio-native or backend-neutral transport for that vendor feature
- This is the only path to true portability for that feature

3. `Hard isolation boundary`
- Run the vendor SDK in a dedicated thread/process/service and talk to it through a message boundary
- This can make your library usable from Trio, but the vendor integration is still not “natively Trio”; it is bridged

If the SDK spawns its own asyncio tasks, option 1 is usually the least bad immediate answer.

**Places where backend details still matter**

- `Cancellation semantics`
  - AnyIO uses Trio-style cancel scopes
  - asyncio-native code often assumes one-shot `CancelledError`
  - code that swallows cancellation or uses asyncio primitives with odd cancellation behavior can misbehave under AnyIO

- `Task ownership`
  - tasks started in your AnyIO task group are structured
  - tasks spawned internally by an asyncio SDK are not under your task group’s ownership
  - they may outlive your scope, ignore your shutdown timing, or surface errors differently

- `Native object types`
  - anything exposing `asyncio.Task`, `Future`, loop handles, transports, or callbacks is backend-specific
  - those types must not leak through your public API if you want honest AnyIO support

- `Backend-only dependencies`
  - an asyncio SDK cannot be used under Trio just because the rest of your library uses AnyIO
  - portability stops at the dependency boundary

- `Testing`
  - you need to run the backend-neutral test suite under both asyncio and Trio
  - vendor-adapter tests belong in an asyncio-only test matrix entry

**A sane migration rule**

Use this decision test for every subsystem:

- if it only needs concurrency, cancellation, streams, locks, or timeouts -> move it to AnyIO
- if it depends on asyncio-native library objects or task behavior -> keep it in an adapter and mark it backend-specific

**Practical mapping**

- `asyncio.create_task(...)` -> `tg.start_soon(...)`
- `asyncio.Queue(...)` -> `create_memory_object_stream(...)`
- `await asyncio.wait_for(coro, t)` -> `with fail_after(t): await coro`
- task handles for lifecycle control -> task group + cancel scope + stream closure
- sentinel values in queues -> close the send stream

**Highest-risk issue**

The worst assumption is: “If we wrap our own code in AnyIO, the asyncio vendor SDK becomes portable too.”

That assumption is false. It is the architectural trap here.

**Recommended direction**

- move your core orchestration to AnyIO now
- carve the vendor SDK into an asyncio-only adapter now
- document feature-level backend support, not blanket library-wide support
- only claim full Trio support for the parts with no asyncio-native dependency path

If you want, I can sketch a concrete before/after API shape for your library, including how to structure the asyncio-only vendor adapter without leaking backend-specific types.