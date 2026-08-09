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

Bottom line: **3 SELECTION EVENTS in 41 sessions — all from a single run
on 2026-05-22 (BAC, D, WFC), each with a trades-table row and ZERO broker
order receipts** `[VERIFIED — trades join, committed selections CSV]`.
"selected=1" is a pipeline state; execution at the broker is NOT provable
from this DB (broker_order_id is empty on every buy row in the window), so
every capital-deployment claim here is about the pipeline's willingness to
deploy, not confirmed fills. Also: 5,040 block-events; mean cash fraction **79.1%** `[VERIFIED —
live_state_snapshots derivation, committed]`.

DECISION UNITS (r3, review P0; cadence corrected r5): the funnel's
population is the window's 70 candidate-bearing live runs — mean 1.7 per
candidate date, max 10, and 9 of the 41 dates have more than one
`[VERIFIED — committed summary runs_per_day + candidates CSV]` — each
with buy-order authority, so the primary funnel counts every such run as
a decision attempt (UNIT A); the last-run-per-date slice (UNIT B) is committed
alongside as sensitivity, with an is_canonical flag on every row. Rank 1
(the rank-score floor) is IDENTICAL under both units (2,390 / 1,563
events); ranks 2-3 swap (BULL_CALM admission concentrates in intraday
cycles: 1,155 under A vs 368 under B) — stated; and the #942 root cause is
unit-independent (the artifact's stamps admit buys in zero regimes
regardless of which run you count).

VISIBLE CORRECTION (r5): the r3 push (this note, the derivation
docstring, its commit message, and two PR comments) stated the cycle
cadence as "mean ~35 per day `[VERIFIED — committed summary]`". The
committed summary says **1.7**. The ~35/day figure is the TOTAL live
pipeline cadence — 1,835 runs over the window, ≈33/day `[VERIFIED —
read-only pipeline_runs count, this session]` — dominated by runs that
carry no buy-candidate rows (the intraday sell-only cadence) and are
outside this population. No committed number changes; the prose and its
tag were wrong, not the data.

VISIBLE CORRECTION (r2): this note first quoted the G-E record's
"~$4,820/yr" cash drag. That figure priced idle cash at the replay panel's
backtest return — the exact rate this same day's work (orch#937/#938)
established as unattainable by the live system. The committed derivation
prices drag at an 8% ASSUMED opportunity rate instead: **~$680/yr** on
mean idle cash. The idle-capital PROBLEM is unchanged (79.1% of the book
does nothing); its dollar cost was overstated ~7× by the old convention.

## 2 · Current-window triage (provisional; NOT a cross-period conclusion)

The July capital findings (wash-sale mass block, integer-share flooring —
tasks #14, pipeline#223/#224, orch#608) do not appear in this window's top
blockers: those frictions were real and their fixes remain right; ON THIS WINDOW the
funnel chokes earlier — at the score floors and the regime admission gate.
This is a provisional triage observation for the current window only, not
a general prioritization rule; the re-ranking below is scoped accordingly.

## 3 · The root behind the biggest blocker — orch#942

`regime_admission:failed:BULL_CALM` is not noise: the SERVED prod panel
— repo-qualified path
`RenQuant:backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`
(umbrella repo `hallovorld/RenQuant`, tracked file; `trained_date`
2026-08-02, sha256 `6461b827ab23…` `[VERIFIED — read + shasum -a 256 this
session; working tree matches umbrella HEAD blob]`) —
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
  buy-admissible model serves — a provisional, current-window triage
  ordering (review P1), not a standing law.
* **The grant package re-ranks** (see the package table in the progress
  doc): first authority needed is the #942 decision fork (repair the
  retrain/promote lane vs re-examine the monotonicity bar), plus the
  one-line promotion refusal rule for zero-admissible stamps. The July
  asks (fractional/wash-sale switches, alerts.py sync) remain queued but
  are no longer capital-critical on this window.

## 5 · What this does not show

Whether relaxing the rank floor or qp_delta threshold would have MADE
money — that requires the per-gate relaxation backtest. Per review, its
timing-safe read-only DESIGN (conditioned on the exact served artifact
and historical availability) can be drafted now; its execution is
interpretable only after #942 (today it would simulate feeding a model
that cannot buy), and it must not feed promotion.
