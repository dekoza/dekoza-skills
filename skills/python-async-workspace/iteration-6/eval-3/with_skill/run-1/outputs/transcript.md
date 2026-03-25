# Execution Transcript

## Eval Prompt

Our tests use AnyIO and `pytest-asyncio`, and CI got flaky right after someone set both plugins to auto mode. We also have a module-scoped async fixture for a TCP listener, some tests mutate `contextvars`, one CI job is Windows, and another is PyPy. We want the important tests to run on Trio, plain asyncio, and uvloop where that is actually supported. Show the right pytest setup and tell me what not to do.

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

Use an explicit split. Your current setup is flaky because both plugins in auto mode fight over the same async tests.

`pytest` config:

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
markers = [
  "anyio: backend-portable async test",
  "asyncio: asyncio-only test",
]
```

Do not set `anyio_mode = "auto"` if you also keep `pytest-asyncio` around. The boring, stable rule is:

- `@pytest.mark.anyio` for portable tests
- `@pytest.mark.asyncio` for asyncio-only tests
- `pytest-asyncio` stays in `strict` mode
- never put both marks on the same test

For the important cross-backend tests, scope the backend matrix only to that test package/module, not the whole suite:

```python
# tests/important_async/conftest.py
import platform
import sys

import pytest


def important_backends():
    params = [
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param(("trio", {}), id="trio"),
    ]

    # uvloop is an asyncio runtime option, not a third backend.
    # Do not try to use it on Windows or PyPy.
    if sys.implementation.name == "cpython" and platform.system() != "Windows":
        params.append(
            pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")
        )

    return params


@pytest.fixture(scope="module", params=important_backends())
def anyio_backend(request):
    return request.param
```

That `scope="module"` part matters because you said you have a module-scoped async fixture. Higher-scope async fixtures need a matching higher-scope `anyio_backend`.

Example TCP listener fixture:

```python
# tests/important_async/conftest.py
import anyio
import pytest


@pytest.fixture(scope="module")
async def tcp_listener(anyio_backend, free_tcp_port_factory):
    port = free_tcp_port_factory()

    async def handler(stream):
        await stream.send(b"ok")
        await stream.aclose()

    listener = await anyio.create_tcp_listener(local_host="127.0.0.1", local_port=port)

    async with listener, anyio.create_task_group() as tg:
        tg.start_soon(listener.serve, handler)
        yield port
        tg.cancel_scope.cancel()
```

And a portable test:

```python
import pytest

pytestmark = pytest.mark.anyio


async def test_listener_responds(tcp_listener):
    stream = await anyio.connect_tcp("127.0.0.1", tcp_listener)
    data = await stream.receive()
    assert data == b"ok"
    await stream.aclose()
```

For `contextvars`, assume leakage is real. AnyIO runs async fixtures and tests in the same task runner, so mutated context can bleed between fixture/test boundaries. Reset what you touch:

```python
# tests/conftest.py
import contextvars
import pytest

request_id = contextvars.ContextVar("request_id", default=None)


@pytest.fixture(autouse=True)
def clear_request_id():
    token = request_id.set(None)
    try:
        yield
    finally:
        request_id.reset(token)
```

What not to do:

- Don’t set both AnyIO and `pytest-asyncio` to `auto`
- Don’t mark one test with both `@pytest.mark.anyio` and `@pytest.mark.asyncio`
- Don’t make a module-scoped async fixture depend on a function-scoped `anyio_backend`
- Don’t treat `uvloop` as a third async model; it is only `asyncio + different loop`
- Don’t try `uvloop` on Windows or PyPy
- Don’t hardcode TCP ports; use `free_tcp_port_factory()` or listener-assigned ports
- Don’t assume `contextvars` magically reset between async fixtures/tests
- Don’t run the full suite on Trio if only a subset actually claims backend portability

Practical split:

- portable/important tests: `@pytest.mark.anyio`, run on `asyncio`, `trio`, and `asyncio+uvloop` when supported
- asyncio-only tests: `@pytest.mark.asyncio`
- uvloop coverage: only on supported CPython POSIX jobs

Mode: `AnyIO-portable`, with an `asyncio-runtime-specific` uvloop axis.

References used: `testing.md`, `backend-uvloop.md`, `backend-trio.md`, `decision-matrix.md`.

If you want, I can also turn this into a ready-to-drop `pyproject.toml` + `tests/conftest.py` layout for your repo.
