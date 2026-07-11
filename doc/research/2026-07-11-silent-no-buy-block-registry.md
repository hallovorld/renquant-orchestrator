# Silent no-buy block registry — whole-history retrospective (2026-07-11)

**Status:** research registry (requirements input for the funnel-integrity pipeline step).
r2 (Codex review, 2026-07-11): evidence sealed to `renquant-artifacts` (mutable DB/log/state
paths were the r1 evidence citation), denominator formally predeclared and cross-checked,
GE broker-truth date corrected (was 05-18, a canceled order — true value is 06-01, with a
downstream correction to the "GE wrongfully blocked in 8 sessions" claim), descriptive-vs-
validated framing added, and a per-invariant (I1-I10) online-identifiability assessment added.
**Scope:** every session of the RenQuant-104 live era, 2026-04-21 → 2026-07-10 (56 NYSE
sessions, denominator predeclared and cross-checked three independent ways — see §0).
READ-ONLY forensic sweep; no production state touched.
**Sources:** the durable forensic record for this doc is
[`renquant-artifacts#17`](https://github.com/hallovorld/renquant-artifacts/pull/17)
(`store://experiments/silent-no-buy-block-registry-20260711/RUN-LOCK.json`) — a sealed,
content-addressed extract of the population/denominator rule, per-session raw signals for
all 56 real sessions (each citing its source log's sha256), the C1-C8 classifier rubric, the
I1-I10 online-identifiability assessment, and fresh broker-truth evidence for GE/HON/EQIX.
It was built read-only from `data/runs.alpaca.db` (immutable open — `pipeline_runs`,
`candidate_scores`, `ticker_daily_state`, `live_state_snapshots`, `trades`), all
`logs/daily_104/*.log` and `logs/intraday_104/*.log`, `live_state.alpaca.json`, and a fresh
Alpaca `TradingClient.get_orders` read-only query — those live-tree/mutable paths are the
ORIGINAL sources the sealed bundle was extracted from, not this doc's durable citation.
**Method:** reused the extraction logic of
`.claude/skills/decision-tree-review/scripts/extract_decision_tree.py`
plus a normalized-template mining pass over all `logs/daily_104/2026-*.log` and
`logs/intraday_104/*.log`, plus latest `live_state` snapshot vs broker-truth fills.
Key patterns and queries are in Appendix B so the sweep is reproducible.

---

## 0. Predeclared population & denominator

**Rule (checked, not assumed):** every calendar date in [2026-04-21, 2026-07-10] for which
`logs/daily_104/<date>.log` (bare filename, no suffix) exists is *cron-fired*. A cron-fired
date is `MARKET_CLOSED` if the log body is the self-declared "NYSE closed today ... skipping
run" skip-stub (≤6 lines, no decision content). Every other cron-fired date is `REAL_SESSION`.
Any weekday-minus-federal-holiday date with **no** log file at all would be `MISSING_LOG` —
checked for; none exists in this window.

- 61 cron-fired dates total: **56 REAL_SESSION + 5 MARKET_CLOSED** (2026-04-25 Sat,
  2026-05-25 Memorial Day, 2026-06-07 Sun, 2026-06-19 Juneteenth, 2026-07-03 Independence
  Day observed) **+ 0 MISSING_LOG**.
- Cross-check: 56 REAL_SESSION == (59 weekdays in the window) − (3 federal-market holidays:
  05-25, 06-19, 07-03) == the 56-row per-session table in §3. All three counts agree
  independently; no session was silently dropped from the denominator.
- **6 REAL_SESSION dates produced zero decision notification of any kind** (no `ntfy sent:
  RENQUANT-104 [full|sell-only] {DECISION,TRADE,PENDING,PREFLIGHT-FAIL,BUY-BLOCKED}` line):
  2026-04-21, 04-22, 04-28, 05-05, 05-07, 06-05. These carry an explicit
  `MISSING_DECISION_NO_NOTIFICATION` disposition in the sealed bundle and are **never**
  counted as an economic no-trade decision, per Codex's review. Per-date manual confirmation
  (sealed in `renquant-artifacts#17`):
  - **04-21** — pipeline completed twice (0 orders both times, drawdown circuit-breaker halt
    at 90% ≥ 35%) but never emitted an ntfy line — the very first live session; notification
    on a zero-order outcome appears not to have been wired yet. A genuine circuit-breaker
    halt, not a silent crash, but never externally communicated.
  - **04-22** — **new finding, not in the r1 draft, and more nuanced than a simple crash:**
    the log shows three same-day script invocations (13:55, 17:33, 22:26 PDT — likely manual
    reruns during initial live rollout, this being the 2nd live session). The first two
    completed the inference pipeline in ~0.2s with `SizeAndEmitTask: 0 orders placed` each
    time, but neither emitted an ntfy line of any kind — the same "0-orders produces no
    notification" gap seen on 04-21, not obviously any single C1-C8 class. The **third**
    invocation (22:26) is the one that truncates mid-run at line 421 (last line:
    `LoadInsiderTradesTask` fetching missing tickers) and never reaches decision-emission —
    that part is a genuine C8 (run crash). r1 folded the whole day into a generic
    "degraded-inputs" C4 label without surfacing either of these; this round reclassifies
    it C4/C8 (mixed) with both mechanisms stated explicitly.
  - **04-28, 05-05, 05-07** — training pipeline `FAILED` (calibrator-refresh guard /
    exception); each log ends at the `FAILED` line, same-day decision phase never reached.
  - **06-05** — process `Terminated` (SIGTERM) mid-run during the news-sentiment-refresh
    step. Matches the original C8 classification exactly.

**Why this matters — and a second, larger correction it surfaced:** cross-checking every
zero-buy session against this doc's OWN per-class citations (§2's C4/C7/C8 tables) against
Appendix A's "27 full-block" list found Appendix A itself under-counts. It only captures the
abort/sell-only-fallback/scan-collapse style of full block, and silently omits sessions this
doc's own C7 table already cites as 100%-single-gate kills (**05-04, 05-06**:
`veto:rank_score_below_floor` → `no_candidates`, independently re-confirmed against the raw
log this round; **06-25, 06-26**: `risk_gate_vol_dropped(21/22)`, also re-confirmed) and the
five early training-pipeline-crash sessions this correction round newly verified against raw
logs (**04-21, 04-22, 04-28, 05-05, 05-07**). All nine have buys=0 and a citation-backed
engineering cause, by this doc's own taxonomy — they were just never added to Appendix A's
list, which understates the headline. §1's 27/56, 67%, and 11/33 figures are corrected below;
see the recomputed accounting there. The two remaining zero-buy sessions not claimed as
engineering here (**04-24**: `no trade (defensives_filtered(1))`, a portfolio-construction
decision with 5-6 real candidates, not a funnel kill; **05-11**: the paper/live dual-track
gap, re-confirmed via `PaperBroker.place_order` lines showing paper-side buys with no live
counterpart — plausibly a live-specific risk control rather than a bug, not re-classified
here for lack of evidence either way) are the only sessions this sweep cannot rule out as a
genuine economic no-trade.

---

## 1. Bottom line

- **The live system is 56 sessions old — a "last 120 sessions" window does not exist.**
  All numbers below are over the full 56-session live history.
- **Corrected accounting (r2 — see §0 for the derivation):** Appendix A's original
  "27 full-block" list under-counted by omitting sessions this doc's own §2 class tables
  already cite as 100%-engineering-kill. Adding **05-04, 05-06, 06-25, 06-26** (C7,
  independently re-confirmed against raw logs this round) and **04-21, 04-22, 04-28, 05-05,
  05-07** (C4/C8 training-pipeline crashes / drawdown-halt / truncated run, newly verified
  against raw logs) gives **36 / 56 sessions (64%)** where the scheduled buy path was fully
  dead for a non-economic, engineering cause — not 27/56 (48%) as originally stated.
- **33 / 56 sessions had zero live buys. 31 of those 33 (94%) are engineering-attributable
  by this doc's own class citations** — not 22/33 (67%) as originally stated. Only **2/33**
  (04-24: a portfolio-construction filter with real surviving candidates; 05-11: an
  unresolved paper/live dual-track gap) are not claimed as engineering here; that is the
  outer ceiling on genuine economic no-trade days in this history, not 11/33.
- **8 more sessions were materially non-zero-buy but degraded** (wrongful wash-sale blocks,
  admission staleness creep, universe collapsed to 45%, intraday buy path dead all day) —
  this bucket's own count was not re-verified in this correction round (it is disjoint from
  the corrected 36, since all 9 newly-added sessions are zero-buy). Combining the corrected
  36 with the original, un-re-verified 8 gives **44 / 56 (79%) degraded-or-dead**; treat the
  "8" component of that figure with the same descriptive, not re-audited, caveat as the rest
  of §5.
- **Input-integrity overlay (fully silent):** the fundamentals actually served to the
  scorer were frozen at 2026-02-10 → 70–121 d stale for every session until 06-12,
  and ~88–92 d stale until 06-23 (~40 sessions). First signal of any kind: a log
  WARNING added 06-11. Zero decision-level signal, ever. [VERIFIED from
  `fundamentals feed STALE` lines 06-11 → 06-23]
- **Flagged at the time (corrected for the 36-session full-block figure):** 17 (47%) loud
  (PREFLIGHT-FAIL / abort ntfy), 10 (28%) semi (block-reason string embedded in a
  routine-looking "no trade (…)" notification — includes the newly-added 05-04, 05-06,
  06-25, 06-26), **9 (25%) fully silent** (04-21, 04-22, 04-28, 05-05, 05-07, 06-05: no
  report at all; 06-30, 07-08, 07-09: reported as a normal `no trade (no_candidates)`,
  indistinguishable from an economic no-trade). Of the 8 degraded sessions and the
  40-session stale-fundamentals overlay: **0% flagged at decision level.**
- **Still broken today [VERIFIED against 2026-07-10 live_state snapshot; re-verified fresh
  2026-07-11 against the live broker, sealed in `renquant-artifacts#17`]:** `last_sell_dates`
  stamps GE=2026-06-26 (broker truth **2026-06-01**, corrected from an earlier erroneous
  05-18 citation — that was a canceled order, never filled), HON=2026-06-26 (truth 06-03),
  EQIX=2026-06-26 (truth 06-17). **Correcting the GE date changes the wrongful-block count:**
  GE's true 31-day wash window closes 2026-07-02 (06-01 + 31 d); sessions 06-23 → 07-01 were
  within that true window and would have been correctly blocked even absent the mis-stamp —
  only **2026-07-10** (39 d since the true sale) is confirmed wrongful in the evidence cited
  here, not "8 sessions" as originally stated (07-03 → 07-09 were not independently
  re-audited for a GE wash-drop line in this round, so the true count for that gap is
  unknown, not zero). HON is wrongfully blocked since 07-04; EQIX becomes wrongfully blocked
  07-18 → ~07-27 unless the stamps are corrected. The code fix (fill-date lookup,
  `EXT_SELL_LOOKBACK_DAYS=45`) is in the umbrella working tree
  (`backtesting/renquant_104/adapters/runner_ext_sell.py`). **Update:** the live-state stamps
  for all three names were corrected directly on 2026-07-11 (operator-approved, following
  the same precedent as the META correction; backed up before writing) — GE→06-01,
  HON→06-03, EQIX→06-17 — re-verified fresh against the live `live_state.alpaca.json` and a
  fresh read-only broker query as part of sealing `renquant-artifacts#17`. This closes the
  live-state side of the recurrence; it does not establish these three were the only names
  affected by the underlying pre-fix reconciliation bug (see the open follow-up in this
  doc's memory record).

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

- **06-23 stamp event:** GE / HON / META stamped "sold 8 d ago" (=06-15). Broker truth
  (corrected — see below): **GE 2026-06-01**, HON 06-03, META 06-02.
- **06-26 mass re-stamp event:** reconciliation stamped GE, HON, META, EQIX all
  `last_sell_dates = 2026-06-26` ("sold 0d ago") — the heuristic discarded the real
  fetched fill date and stamped "today".
- **Realized wrongful blocks** (blocked while broker-truth age > 31 d) **— corrected**:
  the original draft cited GE's broker-truth last sell as 05-18 and claimed 8 wrongfully
  blocked sessions from that. That 05-18 date was a **canceled** order, never filled;
  re-derived strictly from `status=filled` sell orders, GE's true last sell fill is
  **2026-06-01**. GE's true 31-day wash window therefore closes **2026-07-02**, not
  ~06-19 as the wrong date implied — sessions 06-23 through 07-01 were inside the TRUE
  wash window and would have been correctly blocked even with a bug-free stamp; only
  **07-10** (39 d since the true sale) is confirmed wrongful in the evidence cited here.
  Whether GE was wrongfully re-blocked on any of 07-03 → 07-09 is **not established** by
  this sweep (those sessions' buy-scan universes mostly collapsed to 0 for unrelated C1
  reasons, so GE likely never reached the wash gate on most of them, but this was not
  individually re-audited). META's stamp was 24 d off; its realized wrongful window (from
  07-03) was masked by the C1 universe collapse, then live-corrected 07-01 (same-day,
  before this sweep). HON wrongfully blocked since 07-04 (not yet realized as a
  candidate-drop — it hasn't reached the wash gate as of the sessions covered here). EQIX
  pending (wrongful window 07-18 → ~07-27) as of this sweep's original write-up; both
  HON and EQIX were corrected in live state 2026-07-11 alongside GE (see §1).
- **Sub-finding (ledger gap):** sells executed in the 05-26 → 06-05 sell-only era
  (BAC, D, WFC, CSCO, DUK, FTNT, XOM, …) have **no sell rows in `trades`** — fills
  happened at the broker but were never persisted, so stamps from that era are
  unauditable from the DB.
- Pre-05-22 wash drops ran against the **paper** book (daily-full was paper until
  05-21) and cannot be adjudicated against Alpaca truth — excluded from the wrongful
  count rather than claimed.

**Looked like:** nothing. Wash drops are INFO log lines; never surfaced in the decision
notification. **Detected:** 07-01 forensics (META); this sweep (GE/HON/EQIX), 07-11.
**Fix today:** code fix present in the umbrella working tree (`runner_ext_sell.py`, 45 d
fill lookback) [VERIFIED file content]; state was NOT retro-corrected as of the 07-10
snapshot this sweep originally cited [VERIFIED], but **was corrected 2026-07-11** for
GE/HON/EQIX (operator-approved direct correction, same precedent as META) — re-verified
fresh against the live state file and a fresh broker query, sealed in
`renquant-artifacts#17`.

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
- **04-22 — corrected r2:** three same-day script invocations; the first two completed
  the inference pipeline (0 orders, no ntfy — see §0), the third truncates mid-run and
  never reaches decision-emission. r1's "(rerun same day succeeded)" parenthetical is
  wrong — no later invocation that day is confirmed to have produced a decision or ntfy
  line; re-verified against the raw log this round.
- **Training-pipeline crashes — corrected r2:** 04-28, 05-05, 05-07 each have a log that
  ends at the `Training pipeline FAILED` line — the SAME-day `daily_104.sh` invocation
  aborted there and never reached the decision phase at all (r1's "decision unaffected
  same day" was wrong for these three, re-verified against the raw log this round). They
  also froze the tournament going forward (feeds C1a). 04-21 is mechanistically different:
  its inference pipeline DID complete (twice, 0 orders via drawdown-circuit-breaker halt,
  see §0) — it belongs here only because neither completed run emitted an ntfy line, not
  because of a training-pipeline crash blocking that day's own decision phase.

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
| 06-23 | 10 | degraded — wash mis-stamp (GE 22d true age, within true wash window — see §2 C2 correction), stale creep begins | C1/C2 | NO |
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

| Inv | Class | Assertion (per daily-full run, fail = structured alert distinct from no-trade) | Online-identifiable? |
|---|---|---|---|
| I1 | C1 | admitted/universe ≥ floor; n_tournament drop ≤30% d/d; `live_train_end ≥ last_session − k` | **Yes** — pure function of the same session's own admission counters, no hindsight needed |
| I2 | C2 | every `last_sell_dates[t]` equals a broker fill date ±1 trading day | **Yes** — requires a synchronous broker fill-date fetch at stamp-write time (the lookup already exists as a side query; it just needs to gate the write instead of being discarded) |
| I3 | C2 | broker sell fills ⊆ trades ledger (completeness) | **Partial** — only checkable on ledger rows that exist; a ledger-write failure (the confirmed 05-26→06-05 gap) is itself invisible to an in-pipeline check without an independent broker reconciliation pass run separately |
| I4 | C3 | fingerprint parity asserted pre-market; mid-run contract failure ⇒ `contract_failure` state, never `no_candidates` | **Yes** — fingerprint parity is a pure function of already-loaded artifacts, assertable before the pipeline runs |
| I5 | C4 | serving-axis max-date lag ≤ N per feature family; alert on monotone lag growth | **Yes** — the lag itself is known at feature-load time; the derivative (day-over-day growth) needs one prior session's value persisted, which is a 1-session memory, not hindsight |
| I6 | C5 | buy-capability SLO: ≥2 consecutive dead-buy-path sessions ⇒ page (cause-agnostic) | **Yes** — a running counter by construction |
| I7 | C6 | active bars vs max-achievable μ/er/Δw; bar > max for ALL candidates ⇒ `STRUCTURAL_BLOCK` | **Yes** — computable from the same session's candidate set before the decision is emitted |
| I8 | C7 | any gate with 100% kill-rate ⇒ `funnel_kill` alert naming the gate; n_buys==0 carries dominant-gate attribution | **Yes** — same-session funnel counters; the 3-session-80% variant needs a short rolling window of already-available prior sessions |
| I9 | C8 | exactly one completed daily-full decision per NYSE session (heartbeat) | **Yes, but only as an EXTERNAL watchdog** — the defining C8 scenario (2026-06-05) is precisely when the run cannot self-report; this invariant cannot live inside the pipeline task it is meant to police |
| I10 | all | the decision notification must carry `capability: FULL / DEGRADED(reason) / BLOCKED(reason)` computed from I1–I9 — a no-trade without a clean capability bill is not reportable as "no trade" | **Composite** — inherits I9's caveat: if the run never starts or finishes, no in-pipeline task can emit a capability bill, so the external watchdog is a structural prerequisite for I10 on a C8 session, not an optional enhancement |

Full derivation sealed in `renquant-artifacts#17` (`online_identifiability_i1_i10` block).

## 5. Methodological caveats: descriptive taxonomy, not a validated detector

This registry is a **retrospective, descriptive classification** of one historical
population (56 sessions, one strategy, one live account). It is NOT:

- **A validated detector performance estimate.** The 36/56, 94%, and per-class percentages
  above describe what happened in this specific window; they are not precision/recall
  figures for the I1-I10 invariants, because no online detector existed during this window
  to measure against. Do not read "94% of no-buy days were engineering" as "a live I1-I10
  detector would catch 94% of future incidents" — that is an untested claim.
- **A basis for default-on alert thresholds.** Specific numeric thresholds floated in §2/§4
  (30% d/d tournament drop, 45-day freshness limit, 2-session dead-path SLO, etc.) are
  carried over from the incidents that motivated each invariant, not fit or validated
  against a labeled dataset. `renquant-pipeline#186`'s implementation should treat these as
  starting points requiring their own validation (e.g. a shadow/observe-only period), not as
  pre-approved production thresholds.
- **An exhaustive audit.** The C1-C8 taxonomy and the classifier rubric sealed in
  `renquant-artifacts#17` are versioned (`silent-no-buy-classifier-v1`) specifically so
  future revisions are traceable, because this round's own re-verification pass (§0, §2 C2)
  already found and corrected two classification errors in the r1 draft (the GE broker-date
  error and the Appendix A under-count) — a strong prior that further undiscovered errors
  remain, not a signal that the taxonomy is now exhaustively correct.

The correct use of this document is as **requirements input** for `pipeline#186`'s detector
design (which invariants to implement, in what order, with what online-identifiability
constraints) — not as a certified measurement of system reliability.

## Appendix A — full-block session list (36, corrected r2)

**Original abort/sell-only/scan-collapse style blocks (27):** 05-19, 05-20, 05-21, 05-22*,
05-26, 05-27, 05-28, 05-29, 06-01, 06-02, 06-03, 06-04, 06-05, 06-08, 06-09*, 06-10*, 06-11,
06-12, 06-15, 06-16, 06-17, 06-18, 06-22*, 06-30, 07-06*, 07-08, 07-09.
(* = manual same-day rescue placed buys.)

**Added r2 (C7 100%-single-gate-kill sessions already cited in §2's C7 table but omitted
here originally, independently re-confirmed against raw logs):** 05-04, 05-06, 06-25, 06-26.

**Added r2 (C4/C8 training-pipeline-crash / drawdown-halt / truncated-run sessions, newly
verified against raw logs this round — see §0):** 04-21, 04-22, 04-28, 05-05, 05-07.

Total: 27 + 4 + 5 = **36**. None of the 9 additions carry a rescue asterisk (all 9 remained
zero-buy).

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
