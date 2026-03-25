# Execution Transcript

## Eval Prompt

Should I enable uvloop in my public async library so users get better performance automatically? We also have Windows developers, and our supported runtime policy includes multiple CPython versions. If not, where does uvloop actually belong and what is the modern way to wire it in for a supported asyncio app?

## Configuration

- Mode: with_skill
- Skill expected: True
- Model: github-copilot/gpt-5.4

## Event Summary

- Tool use: skill:python-async
- Tool use: skill:court-jester
- Step finished: tool-calls
- Tool use: read
- Tool use: read
- Tool use: read
- Step finished: tool-calls
- Tool use: webfetch
- Tool use: webfetch
- Tool use: webfetch
- Step finished: tool-calls
- Tool use: webfetch
- Step finished: tool-calls
- Step finished: stop

## Skill Trigger Check

- python-async skill triggered: True

## Final Response

No. Enabling `uvloop` inside a public async library is the wrong layer.

- Mode: `asyncio-runtime-specific`
- `uvloop` is an `asyncio` event loop implementation, not a library API feature and not a correctness feature.
- A public library should not silently pick the user's loop, own top-level runners, or make Windows users second-class citizens.
- Your support policy makes auto-enablement worse: current `uvloop` support is CPython on POSIX/macOS, not Windows, so "automatic for everyone" is false on day one.

**Thesis**

You want users to get free performance by default, without extra setup.

**Antithesis**

That is brittle. A library that auto-installs or auto-selects a loop is stealing runtime control from the application. It also couples your library to platform-specific packaging and version support you do not actually own.

**What actually belongs where**

- `uvloop` belongs in app startup, CLI entry points, service bootstrap, benchmarks, and runtime-specific test axes.
- It does not belong in reusable library APIs.

**Modern wiring**

For an `asyncio` app you own:

```python
import asyncio
import uvloop

async def main() -> None:
    ...

if __name__ == "__main__":
    asyncio.run(main(), loop_factory=uvloop.new_event_loop)
```

Or, with newer `uvloop` style:

```python
import uvloop

async def main() -> None:
    ...

if __name__ == "__main__":
    uvloop.run(main())
```

If you need multiple top-level calls in one loop:

```python
import asyncio
import uvloop

with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
    runner.run(main())
```

For an AnyIO app bootstrap:

```python
import anyio

async def main() -> None:
    ...

anyio.run(main, backend="asyncio", backend_options={"use_uvloop": True})
```

**What not to do**

- Do not call `uvloop.install()` as the default modern pattern.
- Do not rely on event-loop policies; Python docs deprecate that system and say to use `loop_factory` instead.
- Do not call runners from inside library code.
- Do not claim `uvloop` as a portability feature; it is still asyncio-only.

**Best synthesis**

- Keep the library loop-agnostic.
- Put `uvloop` behind an optional app-level toggle or extra.
- Enable it only in supported deployments, and benchmark before advertising it as a win.

**Highest-risk issue**

The real footgun is not performance. It is hidden runtime ownership. Once a library starts deciding the event loop, it breaks composition and makes framework/app integration harder.

**Practical policy**

1. Library: no automatic `uvloop`.
2. App/CLI/service: optional `uvloop` in bootstrap.
3. Framework-owned loop: configure it at the server/framework layer, not from inside request-handling code.
4. CI: test normal asyncio everywhere; add a separate `uvloop` axis only on supported CPython POSIX targets.

Verified against Python `asyncio` runner docs, `uvloop` README/PyPI metadata, and AnyIO backend options docs.
