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

Use one plugin to own portable async tests, and stop pretending two auto modes can coexist. They cannot.

`AnyIO-portable` answer with `asyncio-runtime-specific` `uvloop` notes. References used: `python-async` skill docs from `references/testing.md`, `references/backend-uvloop.md`, `references/backend-trio.md`, `references/backend-asyncio.md`.

**Pytest Setup**
- Keep `pytest-asyncio` in `strict` mode.
- Do not use `pytest-asyncio` auto mode if AnyIO is present.
- Prefer explicit `@pytest.mark.anyio` for backend-portable tests.
- Reserve `@pytest.mark.asyncio` for genuinely asyncio-only tests.

`pytest.ini`
```ini
[pytest]
asyncio_mode = strict
markers =
    anyio: portable async test managed by AnyIO
    asyncio: asyncio-only test managed by pytest-asyncio
```

I would not enable `anyio_mode = auto` globally in this mixed-plugin setup. It can work if `pytest-asyncio` is not auto, but explicit marks are cleaner and less flaky.

**Backend Matrix**
Use a shared backend list, and gate `uvloop` by real runtime support.

`tests/conftest.py`
```python
import platform
import sys

import pytest

ANYIO_BACKENDS = [
    pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
    pytest.param(("trio", {}), id="trio"),
]

if sys.platform != "win32" and platform.python_implementation() == "CPython":
    ANYIO_BACKENDS.append(
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop")
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

For the important portable tests, parametrize the backend explicitly:

```python
import pytest

from tests.conftest import ANYIO_BACKENDS


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ANYIO_BACKENDS)
async def test_important_behavior(anyio_backend):
    ...
```

That keeps the full matrix on the important tests only, instead of tripling the whole suite.

**Module-Scoped Async Fixture**
Your module-scoped TCP listener is a trap unless `anyio_backend` has matching scope.

```python
import pytest

from tests.conftest import ANYIO_BACKENDS


@pytest.fixture(scope="module", params=ANYIO_BACKENDS)
def anyio_backend(request):
    return request.param


@pytest.fixture(scope="module")
async def tcp_listener(anyio_backend):
    listener = await make_listener_on_ephemeral_port()
    try:
        yield listener
    finally:
        await listener.aclose()
```

If that fixture starts background tasks, use a readiness handshake, not `sleep()`.

**ContextVars**
AnyIO runs async fixtures and tests in the same task for that runner. If tests mutate `contextvars`, they can leak.

Do this:

```python
token = request_id_var.set("test-value")
try:
    ...
finally:
    request_id_var.reset(token)
```

Or wrap it in a fixture that always resets. If you do not reset tokens, Trio/asyncio differences will expose garbage state in random places.

**What Not To Do**
- Do not leave both AnyIO and `pytest-asyncio` in auto mode.
- Do not mark the same test with both `@pytest.mark.anyio` and `@pytest.mark.asyncio`.
- Do not treat `uvloop` as a third async model; it is only an asyncio runtime option.
- Do not enable `uvloop` on Windows or PyPy; gate it to supported CPython POSIX jobs.
- Do not use a module-scoped async fixture with a function-scoped `anyio_backend`.
- Do not hardcode TCP ports; bind to port `0` or use a free-port fixture.
- Do not use `sleep()` to wait for listener startup; use an explicit readiness signal.
- Do not mutate `ContextVar` state without resetting via the token.

**CI Shape**
- Run portable important tests on `trio` and plain `asyncio` everywhere.
- Add `asyncio+uvloop` only on supported CPython POSIX jobs.
- Keep asyncio-only tests separate with `@pytest.mark.asyncio`.

A sane matrix is:
1. Linux + CPython: `asyncio`, `trio`, `asyncio+uvloop`
2. Windows + CPython: `asyncio`, `trio`
3. PyPy: `asyncio`, `trio`

If you want, I can turn this into a ready-to-drop `conftest.py` and marker layout for your repo.
