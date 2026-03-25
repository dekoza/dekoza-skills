The flaky setup is caused by a real plugin conflict: `anyio_mode = "auto"` and `asyncio_mode = "auto"` both try to claim async tests. That is exactly what AnyIO warns against. In a mixed AnyIO + `pytest-asyncio` suite, keep `pytest-asyncio` in strict mode and let the cross-backend tests opt into AnyIO explicitly.

Recommended pytest setup:

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "strict"
markers = [
  "anyio: run this test via the AnyIO pytest plugin",
]
```

```python
# conftest.py
import pytest


@pytest.fixture(
    params=[
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop"),
        pytest.param(
            ("trio", {"restrict_keyboard_interrupt_to_checkpoints": True}),
            id="trio",
        ),
    ]
)
def anyio_backend(request):
    return request.param
```

Use that backend matrix only for the tests that are supposed to be portable:

```python
import pytest


@pytest.mark.anyio
async def test_retry_and_cancellation_semantics(anyio_backend):
    ...
```

If you also have asyncio-only tests, keep them separate and explicit:

```python
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def asyncio_service():
    ...


@pytest.mark.asyncio
async def test_asyncio_only_integration(asyncio_service):
    ...
```

What to do:

- Use `@pytest.mark.anyio` plus `anyio_backend` for the portability matrix.
- Keep `pytest-asyncio` in `strict` mode so it only handles tests you explicitly mark with `@pytest.mark.asyncio`.
- Treat `trio`, plain `asyncio`, and `asyncio+uvloop` as three meaningful runtime targets for important backend-agnostic tests.
- Treat `asyncio+uvloop` as extra coverage on the asyncio branch, not as a substitute for Trio.

What not to do:

- Do not set both `anyio_mode = "auto"` and `asyncio_mode = "auto"`.
- Do not switch `pytest-asyncio` to auto mode in a suite that also needs Trio coverage.
- Do not put both `@pytest.mark.anyio` and `@pytest.mark.asyncio` on the same test.
- Do not assume passing on `asyncio+uvloop` proves portability; it tells you nothing about Trio-specific scheduling and cancellation behavior.
- Do not force the entire suite through the 3-backend matrix if some tests are intentionally asyncio-specific; mark only the contract tests that should be backend-neutral.

References used:

- Official AnyIO testing docs: `https://anyio.readthedocs.io/en/stable/testing.html`
- Official `pytest-asyncio` concepts docs: `https://pytest-asyncio.readthedocs.io/en/stable/concepts.html`

Verification strategy:

- Verified the auto-mode conflict and the `anyio_backend` tuple form against the official AnyIO testing docs.
- Verified that `pytest-asyncio` strict mode is the intended coexistence mode for multi-backend suites against the official `pytest-asyncio` concepts docs.
- Did not run local pytest commands here because this repository does not include the async test plugins in `pyproject.toml`, so execution claims would have been made up.
