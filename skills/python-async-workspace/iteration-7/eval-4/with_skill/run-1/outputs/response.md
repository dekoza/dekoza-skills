No. Enabling `uvloop` inside a public async library is the wrong layer.

- `uvloop` is an `asyncio` event loop implementation, not a general async upgrade. A reusable library should not silently choose the app's runtime.
- Your constraints make auto-enable even worse: Windows is not a supported `uvloop` target, and `uvloop` support can lag specific CPython releases. Shipping it as an automatic library behavior turns your compatibility matrix into a trap.
- The real ownership boundary is simple: libraries provide correct async code; applications choose the runner.

Where it belongs:

- app startup for a CLI/service you own
- deployment/runtime config
- performance benchmarks
- an optional test axis for supported POSIX CPython runtimes

Modern wiring for an `asyncio` app you control:

```python
import uvloop

async def main() -> None:
    ...

if __name__ == "__main__":
    uvloop.run(main())
```

If you need lower-level runner control, use the modern `asyncio.Runner` hook, not legacy event-loop policies:

```python
import asyncio
import uvloop

async def main() -> None:
    ...

if __name__ == "__main__":
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main())
```

If your app uses AnyIO on the `asyncio` backend, the toggle belongs at the app entrypoint:

```python
import anyio

async def main() -> None:
    ...

anyio.run(
    main,
    backend="asyncio",
    backend_options={"use_uvloop": True},
)
```

The highest-risk mistake is letting a library own loop setup. That causes platform breakage, conflicts with framework-owned lifecycles, and pushes runtime policy into code that should stay portable.

Verification:
- benchmark before claiming a win
- gate by supported platform/runtime
- if you document portability, test normal `asyncio`; add `asyncio+uvloop` only as an extra supported runtime axis

Mode: `asyncio-runtime-specific`

References used: `backend-uvloop.md`, `decision-matrix.md`, `testing.md`

If you want, I can also give you a concrete support policy matrix for:
1. public library
2. CLI app
3. ASGI server/app bootstrap