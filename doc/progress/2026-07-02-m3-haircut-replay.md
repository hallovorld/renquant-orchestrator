# M3 conviction uncertainty-haircut ledger replay — research PR

STATUS:   research evidence (READ-ONLY study; script + committed JSON + memo). No
          config, gate, or behavior change. Verdict: the #231 M3 config-PR
          precondition is NOT met on this data.
REVISION: r1.
WHAT:     task M3 of the unified plan (#231 Term TC row M3 / H2 roadmap §M3):
          `scripts/m3_haircut_replay.py` (one-command reproduce, sqlite mode=ro,
          deterministic seed) + `doc/research/evidence/2026-07-02-m3/*.json` +
          `doc/research/2026-07-02-m3-haircut-replay.md` +
          `tests/test_m3_haircut_replay.py` (12 in-memory-fixture tests).
WHY/DIR:  the M3 gate change (`mu − k·SE(mu) > floor`) ships ONLY if a ledger replay
          shows the haircut removes more losers than winners (net expectancy gain).
          Replayed 26 canonical daily full live runs (2026-05-04→07-02, one run/date,
          #234 dedup discipline), 430 floor-clearing decisions, SE(mu) = era-stratified
          trailing cross-run mu dispersion (no SE column exists; stability proxy,
          stated as such). RESULT — AC FAIL: at the primary fwd_20d horizon the
          haircut removes MORE winners than losers at both k (k=0.5: 18W/15L removed,
          Δ +0.14pp, CI spans 0; k=1.0: 28W/22L, Δ −0.51pp, block-5 CI [−0.89,−0.01]pp
          — actively harmful, it cuts high-dispersion names that were the BULL_CALM
          winners). Thin-margin admits drop only to 20–24%, not ~0 (margin ⊥
          stability). The OXY/GRMN motivating fixtures have UNDEFINED SE (fresh pool
          entrants, 1–2 obs) — the rule cannot rule on its own motivating cases.
          Recommendation: take the plan's pre-declared contingency (observe-only
          thin-margin alert), not the gate change; revisit after S5 accrues
          panel-era fwd_60d outcomes.

EVIDENCE:
```
artifact:      scripts/m3_haircut_replay.py +
               doc/research/evidence/2026-07-02-m3/{m3_haircut_replay,
               m3_admission_composition,m3_fixture_cases}.json (committed output) +
               doc/research/2026-07-02-m3-haircut-replay.md (memo)
prod or exp:   experiment — read-only replay, no config/order/gate change
existing data: runs.alpaca.db candidate_scores/pipeline_runs/ticker_forward_returns
               (26 canonical daily full live runs 2026-05-04→2026-07-02); panel
               calibrator JSON read-only (proxy-b metadata only)
best-known?:   best-available: fwd_60d (mu's own horizon) is unresolvable for the
               ENTIRE live window — primary outcome is fwd_20d excess vs SPY
               (8 usable dates), fwd_10d/fwd_5d sensitivity; resolved outcomes exist
               only for RETIRED scorer eras (pre-tournament + legacy tournament) —
               zero resolved 10/20d outcomes for the current panel_ltr_xgboost era;
               spec'd block-13 bootstrap is degenerate at 8–13 dates (flagged),
               block-5/1 sensitivity carried
scope:         this is scripts/m3_haircut_replay.py, EXPERIMENT/replay, vs the
               current production admit rule `mu > 0.03` as baseline (rule unchanged
               by this PR)
```

**Honest calls (in the memo, §Honest calls):** horizon mismatch (60d mu judged on
20d outcomes), retired-era evidence (does not transfer to the current scorer),
unvalidated model (D1 pending — this measures the historical mu ordering only),
overlapping forward windows (block bootstrap + degenerate-stride flagged),
survivorship (winner-biased watchlist), SE-proxy limits (dispersion conflates noise
with information arrival/retrains; calibrator JSON carries no per-name band — the
only derivable proxy-b figure is a per-name-blind constant ≈0.046 that degenerates
to a blunt floor raise).

**Tests:** `python3 -m pytest tests/test_m3_haircut_replay.py -q` → 12 passed
(canonical-run dedup incl. sub-threshold/sim exclusion, era-stratified SE windows
never crossing scorer eras, MIN_OBS/window caps, strict-inequality admit boundary,
winner-vs-cost threshold, weekend→prior-trading-day outcome mapping, replay
winner/loser counting, undefined-SE pass-through sensitivity, degenerate-bootstrap
flagging, thin-margin band edges).

NEXT:     (1) if the observe-only thin-margin alert is wanted, that is a separate
          small PR citing this memo (plan's own M3 contingency row); (2) re-run this
          replay forward once S5-ledger panel-era decisions age past 60 trading days
          — the current-scorer verdict is genuinely open; (3) a real per-name
          uncertainty (ensemble/bootstrap band persisted at scoring time) would make
          the k-haircut testable as designed — the stability proxy is structurally
          blind to "stably thin" names and undefined on fresh entrants (the OXY
          class), which is itself a finding about the rule as specified.
