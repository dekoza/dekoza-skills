# Execution Transcript

## Eval Prompt

I have an AnyIO pipeline that uses `create_memory_object_stream()`, an `Event`, and a module-scoped async fixture that seeds context variables for tests. Review the design for real async footguns: default buffering, unbounded queues, event reuse, and fixture/task context leakage. I do not want generic concurrency advice.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:court-jester
- Step finished: tool-calls
- Tool use: bash
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

Your design is only sound if you are deliberately using rendezvous channels, one-shot events, and per-test context seeding. If you are treating these pieces like a normal buffered queue, resettable latch, and harmless test setup, the design is wrong.

- `create_memory_object_stream()` default buffering is `0`, not "small queue" semantics. That means `send()` blocks until some task is already in `receive()`. If your pipeline assumes producer startup can get ahead of consumer startup by even one item, you built a hidden handshake, not a queue. In practice this creates startup deadlocks, test hangs that depend on scheduling, and fake "synchronization" where the stream itself is already acting as the barrier.
- Unbounded buffering (`math.inf`) is a real footgun, not a convenience knob. AnyIO explicitly documents it as not recommended. It removes backpressure, lets producers outrun stalled consumers indefinitely, and makes teardown/cancellation uglier because the pipeline can accumulate arbitrary in-memory work after the test has logically moved on. If your tests use unbounded streams to "avoid flakes", they are masking the exact async bug you need to see.
- `Event` reuse is invalid in AnyIO terms. AnyIO events are one-shot and must be replaced, specifically to avoid race classes that reusable events create. If one `Event` instance is shared across multiple pipeline cycles, multiple tests, or restart logic, later waiters can observe an already-set event and skip synchronization entirely. That is not a subtle bug; it is broken state reuse.
- The module-scoped async fixture seeding `ContextVar`s is the nastiest problem here. AnyIO's pytest runner executes async fixtures and async tests in the same task, and higher-scoped async fixtures cause runner sharing. So context seeded in that module fixture is not isolated per test; it is ambient state for every async test in that runner unless you reset it with tokens. Worse, any background task started under that seeded context inherits a snapshot at task creation and can keep stale values for the rest of the module.

Highest-risk issue: the module-scoped async fixture plus long-lived tasks. That combination silently couples tests through `ContextVar` state and makes failures order-dependent.

What I would treat as the safe shape:

- Use explicit finite buffer sizes; choose the bound as part of the contract, not as an afterthought.
- Create a fresh `Event` per pipeline run or phase; never share one across tests or iterations.
- Seed `ContextVar`s with token/reset discipline in function scope unless cross-test sharing is explicitly the thing being tested.
- Do not let background worker tasks depend on ambient fixture-seeded context; pass the needed values explicitly when spawning them.

The uncomfortable conclusion: the stream and event issues are visible bugs, but the fixture/context design is the one that will poison your test suite slowly and make it lie to you. If you want, I can next turn this into a concrete "bad pattern -> corrected pattern" review for your exact fixture/pipeline shape.
