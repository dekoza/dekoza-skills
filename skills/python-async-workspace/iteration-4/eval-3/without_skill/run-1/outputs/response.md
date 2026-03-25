Both plugins in `auto` mode is the bug. In a mixed AnyIO + `pytest-asyncio` suite, that setup is wrong and flaky by design.

**Use This**
- Keep `pytest-asyncio` in `strict` mode.
- Do not enable `anyio_mode = auto` globally; mark only the tests that should run on the AnyIO backend matrix.
- Run cross-backend tests through AnyIO; keep `pytest-asyncio` only for asyncio-specific tests.

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
addopts = "--strict-markers"
markers = [
  "anyio: run test via AnyIO backend matrix",
]

# Important: do NOT set anyio_mode = "auto" here in a mixed suite.
```

```python
# tests/conftest.py
import platform

import pytest


def _supports_uvloop() -> bool:
    if platform.python_implementation() != "CPython":
        return False
    if platform.system() == "Windows":
        return False
    try:
        import uvloop  # noqa: F401
    except ImportError:
        return False
    return True


ANYIO_BACKENDS = [
    pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
    pytest.param("trio", id="trio"),
]

if _supports_uvloop():
    ANYIO_BACKENDS.append(
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")
    )


@pytest.fixture(params=ANYIO_BACKENDS)
def anyio_backend(request):
    return request.param
```

**How To Use It**
- For important portable tests, use `pytest.mark.anyio` and depend on `anyio_backend`.
- For raw asyncio-only tests, keep `@pytest.mark.asyncio`.
- Do not mix both markers on one test.

```python
# runs on trio + asyncio + uvloop when supported
import pytest

pytestmark = pytest.mark.anyio

async def test_happy_path(anyio_backend):
    ...
```

```python
# asyncio-only test
import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def asyncio_resource():
    ...

@pytest.mark.asyncio
async def test_low_level_asyncio_behavior(asyncio_resource):
    ...
```

**Your TCP Listener Fixture**
- A module-scoped async fixture is the dangerous part here.
- With AnyIO, higher-scoped async fixtures force a shared test runner; `contextvars` then leak across tests in that runner.
- Since you already have tests mutating `contextvars`, the safe default is: make the listener fixture function-scoped.

```python
import pytest
from anyio import create_task_group, create_tcp_listener
from anyio.abc import SocketAttribute, SocketStream


@pytest.fixture
async def tcp_listener(anyio_backend):
    async def handle(stream: SocketStream) -> None:
        async with stream:
            data = await stream.receive()
            await stream.send(data)

    async with await create_tcp_listener(local_host="127.0.0.1") as listener:
        async with create_task_group() as tg:
            tg.start_soon(listener.serve, handle)
            yield listener.extra(SocketAttribute.local_port)
            tg.cancel_scope.cancel()
```

If you insist on `scope="module"`, then `anyio_backend` must also be module-scoped for that module. That is exactly the setup that reduces isolation and makes `contextvars` contamination more likely. So unless startup cost is brutal, don’t do it.

**Contextvars Rule**
- Treat `contextvars` mutations as test-local state and reset them with tokens.
- Do not rely on fixture teardown from another task to clean them up.
- Do not share a module/session async runner when tests mutate them.

```python
token = request_id_var.set("test-value")
try:
    ...
finally:
    request_id_var.reset(token)
```

**What Not To Do**
- Do not set both `anyio_mode = "auto"` and `asyncio_mode = "auto"`.
- Do not run the same test under both `@pytest.mark.anyio` and `@pytest.mark.asyncio`.
- Do not keep broad module/session-scoped async fixtures when tests mutate `contextvars`.
- Do not hard-force uvloop on Windows or PyPy; uvloop is CPython-only and not for Windows.
- Do not hard-code TCP ports; bind to port `0` or use AnyIO’s free-port fixtures.
- Do not widen asyncio loop scope casually in `pytest-asyncio`; shared loops reduce isolation and hide leaks.

**Practical Split**
- `AnyIO` tests: backend-portable behavior, cancellation, streams, sockets, timeouts, task groups.
- `pytest-asyncio` tests: asyncio-only APIs, loop internals, transport/protocol details, code that is not Trio-compatible.

If you want, I can turn this into a complete `conftest.py` and a small CI matrix example for Linux/macOS/Windows with CPython and PyPy.
