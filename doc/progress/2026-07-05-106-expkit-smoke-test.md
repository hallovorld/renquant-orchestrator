# 106 expkit smoke test

Date: 2026-07-05

## What changed

Added `scripts/expkit_smoke_test.py` — exercises the full 106 experiment
framework flow with synthetic data: FrozenSpec → write/load → per_date_ic →
block_bootstrap → multi_seed_unanimity → evidence manifest → verify.

All paths pass. Framework's plumbing and statistical-evaluation logic are
verified correct end-to-end on synthetic data (see Round 2) — this is a
harness/mechanics check, not evidence that a real WF-gate corpus experiment
would pass the frozen bars.

## N2 PIT collector status

Already deployed: `com.renquant.pit-estimate-snapshot` running, 102 snapshots
collected (latest 2026-07-03), weekdays 14:30. No action needed.

## Round 2 (Codex review)

Codex held this PR on two issues in the smoke test's own evaluation logic:

1. **Criterion/statistic mismatch.** The frozen criterion `paired_delta_p`
   (`threshold=0.05`, `direction="lt"`, described as "paired delta
   significance") was being evaluated against `lb_one_sided` (a confidence
   bound from `summarize_boot`), not an actual p-value — the test froze one
   decision rule and evaluated a different one. Fixed by computing a genuine
   one-sided bootstrap-percentile p-value from the SAME resample distribution
   already used for the CI/lb (`paired_delta_p_value = np.mean(boot <= 0.0)`
   — the Monte Carlo equivalent of `exact_block_tail_masses`'s exact
   `p_le_threshold`; exact enumeration isn't feasible here since
   n_dates=200/block=20 implies 200**10 tuples, far past
   `EXACT_ENUM_LIMIT=300_000`). `paired_delta_p` is now evaluated against
   this real p-value.
2. **Weak `all_ok` pass condition.** Previously only required
   `mean_ic_genuine > 0`, `criterion_ic_met is not None` (true even if the
   criterion FAILED), and `manifest_ok` — never actually requiring the frozen
   criteria to pass. Fixed: `all_ok` now requires `criterion_ic_met is True`
   AND `criterion_paired_delta_p_met is True` AND `manifest_ok`. `verdict`
   is now `GO` only if both frozen criteria are met (was: only `genuine_ic`).

Re-ran with the corrected logic: `paired_delta_p_value=0.0000`,
`criterion_paired_delta_p_met=True`, `verdict=GO`, `all_ok=True` — the
smoke test still genuinely passes end-to-end on the corrected, stricter
logic (synthetic data has strong signal-by-construction, so this is
expected, not evidence-shopped). `make test`: 2622 passed, 3 skipped (2
pre-existing unrelated failures in `test_bundle_consistency_ci_gate.py`
confirmed reproducing identically on clean `origin/main` this session).
`[VERIFIED — ran corrected script + full suite, this session]`
