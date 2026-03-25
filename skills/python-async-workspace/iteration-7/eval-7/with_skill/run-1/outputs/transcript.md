# Execution Transcript

## Eval Prompt

I have an AnyIO pipeline that uses `create_memory_object_stream()`, an `Event`, and a module-scoped async fixture that seeds context variables for tests. Review the design for real async footguns: default buffering, unbounded queues, event reuse, and fixture/task context leakage. I do not want generic concurrency advice.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:court-jester
- Tool use: skill:python-async
- Tool use: glob
- Tool use: grep
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

I could not inspect your actual implementation here; the workspace only contains reference material, not your pipeline code. So this is a design review against verified AnyIO behavior, not a pretend line-by-line audit.

`AnyIO-portable` review, using `streams-synchronization.md`, `testing.md`, and `code-review-checklist.md`.

**Verdict**
- The biggest real footgun is not the stream. It is the module-scoped async fixture seeding `ContextVar`s.
- Second place is `Event` reuse. If you reuse one across runs or tests, your readiness logic turns into a stale latch.
- Third is treating `create_memory_object_stream()` like a queue without deciding whether you want rendezvous, bounded buffering, or memory blow-up.

**What Breaks**
- `create_memory_object_stream()` defaults to buffer size `0`, so it is a rendezvous, not a queue. If your producer does `send()` before the consumer is actively receiving, it blocks immediately.
- That becomes a deadlock if your coordination is "consumer waits on `Event`; producer sets `Event` after first `send()`". With a zero-buffer stream, the `send()` never completes, so the `Event` never gets set.
- Switching to `math.inf` or a huge buffer to "fix" that is just hiding the bug. AnyIO docs explicitly do not recommend unbounded buffering. Your overload policy becomes "grow memory until something else dies."
- `Event` is single-use in AnyIO. Once set, it stays set; it is not a reusable cycle barrier. Reusing one across batches, retries, or tests means later waiters pass immediately on stale state.
- A module-scoped async fixture that seeds `ContextVar`s is a contamination machine. AnyIO's pytest runner executes async fixtures and tests in the same task, so contextvar state can leak within that runner. If one test mutates ambient context and you do not reset with the token, the next test can inherit garbage.
- It gets worse if that fixture also spawns tasks: child tasks inherit the context snapshot at spawn time. Now you have background work carrying old per-test context long after the test that "owned" it is gone.

**Specific Design Risks**
- If your module fixture owns a send stream clone and never closes it, consumers using async iteration may hang forever waiting for the send side to actually end.
- If the fixture is higher-scope async, you also need a matching higher-scope `anyio_backend` fixture. Without that, fixture lifetime and backend runner lifetime are misaligned.
- If you also have `pytest-asyncio` in auto mode, stop doing that. AnyIO docs explicitly warn it conflicts with AnyIO auto mode.

**Synthesis**
- Use a bounded stream size chosen on purpose. `0` if you want strict handoff; a small positive bound if you want controlled decoupling. Never unbounded unless "memory growth under overload" is truly your policy.
- Use a fresh `Event` per lifecycle edge only. Good for one-shot readiness; wrong for reusable phase signaling.
- Do not keep per-test `ContextVar` state in a module-scoped async fixture. Seed/reset with tokens per test, or pass explicit context objects through the pipeline instead of ambient state.
- If you must keep a module-scoped fixture, keep only inert shared resources there. Not mutable ambient context, not reusable events, not long-lived tasks carrying test-local context.

**Highest-Risk Issue**
- Module-scoped async fixture + `ContextVar` seeding is the nastiest bug source here, because it fails silently: tests pass in isolation, then order-dependent contamination appears later and looks supernatural.

If you want, paste the actual fixture and pipeline setup and I will do the non-generic version.
