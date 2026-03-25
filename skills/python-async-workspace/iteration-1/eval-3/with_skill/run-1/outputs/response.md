Answer mode: `AnyIO-portable`

References used: `references/testing.md`, `references/backend-uvloop.md`, `references/decision-matrix.md`

The flakiness is not mysterious. You broke pytest by putting both async plugins in auto mode. AnyIO's docs explicitly warn that `anyio_mode = auto` conflicts with `pytest-asyncio` auto mode.

Use this setup instead:

```ini
# pytest.ini
[pytest]
anyio_mode = auto
asyncio_mode = strict
```

```python
# conftest.py
import pytest


@pytest.fixture(
    params=[
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param(("trio", {}), id="trio"),
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio+uvloop"),
    ]
)
def anyio_backend(request):
    return request.param
```

Use `@pytest.mark.anyio` on the important tests that must stay backend-portable. Keep `@pytest.mark.asyncio` only for genuinely asyncio-only tests.

```python
import pytest


@pytest.mark.anyio
async def test_service_round_trip():
    ...
```

What this means:

- `trio` and plain `asyncio` are the serious portability matrix.
- `asyncio+uvloop` is an extra asyncio runtime axis.
- `uvloop` does not replace Trio coverage.
- `uvloop` is only worth running on supported CPython/POSIX CI jobs.

What not to do:

- Do not leave both plugins in auto mode.
- Do not pretend `pytest-asyncio` can cover Trio. It cannot.
- Do not treat `uvloop` as a third async model. It is still asyncio.
- Do not claim backend neutrality if the suite only ran on asyncio.
- Do not enable `uvloop` as a correctness fix. It is runtime tuning, not a semantic repair.

Recommended split:

- Portable tests: `@pytest.mark.anyio` + the `anyio_backend` matrix above.
- Asyncio-only tests: `@pytest.mark.asyncio` and no Trio claim.
- If the full 3-axis matrix is too expensive, keep `asyncio` + `trio` as the default serious matrix and run `asyncio+uvloop` on the critical subset or a dedicated CI job.

Verification strategy:

- Run the important AnyIO tests and confirm they execute under `asyncio`, `trio`, and `asyncio+uvloop`.
- Gate the `asyncio+uvloop` job to supported runtime/platform combinations.
- If you claim portability, failures on either `trio` or plain `asyncio` block that claim.

The highest-risk footgun is simple: mixing AnyIO auto mode with `pytest-asyncio` auto mode and then misreading plugin fights as random CI flakes.
