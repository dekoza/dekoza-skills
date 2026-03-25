# Transcript

- User task: explain why swallowing `CancelledError` and using raw `asyncio.shield()` can hang shutdown; provide a safer pattern.
- Constraints followed: no skill loaded; no repository files modified beyond requested output artifacts.
- Verified against Python docs:
  - `asyncio.CancelledError`: "In almost all situations the exception must be re-raised."
  - `asyncio` task cancellation docs: swallowing `CancelledError` can break structured concurrency and misbehave.
  - `asyncio.shield()`: protects the inner awaitable from cancellation, but the caller still receives `CancelledError`.
- Produced `response.md` with:
  - explicit statement that swallowing cancellation is a bug
  - re-raise-after-cleanup guidance
  - warning against raw `asyncio.shield()` as the default fix
  - bounded-cleanup examples using `anyio.move_on_after(..., shield=True)` and plain `asyncio` timeout-based cleanup
