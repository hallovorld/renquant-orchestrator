# The capital funnel, re-measured — and the zero-admissible model behind it

Phase-3 step ⑧ (operator re-planning 2026-08-09). Accounting simulation
from recorded history only (`ticker_daily_state` × `pipeline_runs`,
mode=ro): what actually blocks capital deployment on the CURRENT window,
41 live sessions 2026-05-20..08-07.

Auditability (reviews r1+r2): the derivation is COMMITTED with full
semantics in its docstring (block-EVENT vs unique-candidate counts, as-of
rule, buy definition, gate-order ownership, dedup policy; per-row run_id +
commit_sha + training_cutoff + model_content_sha256) —
`data/2026-08-09-funnel-derivation.py` (versioned read-only query contract)
with its machine-readable outputs (`…-funnel-candidates.csv`, all 5,040+
candidate rows with blocker labels; `…-funnel-sessions.csv`, per-session
counts; `…-funnel-summary.json`) and `data/2026-08-09-funnel-verify.py`,
which re-asserts every quoted number from the committed rows
`[VERIFIED — exit 0 this session]`. The table below is those artifacts,
not prose.

## 1 · The Pareto `[VERIFIED — runs DB aggregation, this session]`

| blocker | candidate-blocks | Kelly mass choked (pp) |
|---|---|---|
| veto:rank_score_below_floor | 2,390 | 0 (vetoed pre-sizing) |
| regime_admission:failed:BULL_CALM | 1,155 | 0 (blocked pre-sizing) |
| not_selected | 737 | 5.6 |
| conviction:mu_below_floor | 277 | 0 |
| qp_delta_below_min_dw | 149 | 12.6 |
| panel_fundamentals_missing | 72 | 0 |
| kelly_zero:mu_le_min_edge | 57 | 0 |
| broker_pending_submitted | 56 | 3.9 |

Bottom line: **3 buys in 41 sessions**; 5,040 block-events; mean cash
fraction **79.1%** `[VERIFIED — live_state_snapshots derivation, committed]`.

VISIBLE CORRECTION (r2): this note first quoted the G-E record's
"~$4,820/yr" cash drag. That figure priced idle cash at the replay panel's
backtest return — the exact rate this same day's work (orch#937/#938)
established as unattainable by the live system. The committed derivation
prices drag at an 8% ASSUMED opportunity rate instead: **~$680/yr** on
mean idle cash. The idle-capital PROBLEM is unchanged (79.1% of the book
does nothing); its dollar cost was overstated ~7× by the old convention.

## 2 · The July diagnosis is stale for this window

The July capital findings (wash-sale mass block, integer-share flooring —
tasks #14, pipeline#223/#224, orch#608) do not appear in this window's top
blockers: those frictions were real and their fixes remain right, but the
funnel now chokes EARLIER — at the score floors and the regime admission
gate. Any grant package ordered by the July picture would spend authority
on non-binding constraints. VISIBLE RE-RANKING below.

## 3 · The root behind the biggest blocker — orch#942

`regime_admission:failed:BULL_CALM` is not noise: the SERVED prod panel
(`artifacts/prod/panel-ltr.alpha158_fund.json`, trained 2026-08-02)
carries trade-monotonicity stamps that admit buys in **zero** of its three
stamped regimes (BULL_CALM eligible-but-failed; BULL_VOLATILE and CHOPPY
not eligible) `[VERIFIED — artifact stamps read, this session]`. The
admission gate is doing its job on a model that should not have been
promoted with those stamps. Full chain and decision fork: orch#942;
adjacent freshness breaches: orch#941 (tournament 47d, prod cutoff
UNKNOWN, shadow 180d).

## 4 · Consequences for the plan (visible re-scoping)

* **⑨ (sizing redesign) is re-scoped BEHIND #942**: sizing governs how
  much to buy; nothing sizes zero admissions. Its prereg waits until a
  buy-admissible model serves.
* **The grant package re-ranks** (see the package table in the progress
  doc): first authority needed is the #942 decision fork (repair the
  retrain/promote lane vs re-examine the monotonicity bar), plus the
  one-line promotion refusal rule for zero-admissible stamps. The July
  asks (fractional/wash-sale switches, alerts.py sync) remain queued but
  are no longer capital-critical on this window.

## 5 · What this does not show

Whether relaxing the rank floor or qp_delta threshold would have MADE
money — that requires the per-gate relaxation backtest, which is only
meaningful after #942 (today it would simulate feeding a model that
cannot buy).
