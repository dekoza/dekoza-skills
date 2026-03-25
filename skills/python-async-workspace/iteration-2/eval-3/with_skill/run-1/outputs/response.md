Use AnyIO to drive the portable async tests, and keep `pytest-asyncio` out of auto mode.

`pytest.ini`
```ini
[pytest]
asyncio_mode = strict
```

Do not set both of these:
```ini
# wrong
anyio_mode = auto
asyncio_mode = auto
```

A sane mixed setup looks like this:

`tests/conftest.py`
```python
import sys

import pytest

_ANYIO_BACKENDS = [
    pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
    pytest.param(("trio", {}), id="trio"),
]

if sys.platform != "win32":
    _ANYIO_BACKENDS.append(
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")
    )


@pytest.fixture(scope="module", params=_ANYIO_BACKENDS)
def anyio_backend(request):
    return request.param
```

Then mark only the portable tests that should run on the backend matrix:

`tests/test_tcp_listener.py`
```python
import pytest

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
async def tcp_listener(anyio_backend):
    listener = await start_test_listener()
    try:
        yield listener
    finally:
        await listener.aclose()


async def test_accepts_connection(tcp_listener):
    ...
```

Why this is the right setup:
- `pytest-asyncio` stays in `strict`, so it only handles tests explicitly marked `@pytest.mark.asyncio`.
- AnyIO handles the cross-backend tests via `@pytest.mark.anyio`.
- Your module-scoped async fixture works because `anyio_backend` is also module-scoped.
- `uvloop` is treated correctly: it is an `asyncio` runtime option, not a third async model.

What not to do:
- Do not put both plugins in auto mode. That conflict is real, not “CI being weird”.
- Do not mark the same test with both `@pytest.mark.anyio` and `@pytest.mark.asyncio`.
- Do not use a function-scoped `anyio_backend` with a module-scoped async fixture; that scope mismatch is broken.
- Do not treat `uvloop` as equivalent to Trio coverage. It only changes the `asyncio` loop implementation.
- Do not hardcode TCP ports or use `sleep()` for listener readiness; use a real readiness signal or an OS-assigned free port.

If you still need some asyncio-only tests, keep them explicit and separate:
```python
import pytest

@pytest.mark.asyncio
async def test_asyncio_specific_behavior():
    ...
```

Minimum verification:
- Run the important AnyIO-marked tests and confirm you see `asyncio`, `trio`, and `asyncio+uvloop` in the node ids.
- Keep CI on supported POSIX/CPython jobs for the `uvloop` axis.

References used: AnyIO pytest plugin testing guidance, asyncio backend notes, and uvloop runtime guidance.
