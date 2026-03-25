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
- Tool use: bash
- Tool use: bash
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
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

Your design is plausible if you want strict backpressure and inherited ambient context, but it has four real AnyIO-specific traps.

- `create_memory_object_stream()` defaults to `buffer_size=0`, which is not a queue in the normal sense; it is a rendezvous channel. `send()` blocks until some task is already receiving. If your producer starts first, or your fixture seeds work before the consumer task is actually at `receive()`, you get startup stalls that look nondeterministic but are just scheduling-dependent.
- An unbounded stream (`math.inf`) is a bad escape hatch here. AnyIO documents it as possible but not recommended. In a pipeline, it masks the exact bug a bounded channel would expose: consumer lag, missed wakeups, or a stuck downstream stage. Tests then "pass" by accumulating memory and latency instead of applying backpressure.
- Reusing an `Event` is simply the wrong primitive in AnyIO. Unlike `asyncio.Event`, AnyIO events are one-shot and must be replaced, specifically to avoid race classes. If you keep one event on a long-lived pipeline object and use it for multiple cycles/phases, future waiters may pass immediately from an old `set()`, and your test stops verifying real coordination.
- The module-scoped async fixture is the nastiest footgun. AnyIO's pytest plugin runs async fixtures and tests in the same task within the same async test runner, and context variables propagate within that runner. So a module-scoped async fixture that seeds `ContextVar`s is not isolated per test; async tests in that module can observe and mutate shared ambient context unless every mutation is token-reset. That is real cross-test leakage, not theory.

The deeper context bug is worse than just "fixture leakage":

- AnyIO copies context when spawning a new task, from the task calling `start()` / `start_soon()`, not from some abstract task-group owner.
- That means a worker started under fixture-seeded context gets a snapshot of that context at spawn time.
- If a later test mutates the `ContextVar`, already-running worker tasks do not magically see the update.
- But new tasks spawned after the mutation do inherit it.
- So you get asymmetric behavior: old tasks use stale context, new tasks use polluted context, and tests become order-coupled in a way that looks like random async flakiness.

What I would call weak in the design:

- Using `Event` alongside a memory stream often means the model is underspecified. If the event means "there is data," the stream already encodes that. If it means "phase transition," it must be a fresh event per phase, not a reusable latch.
- Using module-scoped async context seeding for convenience is brittle unless the whole point of the test is to verify inherited ambient context across a module. For ordinary pipeline tests, it is the wrong scope.

Stronger design, still specific to your setup:

- Pick the stream size intentionally. `0` only if you truly want rendezvous semantics; `1` or small `N` if you want bounded queue semantics with visible backpressure.
- Never use `math.inf` unless memory growth is explicitly part of the contract you are testing.
- Treat `Event` as single-use; allocate a new one per generation/phase, or remove it if the stream/close/sentinel already carries the signal.
- Move context seeding to function scope, or wrap each test mutation in `token = var.set(...); ...; var.reset(token)`. A module-scoped async fixture that sets once and resets at teardown is not test isolation.
- If you need deterministic task context, spawn tasks from the exact code path whose context you want inherited. With AnyIO, spawn site matters.

Highest-risk issue: the module-scoped async fixture plus `ContextVar` seeding. That is the most likely source of non-obvious, order-dependent failures, because the AnyIO test runner deliberately shares task context across async fixtures/tests in the same runner.

I could give you a sharper review if you paste the actual fixture and pipeline startup code; without code, this is the real footgun map, not generic advice.
