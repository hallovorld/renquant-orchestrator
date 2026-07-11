# META no-buy forensics — sessions 2026-07-06 → 2026-07-10

**Status:** research (read-only forensic; no state mutated, no orders touched)
**Author:** claude (decision-tree-review skill), 2026-07-11
**Sources:** `data/runs.alpaca.db` (immutable open), `logs/daily_104/2026-07-0{6,7,8,9,10}.log`,
`backtesting/renquant_104/live_state.alpaca.json`, Alpaca account activities + data API (read-only GET),
pinned `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`, GitHub PR metadata.
Run IDs audited: `2026-07-06-live-ebb9c2ca`, `2026-07-07-live-dc2a3247`, `2026-07-08-live-369734c3`,
`2026-07-09-live-40e2dbd0`, `2026-07-10-live-6f9d5284` (the five daily-full runs; intraday runs do no buy scan).

---

## 1. Verdict (bottom line)

**The META no-buy is a MODEL VIEW, not an engineering block, and it is NOT the wash-sale
recurrence.** On every session where the buy funnel actually ran (07-06, 07-07, 07-10) the
XGB panel scored META positive-but-weak and it was **double-killed by two independent,
correctly-functioning gates**: its rank_score was below the relative VetoWeakBuys floor
(`mean+1σ` of the day's cross-section) *and* its calibrated 60d mu was below the absolute
ConvictionGate floor (0.03) — so no single-gate miscalibration explains it. The funnel was
alive and buying other names it ranked higher (AVGO, MCHP on 07-06; ZM on 07-07; FTNT, APH,
ZM, NFLX on 07-10). `[VERIFIED]` per-gate evidence in §3.

- **Wash-sale recurrence: ruled out three independent ways** (§4): no META key in
  `last_sell_dates` at all; broker-truth last META sell fill = 2026-06-02 (30d window expired
  2026-07-02, before the week began); `blocked_wash=0` in every buy-scan run's counters. The
  permanent fix (umbrella PR #428) is **merged (2026-07-02T01:30Z) AND deployed** in the live
  tree. `[VERIFIED]`
- **Separate engineering finding (universe-wide, not META-specific):** on 07-08 and 07-09 the
  buy scan ran with **0 tickers** — 133/145 per-ticker admission models failed the
  `live_train_end` 60d freshness gate (`stale_76d/77d_limit_60`), leaving only the 4 held
  names loaded. No name could be bought those two sessions. Given META's scores on the
  bracketing days (mu 0.018 on 07-07, 0.006 on 07-10), the outage did not change META's
  fate. Resolved by the 2026-07-09 per-ticker retrain (07-10: 125/145 loaded, 116 scanned).
  `[VERIFIED]` (§5)
- **Model vs street divergence (flagged, not overridden):** META rallied **+11.5% on the week**
  ($600.42 → $669.25 close-to-close) and street consensus is Buy (92% Buy/Strong Buy of 38
  analysts, ~$834 consensus target ≈ +25% vs the $669.25 account price). The model faded the
  move: panel raw score fell from −0.047 to −0.176 as the rally spiked. The model is primary;
  this divergence is surfaced for the operator, not "fixed". (§6)

One-sentence root cause: **the XGB panel genuinely ranked META mid-pack all week (rank
13/35 → 11/33 → below-floor of 85 scanned; 60d mu 0.019 → 0.018 → 0.006, never ≥ the 0.03
conviction bar), so a correctly-scaled two-gate admission funnel never admitted it — while a
separate two-day universe-wide admission-staleness outage (07-08/09) blocked ALL buys and
merely masked the same verdict.**

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

## 5. Engineering finding: 07-08/09 admission outage (universe-wide, resolved)

- 07-06 and 07-07 loaded 58/145 per-ticker admission models (the rest: `no_artifact` or
  `sharpe_below_0.5`); META loaded with `TRAINED=2026-06-30, live_train_end=2026-06-23`.
- 07-08 13:55 PT: **133/145 skipped `stale_76d_limit_60:live_train_end`** (implying the
  then-current metadata carried `live_train_end≈2026-04-23`) → `Loaded models for 4/145`
  (the held names) → `Phase 2b (buy scan): 0 candidates from 0 tickers`. Identical on 07-09
  (`stale_77d`). The freshness gate itself behaved correctly (fail-closed on stale vintage).
- The metadata regression (live_train_end 2026-06-23 → 2026-04-23) happened **between the
  07-07 14:00 PT and 07-08 13:55 PT runs** — the window that coincides with the known
  2026-07-08 live-tree mutation incident. Attribution of the regression is out of scope here;
  flagged as a follow-up (below).
- Recovery: per-ticker retrain stamped `trained_date=2026-07-09`, `live_train_end=2026-06-23`
  (current `models/META/META-policy-metadata.json`) → 07-10 loaded 125/145, scanned 116.
- **Impact on META: none beyond the shared outage.** Its panel scores on the bracketing days
  (mu 0.018 → 0.006) were nowhere near admission; the outage cost the BOOK two sessions of
  buy capability, not META specifically.
- **Observability gap:** both outage days were reported to ntfy as
  `DECISION | no trade (no_candidates)` — an infrastructure outage rendered as a normal
  no-trade verdict. A `buy scan: 0 tickers` day is an availability incident and should alert
  as one.

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

## 8. Recommendations (ownership)

1. **No META-specific action.** The no-buy is the model's consistent cross-sectional view,
   double-gated. Track the divergence via the decision ledger (orchestrator #133/#190 lineage)
   rather than loosening the veto/conviction floors off one name-week.
2. **Alert on buy-scan universe collapse** (owner: umbrella `RenQuant` live runner or the
   orchestrator monitor): `Phase 2b: 0 candidates from 0 tickers` (or loaded-models below a
   sanity floor, e.g. <20% of watchlist) must page as an OUTAGE, distinct from
   `no trade (no_candidates)`. Two full sessions of zero buy capability passed as normal
   no-trade decisions this week.
3. **Root-cause the 07-08 `live_train_end` metadata regression** (owner: umbrella `RenQuant`,
   train_104/models pipeline): what rewrote per-ticker policy-metadata from vintage 2026-06-23
   to 2026-04-23 between the 07-07 and 07-08 runs (window coincides with the 07-08 live-tree
   mutation incident). The 60d freshness gate fail-closed correctly; the input regressed.
4. **Wash-sale: nothing to do** — #428 merged and deployed; state, broker truth, and counters
   all agree.
