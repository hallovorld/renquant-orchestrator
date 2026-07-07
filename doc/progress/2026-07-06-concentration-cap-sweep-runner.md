# 2026-07-06 — Concentration cap sweep runner

**PR**: sweep script for #403 research design

## What

`scripts/run_concentration_cap_sweep.py` — 3D parameter sweep over
`entry_cap × drift_buffer × topup_threshold`, matching #403's frozen grid
exactly. 75 grid variants + 1 A/A control × 3 frozen seeds.

## Grid (matches #403 exactly)

- entry_cap: {8%, 10%, 12%, 15%, 20%}
- drift_buffer: {0%, 8%, 13%, 18%, ∞} — occupies the same `trim_threshold`
  slot `TrimHeldTask` already reads; `∞` maps to `trim_enabled=False`
  (today's incumbent), finite values map to `trim_enabled=True` +
  that `trim_threshold`. No new trigger mechanism.
- topup_threshold: {2%, 3%, 5%}
- 5 × 5 × 3 = 75 combinations

## Round 2 (codex review)

STATUS: fixed
WHAT: four issues — (1) the runner silently narrowed #403's approved 3D
grid to a 2D `entry_cap × topup_threshold` sweep with trim fixed OFF,
redefining the approved contract inside the execution PR instead of
implementing it; (2) the frozen seed rule was broken (hardcoded default
`(0, 1, 2)` plus an arbitrary `--seeds` override); (3) the output contract
was too thin to support the promised verdict (no A/A, no placebo wiring,
no turnover/fill/cost reporting, no per-regime-across-all-regimes check,
no winner-continuation diagnostic); (4) a repeat of the hardcoded-umbrella-
path regression just fixed in #404.
WHY-DIR: codex was right that a narrower study needs its own design PR —
#403 already went through 3 careful review rounds to reach its current
frozen state, so the fix is to implement what it actually specifies, not
propose scope-narrowing inside this PR.
EVIDENCE:
- Grid: rebuilt as the full 75-variant 3D sweep. `drift_buffer` writes
  `trim_enabled`/`trim_threshold` — the pre-existing `TrimHeldTask` slot
  (confirmed via `renquant-pipeline/.../task_trim.py`: `trim_enabled`
  already gates the mechanism, `trim_threshold` is the existing buffer
  value read as `current_pct > kelly_target + trim_threshold`). No
  pipeline-repo change was needed — #403's "config wiring" estimate
  appears to have predated realizing the mechanism was already fully
  wired under its current name.
- Seeds: hard-pinned to `FROZEN_SEEDS = (42, 43, 44)` by default. A
  `--dev-seeds` escape hatch exists for local iteration only, gated behind
  an explicit `--i-know-this-breaks-the-frozen-contract` flag and flagged
  `seeds_frozen: false` in the plan output — no silent override path.
- Output contract: added A/A control (incumbent config, seed-offset
  resplit via `AA_SEED_OFFSET=1000`, same pattern as
  `run_kelly_sigma_horizon_ab.py`), placebo evidence loading via
  `--placebo-json` (same external-script pattern), turnover/fill-count
  computed from `trade_log`'s real `target_pct` field, a modeled cost-delta
  proxy (documented honestly as a proxy — no formal per-trade cost model
  exists anywhere in this sim to read from), per-regime no-material-
  regression checked on all 3 of BULL_CALM/BEAR/BULL_VOLATILE individually
  (not just the primary regime), and a winner-continuation diagnostic
  approximated from entry `target_pct` + exit `pnl_pct` (documented as an
  approximation — this sim exposes discrete trade events, not a continuous
  per-ticker daily weight trace).
- Verdict logic: rewritten as genuine per-seed UNANIMITY (not
  mean/std aggregation) — `unanimity_verdict()` evaluates each of #403's 7
  criteria independently per seed and requires all 3 frozen seeds to agree;
  missing data yields NULL (blocks the verdict), never "average out."
- Path authority: `runtime_paths.default_repo_root()` replaces the
  hardcoded `UMBRELLA_REPO`/`STRATEGY_DIR` constants.
- 17 new tests (`tests/test_run_concentration_cap_sweep.py`) prove: the
  grid is exactly 75 variants matching #403's frozen values; `drift_buffer`
  maps correctly to `trim_enabled`/`trim_threshold`; the frozen seed set is
  used by default and `--dev-seeds` is rejected without the confirmation
  flag; no hardcoded path references remain; turnover/winner-continuation
  compute correctly from synthetic trade logs; and the unanimity verdict
  genuinely requires all 3 seeds to pass (a 2-of-3 pass is NOT enough),
  including the exact #403 round-3 example (candidate keeps BEAR flat,
  improves BULL_CALM, damages BULL_VOLATILE — correctly fails criterion 4).
  Full repo suite: 3163 passed, 3 skipped, 0 failures.
NEXT: a genuine end-to-end execution of the full 75-variant grid has not
been run in this pass (would take hours of wall-clock time per #403's own
estimate) — this round focused on making the contract/structure correct
and unit-tested, per the standing instruction to prioritize that when a
live run is infeasible. The turnover-based cost-delta and winner-
continuation diagnostics are documented proxies, not exact readouts of a
pre-existing cost model or continuous position trace; a future round could
tighten either if the sim harness grows the underlying data (e.g. a daily
per-ticker weight series, or a real commission/slippage model).
