# S9 — Track A conditional pick-quality test: executed against the frozen §4 spec — NULL

STATUS:   EXECUTED + VERDICT RECORDED — **NULL (STOP)**. The pre-registered Track A
          candidate-quality test (direction-decision §4, origin/main, criteria frozen)
          ran against the freshly regenerated durable OOS pick table; no conditioning
          cleared all of gates (a)-(e) on the held-out test window. Per the spec the
          NULL is recorded, never re-argued: **Track B (an input change) is now the only
          remaining directional path** for renquant105. Read-only on all inputs; no git
          anywhere near the live tree; evidence committed in this PR only.
WHAT:     `scripts/s9_track_a_conditional.py` — one-command reproduce of the whole test:
          (0) substrate verification via the owning #59 contract
          (`renquant_backtesting.analysis.pick_table.verify_pick_table`): content hash
          `ba964b40…` + counts (508 dates / 292 names / 147,066 rows) MATCH the sidecar;
          (1) frozen label `y = 1 iff fwd_60d_excess_raw > 11bps` — the table's
          `fwd_60d_excess` is the per-date STANDARDIZED training label (verified), so the
          raw-unit label is joined from §4's own named durable input
          (`alpha158_291_fundamental_dataset_rawlabel.parquet`), join proven exact
          (15,109/15,109 rows, max std-label diff 0.0); (2) §4 PIT checks: vars 1-3
          (regime / dispersion / margin) VERIFIED and ran; var 4 (earnings-surprise
          window) **DROPPED — `earnings_291.parquet` has NO `acceptedDate` PIT key**
          (single-snapshot `fetched_at` 2026-06-25 = backfilled, not PIT-collected; no
          substitution per §4); var 5 (60d vol + ADV) **PASSED** — durable bars panel
          confirmed at `data/ohlcv/<T>/1d.parquet` (292/292 names, back-adjusted, 100%
          coverage) and ran; (3) frozen chronological split: train 305d (2024-02-02 →
          2025-04-22), embargo 60d, test 143d (2025-07-21 → 2026-02-11); (4) three
          conditioning candidates fit on train only (logistic meta-model; BEAR regime
          whitelist; within-date margin top-half); (5) §4 metric suite with date-block
          bootstrap (block=13, 2,000 resamples, fixed seed) incl. the binding annualized
          capital-weighted book-return gate.
WHY/DIR:  Direction-decision §4 pre-registered this as Track A's first falsifiable step:
          is pick quality measurably higher in an identifiable ex-ante state? Test-window
          answer: NO on every candidate. C1 logit: train +592 bps/yr book lift flips to
          **−636 bps/yr [−1352, +64] OOS** (overfit, no stable state). C2 BEAR whitelist:
          hit-lift +6.7pp [+3.1, +9.1] passes (c) but the test window has **1 BEAR date**
          → 0.7% active exposure vs the 25% floor — exactly the pre-registered "(d) likely
          binding" failure mode of the known BEAR-only skill slice. C3 margin-top-half:
          +1158 bps/yr [+632, +1713] on test but **train hit-lift is −0.3pp** (sign
          instability = window artifact, not an identifiable state; champion-by-train
          protocol picked C1, not C3) and it drops **42.9% of baseline winners** > the 1/3
          cap — gate (e) FAIL by design ("hit-rate gain bought by dropping winners is not
          a win"). Verdict applied §4's literal GENEROUS rule (GO iff ANY candidate clears
          all gates): zero cleared → NULL; the stricter champion protocol agrees.
EVIDENCE:
          artifact:      `scripts/s9_track_a_conditional.py`,
                         `doc/research/2026-07-03-s9-track-a-conditional.md`,
                         `doc/research/evidence/2026-07-03-s9/{substrate_verification,
                         pit_checks,s9_results}.json` (this PR).
          prod or exp:   EXP / research-only. Inputs read-only from the umbrella tree
                         (`data/exp/` pick table, rawlabel panel, `data/ohlcv/`,
                         `data/fmp_harvest/`); contract verifier imported read-only from
                         renquant-backtesting@main 68b222e. No prod path written, no git
                         in any primary checkout, no orders.
          existing data: the S8-regenerated `data/exp/oos_pick_table_recipe_v2.parquet`
                         (+ sidecar) — verified against its own content anchor before use.
          best-known?:   best available execution of the frozen spec on the durable
                         substrate; the panel remains current-watchlist / survivorship-
                         biased (same scope limit as A1/A2), and the single 143-date test
                         window is 82.5% BULL_CALM — differences, not absolute levels,
                         are the supported read.
          scope:         research measurement only — no strategy/config/pipeline change;
                         3 candidates = mild multiplicity in the GO direction only (none
                         passed, so it cannot have manufactured the NULL).
NEXT:     (1) operator/Codex review of the NULL; per §4 no filter-fishing follow-up is
          permitted; (2) the directional path is now formally Track B (universe down-cap
          or new PIT-clean data — e.g. RS5's down-cap panel spec, and #205-style PIT
          revision history once it exists) — an OPERATOR-level call, not started here;
          (3) non-directional Track A levers (vol/risk-timing sizing, execution/cost)
          remain open and are explicitly not directional edge.
