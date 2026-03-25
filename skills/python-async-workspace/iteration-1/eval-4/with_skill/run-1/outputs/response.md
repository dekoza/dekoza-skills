Answer mode: `asyncio-runtime-specific`

References used: `references/backend-uvloop.md`, `references/decision-matrix.md`

Verified against: Python 3.14 `asyncio` runners docs, the current `uvloop` README/PyPI metadata, and AnyIO basics docs.

No. Enabling `uvloop` inside a public async library is the wrong boundary.

- `uvloop` is an `asyncio` event loop implementation, not a third async model.
- A library should not silently choose the application's event loop policy or runtime tuning.
- That is especially wrong when you have Windows developers, because current `uvloop` metadata advertises CPython on POSIX/MacOS, not Windows.
- `uvloop` does not make code Trio-compatible, and it is not a correctness fix for blocking code, bad task ownership, or cancellation bugs.

Where `uvloop` belongs:

- application bootstrap
- runtime configuration
- benchmarks
- optional CI/runtime axes for supported deployments

Modern wiring for a supported `asyncio` app:

```python
import asyncio
import sys

import uvloop


async def main() -> None:
    ...


if sys.platform == "win32":
    asyncio.run(main())
else:
    uvloop.run(main())
```

If you need explicit runner control instead of the convenience helper:

```python
import asyncio

import uvloop


async def main() -> None:
    ...


with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
    runner.run(main())
```

That is the modern style. Old global policy-based setup is legacy territory; Python deprecates the policy system and removes it in 3.16.

If the app is AnyIO-based but running on the `asyncio` backend, the app-level toggle is:

```python
from anyio import run


async def main() -> None:
    ...


run(main, backend="asyncio", backend_options={"use_uvloop": True})
```

Recommendation:

- keep `uvloop` out of the library API
- document it as an optional app deployment optimization for supported platforms
- benchmark before turning it on by default anywhere
- gate it by runtime and platform support instead of pretending it is universal

Highest-risk footgun: putting `uvloop` into library initialization and accidentally baking an `asyncio`-only, non-Windows runtime decision into code that the application should own.

Minimum verification step:

- benchmark the supported app on stock `asyncio` vs `uvloop`
- run a smoke test on supported CPython/POSIX targets
- keep Windows on the default event loop unless you choose a different supported Windows-specific runtime explicitly
