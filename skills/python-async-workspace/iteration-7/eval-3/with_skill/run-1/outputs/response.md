Use AnyIO as the owner of portable async tests, keep `pytest-asyncio` in strict mode, and gate `uvloop` so it only appears on supported jobs. The flaky setup is not mysterious; putting both plugins in auto mode is wrong.

- Answer type: `AnyIO-portable` with an `asyncio-runtime-specific` `uvloop` axis
- Sources used: AnyIO testing docs, `pytest-asyncio` concepts docs, `uvloop` README/usage docs

`pyproject.toml`
```toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
# Do not set anyio_mode = "auto" if you want clean mixed-plugin behavior.
# Mark portable tests explicitly with @pytest.mark.anyio.

markers = [
  "anyio: backend-portable async tests run by AnyIO",
  "asyncio_native: asyncio-only tests run by pytest-asyncio",
]
```

`tests/conftest.py`
```python
import sys

import pytest


def _supports_uvloop() -> bool:
    return sys.implementation.name == "cpython" and sys.platform != "win32"


_BACKENDS = [
    pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
    pytest.param(("trio", {}), id="trio"),
]

if _supports_uvloop():
    _BACKENDS.append(
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")
    )


@pytest.fixture(params=_BACKENDS)
def anyio_backend(request):
    return request.param
```

Portable tests
```python
import pytest

pytestmark = pytest.mark.anyio


async def test_important_path(anyio_backend):
    ...
```

For the module-scoped TCP listener, the fixture scope must match `anyio_backend` scope in that module:
```python
import pytest
from anyio import create_task_group, create_tcp_listener
from anyio.abc import SocketAttribute

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module", params=[
    pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
    pytest.param(("trio", {}), id="trio"),
    *(
        [pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")]
        if sys.implementation.name == "cpython" and sys.platform != "win32"
        else []
    ),
])
def anyio_backend(request):
    return request.param


@pytest.fixture(scope="module")
async def tcp_listener(anyio_backend):
    async with await create_tcp_listener(local_host="127.0.0.1") as listener:
        port = listener.extra(SocketAttribute.local_port)
        async with create_task_group() as tg:
            tg.start_soon(listener.serve, handle_client)
            yield port
            tg.cancel_scope.cancel()
```

What matters for your edge cases:

- `contextvars`: AnyIO runs async fixtures/tests in the same task within a runner; with a module-scoped async fixture, contextvar mutations can leak across tests in that module. Keep those tests function-scoped, reset tokens in `finally`, or isolate them into modules without higher-scope async fixtures.
- Windows: do not try `uvloop`; run only `asyncio` and Trio.
- PyPy: do not try `uvloop`; treat it as unsupported unless you have verified otherwise for your exact version.
- `uvloop`: it is not a third async model. It is only an `asyncio` runtime variant.

What not to do:

- Don’t set both `anyio_mode = "auto"` and `asyncio_mode = "auto"`.
- Don’t mark the same test with both `@pytest.mark.anyio` and `@pytest.mark.asyncio`.
- Don’t run Trio-intended tests through `pytest-asyncio`.
- Don’t keep contextvar-mutating tests in the same module runner as a module/session-scoped async fixture unless you explicitly reset state.
- Don’t hardcode TCP ports; use AnyIO’s free-port fixtures or bind and read back the assigned port.
- Don’t enable `uvloop` on Windows or PyPy CI jobs.
- Don’t claim backend portability if the important tests only ran on asyncio.

A sane split is:

1. Portable tests: `@pytest.mark.anyio`, run on `asyncio`, Trio, and `asyncio+uvloop` only where supported.
2. Asyncio-only tests: `@pytest.mark.asyncio`, left under `pytest-asyncio` strict mode.
3. Contextvar-sensitive tests: function-scoped async fixtures only.

If you want, I can turn this into a complete `pyproject.toml` + `conftest.py` layout with CI matrix examples for Linux, Windows, and PyPy.