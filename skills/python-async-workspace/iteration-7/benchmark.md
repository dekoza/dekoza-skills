# python-async Skill Benchmark — Iteration 7

**Model:** github-copilot/gpt-5.4
**Date:** 2026-03-25
**Evals:** 1–8 (58 unique expectations)
**Runs per configuration:** 1

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|-----------|---------------|-------|
| Pass Rate | 97.92% | 92.26% | **+5.66%** |
| Time (mean) | 50.0s | 65.2s | -15.2s |
| Tokens (mean) | 94,139 | 101,773 | -7,634 |

## Per-Eval Breakdown

| Eval | With Skill | Without Skill | Discriminates? | Missing without skill |
|------|-----------|---------------|----------------|----------------------|
| 1 | 6/6 (100%) | 6/6 (100%) | No (tie) | — |
| 2 | 6/6 (100%) | 5/6 (83%) | **Yes** | `uncancel()` to clear cancellation state |
| 3 | 7/7 (100%) | 6/7 (86%) | **Yes** | Higher-scope `anyio_backend` fixture matching |
| 4 | 7/7 (100%) | 6/7 (86%) | **Yes** | Benchmark-first requirement for uvloop |
| 5 | 10/10 (100%) | 10/10 (100%) | No (tie) | — |
| 6 | 9/9 (100%) | 9/9 (100%) | No (tie) | — |
| 7 | 5/6 (83%) | 5/6 (83%) | No (tie) | Both miss concrete verification step |
| 8 | 7/7 (100%) | 7/7 (100%) | No (tie) | — |

## Key Findings

1. **Only 3 of 8 evals discriminate.** The skill provides value on evals 2, 3, and 4 — all targeting specific AnyIO/asyncio knowledge gaps that gpt-5.4 does not cover natively.

2. **Eval-6 stopped discriminating.** In iteration-5, with_skill scored 8/9 while without_skill scored 7/9. Now both score 9/9 — the model learned the `from_thread.run()` vs `from_thread.run_sync()` distinction.

3. **Eval-5 saturated despite tightening.** Adding failure-observation and admission/backpressure expectations did not break the tie. Both configs score 10/10.

4. **Eval-7 is a shared weakness.** Neither configuration provides a concrete verification step (runnable test/script). Both offer to help if the user pastes code.

5. **The remaining skill value is narrow but real:**
   - `uncancel()` for intentional cancellation suppression (eval-2)
   - Higher-scope `anyio_backend` fixture requirement (eval-3)
   - Benchmark-before-recommend for uvloop (eval-4)

6. **Performance:** The skill is faster and cheaper, likely because it provides direct answers instead of web-searching for AnyIO docs. This is a side benefit, not a quality driver.

## Comparison with Iteration 5

| Metric | Iteration 5 | Iteration 7 | Change |
|--------|------------|-------------|--------|
| with_skill pass rate | 98.61% | 97.92% | -0.69% (eval-7 regression) |
| without_skill pass rate | 83.47% | 92.26% | +8.79% (model improved) |
| Delta | +15.14% | +5.66% | -9.48% (less discrimination) |
| Discriminating evals | 7/8 | 3/8 | -4 evals |
| Expectations | 55 | 58 | +3 new |

The skill delta shrank because gpt-5.4 now handles more AnyIO concepts natively, not because the skill degraded. The skill's with_skill scores remain near-perfect (97.92%).
