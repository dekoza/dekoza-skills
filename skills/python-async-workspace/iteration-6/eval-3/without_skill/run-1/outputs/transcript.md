# Execution Transcript

## Eval Prompt

Our tests use AnyIO and `pytest-asyncio`, and CI got flaky right after someone set both plugins to auto mode. We also have a module-scoped async fixture for a TCP listener, some tests mutate `contextvars`, one CI job is Windows, and another is PyPy. We want the important tests to run on Trio, plain asyncio, and uvloop where that is actually supported. Show the right pytest setup and tell me what not to do.

## Configuration

- Mode: without_skill
- Skill expected: False
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: webfetch
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: False

## Final Response

Your flake is not mysterious. Setting both plugins to `auto` is the mistake.

**Use this setup**
```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
asyncio_default_fixture_loop_scope = "function"
asyncio_default_test_loop_scope = "function"
markers = [
  "anyio: run with AnyIO's pytest plugin",
  "backend_matrix: run this test on asyncio, Trio, and uvloop when supported",
]
```

Do not set `anyio_mode = "auto"` if `pytest-asyncio` is installed. AnyIO explicitly warns that its auto mode conflicts with `pytest-asyncio` auto mode.

Use explicit markers:
- `@pytest.mark.anyio` for cross-backend tests
- `@pytest.mark.asyncio` only for asyncio-only tests

**Backend matrix**
```python
# conftest.py
import platform
import sys

import pytest


def supported_anyio_backends():
    backends = [
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param("trio", id="trio"),
    ]

    # Real uvloop: CPython + non-Windows only
    if sys.implementation.name == "cpython" and platform.system() != "Windows":
        backends.append(
            pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")
        )

    return backends
```

Run only the important tests on all backends:
```python
import pytest

from conftest import supported_anyio_backends


@pytest.mark.anyio
@pytest.mark.backend_matrix
@pytest.mark.parametrize("anyio_backend", supported_anyio_backends())
async def test_critical_flow(anyio_backend):
    ...
```

Keep ordinary async tests on one backend unless they are genuinely portability-critical.

**Module-scoped async TCP listener**
If you keep a module-scoped async fixture, give it a matching scoped `anyio_backend`. Otherwise scope mismatch or runner weirdness is inevitable.

```python
# tests/network/test_listener.py
import pytest
from anyio import create_task_group, create_tcp_listener
from anyio.abc import SocketAttribute

from conftest import supported_anyio_backends


@pytest.fixture(scope="module", params=supported_anyio_backends())
def anyio_backend(request):
    return request.param


@pytest.fixture(scope="module")
async def tcp_listener(anyio_backend):
    async def handle(stream):
        async with stream:
            data = await stream.receive()
            await stream.send(data[::-1])

    async with await create_tcp_listener(local_host="127.0.0.1", local_port=0) as listener:
        async with create_task_group() as tg:
            tg.start_soon(listener.serve, handle)
            yield listener.extra(SocketAttribute.local_port)
            tg.cancel_scope.cancel()
```

**The ugly part: `contextvars`**
This matters a lot. AnyIO runs async fixtures and tests in the same task, and with a higher-scoped async fixture it can keep one runner alive for the whole scope. That means `contextvars` mutations can bleed between tests in that runner.

So:
- prefer function-scoped async fixtures if tests mutate `contextvars`
- or isolate the module-scoped listener tests into their own module
- or reset every mutated `ContextVar` in a function-scoped fixture

Example reset:
```python
import pytest

from myapp.context import request_id_var


@pytest.fixture(autouse=True)
def reset_request_id():
    token = request_id_var.set(None)
    try:
        yield
    finally:
        request_id_var.reset(token)
```

**What not to do**
- do not set both `asyncio_mode = auto` and `anyio_mode = auto`
- do not mark the same test with both `@pytest.mark.asyncio` and `@pytest.mark.anyio`
- do not expect Trio tests to survive direct `asyncio` calls like `asyncio.get_running_loop()`, `asyncio.Event()`, `asyncio.create_task()`
- do not run uvloop on Windows or PyPy; gate it out at collection time
- do not share a module- or session-scoped async fixture with tests that freely mutate `contextvars` and then act surprised when CI flakes
- do not hard-code TCP ports; use ephemeral ports

**Practical split**
- `pytest-asyncio` strict: for asyncio-only tests
- AnyIO explicit marker: for portability tests
- Trio + asyncio + uvloop: only for the important tests that claim backend neutrality

If you want, I can turn this into a ready-to-drop `pyproject.toml` + `conftest.py` layout for your repo.
