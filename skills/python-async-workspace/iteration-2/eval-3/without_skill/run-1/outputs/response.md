The flaky part is not mysterious: both plugins in `auto` is the wrong setup. AnyIO’s docs explicitly warn that `anyio_mode = "auto"` conflicts with `pytest-asyncio` in `auto`. For a mixed suite, let AnyIO own the cross-backend tests, and keep `pytest-asyncio` in `strict`.

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
# Do not set anyio_mode = "auto" in a mixed AnyIO + pytest-asyncio suite.
```

Use AnyIO explicitly for the backend matrix:

```python
# conftest.py
import pytest
from anyio import create_task_group, create_tcp_listener
from anyio.abc import SocketAttribute, SocketStream


@pytest.fixture(
    scope="module",
    params=[
        pytest.param(
            ("trio", {"restrict_keyboard_interrupt_to_checkpoints": True}),
            id="trio",
        ),
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop"),
    ],
)
def anyio_backend(request):
    return request.param


@pytest.fixture(scope="module")
async def tcp_listener(anyio_backend):
    async def handle(stream: SocketStream) -> None:
        async with stream:
            payload = await stream.receive()
            await stream.send(payload)

    async with await create_tcp_listener(local_host="127.0.0.1") as listener:
        port = listener.extra(SocketAttribute.local_port)
        async with create_task_group() as task_group:
            task_group.start_soon(listener.serve, handle)
            yield port
            task_group.cancel_scope.cancel()
```

And mark the important tests with AnyIO:

```python
# test_listener.py
import anyio
import pytest

pytestmark = pytest.mark.anyio


async def test_round_trip(tcp_listener):
    async with await anyio.connect_tcp("127.0.0.1", tcp_listener) as stream:
        await stream.send(b"ping")
        assert await stream.receive() == b"ping"
```

For asyncio-only tests that are not supposed to run on Trio, keep using `pytest-asyncio` explicitly:

```python
import pytest

@pytest.mark.asyncio
async def test_asyncio_only_behavior():
    ...
```

What not to do:

- Don’t set both `anyio_mode = "auto"` and `asyncio_mode = "auto"`.
- Don’t ask `pytest-asyncio` to solve Trio coverage; it only manages asyncio.
- Don’t use the default function-scoped `anyio_backend` with a module-scoped async fixture; define your own scoped `anyio_backend`.
- Don’t hard-code TCP ports; bind ephemerally or use AnyIO’s free-port fixtures.
- Don’t blur ownership of the same test; cross-backend tests should be `@pytest.mark.anyio`, asyncio-only tests should be `@pytest.mark.asyncio`.

One more sharp edge: a higher-scoped async fixture means a longer-lived AnyIO test runner. That is fine for a shared listener, but it also means shared async state can leak farther, so keep that fixture narrowly scoped and avoid mutating shared context in those tests.

If you want, I can turn this into a ready-to-drop `pyproject.toml` + `conftest.py` layout for your repo.
