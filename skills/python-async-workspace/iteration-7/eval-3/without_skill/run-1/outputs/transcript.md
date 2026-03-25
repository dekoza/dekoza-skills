# Execution Transcript

## Eval Prompt

Our tests use AnyIO and `pytest-asyncio`, and CI got flaky right after someone set both plugins to auto mode. We also have a module-scoped async fixture for a TCP listener, some tests mutate `contextvars`, one CI job is Windows, and another is PyPy. We want the important tests to run on Trio, plain asyncio, and uvloop where that is actually supported. Show the right pytest setup and tell me what not to do.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:court-jester
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

The flaky bit is not mysterious: setting both plugins to `auto` is wrong in a mixed AnyIO + `pytest-asyncio` suite. They compete for the same async tests and fixtures, and your module-scoped async fixture plus `contextvars` makes the fallout worse.

**Use This Setup**

`pyproject.toml` / `pytest.ini`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
asyncio_default_fixture_loop_scope = "function"
asyncio_default_test_loop_scope = "function"

markers = [
  "anyio: run test via AnyIO backend matrix",
  "asyncio: run test with pytest-asyncio only",
]
```

- Keep `pytest-asyncio` in `strict` mode.
- Do not set `anyio_mode = "auto"` in a suite that also uses `pytest-asyncio`.
- Mark cross-backend tests with `@pytest.mark.anyio`.
- Mark true asyncio-only tests with `@pytest.mark.asyncio`.

**Backend Matrix**

`conftest.py`:

```python
import importlib.util
import sys

import pytest


def _supports_real_uvloop() -> bool:
    return (
        sys.implementation.name == "cpython"
        and sys.platform != "win32"
        and importlib.util.find_spec("uvloop") is not None
    )


_BACKENDS = [
    pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
    pytest.param("trio", id="trio"),
]

if _supports_real_uvloop():
    _BACKENDS.append(
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")
    )


@pytest.fixture(params=_BACKENDS)
def anyio_backend(request):
    return request.param
```

- This gives you Trio, plain asyncio, and uvloop only where it is actually supported.
- On Windows and PyPy, `asyncio+uvloop` should not be in the matrix.

**Important Tests**

For tests that must pass on all supported backends:

```python
import pytest

pytestmark = pytest.mark.anyio


async def test_client_round_trip(anyio_backend):
    ...
```

For asyncio-specific tests only:

```python
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def asyncio_only_resource():
    ...


@pytest.mark.asyncio
async def test_raw_asyncio_behavior(asyncio_only_resource):
    ...
```

- Use AnyIO for backend-agnostic behavior.
- Use `pytest-asyncio` only when the test is really about raw asyncio semantics.

**Your Module-Scoped TCP Listener**

This is the other footgun.

With AnyIO, a higher-scoped async fixture keeps one async test runner alive longer. AnyIO’s docs explicitly say `contextvars` are shared within that runner. So if tests mutate `contextvars`, a module-scoped async fixture increases bleed between tests.

Best fix:

- make the listener fixture `function` scoped for cross-backend tests
- bind to an ephemeral port (`local_port=0`) or use `free_tcp_port`
- keep backend-matrix tests isolated

Example shape:

```python
import pytest
from anyio import create_task_group, create_tcp_listener
from anyio.abc import SocketAttribute


@pytest.fixture
async def tcp_listener(anyio_backend):
    async def handler(stream):
        ...

    async with await create_tcp_listener(local_host="127.0.0.1", local_port=0) as listener:
        port = listener.extra(SocketAttribute.local_port)
        async with create_task_group() as tg:
            tg.start_soon(listener.serve, handler)
            yield port
            tg.cancel_scope.cancel()
```

If you insist on `scope="module"`, then do not pretend that module is safely backend-matrix + `contextvars`-mutation friendly. It is not. Split it into dedicated backend-specific modules or move the long-lived server outside the async runner.

**What Not To Do**

- Do not enable both `asyncio_mode = auto` and `anyio_mode = auto`.
- Do not use `@pytest.mark.asyncio` for tests you expect to run on Trio.
- Do not keep a module-scoped async fixture in the same AnyIO runner as tests that mutate `contextvars` unless you enjoy state leakage.
- Do not hard-code TCP ports in CI; use `local_port=0` or `free_tcp_port`.
- Do not put `asyncio+uvloop` in Windows or PyPy jobs and call that “coverage”; uvloop is not your portable backend.
- Do not mix raw `asyncio` APIs into tests claimed to be backend-agnostic; Trio will expose that lie immediately.

**Practical CI Split**

- Linux/macOS CPython: `trio`, `asyncio`, `asyncio+uvloop`
- Windows CPython: `trio`, `asyncio`
- PyPy: `trio`, `asyncio`

**Highest-Risk Issue**

Your module-scoped async listener plus tests that mutate `contextvars` is a contamination machine. Even after fixing plugin modes, that can still make CI flaky.

If you want, I can turn this into a concrete `pyproject.toml` + `conftest.py` + example test layout for your repo.
