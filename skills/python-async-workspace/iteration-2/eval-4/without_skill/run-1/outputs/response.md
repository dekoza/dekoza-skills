No. Auto-enabling `uvloop` inside a public async library is the wrong layer.

- Your library does not own the event loop lifecycle; the application, framework, test runner, or embedding environment does.
- `uvloop` is not a universal dependency: its published support is `CPython` on `POSIX`/macOS, not Windows.
- The old global-policy approach (`uvloop.install()` / event-loop policies) is aging badly: Python docs deprecate asyncio policies and steer users to `asyncio.run(..., loop_factory=...)` or `asyncio.Runner(..., loop_factory=...)`.
- Forcing it in a library creates hidden behavior, platform skew, and support pain for zero consent from callers.

The bad assumption here is “a library should silently choose a faster loop for everyone.” That is brittle. Libraries should be loop-agnostic; apps choose the runner.

Where `uvloop` belongs:
- app entrypoints
- CLI `main()`
- ASGI/server bootstrap
- worker process startup
- benchmark or production deployment wiring

Modern wiring for an app:
- Python `3.12+`: use `asyncio.run(..., loop_factory=uvloop.new_event_loop)`
- Python `3.11+` with multiple top-level async calls: use `asyncio.Runner(loop_factory=uvloop.new_event_loop)`
- `uvloop.run(...)` is also fine if you explicitly want a uvloop-owned helper
- avoid policy-based `uvloop.install()` unless you are only carrying legacy compatibility for older Python versions

A sane cross-platform app pattern is:

```python
import asyncio
import sys

try:
    import uvloop
except ImportError:
    uvloop = None


def run(main_coro):
    if uvloop is not None and sys.platform != "win32":
        if sys.version_info >= (3, 12):
            return asyncio.run(main_coro, loop_factory=uvloop.new_event_loop)
        if sys.version_info >= (3, 11):
            with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
                return runner.run(main_coro)
        return uvloop.run(main_coro)  # legacy fallback path

    return asyncio.run(main_coro)
```

What your library should do instead:
- document that it supports standard `asyncio`
- optionally document that apps may use `uvloop` for supported runtimes
- never call `uvloop.install()` or mutate global loop config from import-time or library code

If you want, I can also give you a short “library policy” paragraph for your README and a version-matrix recommendation for `3.8` through `3.13+`.
