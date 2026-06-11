# σ-horizon contract is inconsistent across consumers — RFC (do not blind-fix)

**Status:** diagnosis / RFC. The `sigma` field on candidates and holdings carries **no canonical horizon**, and its two main consumers (Kelly sizing and the σ-aware exits) assume **different** horizons. This is a real-money risk path, so it must be reconciled with a trace + validation — *not* a quick code change (a wrong fix could mis-scale the active `sdl_n_sigma` stop). Filed instead of patched on purpose.

Repo: `renquant-pipeline`. All line numbers as of 2026-06-11 main.

## The field and its producers

`cand.sigma` / `HoldingState.sigma` (same value written to both) has two producers:

1. **NGBoost head** — `ApplyNGBoostTask` writes `cand.sigma = float(sigma_val)` and `hs.sigma = float(sigma_val)` (`job_panel_scoring.py:3023, 3039`). This σ is a **per-period (≈5-day)** forward σ: `HoldingState.sigma` is documented "fwd-5d" (`exits.py:133`) and the exits path converts it with `/√5`.
2. **Realized-vol fallback** — `ApplyRealizedVolFallbackTask` writes `cand.sigma` / `hs.sigma` = **annualized (252-day)** realized vol (`job_panel_scoring.py:3147, 3155`, via `_realized_vol_annualized`), but only when NGB did not already set σ.

So the **same field is 5-day when from NGB and 252-day-annualized when from realized-vol.**

## The consumers disagree about its horizon

- **Kelly** — `_rescale_annualized_sigma_for_kelly` (`job_panel_scoring.py:3200`) treats σ as **252-annualized** and rescales it to the Kelly horizon.
- **σ-aware exits** — `_resolve_daily_sigma` (`exits.py` ~443) treats `state.sigma` as **5-day** and divides by `√5` to get a daily σ for `check_stop_loss` (`stop_n_sigma`) and `check_single_day_loss` (`sdl_n_sigma`).

Cross-tabulating producer × consumer:

| σ source | actual horizon | Kelly assumes 252d | exits assume 5d |
|---|---|---|---|
| NGBoost | ~5d | **wrong** (treats 5d as annual → variance off ~50×, over-sizes) | correct |
| realized-vol | 252d (annual) | correct | **wrong** (treats annual as 5d → daily σ ≈ ×√(252/5)=×7.1 too large) |

## What is latent vs what may be active

- **NGB → Kelly (latent):** NGB is OFF in prod, so the 4–50× Kelly mis-scale is dormant — a landmine the moment `ngboost.enabled=true`. (The config-level guard for this class shipped in pipeline #101; this is the code-level twin.)
- **realized-vol → exits (possibly ACTIVE, timing-dependent):** in prod (NGB off) the realized-vol fallback writes an **annualized** σ that `_resolve_daily_sigma` would treat as 5-day, inflating the daily σ ~7×, which would make the **active** `sdl_n_sigma=3` single-day-loss stop in BULL_CALM fire only at ~7× the intended move (effectively neutered). **BUT** the sell pass (`_make_sell_tctx` → exits) runs in **Phase 2a**, *before* `PanelScoringJob` (Phase 3) writes the realized-vol σ — so at exit time `state.sigma` may still be unset and the exits may correctly fall through to `state.realized_sigma_daily` (a true daily σ, priority 2). **Whether the annualized σ ever reaches `_resolve_daily_sigma` depends on cross-bar state persistence and task ordering and must be traced before any claim or fix.**

## Why this is filed, not fixed

Any "fix" touches a live risk path:
- Making σ **canonically annualized** (annualize the NGB output) fixes Kelly but, if `state.sigma` reaches exits, breaks the exits' `/√5` assumption — i.e. changes the **active** σ-aware SDL stop behaviour.
- Making the **Kelly rescaler source-aware** (stamp `sigma_horizon_days` per source) fixes Kelly safely without touching exits — but only addresses half the contract.

A blind change risks mis-scaling an active stop on real money. The decision-tree audit's own discipline (e.g. the M6 placebo: diagnose, don't force) applies.

## Recommended reconciliation (a dedicated, validated change)

1. **Define one canonical horizon for `sigma`** (recommend **annualized / 252d**, the more standard unit) and stamp `sigma_horizon_days` wherever σ is written (NGB → annualize from its training horizon; realized-vol → already 252).
2. **Make every consumer horizon-aware:** Kelly rescales from the stamped horizon (not an assumed 252); `_resolve_daily_sigma` converts from the stamped horizon to daily (not a hard-coded `/√5`).
3. **Also stamp `mu_horizon_days` on the NGB μ path** (`job_panel_scoring.py:3022`) — currently unset, so the QP horizon guard (`mu_horizon_days != expected`) cannot protect NGB μ.
4. **Trace first:** instrument `_resolve_daily_sigma` to log the σ source + horizon actually used in a live (NGB-off) sell pass, to settle whether the realized-vol→exits path is active.
5. **Validate:** unit tests pinning each producer→consumer horizon; a sim/WF check that the σ-aware SDL stop fires at the intended move size before and after.

## Related
- pipeline #101 (config-level σ==μ preflight guard) — the cousin of this code-level issue.
- The shipped H-2 (SDL defers to trailing) and H-1 (SDL entry-regime anchor) fixes operate on the same SDL stop; this σ-horizon question affects the *threshold* those use.

Agent-Origin: Claude
