No. Enabling `uvloop` inside a public async library is the wrong layer.

- Your thesis, steelmanned: “We can give users free speed by turning on `uvloop` for them.” Nice idea, wrong boundary.
- The biggest flaw: a library should not choose the process-wide event loop implementation. That is application/runtime policy, not library behavior.
- `uvloop` is not a universal baseline anyway. Its published metadata targets `CPython` and OS classifiers `POSIX` / `MacOS`, not Windows. If your library supports Windows developers, auto-enabling it bakes in a platform split.
- The old global-policy style is also aging out. Python’s `asyncio` docs say the policy system is deprecated and will be removed in 3.16, and recommend `loop_factory` instead of policies.
- So if your library calls `uvloop.install()` or otherwise swaps the loop behind the user’s back, you are coupling your API to a runtime choice that users may not support, want, or be able to install.

Where `uvloop` belongs:

- In the application entrypoint.
- In a server bootstrap layer.
- In a CLI `main()`.
- In deployment/runtime config owned by the app, not by reusable library code.

Modern wiring for a supported asyncio app:

```python
import asyncio
import uvloop

async def main() -> None:
    ...

if __name__ == "__main__":
    asyncio.run(main(), loop_factory=uvloop.new_event_loop)
```

If you need multiple top-level async calls in one loop:

```python
import asyncio
import uvloop

with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
    runner.run(main())
```

If you want the shortest app-facing helper and you already depend on `uvloop`, its README says the preferred API since `uvloop 0.18` is:

```python
import uvloop

uvloop.run(main())
```

What your library should do instead:

- Stay compatible with the standard `asyncio` loop.
- Avoid import-time side effects or loop installation.
- Document an optional “use `uvloop` in production” recipe for apps.
- If you ship an app/CLI alongside the library, enable `uvloop` there, not in the reusable library package.

Highest-risk issue:

- Silent global runtime mutation. That is the kind of “helpful” optimization that turns into platform bugs, test weirdness, and support debt.

If you want, I can draft a small compatibility policy for your README: library stance, optional extra, and version-gated entrypoint examples for `3.11` vs `3.12+`.