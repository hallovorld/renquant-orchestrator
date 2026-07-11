# META no-buy forensics — sessions 2026-07-06 → 2026-07-10

**Status:** research (read-only forensic; no state mutated, no orders touched)
**Author:** claude (decision-tree-review skill), 2026-07-11; r2 (Codex review, 2026-07-11):
mixed-result framing correction, repository ownership correction, evidence sealed to
`renquant-artifacts` (mutable live paths were the r1 evidence citation; see below).
**Sources:** the durable forensic record for this doc is now
[`renquant-artifacts#16`](https://github.com/hallovorld/renquant-artifacts/pull/16)
(`store://experiments/meta-no-buy-forensics-20260711/RUN-LOCK.json`,
commit `1737d4b`) — a sealed, content-addressed extract of the decision-ledger rows and log
lines cited below. It was built read-only from `data/runs.alpaca.db` (immutable open),
`logs/daily_104/2026-07-0{6,7,8,9,10}.log`, `backtesting/renquant_104/live_state.alpaca.json`,
and Alpaca account activities + data API (read-only GET) — those live-tree/mutable paths are
the ORIGINAL sources the sealed bundle was extracted from, not this doc's durable citation.
Pinned `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json` and GitHub
PR metadata are cited directly (not sealed) as they are independently version-controlled.
Run IDs audited: `2026-07-06-live-ebb9c2ca`, `2026-07-07-live-dc2a3247`, `2026-07-08-live-369734c3`,
`2026-07-09-live-40e2dbd0`, `2026-07-10-live-6f9d5284` (the five daily-full runs; intraday runs do no buy scan).

---

## 1. Verdict (bottom line) — MIXED result (r2 correction)

**On the 3 sessions where the buy funnel actually scored META (07-06, 07-07, 07-10), the
result is a genuine MODEL VIEW: XGB scored META positive-but-weak and it was
double-killed by two independent, correctly-functioning gates.** On the 2 remaining sessions
(07-08, 07-09) the entire buy universe collapsed and META was **never scored at all** — an
availability outage, not a per-ticker rejection. **META's counterfactual outcome on those two
specific days is UNKNOWN; bracketing-day scores from 07-07/07-10 do not establish what would
have happened to META on 07-08/07-09 specifically** (r1 incorrectly inferred the outage
"did not change META's fate" from the surrounding days' scores — corrected below, per Codex
review). This is NOT the wash-sale recurrence on any of the 5 sessions.

- **On the 3 scored sessions:** its rank_score was below the relative VetoWeakBuys floor
  (`mean+1σ` of the day's cross-section) *and* its calibrated 60d mu was below the absolute
  ConvictionGate floor (0.03) — so no single-gate miscalibration explains it. The funnel was
  alive and buying other names it ranked higher (AVGO, MCHP on 07-06; ZM on 07-07; FTNT, APH,
  ZM, NFLX on 07-10). `[VERIFIED]`, sealed in `renquant-artifacts#16` (§3).
- **Wash-sale recurrence: ruled out three independent ways** (§4): no META key in
  `last_sell_dates` at all; broker-truth last META sell fill = 2026-06-02 (30d window expired
  2026-07-02, before the week began); `blocked_wash=0` in every buy-scan run's counters. The
  permanent fix (umbrella PR #428) is **merged (2026-07-02T01:30Z) AND deployed** in the live
  tree. `[VERIFIED]`
- **Separate engineering finding (universe-wide, not META-specific, symptom recovered —
  root cause NOT identified):** on 07-08 and 07-09 the buy scan ran with **0 tickers** —
  133/145 per-ticker admission models failed the `live_train_end` 60d freshness gate
  (`stale_76d/77d_limit_60`), leaving only the 4 held names loaded. No name could be bought
  those two sessions — including, but not specific to, META. `[VERIFIED]` (§5)
- **Model vs street divergence (flagged, not overridden):** META rallied **+11.5% on the week**
  ($600.42 → $669.25 close-to-close) and street consensus is Buy (92% Buy/Strong Buy of 38
  analysts, ~$834 consensus target ≈ +25% vs the $669.25 account price). The model faded the
  move: panel raw score fell from −0.047 to −0.176 as the rally spiked. The model is primary;
  this divergence is surfaced for the operator, not "fixed". (§6)

One-sentence root cause: **the XGB panel genuinely ranked META mid-pack on the 3 sessions it
was scored (rank 13/35 → 11/33 → below-floor of 85 scanned; 60d mu 0.019 → 0.018 → 0.006,
never ≥ the 0.03 conviction bar), so a correctly-scaled two-gate admission funnel never
admitted it on those days — while a separate two-day universe-wide admission-staleness
outage (07-08/09) blocked ALL buys, and META's counterfactual on those two specific days is
genuinely unknown, not inferred from the model view on the other three.**

## 2. Method

Per-session decision-tree extraction via
`renquant-orchestrator/.claude/skills/decision-tree-review/scripts/extract_decision_tree.py`
(`--run-id <id> --json`), cross-checked against `candidate_scores` + `ticker_daily_state`
rows in `runs.alpaca.db`, raw `logs/daily_104` gate lines, live_state JSON, and read-only
Alpaca account/data API calls. Prime-suspect (wash-sale) checked first per the operator's
prior-informed ordering.

## 3. Per-session META funnel table `[VERIFIED]`

Floors from the pinned strategy config: VetoWeakBuys `rank_score >= max(0.20, mean+1.00*std)`
(cross-sectional, per day); ConvictionGate `mu_floor=0.03`, `demean_cross_sectional=false`
(the 2026-06-29 revert is the live setting). META passed candidate generation, wash-sale,
and RealizedVolGate on every scanned day (it reached panel scoring; `in_candidates=1`).

| Session | Buy scan alive? | META killed at | The number | Conviction counterfactual |
|---|---|---|---|---|
| 2026-07-06 | yes — 52 cands from 53 tickers; 35 scored | `veto:rank_score_below_floor` | rank 0.5413 < floor **0.565** (rank 13/35) | mu 0.0192 < 0.03 → dies anyway |
| 2026-07-07 | yes — 51 from 52; 33 scored | `veto:rank_score_below_floor` | rank 0.5375 < floor **0.554** (rank 11/33) | mu 0.0179 < 0.03 → dies anyway |
| 2026-07-08 | **NO — 0 candidates from 0 tickers** | `universe:stale_76d_limit_60:live_train_end` | 133/145 admission models stale; only held AVGO/CSCO/MU/PANW loaded | not scored (no panel candidate row) |
| 2026-07-09 | **NO — 0 candidates from 0 tickers** | `universe:stale_77d_limit_60:live_train_end` | same 4/145 | not scored |
| 2026-07-10 | yes — 116 from 122; 85 scored | `veto:rank_score_below_floor` | rank 0.5053 < floor **0.544** | mu 0.0064 < 0.03 → dies anyway |

Names that DID clear both gates and were submitted (`broker_pending_submitted` counter → order
path), proving the funnel was not frozen: 07-06 AVGO (rank 0.600/mu 0.040), MCHP (0.586/0.035)
— both appear as holdings on 07-07, i.e. filled; 07-07 ZM (0.582/0.034); 07-10 FTNT
(0.616/0.046), APH (0.588/0.036), ZM (0.578/0.032), NFLX (0.575/0.031). META never outranked
any submitted name on any day.

Other gates, checked and NOT the killer for META: cash (free cash ~$8.4–9.2k vs 1 whole META
share ~$600–669 — affordable; `size_insufficient_cash` hit EME on 07-10, not META), slots
(`slots full` hit XLK on 07-10 after 4 submissions — META was already dead at veto),
correlation/sector caps (hit PANW on 07-10, `corr_blocks=1`; `sector_blocks=0` all week),
rotation (initiate threshold 0.06 vs META er ≤ 0.019 — never in contention), top-up (META not
held). Wash-sale: §4.

## 4. Wash-sale state — the prime suspect, cleared `[VERIFIED]`

Known incident class (2026-06-25/07-01): reconciliation stamped `last_sell_dates[META]` with
the reconciliation-run date (2026-06-26) instead of the broker fill date (2026-06-02), wrongly
extending the 30d wash-sale block. Checked all three legs:

1. **Live state:** `backtesting/renquant_104/live_state.alpaca.json` → `last_sell_dates` has
   **10 entries and NO META key** (AMZN 07-08, CRWD 07-02, CSCO 07-10, EQIX/GE/HON 06-26,
   MCHP 07-08, NEE 07-01, PANW 07-10, SOFI 07-07). The heuristic did **not** re-stamp META.
2. **Broker truth (Alpaca `/v2/account/activities/FILL`, read-only):** last META sell fill =
   **2026-06-02T13:42:26Z, 1 sh @ $596.784** (prior buy 2026-05-18 @ $609.35 — a loss sale,
   which is why the wash-sale clock mattered in June). Window: 06-02 + 30d (`wash_sale_days=30`
   in pinned config) = **2026-07-02 — expired before the week's first session**. Even a
   perfectly-stamped state could not have blocked META this week.
3. **Runtime counters:** `blocked_wash=0` in the counters of all three buy-scan runs
   (07-06/07-07/07-10). The gate never fired for anyone this week.

**Permanent fix status: merged AND deployed.** Umbrella PR
[hallovorld/RenQuant#428] "fix(runner): STATE-EXT-SELL reconciliation must stamp the ACTUAL
broker fill date, not today (wash-sale clock extension bug)" — **MERGED 2026-07-02T01:30:03Z**
(merge commit `934ccc5e`). Deployed evidence in the live serving tree:
`backtesting/renquant_104/adapters/runner_ext_sell.py` implements `ext_sell_fill_date` (broker
fill timestamp authoritative; ambiguous-side and naive-timestamp fail-closed) and
`ext_sell_stamp_decision` (`actual_fill` > `unresolved_preserve` > `no_fill_fallback`), wired
via delegates at `backtesting/renquant_104/adapters/runner.py:995–1011` with the 45d fill
lookback (also #428). No merged-but-not-pinned gap exists for this fix.

## 5. Engineering finding: 07-08/09 admission outage (universe-wide, SYMPTOM RECOVERED —
    root cause NOT identified; r2 correction)

- 07-06 and 07-07 loaded 58/145 per-ticker admission models (the rest: `no_artifact` or
  `sharpe_below_0.5`); META loaded and was scored both days.
- 07-08 13:55 PT: **133/145 skipped `stale_76d_limit_60:live_train_end`**, including META
  (`META stale_76d_limit_60:live_train_end, skipping`) → `Loaded models for 4/145` (the held
  names: AVGO, CSCO, MU, PANW) → `Phase 2b (buy scan): 0 candidates from 0 tickers`. Identical
  on 07-09 (`stale_77d`). The freshness gate itself behaved correctly (fail-closed on stale
  vintage) — `[VERIFIED]`, sealed in `renquant-artifacts#16`.
- **The exact `live_train_end` value carried during the regression window is NOT
  independently reconstructable** (r2 correction — r1 stated `live_train_end≈2026-04-23` as
  if observed; it was not). No commit exists on `META-policy-metadata.json` in the 07-07→07-08
  window (the live-tree copy is not incrementally committed per retrain) and no other snapshot
  mechanism was found. The "~2026-04-23" figure is an INFERENCE from the log's own stated
  staleness distance (`stale_76d_limit_60` as of 2026-07-08 implies a cutoff ~76 calendar days
  prior) — reported here as an inference, not a verified fact. Sealed provenance note in
  `renquant-artifacts#16`.
- The regression happened **between the 07-07 14:00 PT and 07-08 13:55 PT runs** — the window
  that coincides with the known 2026-07-08 live-tree mutation incident. **This is a
  coincidence in timing, not an established causal link** — attribution of the actual
  producer mutation is NOT identified by this forensic and is flagged as a follow-up (§8).
- **Symptom recovery** (not root-cause resolution): a per-ticker retrain on 2026-07-09 stamped
  `trained_date=2026-07-09`, `live_train_end=2026-06-23` for META (current
  `models/META/META-policy-metadata.json`, sealed snapshot in `renquant-artifacts#16`) → 07-10
  loaded 125/145, scanned 116. The admission models became fresh again; WHY they went stale in
  the first place is not known. Describing this as "resolved" would overclaim — it is symptom
  recovery until the producer mutation is causally identified.
- **Impact on META specifically: UNKNOWN, not "none."** r1 claimed the outage "did not change
  META's fate" by reasoning from its scores on the bracketing days (07-07 mu 0.018, 07-10 mu
  0.006). That is exactly the bracketing-day inference Codex's review rejected: META was never
  evaluated on 07-08/09 at all (no `candidate_scores` row exists for those two run_ids —
  confirmed directly, sealed in `renquant-artifacts#16`), so there is no observed outcome to
  reason from for those two specific days. The outage cost the BOOK two sessions of buy
  capability; whether it specifically cost META a buy on those two days is not established
  either way.
- **Observability gap:** both outage days were reported to ntfy as
  `DECISION | no trade (no_candidates)` — an infrastructure outage rendered as a normal
  no-trade verdict. A `buy scan: 0 tickers` day is an availability incident and should alert
  as one (ownership: §8).

## 6. Model-capability read (model vs street)

- Account-price reality (Alpaca IEX bars, split-adjusted): META closed 600.42 (07-06), 615.41
  (07-07), 603.12 (07-08), 631.48 (07-09, intraday 584→631), 669.25 (07-10) — **+11.5% on the
  week**, concentrated in 07-09/07-10.
- The panel's view moved the OTHER way as the rally spiked: raw panel_score −0.047 (07-06) →
  −0.060 (07-07) → **−0.176 (07-10)**; 60d mu 0.0192 → 0.0179 → 0.0064; while META's
  rs_score rose 0.006 → 0.044 → 0.120. Read: the model treats the post-spike level as
  overextended on its 60d relative-return horizon (its monotone constraints penalize
  `price_to_high` proximity only positively, but beta/realized-vol/reversal features dominate
  here) — a coherent fade-the-spike view, consistently applied, not a scoring artifact.
- Street (2026-07-09/10): consensus **Buy** — 53% Strong Buy / 39% Buy / 8% Hold of 38
  analysts; consensus target ≈ **$834** (+25% vs $669.25); Wells Fargo 07-02 target $767.
  Sources: [Benzinga](https://www.benzinga.com/quote/META/analyst-ratings),
  [TipRanks](https://www.tipranks.com/stocks/meta/forecast),
  [stockanalysis.com](https://stockanalysis.com/stocks/meta/forecast/).
- **Judgment:** on 07-06/07-07 (pre-rally, META flat) the weak-mu view was defensible; the
  system missed the 07-09/07-10 pop, but a 60d-horizon cross-sectional model declining to
  chase a one-week +11% move is a model OPINION, not a malfunction. Whether that opinion is
  systematically wrong on momentum continuation is exactly what the decision-ledger forward
  returns are accruing to answer — do not hand-tune gates off one name-week.

## 7. Structural checklist (skill §5) — none of these killed META

- Threshold-vs-scale: conviction bar reachable every scanned day (day-max mu 0.040–0.046 >
  0.03; names cleared it and were submitted). The 🔴 flag that DOES fire is the **rotation**
  initiate bar (0.06 vs week-max er 0.0484) — a book-level cash-deployment issue (81% idle
  cash), previously known, irrelevant to META's new-buy path since open slots existed.
- Hold/buy asymmetry 🟡 (11 conviction-blocked names with mu ≥ held GRMN's 0.011) and
  vol-gate grandfathering (held MU at 105% ann vol vs 60% new-buy cap) — real asymmetries,
  not META killers.
- Negative-raw top-up block fired only for held GRMN. min_hold/tax froze only rotations of
  MU/AVGO/GRMN. `sector_blocks=0`; `corr_blocks` hit PANW only.

## 8. Recommendations (ownership — r2 correction: the deprecated umbrella is not an owner)

1. **No META-specific action.** The no-buy is the model's consistent cross-sectional view on
   the 3 sessions it was actually scored, double-gated; the 2 outage sessions have no
   established counterfactual either way. Track the divergence via the decision ledger
   (orchestrator #133/#190 lineage) rather than loosening the veto/conviction floors off one
   name-week, and do not treat the outage days as confirmatory either direction.
2. **Alert on buy-scan universe collapse** (owner: **`renquant-orchestrator`'s own monitor
   layer** — this repo already owns model-freshness monitoring via
   `src/renquant_orchestrator/model_freshness_monitor.py`; extend that module or add a
   sibling alert, not the deprecated umbrella): `Phase 2b: 0 candidates from 0 tickers` (or
   loaded-models below a sanity floor, e.g. <20% of watchlist) must page as an OUTAGE, distinct
   from `no trade (no_candidates)`. Two full sessions of zero buy capability passed as normal
   no-trade decisions this week. The live runner currently executing from the umbrella tree is
   a temporary migration shim for where the alert is TRIGGERED from, not the owner of the
   alerting logic itself.
3. **Root-cause the 07-08 `live_train_end` metadata regression** (owner: **`renquant-pipeline`**
   — confirmed by direct inspection: the freshness-gate consumer of `live_train_end` is
   `src/renquant_pipeline/kernel/pipeline/job_universe.py`, and the per-ticker training/
   freshness-stamping logic is `src/renquant_pipeline/kernel/pipeline/pp_training.py`; NOT
   "umbrella `RenQuant`, train_104/models pipeline" as r1 stated). What rewrote per-ticker
   policy-metadata's effective vintage between the 07-07 and 07-08 runs (window coincides with,
   but is not established to be caused by, the 07-08 live-tree mutation incident — see §5) is
   NOT identified by this forensic. The 60d freshness gate fail-closed correctly; the input
   regressed for reasons not yet known. The umbrella's `scripts/tournament_retrain_marker.py`
   reads `live_train_end` as a verification/staleness-check tool — it is a consumer/checker,
   not the producer, and should be treated as a temporary umbrella-resident tool pending
   migration, not evidence that the umbrella owns this logic.
4. **Wash-sale: nothing to do** — #428 merged and deployed; state, broker truth, and counters
   all agree.
