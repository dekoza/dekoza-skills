# Execution Transcript

## Eval Prompt

I have an AnyIO pipeline that uses `create_memory_object_stream()`, an `Event`, and a module-scoped async fixture that seeds context variables for tests. Review the design for real async footguns: default buffering, unbounded queues, event reuse, and fixture/task context leakage. I do not want generic concurrency advice.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

This design has real footguns. The highest-risk one is the module-scoped async fixture seeding `contextvars`: in AnyIO tests, async fixtures and tests run in the same task, so context can leak between tests unless you reset it explicitly. That is not hypothetical; it is a known AnyIO testing behavior.

- `create_memory_object_stream()` default buffering is `0`, not "some small queue". That means rendezvous semantics: `send()` blocks until a receiver is ready. If your pipeline also gates startup with an `Event`, you can build a clean handshake or a stupid deadlock. If producer waits on event and consumer is not yet receiving, or consumer waits on event that producer only sets after `send()`, you created a self-inflicted stall.
- Unbounded buffering is a real bug, not a convenience. In AnyIO, `math.inf` makes the stream unbounded and the docs explicitly recommend against it. If you do that, overload policy becomes "grow RAM until the process is sick". If producer throughput can exceed consumer throughput even briefly, capacity must be an intentional contract.
- `Event` reuse is wrong in AnyIO. Events are single-use, not resettable gates. Once set, future waiters pass immediately. Reusing one across pipeline runs, stages, or tests gives you fake readiness and test pollution. If you need repeated phase coordination, create a fresh `Event` per cycle or use a different primitive.
- Module-scoped async fixtures are especially dangerous here. AnyIO requires higher-scope async fixtures to have a matching higher-scope `anyio_backend` fixture, and even then the contextvar state can persist within that runner. Seeding context once at module scope means every task spawned later may inherit that stale context snapshot unless each test sets and resets its own values.
- Task context leakage is subtle: spawned tasks inherit the current `contextvars` context at spawn time. So if your fixture seeds contextvars before starting the pipeline, every worker task may capture that fixture state and keep it even if later tests mutate/reset the parent context. That produces "why is this task still seeing old request/test state?" failures.
- Close semantics matter with streams. If you clone send/receive ends and do not close them deterministically, receivers may hang forever waiting for end-of-stream. In these designs, "queue drained" and "producer side fully closed" are not the same thing.

What I would change:

- Use a bounded memory object stream with an explicit capacity chosen from load expectations.
- Treat `Event` as one-shot only; never reuse the same instance across runs/tests.
- Move contextvar seeding to function scope, or wrap each test in explicit token reset logic.
- Spawn pipeline tasks only after per-test context is established, not from a long-lived fixture that outlives the test's intended context.
- Add a backend-matrix test on `asyncio` and Trio that proves: bounded backpressure, no event reuse bleed, and no contextvar leakage across tests/tasks.

References used: `streams-synchronization.md`, `testing.md`, `code-review-checklist.md`
Classification: `AnyIO-portable`

Minimum verification:
- write tests that intentionally overproduce into the stream,
- run two tests back-to-back that seed different contextvar values,
- assert a fresh `Event` is required per run,
- run on both `asyncio` and Trio.

If you want a real review instead of a design autopsy, paste the fixture and pipeline snippet. Without code, this is the sharpest honest answer available.
