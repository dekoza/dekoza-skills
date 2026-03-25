This design is plausible, but it has four real places to lie to you.

- References used: `streams-synchronization.md`, `testing.md`, `structured-concurrency.md`, `threads-boundaries.md`
- Classification: `AnyIO-portable`

**Thesis**

You are trying to coordinate a pipeline with a stream for data flow, an `Event` for readiness/gating, and a module-scoped async fixture that preloads `contextvars` for tests. That can work, but only if you treat buffering, event lifetime, and test task ownership as part of the contract. If you do not, the tests will pass on optimism and fail on timing.

**The real footguns**

- `create_memory_object_stream()` defaults to `buffer_size=0`; that is not a queue, it is a rendezvous. If your producer assumes "send now, consumer will catch up later", you already have a hidden blocking point. In pipelines this often turns into startup deadlock when the producer is waiting to send the thing that would let the consumer become ready.
- Unbounded buffering via `math.inf` is design cowardice, not flexibility. It removes backpressure, hides overload, and converts a timing bug into a memory-growth bug. If producers can outrun consumers, you need an explicit bound and an overload policy.
- AnyIO `Event` is single-use and not reusable. If your design treats one `Event` like a resettable phase gate, it is wrong. Once set, later waiters pass forever. Reusing the same event across iterations, test cases, or pipeline restarts gives fake readiness and stale state.
- Module-scoped async fixture + `contextvars` is the nastiest one. AnyIO's pytest runner executes async fixtures and tests in the same task, so context seeded in the fixture can leak through that runner. With module scope, you are widening the blast radius on purpose. If a test mutates a seeded context var and does not restore it, later tests can inherit contaminated state.
- Detached or long-lived child tasks make the fixture leak worse. Tasks inherit context at spawn time. If the fixture seeds context once and a background task outlives a test boundary, it can keep running with stale per-test context long after the test that "owned" it ended.
- Higher-scope async fixtures need a matching higher-scope `anyio_backend` fixture. If you are mixing module-scoped async fixtures with the default function-scoped backend fixture, your setup is already on thin ice.

**Where this usually fails**

- Producer and consumer both wait on the same readiness story: producer blocks on zero-buffer send, consumer blocks on event, nobody moves.
- Tests "prove" readiness because an old `Event` stayed set from prior use.
- One test mutates a context var from the module fixture, another test sees it and fails only in a different order or backend.
- Asyncio passes by accident, Trio exposes the bug because your coordination assumptions were sloppy.

**Stronger design**

- Treat stream capacity as an explicit contract: `0` only if you truly want rendezvous semantics; otherwise choose a small bounded size for known burst tolerance.
- Allocate a fresh `Event` per lifecycle phase or per test. Never treat it as resettable shared state.
- Keep context seeding function-scoped unless you can prove the value is immutable and safe to share across all tests in that runner.
- Bind every pipeline task to a task group owned by the test or fixture teardown, so no task survives with borrowed context.
- If you need "module defaults" for context, seed immutable base values in the fixture and override per test with tokens that are always reset.

**Highest-risk issue**

- The module-scoped async fixture seeding `contextvars` is the most dangerous part. It creates cross-test contamination that looks like business logic flakiness, not a fixture bug.

**What I would verify next**

1. Run the same tests on both `asyncio` and Trio.
2. Add one test that mutates a seeded context var and assert the next test starts clean.
3. Add one test where the consumer starts late and confirm your chosen stream capacity behaves intentionally.
4. Add one test that reuses the pipeline twice and prove a fresh `Event` is required.

If you want, paste the actual fixture and pipeline setup; that would allow a sharper review instead of this design-level autopsy.
