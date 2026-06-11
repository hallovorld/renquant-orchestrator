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

## What is latent vs what is ACTIVE

- **NGB → Kelly (latent):** NGB is OFF in prod, so the 4–50× Kelly mis-scale is dormant — a landmine the moment `ngboost.enabled=true`. (The config-level guard for this class shipped in pipeline #101; this is the code-level twin.)
- **realized-vol → exits (CONFIRMED ACTIVE — traced 2026-06-11):** the prod σ-aware single-day-loss stop in BULL_CALM uses a daily σ that is **≈7.1× too large**, effectively neutering it. Trace:
  1. `ApplyRealizedVolFallbackTask` (`job_panel_scoring.py:3159`, gated by `ranking.kelly_sizing.use_realized_vol_fallback` which is **true** in prod) writes `hs.sigma` = **annualized** realized vol, and **skips when `hs.sigma` is already finite** (`:3155`) — so once set it stays annualized.
  2. `hs.sigma` is **persisted to and reloaded from `live_state`** (`persistence.py:1150` serialize, `:1283/:1747` deserialize) — it carries across bars. `task_sell.py:227` documents `hs.sigma` as "set by PanelScoringJob in the previous bar."
  3. `PrepareHoldingTask` (`task_sell.py:81–97`) sets the *daily* `realized_sigma_daily` each bar but **does NOT reset `state.sigma`** — and its own comment still assumes "(state.sigma is None)", which is stale.
  4. Therefore at the next bar's sell pass (Phase 2a) `state.sigma` ≠ None (it holds the persisted annualized value), so `_resolve_daily_sigma` takes **priority 1** and returns `annualized / √5` instead of falling through to the correct `realized_sigma_daily` (priority 2). Daily σ is overstated by `√(252/5) ≈ 7.1×`.
  5. **Impact:** in BULL_CALM (the trading regime) `max_single_day_loss_pct = 0` and `sdl_n_sigma = 3`, so the SDL threshold is `3 · daily_σ` and now fires only near a **3·7.1 ≈ 21×** true-daily-σ move (~40% gap-down for a 2%-σ name) instead of the intended ~6%. The configured σ-aware single-day-loss protection is **effectively OFF in prod.** `_resolve_daily_sigma`'s docstring claim that "state.sigma is always None in prod" is **false** and is the source of the error.

## A targeted, low-risk fix for the confirmed-active half

The exits already have an **unambiguously-daily** field, `realized_sigma_daily` (set every bar by `PrepareHoldingTask`). The bug is only that the **ambiguous** `state.sigma` (annualized in prod) shadows it at priority 1. The minimal correct fix:

> In `_resolve_daily_sigma`, **prefer `realized_sigma_daily` (already daily) over `state.sigma`** — i.e. swap the priority, or only use `state.sigma/√5` when `realized_sigma_daily` is absent.

In prod (NGB off, `realized_sigma_daily` always populated) this yields the **correct daily σ** and the σ-aware SDL fires as configured. It changes no NGB-on behaviour materially (a clean realized daily vol is a fine σ source).

**Caveat that makes this an operator decision, not a silent ship:** the fix **re-activates a currently-dormant live stop** — the BULL_CALM σ-aware SDL goes from "fires near ~40%" to "fires near ~6%", a real behaviour change on real money. It should ship **behind a flag (default = current behaviour)** and be validated (does it cull winners? — note it interacts with the shipped H-2 "SDL defers to trailing on winners" and H-1 anchor), with a sim/WF check of SDL fire-rate and net Sharpe before activation. A blind flip is exactly the kind of stop-mis-scaling change the decision-tree audit's discipline (M6: diagnose, don't force) warns against.

## Why the broader contract still needs reconciliation

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
