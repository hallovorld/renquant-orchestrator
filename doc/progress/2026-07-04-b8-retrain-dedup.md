# B8: Retrain operator dedup (campaign B8)

**Date**: 2026-07-04
**PR**: (this PR)
**Campaign item**: B8 — single shared retrain operator module + anti-skew test

## What

Extracted 7 duplicated functions from `retrain_alpha158_fund.py` (1658L) and
`retrain_alpha158_linear.py` (277L) into a new `retrain_common.py` shared module.

### Extracted (behavior-identical)

| Function | Lines saved | Notes |
|---|---|---|
| `subrepo_srcs` | ~3 | Identical in both |
| `subrepo_pythonpath` | ~15 | Fund adds `RENQUANT_STRATEGY_CONFIG`; handled via optional kwarg |
| `run_subprocess` | ~7 | Fund passes strategy_config through; linear delegates directly |
| `read_json_object` | ~10 | Fund lacked explicit `encoding="utf-8"` (no behavior change for JSON) |
| `resolve_path` | ~3 | Identical |
| `staging_path` | ~2 | Identical |
| `validate_repo_dir` | ~5 | Identical |

### Kept specialized (NOT unified)

- `_validate_scorer_artifact` — fund checks GBDT fields, linear checks `panel_linear`
- `_validate_calibrator_artifact` — fund checks binding fingerprint, linear checks kind
- `build_pipeline` — completely different pipeline compositions

## How

- New `src/renquant_orchestrator/retrain_common.py` (105 lines): shared functions +
  `RetrainContextLike` protocol for typing `run_subprocess`.
- Fund module: thin `_run` wrapper calls `run_subprocess` with
  `env_strategy_config=_fund_strategy_config()`.
- Linear module: thin `_run` wrapper calls `run_subprocess` directly.
- Tests updated to monkeypatch `retrain_common.subprocess` instead of
  `mod.subprocess`.
- Unused imports removed from both modules (`subprocess` from both, `json`/`os` from linear).

## Verification

- All 1912 tests pass (`make test`).
- The 3 divergent validators intentionally kept separate per campaign audit guidance.
