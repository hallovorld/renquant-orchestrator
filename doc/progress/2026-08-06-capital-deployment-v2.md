# Capital deployment v2 — one causal chain, and v1 was wrong   (PR #877)

STATUS:    delivered. Design doc only — no production surface touched, no code changed.

WHAT:      Replaces orch#848's "three separate defects" framing with a single measured
           causal chain (regime cap → hard-coded confidence multiplier → conviction
           multiplier → sigma multiplier → int() flooring) and names the dominant
           cause: `conviction_multiplier` still calibrated for the retired XGB
           `rank:pairwise` raw-score scale (~0.02-0.15) after the 2026-08-04 z-blend
           switch made `panel_score` a z-composite (range roughly -2.7..+4.1). A
           same-day self-correction (commit `b89fb3c`) then revises the ordering after
           a second, independent 30-session audit: chronic idle buying power is ~80%
           (not the 47% v1 led with), `VetoWeakBuysTask`'s relative floor starves the
           funnel upstream of sizing, and even funded sessions deploy a median 4.3% of
           available cash — so R1 (re-calibrate `sizing.ceiling`) is necessary but not
           sufficient. Revised again after review: new R0b (fix the 23% session-loss
           rate) ranks above R1, since it is proven and needs no experiment; new R0
           (absolute-or-relative veto floor) is demoted from "highest" to a
           **hypothesis to test**, pending a bounded experiment (candidate rules,
           frozen in-sample/holdout windows, baseline, risk constraints, predeclared
           decision criteria) — its evidence shows the current floor admits few names,
           not that a looser floor improves rather than degrades book quality.

WHY/DIR:   GOAL-5 P0, operator-escalated cash-drag/position-cap issue. orch#848 was
           written before the in-flight blind spot (orch#866), the TSLA-fill
           retraction (orch#854), and this sizing-cascade measurement existed.
           Supersedes orch#848's framing; does not implement any of R0/R0b/R1/R2/R3/R4
           — those remain operator-authorized follow-up work in strategy-104/pipeline.

EVIDENCE:
| claim | value | provenance |
|---|---|---|
| all six live 2026-08-04 orders reproduce to logged precision via the cascade | DDOG 2.62%, SOFI 1.53%, NVDA 1.93%, GOOG 3.40%, WELL 6.31%, VLO 5.59% | [VERIFIED — `data/runs.alpaca.db` + Alpaca filled-order API, replayed against `sizing.py`/`task_selection.py`] |
| conviction_multiplier saturates or zeroes most of the universe | n=94, 39.4% conviction=1.00 (saturated), 52.1% conviction=0.00 -> unbuyable | [VERIFIED — run `2026-08-05-live-2d99f969`] |
| chronic idle buying power, not 47% | today 73.5%, 30-session median 80.9%, min 65.2%, 54 consecutive sessions >=58.8% idle, last <=50% idle was 2026-05-19 | [VERIFIED — prior work, commit `b89fb3c`, 30-session audit against `data/runs.alpaca.db` + Alpaca account API] |
| funded sessions still barely deploy | 12/30 sessions placed orders; median 4.3% of available cash ($75-$1,071 vs $8-9.9k) | [VERIFIED — prior work, commit `b89fb3c`, same 30-session `data/runs.alpaca.db` + Alpaca filled-order API audit] |
| session-loss rate | 7/30 (23%) sessions produced zero buy decisions — 2 wrapper aborts, 1 no-run, 3 empty-universe, 1 gap | [VERIFIED — prior work, commit `b89fb3c`, same 30-session run-log survey] |
artifact:      `doc/design/2026-08-06-capital-deployment-v2.md`
prod or exp:   prod (mechanism claim against the live book, equity $10,943 on
               2026-08-06) — this PR itself changes no prod surface
existing data: orch#848 (three undecided defects), orch#866 (in-flight blind spot),
               orch#854 (TSLA-fill retraction), orch#872 (shared count-guard bug)
best-known?:   yes for the stated mechanism; explicitly asserts no return/P&L claim
scope:         design document only; no code, config, or artifact change in this PR

NEXT:      R0b (fix the 23% session-loss rate) is the highest-ranked, proven,
           experiment-free follow-up. R0 (absolute-or-relative VetoWeakBuys floor)
           is a hypothesis, not an authorized follow-up, until its bounded
           experiment (candidate rules, frozen in-sample/holdout windows, baseline,
           risk constraints, predeclared decision criteria — see the design doc) is
           run. R1 (`sizing.ceiling` re-calibration against the frozen z-composite
           percentile distribution) and R2 (`pipeline#269`, subtract in-flight buys
           from `open_slots`) rank below R0b. None implemented here; each needs its
           own operator-authorized PR in the owning repo (strategy-104 or pipeline).
