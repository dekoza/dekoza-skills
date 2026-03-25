No. Do not enable `uvloop` automatically inside a public async library.

`uvloop` is an `asyncio` event loop implementation. It is not a third async model, and it does nothing for Trio. That alone is enough to keep it out of a portability-facing library API.

Why your current idea is wrong:

- A library should not silently choose the process event loop for its users.
- `uvloop` does not support Windows, so auto-installing or requiring it would immediately make your library less portable for your own developers and for downstream users.
- The old policy-based wiring is the wrong direction now anyway: Python 3.14 docs mark asyncio policies as deprecated and recommend `asyncio.run(..., loop_factory=...)` or `asyncio.Runner(loop_factory=...)` instead.
- Performance claims without measurement are hand-waving. You should recommend `uvloop` only when you have benchmark or deployment evidence that your actual workload benefits from it.

Where `uvloop` belongs:

- In the application/runtime entrypoint.
- In deployment-specific startup code for supported platforms, typically Linux or macOS.
- As an optional runtime choice for asyncio apps, not as a behavior your reusable library forces on everyone.

Modern wiring for a supported asyncio app:

```python
import uvloop


async def main() -> None:
    ...


if __name__ == "__main__":
    uvloop.run(main())
```

If you need a runner explicitly:

```python
import asyncio
import uvloop


async def main() -> None:
    ...


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main())
```

Practical rule:

- Public library: stay compatible with the caller's event loop choice.
- Asyncio application: optionally enable `uvloop` at the top-level entrypoint.
- Trio application: `uvloop` is irrelevant.
- Cross-platform product with Windows support: gate `uvloop` by platform/runtime support and keep a normal asyncio path.

Recommendation:

 - Do not bake `uvloop` into the library.
 - Document it as an optional app-level optimization for supported asyncio deployments.
 - Only recommend it by default after benchmarking your real production workload.

Sources used:

- Python docs: `https://docs.python.org/3/library/asyncio-runner.html`
- Python docs: `https://docs.python.org/3/library/asyncio-policy.html`
- `uvloop` README: `https://github.com/MagicStack/uvloop`
- `uvloop` packaging metadata and setup guards, which show non-Windows support.
