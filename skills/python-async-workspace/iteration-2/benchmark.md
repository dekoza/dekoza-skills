# Skill Benchmark: python-async

**Model**: github-copilot/gpt-5.4
**Date**: 2026-03-25T15:00:50Z
**Evals**: 1, 2, 3, 4, 5, 6, 7, 8 (1 runs each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 95% ± 9% | 83% ± 12% | +0.12 |
| Time | 68.4s ± 28.8s | 60.9s ± 29.3s | +7.4s |
| Tokens | 3401 ± 1055 | 3530 ± 1641 | -129 |

## Notes

- This iteration does not actually contain 3-run replications despite `runs_per_configuration: 3`; `benchmark.json` only has one `run_number` for each eval/config pair. The pass/fail patterns are still useful, but claims about flakiness or stability are weak because there is no repeated sampling inside an eval.
- The hardened evals now show real skill value, but it is concentrated: with-skill beats baseline on 5 of 8 evals (1, 2, 4, 6, 7), ties on 3 evals (3, 5, 8), and never loses an eval. That is more informative than the aggregate `+0.12` pass-rate delta alone.
- Evals 3 and 5 are fully saturated at 100% for both configurations, so those prompts currently measure general async competence rather than discriminating skill value.
- Eval 8 is also near-saturated in a weaker way: both configurations hit 4/5 and miss the same `TaskGroup.start()` / `RuntimeError` readiness-failure assertion. That is a remaining model weak spot, not evidence of skill advantage.
- The strongest discriminating assertions are narrow and explicit rather than generic: only the with-skill run explicitly states vendor-spawned native tasks sit outside AnyIO cancellation ownership (eval 1), explicitly ranks cancellation semantics as the top risk (eval 2), frames `uvloop` as an asyncio loop implementation and requires benchmark/deployment justification (eval 4), adds the foreign-thread cancellation caveat (eval 6), and gives concrete verification steps for AnyIO semantics (eval 7).
- Eval 4 is the clearest proof that the hardened assertions are doing useful work: baseline still sounds broadly correct but misses 2 of 7 sharper claims, while with-skill passes 7/7. The eval is distinguishing between generally competent async advice and the specific portability/runtime framing this skill is supposed to enforce.
- Eval 6 shows a pattern the aggregate pass rate hides: the skill improves the score from 4/6 to 5/6, but both configurations still miss the same exact-scope assertion about `from_thread.run()` / `from_thread.run_sync()` only working directly from AnyIO worker threads spawned via `to_thread.run_sync()`. The bridge-boundary guidance is still not fully pinned down.
- Resource trade-offs are not one-directional. The mean `+7.4s` slowdown hides a 4-faster / 4-slower split, with eval 6 (`132.8s` vs `44.6s`) doing most of the damage. This looks like a few costly prompts rather than a universal latency tax from the skill.
- Token usage is similarly mixed: with-skill uses fewer tokens on evals 1, 3, 5, 6 and more on 2, 4, 7, 8. The aggregate `-129` token delta is basically a wash, so the stronger claim is better specificity without systematic token inflation, not meaningful token savings.
- Most remaining misses are about explicitness, not core direction: baseline answers often land in the right family, and the skill's value is forcing sharper formulations, boundary disclaimers, and concrete verification language. If that is the intended value proposition, the hardened evals are now measuring it.
