# Silent no-buy block registry — whole-history retrospective (2026-07-11)

**Status:** research registry (requirements input for the funnel-integrity pipeline step).
**Scope:** every session of the RenQuant-104 live era, 2026-04-21 → 2026-07-10 (56 NYSE
sessions). READ-ONLY forensic sweep; no production state touched.
**Method:** reused the extraction logic of
`.claude/skills/decision-tree-review/scripts/extract_decision_tree.py`
(runs DB `data/runs.alpaca.db` — `pipeline_runs`, `candidate_scores`,
`ticker_daily_state`, `live_state_snapshots`, `trades` — opened `immutable=1`),
plus a normalized-template mining pass over all `logs/daily_104/2026-*.log` and
`logs/intraday_104/*.log`, plus latest `live_state` snapshot vs broker-truth fills.
Key patterns and queries are in Appendix B so the sweep is reproducible.

---

## 1. Bottom line

- **The live system is 56 sessions old — a "last 120 sessions" window does not exist.**
  All numbers below are over the full 56-session live history.
- **27 / 56 sessions (48%): the scheduled buy path was fully dead for a
  non-economic, engineering cause.** [VERIFIED per-session, §3 + Appendix A]
  On 5 of those 27 a manual same-day intervention placed buys anyway
  (05-22, 06-09, 06-10, 06-22, 07-06); **22 / 56 (39%) realized zero buys.**
- **33 / 56 sessions had zero live buys. 22 of those 33 (67%) were engineering,
  not economics.** The honest "the model chose not to trade" share of no-buy days
  is at most 11/33.
- **8 more sessions were materially degraded** (wrongful wash-sale blocks, admission
  staleness creep, universe collapsed to 45%, intraday buy path dead all day):
  **35 / 56 (63%) degraded-or-dead.**
- **Input-integrity overlay (fully silent):** the fundamentals actually served to the
  scorer were frozen at 2026-02-10 → 70–121 d stale for every session until 06-12,
  and ~88–92 d stale until 06-23 (~40 sessions). First signal of any kind: a log
  WARNING added 06-11. Zero decision-level signal, ever. [VERIFIED from
  `fundamentals feed STALE` lines 06-11 → 06-23]
- **Flagged at the time:** of the 27 full blocks — 17 (63%) loud (PREFLIGHT-FAIL /
  abort ntfy), 6 (22%) semi (block-reason string embedded in a routine-looking
  "no trade (…)" notification), **4 (15%) fully silent** (06-05: no report at all;
  06-30, 07-08, 07-09: reported as a normal `no trade (no_candidates)`,
  indistinguishable from an economic no-trade). Of the 8 degraded sessions and the
  40-session stale-fundamentals overlay: **0% flagged at decision level.**
- **Still broken today [VERIFIED against 2026-07-10 live_state snapshot]:**
  `last_sell_dates` stamps GE=2026-06-26 (broker truth 05-18), HON=2026-06-26
  (truth 06-03), EQIX=2026-06-26 (truth 06-17). GE has been wrongfully
  wash-blocked in 8 sessions and remains blocked; HON is wrongfully blocked since
  07-04; EQIX becomes wrongfully blocked 07-18 → ~07-27 unless the stamps are
  corrected. The code fix (fill-date lookup, `EXT_SELL_LOOKBACK_DAYS=45`) is in the
  umbrella working tree (`backtesting/renquant_104/adapters/runner_ext_sell.py`),
  but the state was never retro-corrected for these three names.

---

## 2. Per-class registry

Each class ends with the **invariant** the funnel-integrity step must assert.
Fix-status tags: [VERIFIED] = checked against the pinned runtime / 07-10 behavior;
[GUESS] = plausible but not independently confirmed here.

### C1 — Admission / tournament staleness collapse

| Episode | Sessions | Impact | Looked like | Detected |
|---|---|---|---|---|
| (a) Tournament freeze onset: per-ticker retrain dead (train_104 timeout at `parallel_ticker_timeout_seconds=600`); training pipeline FAILED 04-21, 04-28, 05-05, 05-07 | onset April; consequences surface in June | model ages toward the 60 d limit; `no_artifact` skips 9–12 tickers/session throughout | training failures visible only inside the daily log; decision path unaffected that day | root-caused 2026-06-30 (timeout 600→3600 retrain) |
| (b) Staleness-limit crossing creep | 06-22 → 06-30 (`stale_61d`…`stale_67d`, 1→42→126 tickers) | 06-30: buy scan **0 candidates from 0 tickers**, 126/145 skipped | `no trade (no_candidates)` — indistinguishable from a normal no-trade | 06-30/07-01; retrain restored 114 candidates on 07-01 [VERIFIED: 07-01 scan 119/114] |
| (c) Artifact loss after models-dir disturbance | 07-06 → 07-07 (`no_artifact` 80/145, n_tournament=58) | universe collapsed to 53/52 scanned | decisions looked routine; 07-06 even placed 2 buys after manual rescue | never explicitly; healed by the 07-10 rebuild. Cause [GUESS]: backup/restore or partial artifact migration |
| (d) `live_train_end` regression | 07-08 → 07-09 (`stale_76-80d_limit_60:live_train_end`, 129/145 skipped, n_tournament=4) | buy scan **0 from 0** both sessions | `no trade (no_candidates)` — fully silent | 07-09 forensics; fixed in the 07-10 deployment [VERIFIED: 07-10 n_tournament=125, scan 122/116, 4 buys] |

**Tickers affected:** whole watchlist (126–129 of 145 on collapse days; 20–50/day during creep).
**Fix today:** (b)+(d) fixed and deployed [VERIFIED behaviorally 07-10]; residual 4
`no_artifact` names on 07-10; (a) timeout fix live [VERIFIED via 07-01 retrain effect].

**Invariant I1:** `n_admitted_to_buy_scan / n_universe ≥ floor` (e.g. 0.6) **and**
`n_tournament` must not drop >30% session-over-session; any `stale_*:live_train_end`
claim where `live_train_end < last_session_date − k` is a hard integrity error, not a skip.

### C2 — Wash-sale mis-stamping (the META class) + trade-ledger gaps

Cross-check of every `DROP_WashSaleFilter` line (344 drops) against broker-truth sell
fills reconstructable from the runs DB:

- **06-23 stamp event:** GE / HON / META stamped "sold 8 d ago" (=06-15). Broker truth:
  GE 05-18, HON 06-03, META 06-02.
- **06-26 mass re-stamp event:** reconciliation stamped GE, HON, META, EQIX all
  `last_sell_dates = 2026-06-26` ("sold 0d ago") — the heuristic discarded the real
  fetched fill date and stamped "today".
- **Realized wrongful blocks** (blocked while broker-truth age > 31 d): **GE in 8
  sessions** (06-23, 24, 25, 26, 29, 07-01, 02, 10) — and ongoing. META's stamp was
  24 d off; its realized wrongful window (from 07-03) was masked by the C1 universe
  collapse, then live-corrected ~07-08. HON wrongfully blocked since 07-04 (not yet
  realized as a candidate-drop — it hasn't reached the wash gate). EQIX pending
  (wrongful window 07-18 → ~07-27).
- **Sub-finding (ledger gap):** sells executed in the 05-26 → 06-05 sell-only era
  (BAC, D, WFC, CSCO, DUK, FTNT, XOM, …) have **no sell rows in `trades`** — fills
  happened at the broker but were never persisted, so stamps from that era are
  unauditable from the DB.
- Pre-05-22 wash drops ran against the **paper** book (daily-full was paper until
  05-21) and cannot be adjudicated against Alpaca truth — excluded from the wrongful
  count rather than claimed.

**Looked like:** nothing. Wash drops are INFO log lines; never surfaced in the decision
notification. **Detected:** 07-08 forensics (META). **Fix today:** code fix present in
the umbrella working tree (`runner_ext_sell.py`, 45 d fill lookback) [VERIFIED file
content]; **state NOT retro-corrected — GE/HON/EQIX stamps still wrong in the 07-10
snapshot [VERIFIED]**.

**Invariant I2:** for every ticker, `last_sell_dates[t]` must equal a broker fill date
(±1 trading day) within the lookback; assert nightly. **Invariant I3:** every position
disappearance must produce a persisted sell row (trades ledger completeness: broker
fills ⊆ trades table).

### C3 — Config / calibrator fingerprint fail-closes

- **Live impact:** 2026-07-06 — `LoadGlobalCalibrationTask` calibrator/scorer
  fingerprint mismatch raised mid-pipeline → full run crashed → sell-only fallback
  ("no trade (no_candidates)" from the fallback); manually re-stamped and re-run
  (2 buys, 00:23 UTC 07-07). Third recurrence of the triple-implementation
  `model_content_sha256` bug (prior: 05-27, 06-22/07-01).
- **Contributes to C5:** P-CONFIG-FP / P-PANEL-CONTRACT / P-RUN-ID hard preflight
  fails were part of the 05-22 → 05-29 abort wall.
- **Shadow stream:** `panel_scorer_config_mismatch` fail-closed the PatchTST shadow
  e2e on 05-25→05-29 and 06-23→06-25 (dark 3 days) — no live-buy impact, but the
  A/B evidence stream silently emitted "no trade" that was a contract failure.

**Looked like:** 07-06 was loud-ish (preflight-system-failure ntfy) but the DECISION
line still read `no trade (no_candidates)`. **Fix today:** re-stamp tooling exists
(`stamp_patchtst_fingerprint.py`, umbrella #410); unified single hash impl:
in flight, not verified here [GUESS].

**Invariant I4:** fingerprint parity (scorer ↔ calibrator ↔ config) checked
**pre-market** as a preflight, never discovered mid-pipeline; a fingerprint
fail-close must emit a distinct `contract_failure` decision state, not `no_candidates`.

### C4 — Fundamentals freshness: silent staleness, then a structurally unsatisfiable gate

- **Silent phase (04-21 → 06-23, ~40 sessions):** the serving fundamentals axis was
  clipped to the training `fwd_60d` label (`build_alpha158_qlib` dropna) → features
  frozen at 2026-02-10: 70 d stale at live start, 121 d by 06-11, ~88–92 d after the
  06-12 partial refresh. The model scored on a frozen fundamental snapshot for the
  entire period. First signal: log WARNING added 06-11. Decision-level signal: none.
- **Gate phase:** `P-FUND-FRESHNESS` (45 d critical) added ~06-24 — instantly
  unsatisfiable against the true serving axis. On **06-29 it hard-failed all day in
  intraday runs (41 aborts, "blocking new buys")**; the daily-full escaped only
  because the serving-axis fix (#26) landed the same window.
- **Fix today:** serving axis decoupled (#26) + split gate / sell-only exempt (#151);
  verified fresh since 07-02 (feed as-of 07-02, 7–8 d old, PASS) [VERIFIED from
  preflight lines 07-06 → 07-10].

**Invariant I5:** per feature family, assert `serving_axis_max_date ≥ today − N` inside
the run (not only in preflight), and alert on the **derivative** (staleness growing
1 d/session = frozen feed).

### C5 — Promote / WF-gate stuck → sell-only / abort era

- **Episode:** 2026-05-21 → 2026-06-22, **19 sessions** where hard preflight fails
  (P-WF-GATE metadata absent/failed, P-REGIME-IC, P-RUN-ID, P-CONFIG-FP,
  P-PANEL-CONTRACT) aborted the full run or forced sell-only fallback. Root causes
  (per the recovery-plan forensics): unstamped `wf_gate_metadata`, promote-pipeline
  manifest mismatch, sim artifact-path bug, config-parity drift — while every fresh
  retrain kept failing its WF gate.
- **Buys in the era came only from manual bypass/re-runs:** 05-22 (3, `live_no_wf_gate_once`),
  06-09/06-10 (5+5, evening SelectionJob re-runs), 06-22 (5, XGB re-promotion day).
- **06-05 special case (class C8 too):** the daily job was killed mid-run
  (`Terminated: 15` during the sentiment step) — **no decision, no notification at
  all** for that session.
- **Looked like:** aborts were loud (ntfy PREFLIGHT-FAIL); but multi-week duration
  made "loud" into wallpaper — the gate stayed red for a month.
- **Fix today:** WF-gate metadata stamped, promote path repaired (R4), preflights
  green since 06-23 [VERIFIED: no P-WF-GATE fails in daily logs after 06-22].

**Invariant I6:** a buy-capability SLO — `consecutive sessions with dead buy path`
is itself a paged metric (limit ~2), independent of why; preflight-red must escalate,
not just repeat.

### C6 — Threshold-vs-score-scale mismatches (structural bars)

| Session | Mechanism | Evidence |
|---|---|---|
| 05-19 | tier threshold above every survivor: **50 candidates passed all gates, 0 selected** | funnel: `passed_no_select: 50`; decision `no trade (tier_threshold)` |
| 05-20 | QP min-trade-size: `qp_delta_below_min_dw` killed **70/70** | counters `qp_delta_below_min_dw: 70`; every candidate's optimal Δw below min notional at a $10.5k book |
| 05-21 | same, 66/66 | counters |
| 07-01 | `top_n=3` bar collapse → single contrarian OXY pick from an unvalidated XGB | OXY forensics (2026-07-01) |

These read as economic ("threshold not met") but are **scale bugs**: the bar sits
above the maximum achievable μ/er/Δw for every name simultaneously.

**Fix today:** knob-tuning lane retired; sizing redesign under RFC #443 — the
structural condition can still recur [GUESS].
**Invariant I7:** per session, compute `max achievable mu / er / qp_delta` across
candidates vs the active bars (exactly `extract_decision_tree.structural_checks`);
if a bar > max achievable for ALL candidates → flag `STRUCTURAL_BLOCK`, distinct
from no-trade.

### C7 — Whole-funnel single-gate kills

| Episode | Gate | Kill |
|---|---|---|
| 05-04, 05-06 | `veto:rank_score_below_floor` | 43/43, 45/45 candidates |
| 06-01 → 06-04 | `regime_admission:failed:BULL_CALM` — the promoted model was not admitted for the prevailing regime | 71, 74, 76, 77 = 100% each session |
| 06-11 | sign-laundering veto (`calibrator_sign_laundered=48`) + panel veto | 71/83 + kelly_zero 12 → 0 pass |
| 06-25, 06-26 | panel veto + conviction + vol gate stacked | 76/76, 79/79 (vol gate reported: 21, 22) |

**Looked like:** `no trade (regime_admission_blocked(74))` / `(risk_gate_vol_dropped(22))`
— reason string present but formatted like a routine no-trade; nobody is forced to ask
"why does one gate kill 100% four days running?"
**Fix today:** the 06-01 regime-admission config era ended with the 06-22/23
re-promotion [VERIFIED: gate absent from later funnels]; rank-floor and sign-launder
vetoes still active gates (correct behavior unconfirmed) [GUESS].
**Invariant I8:** any single gate with `kill_rate == 100%` over ≥1 session (or ≥80%
over 3 sessions) emits a structured `funnel_kill` alert naming the gate; `n_buys==0`
must always carry a machine-readable dominant-gate attribution.

### C8 — Run crash / kill → no decision at all

- 06-05: daily job terminated mid-run — no decision, no ntfy, nothing. Only visible
  as a 201-line log and an intraday-only DB day (31 intraday rows, no full run).
- 04-22: one `daily_104 FAILED` invocation (rerun same day succeeded).
- Training-pipeline crashes (04-21, 04-28, 05-05, 05-07) — decision unaffected same
  day but they froze the tournament (feeds C1a).

**Invariant I9:** end-of-session heartbeat — every NYSE session must have exactly one
completed daily-full run row + decision notification; absence is a page, not silence.

---

## 3. Session-level classification (all 56 live sessions)

`buys` = live Alpaca buy orders attributable to the session (runs DB).
`class` = dominant engineering block; `-` = none found (economic no-trade or healthy).
`flagged` = was the engineering cause distinguishable in what the operator received
that day (`loud` = explicit failure alert, `semi` = reason string inside a routine
no-trade line, `NO` = indistinguishable/absent).

| session | buys | verdict | class | flagged |
|---|---|---|---|---|
| 04-21 | 0 | degraded-inputs (fund 70d stale; training crash) | C4/C8 | NO |
| 04-22 | 0 | degraded-inputs | C4 | NO |
| 04-23 | 2 | ok (stale-fund overlay) | C4 | NO |
| 04-24 | 0 | ok-ish; weekend manual buys followed | C4 | NO |
| 04-27 | 14 | ok (stale-fund overlay) | C4 | NO |
| 04-28 | 0 | degraded (training FAILED; fund stale) | C4/C8 | NO |
| 04-29 | 4 | ok (overlay) | C4 | NO |
| 04-30 | 2 | ok (overlay) | C4 | NO |
| 05-01 | 1 | ok (overlay) | C4 | NO |
| 05-04 | 0 | whole-funnel rank-floor veto 43/43 | C7 | semi (NoCandidateAlert) |
| 05-05 | 0 | degraded (training FAILED) | C4/C8 | NO |
| 05-06 | 0 | whole-funnel rank-floor veto 45/45 | C7 | semi |
| 05-07 | 0 | degraded (training FAILED) | C4/C8 | NO |
| 05-08 | 10 | ok (overlay) | C4 | NO |
| 05-11 | 0 | dual-track gap (paper bought 3, live 0) | C4 | NO |
| 05-12 | 3 | ok (overlay) | C4 | NO |
| 05-13 | 1 | ok (overlay) | C4 | NO |
| 05-14 | 1 | ok (overlay) | C4 | NO |
| 05-15 | 1 | ok (overlay) | C4 | NO |
| 05-18 | 3 | ok (overlay) | C4 | NO |
| 05-19 | 0 | FULL BLOCK — tier bar above all 50 passers | C6 | NO |
| 05-20 | 0 | FULL BLOCK — qp_delta_below_min_dw 70/70 | C6 | semi |
| 05-21 | 0 | FULL BLOCK — preflight abort + qp 66/66 | C5/C6 | loud |
| 05-22 | 3* | FULL BLOCK — abort; *manual `no_wf_gate_once` bought | C5 | loud |
| 05-26 | 0 | FULL BLOCK — sell-only fallback | C5 | loud |
| 05-27 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 05-28 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 05-29 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 06-01 | 0 | FULL BLOCK — regime_admission 71/71 | C7 | semi |
| 06-02 | 0 | FULL BLOCK — regime_admission 74/74 | C7 | semi |
| 06-03 | 0 | FULL BLOCK — regime_admission 76/76 | C7 | semi |
| 06-04 | 0 | FULL BLOCK — regime_admission 77/77 | C7 | semi |
| 06-05 | 0 | FULL BLOCK — job killed, NO decision | C8 | NO |
| 06-08 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 06-09 | 5* | FULL BLOCK — abort; *manual evening run bought | C5 | loud |
| 06-10 | 5* | FULL BLOCK — abort; *manual evening run bought | C5 | loud |
| 06-11 | 0 | FULL BLOCK — abort + sign-launder veto 71/83 | C5/C7 | loud |
| 06-12 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 06-15 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 06-16 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 06-17 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 06-18 | 0 | FULL BLOCK — sell-only | C5 | loud |
| 06-22 | 5* | FULL BLOCK cron — *recovery-day re-promotion bought | C5 | loud |
| 06-23 | 10 | degraded — wash mis-stamp (GE 36d), stale creep begins | C1/C2 | NO |
| 06-24 | 3 | degraded — wash + stale creep | C1/C2 | NO |
| 06-25 | 0 | degraded — stacked funnel kill 76/76 + wash | C7/C1/C2 | semi |
| 06-26 | 0 | degraded — stacked funnel kill 79/79 + mass re-stamp | C7/C1/C2 | semi |
| 06-29 | 2 | degraded — 42 stale skips; intraday buys dead all day (P-FUND) | C1/C4/C2 | loud (intraday only) |
| 06-30 | 0 | FULL BLOCK — tournament staleness collapse, scan 0/0 | C1 | NO |
| 07-01 | 1 | degraded — top_n bar collapse; wash (GE) | C6/C2 | NO |
| 07-02 | 1 | degraded — wash (GE) | C2 | NO |
| 07-06 | 2* | FULL BLOCK — calibrator fingerprint crash → sell-only; universe 80 no_artifact; *manual re-stamp bought | C3/C1 | loud |
| 07-07 | 1 | degraded — universe 53/145 scanned | C1/C2 | NO |
| 07-08 | 0 | FULL BLOCK — live_train_end regression, scan 0/0 | C1 | NO |
| 07-09 | 0 | FULL BLOCK — live_train_end regression, scan 0/0 | C1 | NO |
| 07-10 | 4 | healthy (residual: GE/HON wash stamps, 4 no_artifact) | C2 residual | NO |

Denominator caveats: (1) daily-full ran on the **paper** broker until 05-21 while the
Alpaca account traded via the live runner — the 04-21 → 05-21 rows describe the
Alpaca-visible outcome; (2) `trades` has a sell-ledger gap 05-26 → 06-05 (C2); (3)
06-09/06-10/05-22/06-22/07-06 buys were human interventions, not the scheduled system.

## 4. What the funnel-integrity step must assert (requirements)

| Inv | Class | Assertion (per daily-full run, fail = structured alert distinct from no-trade) |
|---|---|---|
| I1 | C1 | admitted/universe ≥ floor; n_tournament drop ≤30% d/d; `live_train_end ≥ last_session − k` |
| I2 | C2 | every `last_sell_dates[t]` equals a broker fill date ±1 trading day |
| I3 | C2 | broker sell fills ⊆ trades ledger (completeness) |
| I4 | C3 | fingerprint parity asserted pre-market; mid-run contract failure ⇒ `contract_failure` state, never `no_candidates` |
| I5 | C4 | serving-axis max-date lag ≤ N per feature family; alert on monotone lag growth |
| I6 | C5 | buy-capability SLO: ≥2 consecutive dead-buy-path sessions ⇒ page (cause-agnostic) |
| I7 | C6 | active bars vs max-achievable μ/er/Δw; bar > max for ALL candidates ⇒ `STRUCTURAL_BLOCK` |
| I8 | C7 | any gate with 100% kill-rate ⇒ `funnel_kill` alert naming the gate; n_buys==0 carries dominant-gate attribution |
| I9 | C8 | exactly one completed daily-full decision per NYSE session (heartbeat) |
| I10 | all | the decision notification must carry `capability: FULL / DEGRADED(reason) / BLOCKED(reason)` computed from I1–I9 — a no-trade without a clean capability bill is not reportable as "no trade" |

## Appendix A — full-block session list (27)

05-19, 05-20, 05-21, 05-22*, 05-26, 05-27, 05-28, 05-29, 06-01, 06-02, 06-03, 06-04,
06-05, 06-08, 06-09*, 06-10*, 06-11, 06-12, 06-15, 06-16, 06-17, 06-18, 06-22*,
06-30, 07-06*, 07-08, 07-09.  (* = manual same-day rescue placed buys.)

## Appendix B — reproduction signatures

- DB: `pipeline_runs` (`run_type='live'`), `candidate_scores.blocked_by` funnel per
  run, `trades` joined on `run_id` prefix for fill dates, `live_state_snapshots.state_json
  → last_sell_dates`, opened with `sqlite3 file:…?immutable=1`.
- Log patterns (daily_104): `live.runner: <TK> (no_artifact|stale_\d+d_limit_\d+(:live_train_end)?|sharpe_.*), skipping`;
  `Phase 2b (buy scan): N candidates from M tickers`; `preflight ✗ P-…`;
  `FLIGHT FAILED — aborting cron`; `finished sell-only fallback`;
  `DROP_WashSaleFilter [TK]: sold Nd ago`; `RegimeModelAdmissionTask … decision=BLOCK`;
  `panel_scorer_config_mismatch`; `fundamentals feed STALE: max date …`;
  `admission shadow: … n_tournament=N`; `infeasible with C2 caps`;
  `ntfy sent: RENQUANT-104 [full|sell-only] DECISION | …`.
- Intraday: `preflight ✗ P-FUND-FRESHNESS … blocking new buys` (41× on 2026-06-29).
