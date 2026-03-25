---
domain: cancellation-timeouts
category: behavior
priority: critical
scope: python-async
target_versions: "Python 3.11-3.14, AnyIO 4.x, Trio 0.32+"
last_verified: 2026-03-25
source_basis: official docs
---

# Cancellation and Timeouts

This is the highest-risk part of the skill. Get it wrong and the generated code will hang, leak, or shut down unreliably.

## Default Model

- Prefer AnyIO cancel scopes and task-group cancellation for portable code.
- Treat cancellation as part of normal control flow, not an exotic error path.
- Cleanup code must be idempotent and cancellation-aware.

## AnyIO / Trio vs asyncio

| Model | Behavior | Main risk |
|---|---|---|
| AnyIO / Trio level cancellation | Cancellation is re-applied at yield points while the scope remains effectively cancelled | Asyncio-written code may busy-wait or mis-handle repeated cancellation |
| asyncio edge cancellation | A task gets one cancellation injection unless cancelled again | Swallowed `CancelledError` can let code keep running forever |

AnyIO docs explicitly warn that this difference can break code originally written for asyncio. Their example calls out `asyncio.Condition` as a concrete busy-wait hazard under level cancellation.

## Timeout Rules

- Use `move_on_after()` when timeout should stop work quietly and let the caller continue.
- Use `fail_after()` when timeout should raise `TimeoutError`.
- Use `current_effective_deadline()` when nested timeouts matter.
- Prefer caller-owned timeout policy in reusable library code.

Important AnyIO caveat:

- Do not directly cancel a `fail_after()` scope; the docs warn this can currently lead to a spurious `TimeoutError` if exiting the scope is delayed long enough.

## Cleanup Rules

- Catch cancellation with `get_cancelled_exc_class()` when writing portable code.
- If cleanup needs `await`, do it inside a shielded scope.
- Always re-raise the cancellation exception after cleanup.

If the code catches cancellation and keeps going, assume it is wrong until proven otherwise.

## Shielding Rules

- Shield only bounded finalization or teardown.
- Prefer `move_on_after(..., shield=True)` when cleanup must not hang forever.
- Do not use shielding to hide broken lifecycle design.
- Do not recommend raw `asyncio.shield()` for new portable code.

## Asyncio-Specific Timeout Notes

From Python docs:

- `asyncio.timeout()` transforms `CancelledError` into `TimeoutError`, and that `TimeoutError` can be caught only outside the context manager.
- `asyncio.wait_for()` cancels the awaited task on timeout and may wait longer than the nominal timeout while cancellation completes.
- `asyncio.wait()` does not cancel pending tasks on timeout.

Do not blur those APIs together.

## Known Footguns

- `except BaseException:` or broad cancellation swallowing
- Cancelling tasks before first start in raw `asyncio` and losing cleanup
- `asyncio.Condition` under level cancellation can busy-wait
- Yielding from async generators across cancel scopes or task groups
- Manual `CancelScope.__enter__()` / `__exit__()` ordering mistakes
- Cleanup code that awaits without shielding from an already-cancelled scope

## Review Questions

- What cancels this work?
- Where does cleanup run?
- What happens if cleanup itself blocks?
- Is timeout ownership local, caller-owned, or duplicated?
- Does shielded cleanup have its own upper bound?
