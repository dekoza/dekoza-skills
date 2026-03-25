# Skill Benchmark: python-async

**Model**: github-copilot/gpt-5.4
**Date**: 2026-03-25T16:06:21Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 runs each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 99% ± 4% | 83% ± 8% | +0.15 |
| Time | 60.1s ± 16.1s | 69.8s ± 31.0s | -9.8s |
| Tokens | 3930 ± 1103 | 3848 ± 1613 | +82 |

## Notes

- Iteration 5 still has one run per eval/config pair, so the delta is directional evidence, not a stability claim.
- The skill still beats baseline on 7 of 8 evals (1, 2, 3, 4, 6, 7, 8), ties only on eval 5, and never loses.
- Eval 5 remains saturated even after tightening: both configurations now pass 8/8, so it is still measuring general asyncio review competence more than distinct skill value.
- Eval 6 improved from the earlier broken with-skill run and now discriminates: with-skill scores 8/9 while baseline scores 7/9. The remaining with-skill miss is the exact callable split between `from_thread.run()` for async callables and `from_thread.run_sync()` for loop-thread sync callbacks.
- Eval 4 remains a strong discriminator for `uvloop` framing: with-skill gets 7/7 while baseline gets 5/7 by missing the explicit `asyncio` event-loop framing and the benchmark-first requirement.
- Eval 3 and eval 7 still separate the skill from baseline on AnyIO-specific semantics rather than generic async talk: same-task `contextvars` leakage in the test runner and concrete verification guidance.
- Time looks better with the skill in this iteration (`-9.8s` mean), but with a single sample per eval and wide variance, pass-rate separation is the trustworthy signal and timing is secondary.
- Token cost stays nearly flat (`+82` mean), so the sharper answers are not being bought with a large systematic verbosity penalty.
