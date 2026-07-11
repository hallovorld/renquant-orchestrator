# Exit/entry plane coherence + durable broker-reconciled wash-sale ledger

STATUS: DESIGN ONLY — no implementation, no runtime change in this PR.
DATE: 2026-07-11
SCOPE: the two remaining fixes from the ZM/NFLX forensics (orchestrator #484
§8, fixes 5 and 6): (1) scoring-plane coherence for `ModelProtectionExitTask`;
(2) a durable, broker-reconciled, append-only wash-sale ledger replacing the
mutable `live_state.last_sell_dates` dict as the authority for the wash gate.
Both are behavior-adjacent → design-first per the fix-wave rule (behavior
changes ship as staged, flag-gated PRs with shadow evidence; production keeps
placing orders unchanged until each enforcement stage is separately approved).

Companion evidence: #484 (`doc/research/2026-07-11-zm-nflx-buy-bias-forensics.md`
§2, §7.1, §7.2, §8), #474 (silent no-buy block registry — GE/HON/EQIX wrong
stamps, degradations 0% flagged at decision level), #473 §5 (per-ticker
vintage collapse), umbrella RenQuant #428 (STATE-EXT-SELL fill-date truth,
MERGED 2026-07-02 — reused here as the date-truth foundation). All file:line
facts and the §2.2 firing history were established this session by read-only
inspection of the pipeline/execution/umbrella code, `logs/daily_104` +
`logs/intraday_104`, a scratchpad COPY of `runs.alpaca.db`, and
`live_state_snapshots` `[VERIFIED — no git command in the live umbrella tree
or any primary checkout; no production path opened for write]`.

---

## 1. Bottom line

**D1 — plane coherence (Item 1).** A model too stale to BUY with is too
stale to fire a THESIS exit with — and a model that did not admit a position
(and is not a validated successor of the one that did) does not get
unilateral sell authority over it. The protection exit's mu must come from a
scoring plane that (i) passes the *same fail-closed staleness axes the buy
path already enforces* (`FilterStalenessTask`, the Codex-reviewed template)
and (ii) is *coherent* with the plane that admitted the position. Decision
on the fail-direction question: **hybrid — fail-SAFE first (defer the strike
evaluation to the coherent, fresher plane when one qualifies), fail-CLOSED
only as the backstop (skip the thesis exit + page CRITICAL when NO plane
qualifies)**. Path-risk exits (regime stop-loss, trailing stops, sell-gate
B, broker-side GTC catastrophe line, `CrossSectionalPanelExit`) are
explicitly untouched — exits-always-allowed is preserved; this governs only
the model-*opinion* exit. Evidence scale (§2.2): this is not a one-off — 9
protection exits in the task's 20 live trading days, **8 of 9 fired while
the panel plane scored the same name POSITIVE**, every strike sequence ever
started ran 1→2→3/3 with **zero resets in live history**, and 3 of 9 went
first-strike→sell in **24 minutes** against a debounce specified as "3
consecutive DAILY evaluations". Replayed under D1, the one clear good save
(EQIX) is preserved and the clear whipsaw (NFLX) is prevented (§2.3).

**D2 — durable wash-sale ledger (Item 2).** Wash-sale enforcement moves from
a mutable dict inside a whole-file read-modify-write `live_state` (no lock,
three concurrent writer cadences — the erasure hole) to an **append-only,
hash-chained, broker-fill-keyed ledger** whose rows are created from the
broker activity feed (truth) by a nightly reconciler built on the already-
merged #428 toolkit (`runner_ext_sell.py`). Writes are INSERT-only; every
correction is a supersession row; erasure becomes impossible by construction
and *detectable* by the hash chain. **Owner: renquant-execution** (broker
truth is its declared domain and it already carries the graduated
`live_persistence` implementation), with renquant-pipeline owning the pure
gate-derivation function, the umbrella runner reduced to minimal consumer
glue during migration (it must not gain new authority — the Codex R-PIN
posture), and **renquant-orchestrator owning the nightly invariant checker**
(I-W1..6, §3.6). Four-phase migration from `live_state.last_sell_dates`;
Phases 0-1 are zero-runtime-change and immediately establish broker-truth
dates for the standing GE/HON/EQIX mis-stamp class.

Decision needed from review: approve D1's hybrid fail-direction + D2's
execution-repo ownership and the phase gates; everything else is staged
behind flags and separately approvable.

---

## 2. Item 1 — exit/entry plane coherence

### 2.1 The defect, mechanically `[VERIFIED — code inspection]`

The buy plane and the protection-exit plane are different models with
different vintages, and nothing in the system relates them:

- **Exit mu source.** `ModelProtectionExitTask`
  (`renquant-pipeline src/renquant_pipeline/kernel/pipeline/task_sell.py:467-562`)
  reads `hs.expected_return` (task_sell.py:508-512), which is set by
  `ScoreModelTask` (task_sell.py:157-165: `tc.holding.expected_return =
  float(sr.expected_return)`) from `tc.model` — the **per-ticker artifact**
  `ctx.models.get(ticker)` (`kernel/pipeline/pp_inference.py:149`), i.e.
  `models/<TICKER>/<TICKER>-policy-metadata.json` + weights
  (`kernel/models.py:231-303`). The panel plane also sets
  `hs.mu`/`hs.expected_return` (`job_panel_scoring.py:2826-2849`), but
  `PanelScoringJob` is Phase 3 (pp_inference.py:533) and runs AFTER the
  Phase-2a sell pass (pp_inference.py:377) — and in the intraday
  `SellOnlyPipeline` (pp_inference.py:696-750) **the panel never runs at
  all**. The protection exit therefore always fires on the per-ticker plane.
- **The staleness waiver that arms it.** The buy path has a real fail-closed
  vintage gate — `FilterStalenessTask`
  (`kernel/pipeline/job_universe.py:267-342`): axis fields
  `TRAINING_DATA_FIELDS = ("effective_train_cutoff_date","data_cutoff_date",
  "live_train_end","cutoff_date")` (lines 120-125), every present axis must
  pass (`_classify_cutoffs`, 220-248), offensive buys fail closed naming the
  exact failing field (281-285, 335-338) — this is the gate whose per-ticker
  arm collapsed the 07-08 universe (#473 §5). But held names are
  **deliberately waived** (job_universe.py:318-324), and the waiver says so
  in production: `NEE HELD — admitting despite stale trained_date=2026-04-30
  (age=61d > limit=60d, so sell path stays armed)`
  (`logs/daily_104/2026-06-30.log:217`). Correct goal, wrong grain: the
  waiver keeps the stale model loaded so the *mechanical* sell path stays
  armed, but as a side effect its *opinion* (mu) keeps unilateral thesis-exit
  authority with no age bound. `P-MODEL-STALENESS` is warn-only and
  panel-only (`preflight_pipeline/tasks/staleness.py:1-50`).
- **Zero identity plumbing.** No model sha/vintage is stamped anywhere in
  the exit chain: `ScoreResult` (`kernel/models.py:308-313`), `HoldingState`
  (`kernel/exits.py:148-214`), `ExitSignal` (`kernel/exits.py:368-385`), and
  the persisted entry snapshot `entry_signals[t] = {rank_score, panel_score,
  kelly_target_pct, regime}` (umbrella `backtesting/renquant_104/adapters/
  runner.py:1593-1598`) all lack it. A holding cannot answer "which model
  admitted me"; an exit record cannot answer "which model fired me" (the
  NEE firing run's log is missing entirely — DB-only evidence; per-strike mu
  values are never persisted anywhere).
- **Two exits, two planes, no contract.** `CrossSectionalPanelExitTask`
  (`kernel/pipeline/task_panel_conviction_xs.py:206-207`) reads the panel
  plane (`hs.panel_score`, `hs.mu`); `ModelProtectionExitTask` reads the
  per-ticker plane. The book runs both with no coherence contract — the NEE
  case froze the contradiction into a single DB row: sell signal
  `mu=-0.0534` beside snapshot `expected_return=+0.0414` (the panel
  overwrote the holding field after the sell pass, same run).

The NFLX instance (#484 §7.1): panel (trained 06-21) admits NFLX 06-22/23,
fill 06-24 @ 72.62; per-ticker NFLX model (`live_train_end=2026-04-23`, 63d
stale — past even the config's loose 60d limit and 2.25× the 28d governance
bar) re-scores it to −0.0505 by the 06-25 open → `thesis_breached
mu=-0.0505<=tau=+0.0000 strikes=3/3`
(`logs/intraday_104/2026-06-25.log:220`) → sold @ 71.39 (−1.69%), the local
low, while the panel plane replays **+0.066** the same day. The two planes
disagreed by ~0.12 raw and the stale one had unilateral sell authority.

### 2.2 Historical record — every ModelProtectionExitTask firing `[VERIFIED — read-only sweep: all logs since enablement + runs-DB copy + 620 live_state snapshots]`

Task enabled 2026-06-11 (strategy-104 `risk.model_protection`, operator
go-ahead in `_reason`). Denominator: 620 live pipeline runs over 20 trading
days, ~35 holding-evaluations/day, 13 distinct holdings evaluated. **9 of 13
held names were protection-exited (69%); all 9 sequences ran 1→2→3/3 and
sold; the "recovering reading resets" branch never fired once.** Plane
vintage at firing is log-verified per session from the runner MODEL SUMMARY
table; panel mu is the same-run or nearest prior full-run panel value
(1-6d old where noted).

| fired | ticker | protection mu (plane vintage → staleness at firing) | panel mu same/nearest day | fill | +5d / +10d / +20d vs fill | verdict |
|---|---|---|---|---|---|---|
| 06-17 | EQIX | −0.1160 (per-ticker Classification, train_end 04-23 → **55d**) | −0.0017 (06-11) | 1096.00 | −0.8% / −8.6% / n/a | **good save** |
| 06-24 | AVGO | −0.0267, 3 strikes in **24 min** (train_end 04-23 → **62d**) | **+0.0396** (06-23) | 384.66 | −4.0% / +4.3% / n/a | mixed (saved 6% dip, recovered by +10d) |
| 06-25 | NFLX | −0.0505 (train_end 04-23 → **63d**) | **+0.0343** (06-24; same-day replay +0.066) | 71.39 | **+8.8%** / +2.8% / n/a | **whipsaw** (never traded below fill) |
| 06-30 | NEE | −0.0534 (train_end 04-23 → **68d**) | **+0.0414 in the SAME run** | 87.47 | −0.4% (6d window) | flat/mild whipsaw (truncated) |
| 07-06 | SOFI | −0.0255 (train_end 06-23 → 13d) | **+0.0193** same run | 18.60 | 3d: −4.7%..+1.0% | leaning save (truncated) |
| 07-08 | MCHP | −0.1672 (train_end 06-23 → 15d) | **+0.0337** (07-07) | 83.53 | +2d: **+5.7%** | leaning whipsaw (truncated) |
| 07-08 | AMZN | −0.0095, 3 strikes in **24 min** (trained 07-08 but **train_end 04-23 → 76d**) | **+0.0102** (07-07) | 241.47 | +2d: +1.6..2.3% | leaning whipsaw (truncated) |
| 07-10 | CSCO | −0.0969 (train_end 06-23 → 17d) | **+0.0337** (07-09) | 117.59 | none yet | unknown |
| 07-10 | PANW | −0.0228, 3 strikes in **24 min** (train_end 06-23 → 17d) | **+0.0422** same day | 338.27 | none yet | unknown |

Reading, honestly in both directions:

- **Plane disagreement is the norm, not the exception**: 8/9 firings had the
  panel plane positive on the name at firing time. The per-ticker and panel
  planes are structurally different views, not one view at two freshnesses.
- **Staleness made June worse but freshness did not fix July**: the four
  June firings all ran on 55-68d-stale planes (2-2.4× the 28d governance
  bar, and past the 60d config limit — only the held-name waiver kept them
  armed). The 07-09 retrain brought planes to 13-17d, yet MCHP/AMZN still
  lean whipsaw — coherence (identity), not freshness alone, is the binding
  principle. The AMZN row is its own exhibit: `trained 07-08` with
  `train_end 04-23` (76d) — `trained_date` lies about information vintage,
  which is exactly why the design keys on the train-end axis fields and
  never on `trained_date` (matching FilterStalenessTask's own axis choice,
  job_universe.py:116-117).
- **The debounce is not debouncing**: 0 resets in 620 runs; strikes accrue
  per pipeline run, not per day — worst case 3 consecutive 12-minute
  intraday bars (AVGO, AMZN, PANW: 24 minutes first-strike→sell), directly
  contradicting the config's stated contract "N=3 CONSECUTIVE daily
  evaluations" (§2.6).
- **Outcome tally to date**: 1 clear good save (EQIX), 1 clear whipsaw
  (NFLX, −1.69% realized then +8.8%/+5d), 1 mixed (AVGO), 2 leaning whipsaw
  (MCHP, AMZN), 1 leaning save (SOFI), 1 flat (NEE), 2 too recent (CSCO,
  PANW). Labels are short-horizon (+5/+10/+20d against a 60d thesis) and
  several windows are truncated at the 07-10 data edge — they price the
  whipsaw error, not the rule's alpha.

**D1 counterfactual over the same 9 firings** (deferral to the panel plane,
tau unchanged at 0.0): EQIX's panel mu was −0.0017 ≤ tau → strikes still
accrue → **the one clear good save is preserved** (later by up to 2 sessions
under session-grain accrual — disclosed cost); the other 8 had panel mu >
tau → strike resets → no exit, including the NFLX whipsaw. Fail-closed
(skip) would instead have suppressed EQIX too. This asymmetry is the
concrete argument for deferral-first over pure fail-closed.

### 2.3 Error-cost analysis: the two failure modes

**Error A — fire on garbage (status quo).** Realized costs, NFLX case: (1)
the whipsaw — sell −1.69% at the open of a −1.3% down day, name +8.8% five
days later; (2) **wash-sale clock pollution** — the loss sale starts a 30d
re-entry block against the *fresh* plane's own bullish view (the system
fights itself: panel buys, stale plane force-sells, wash clock blocks the
panel from re-entering — and that clock then got erased, Item 2); (3)
transaction cost + tax churn; (4) the debounce defeated (§2.6). Frequency
is NOT rare: 0.45 exits/trading day, 69% of held names exited in 20 days —
at this base rate the whipsaw share of §2.2 recurs weekly, silently
(every firing looks like a normal exit; #474: degradations 0% flagged).

**Error B — suppress a true exit (the risk any gating introduces).** If a
thesis exit is skipped and the name genuinely deteriorates, the loss is
bounded by the layered path-risk backstops, all unconditional `[VERIFIED —
pinned strategy-104 config 0e5d9891]`: regime stop-loss
(`regime_params.*.stop_loss_pct`: BULL_CALM 0.15, BULL_VOLATILE/BEAR 0.05,
CHOPPY 0.08), trailing stops, sell-gate B, `CrossSectionalPanelExit` (panel
plane, ledger-confirmed predictive — untouched), and the broker-resident
GTC catastrophe line (`live.broker_side_stops`: 20%, dead-box guard). Worst
incremental exposure vs status quo = the gap between where the mu exit
would have fired and the nearest backstop — in BULL_CALM up to ~15% of a
single position's remaining path *if* the panel exit also stays silent.
Two mitigations bound this: (i) fail-CLOSED is the backstop, not the
default — the default (deferral) keeps a thesis exit ARMED on the freshest
validated view, and §2.2's counterfactual shows deferral preserving the one
historical good save; (ii) the fail-closed state is loud (CRITICAL page)
and self-describing: reaching it means NO validated fresh plane exists for
a held name — an operations emergency independent of any single exit, and
exactly the condition of the 06-26..07-02 silent-regression window.

**Asymmetry.** Error A converts model-plane engineering debt directly into
realized losses and 30d capital locks, at a measured 0.45/day base rate,
with no alarm. Error B is stop-bounded, requires every plane stale at once,
and pages. The design biases against Error A while refusing to widen Error
B beyond the paged, stop-bounded case.

### 2.4 Decision (a) — the freshness bar and the fail direction

**Rule: the mu that drives a protection exit must come from a plane passing
the SAME fail-closed staleness axes that gate offensive buys** — literally
the same classifier (`FilterStalenessTask._classify_cutoffs` over
`TRAINING_DATA_FIELDS`, same config, same verdicts), not a new parallel bar
(check-existing-contract rule: one staleness contract, two consumers). The
held-name waiver (job_universe.py:318-324) is *narrowed*, not removed: a
stale per-ticker model still loads — the mechanical sell path (gate B,
stops, `fallback_exit`) stays armed exactly as the waiver intends — but its
**mu loses thesis-exit authority**.

Resolution order at each protection evaluation of holding `t`:

1. **Coherent plane** (§2.5): the admitting model identity, or a strictly
   fresher validated successor on the same plane, passing the staleness
   axes → evaluate strikes/exit normally.
2. **Fail-SAFE deferral**: the coherent plane is unavailable or stale, but
   the panel plane passes its rails → evaluate the strike/exit rule on the
   panel-plane mu (`hs.mu` from the latest `PanelScoringJob`, ≤1 session
   old, identity-stamped). Same units — both are calibrated 60d E[R−SPY];
   `exit_mu_threshold` applies unchanged. The thesis exit stays ARMED; this
   is not exit suppression (§2.2's counterfactual: EQIX still exits).
3. **Fail-CLOSED backstop**: no plane passes → skip the thesis exit this
   session, freeze strikes (no accrual, no reset), page CRITICAL
   (`protection_plane_unavailable`, naming both planes' vintages). This
   state implies the ADMISSION plane is itself stale/regressed — the same
   page doubles as an input to the model-identity regression tripwire
   (#484 fix 7, designed separately): the 06-26..07-02 silently regressed
   05-18 panel (39-45d old) would have tripped exactly this.

Why not pure fail-CLOSED (skip whenever the per-ticker plane fails)? It
discards a valid fresher opinion that exists on the panel plane, and §2.2
shows it would have suppressed the one historical good save (EQIX). Why not
pure fail-SAFE with no backstop? When every plane is stale, "defer"
degenerates into firing on garbage again — the regression window is the
existence proof that all-planes-stale happens in production.

Practical consequence, stated honestly: for panel-admitted positions
(everything since the 06-17 panel era), step 1's "same identity" is the
panel itself, so the per-ticker plane's mu effectively becomes advisory for
thesis exits — §2.2 (8/9 contradictions, both stale AND fresh) is the
evidence that this is the correct assignment of authority, not a loss.
The per-ticker plane retains thesis-exit authority only over positions it
admitted (the legacy per-ticker admission lane).

Numeric bar: no new number is introduced. The per-ticker plane inherits the
buy path's axes/thresholds verbatim; the panel plane's deferral eligibility
uses the panel rails that already exist (`task_data_availability.py`
`max_train_age_days`/`max_cutoff_age_days` + the 28d governance policy as
the alerting threshold). If review wants the 28d governance bar hard-wired
into `_classify_cutoffs` for both planes, that is a config change on top of
this design, not a different design.

### 2.5 Decision (b) — plane-coherence principle and identity threading

**Principle: any task that re-scores a HELD position with decision
authority must use (a) the same model identity that admitted the position,
or (b) a strictly fresher, validated (promotion- or governance-override-
recorded) model on an equal-or-better-validated plane. Otherwise its output
is advisory only.**

Identity is threaded as a new stamped fact (nothing today carries it, §2.1):

- **`ScoringPlaneIdentity`** (new frozen dataclass, renquant-pipeline
  `kernel/models.py`): `{plane: "panel"|"per_ticker", artifact_path,
  artifact_sha256, trained_date, train_end_axis}` where `train_end_axis` is
  the first present field of `TRAINING_DATA_FIELDS` (reusing the
  FilterStalenessTask axis contract; `trained_date` stays display-only,
  never an axis — the AMZN `trained 07-08 / train_end 04-23` row is the
  proof it must not be). `artifact_sha256` MUST come from the one shared
  file-hash implementation the run bundle already uses
  (`artifact_contract.py:331` `sha256_file`) — explicitly NOT a new
  hand-copied fingerprint (the calibrator triple-impl lesson: three
  independent hash impls made mismatch permanent by construction).
- **Stamp at admission**: when a fresh buy is recorded, extend
  `entry_signals[t]` (runner.py:1593-1598) and `HoldingState`
  (`kernel/exits.py:148-214`) with `admitted_by: ScoringPlaneIdentity`. The
  panel identity is already resolved per run (`_stamp_active_panel_scorer`,
  job_panel_scoring.py:732-756; run bundle `artifact_hashes.panel`,
  artifact_contract.py:318-361) — this design only persists it onto the
  position. Backfill for existing holdings: from the entry-date run
  bundle's `artifact_hashes.panel`; if unresolvable, `admitted_by = None`
  → coherence degrades to the freshness-only path (§2.4 steps 2-3), never
  to unguarded status quo.
- **Stamp at evaluation**: `ScoreModelTask` attaches the producing
  `ScoringPlaneIdentity` to the re-score (`ScoreResult` gains
  `produced_by`); `ModelProtectionExitTask` records `{produced_by,
  admitted_by, coherence_verdict, staleness_axis_value, strike_mu}` on
  EVERY evaluation (strike or exit) into the run bundle and the decision
  ledger — closing two observability holes §2.2 hit: per-strike mu values
  are currently never persisted, and one firing (NEE) has no log at all.
- **Coherence predicate** (pure function, unit-testable):
  `coherent(produced_by, admitted_by)` :=
  `produced_by.artifact_sha256 == admitted_by.artifact_sha256`
  OR (`produced_by.train_end_axis >= admitted_by.train_end_axis` AND
  `produced_by` passes the buy-path staleness axes AND `produced_by` has a
  promotion/override record). A fresher but never-promoted artifact (the
  05-18 silent-regression class — it re-entered primary with *no gate event
  of any kind*, #484 §6) is NOT coherent by construction.

### 2.6 Strike integrity (same defect, second face)

The config's own contract is "N=3 CONSECUTIVE **daily** evaluations"
(strategy-104 `risk.model_protection._reason`, citing the CUSUM/SPRT
debounce). In production, strikes accrue per *pipeline run*
(`protection_breaches` round-trips live_state on every cadence —
task_sell.py:514-518; runner.py:330, 1947): §2.2 measured three exits at 3
strikes in 24 minutes (three consecutive 12-min intraday bars) and zero
resets ever. Two rules restore the stated contract:

- **Session-grain accrual**: at most one strike increment per NY trading
  session per ticker (mirror `last_streak_inc_date`, which `sell_streak`
  already uses for exactly this). Within-session recovering readings CAN
  still reset (resets stay run-grain; only accrual is throttled) — biased
  toward the debounce actually debouncing.
- **Identity-scoped strikes**: each strike carries `produced_by.
  artifact_sha256`; a strike evaluated under a different plane identity
  than the current one resets the counter. Three strikes must be three
  consecutive daily readings of the SAME model's view, or the count
  measures deployment churn, not thesis breach.

This section is separable into its own PR if review prefers (it changes
exit *timing* even when the plane is coherent).

### 2.7 Decision (c) — staged rollout, shadow first

Flag-gated under `risk.model_protection.plane_coherence` (strategy-104
config; absent key = today's behavior + telemetry only):

- **Stage 0 — telemetry (no behavior change).** Stamp `admitted_by` at
  admission and `produced_by` + coherence verdict + per-strike mu on every
  protection evaluation; write to run bundles + decision ledger; log
  `would_have: {fired|deferred(panel_mu=…)|failed_closed}` per evaluation.
  Ships with the fix-wave behavior-invariance proof (A/B run,
  byte-identical orders).
- **Stage 1 — shadow + alarm.** Decisions unchanged, plus: ntfy WARN on
  every protection exit whose plane is incoherent/stale, CRITICAL page on
  the would-be fail-closed state, daily would-have-differed diff in the
  briefing. Advance criteria: ≥15 sessions AND ≥6 shadowed firings reviewed
  (at the measured 0.45/day base rate both bind in ~3 weeks) AND 0
  unexplained divergences between shadow verdicts and the §2.5 predicate.
- **Stage 2 — enforce.** Flip `enforce: true`: deferral + fail-closed
  become live decision paths. Rollback = flag off (one config revert, no
  code). Separate PR, separate approval.

Verification fixtures the Stage 0 PR must include: (i) NFLX 06-25 replay →
`deferred(panel_mu>0) → no exit, no strike` + WARN on 63d staleness;
(ii) EQIX 06-17 replay → `deferred(panel_mu=-0.0017) → strike accrues`
(good save preserved); (iii) 06-26..07-02 regression window →
`failed_closed` + CRITICAL; (iv) all 9 §2.2 firings replayed through the
predicate with expected verdicts pinned in the test.

### 2.8 Explicitly out of scope

- `CrossSectionalPanelExit` — ledger-confirmed predictive (BULL_CALM
  −0.081, t=−9.3); not relitigated; unchanged. Its plane (panel) already
  satisfies coherence for panel-admitted positions by construction.
- All path-risk exits (stops, trailing, gate B, broker GTC, earnings
  blackout) — unconditional, untouched; exits-always-allowed preserved.
- Model quality itself (#44 v2 features, F4 #479, gated retrain) — separate
  lanes; this design makes exits *coherent*, not *smart*.
- The per-ticker tournament refresh cadence — orthogonal; D1 removes its
  unbounded blast radius on exits regardless.

---

## 3. Item 2 — durable broker-reconciled wash-sale ledger

### 3.1 The failure record — three distinct holes, one root cause

`[VERIFIED — #484 §7.2b, #474, umbrella #428, code inspection this session]`

| # | hole | instance | consequence |
|---|---|---|---|
| H1 | wrong DATE stamped (reconciliation stamps "today", not the fill date) | META: stamped 06-26 vs broker fill 06-02 (24d over-extension) | wrongful blocks |
| H2 | stamp ERASED (state loss) | NFLX: `last_sell_dates[NFLX]=2026-06-25` written 06-25 13:42Z after the loss sale, GONE from the 06-26 17:00Z snapshot (10 keys → 7), still absent | 07-10 NFLX buy submitted 15d into the 30d window with `blocked_wash=0`; only an unrelated order cancel prevented the wash re-entry |
| H3 | names stuck in `entry_dates` re-stamped every session | GE/HON sat in `entry_dates` weeks after their sells → the `disappeared` loop (runner.py:1755-1759) re-fired per session, pre-#428 stamping "today" each time | GE wrongly wash-blocked 8 sessions (#474) |

H1/H3's date component is FIXED (umbrella #428, merged 07-02: fill-date
truth + `unresolved_preserve` + 45d lookback — §3.4 reuses that toolkit
wholesale). H2 is open and is what this design closes; H3's *stuck
entry_dates* precondition also disappears once state stops being a mutable
dict (the ledger has no per-session re-stamping loop at all).

**Root cause of H2 `[VERIFIED — code]`:** `last_sell_dates` lives inside
`live_state.alpaca.json`, loaded once per runner invocation (runner.py:331
via `adapters/state_store.load_live_state`), mutated in memory, and written
back as a **whole-dict replacement** at `commit()` (runner.py:1948 →
`save_live_state_atomic` runner.py:1990) — with **no file locking anywhere**
(no flock/FileLock in runner.py or state_store.py) and **three concurrent
writer cadences** (full daily, 30-min intraday sell-only, pre-close). Any
two overlapping invocations lose the later-arriving keys (classic lost
update). Two further erasure mechanisms exist: `RESTORE-FROM-DB`
(state_store.py:92-121 — on any JSON read failure, resurrects a ≤14d-old
snapshot wholesale and writes it back) and manual rewrites (a
`live_state.alpaca.json.bak_predeadlockfix_20260626_094930` backup exists —
a hand rewrite happened inside the NFLX erasure window). Which mechanism
fired on 06-26 is `[GUESS]`; that all three CAN fire is `[VERIFIED]`.
Point-fixing the dict (locks, key-merges) would still leave enforcement one
`git checkout`, one snapshot-restore, or one crash away from silent reset —
the 2026-06-25 incident class. Hence: move the authority out of mutable
state entirely.

The four current write/erase sites, for the migration inventory: runner
full-liquidation stamp (runner.py:1316-1318), STATE-EXT-SELL reconciliation
(runner.py:1814-1819, the #428-fixed path), fresh-buy key pop
(runner.py:1583-1587), GC prune of not-held stale keys
(runner.py:1901-1917).

### 3.2 Ownership decision `[VERIFIED — read-only inspection]`

Where live_state ownership sits TODAY: the **umbrella legacy runner**
(`backtesting/renquant_104/adapters/runner.py` + `adapters/state_store.py`
+ `kernel/persistence.py` — snapshots are `INSERT OR REPLACE` rows in the
runs DB, persistence.py:192-207, 1549+). `renquant-execution` carries a
graduated PARALLEL implementation
(`src/renquant_execution/live_persistence.py` — `_apply_sell` stamps
`last_sell_dates` at 175-177, own snapshot schema at 65-118) that the daily
path does not import yet (zero `renquant_execution` imports in
adapters/runner.py).

**Decision: the ledger writer + nightly reconciler are owned by
`renquant-execution`.** Rationale: (1) broker fills and order audit are its
declared repo role; (2) it already owns the graduated successor of exactly
this state plane — putting the ledger there converges the migration instead
of forking it; (3) the umbrella must not gain new authority (Codex R-PIN
verdict; new durable facts do not land in the deprecated umbrella); (4)
renquant-pipeline stays the *consumer* (§3.5) — it must not own
broker-truth ingestion (repo boundary: no broker adapters outside
execution). renquant-orchestrator owns the **checker** (§3.6) —
verification, not state (its monitor role, sibling of the #473 §8 alert).
The ledger FILE lives on the state plane beside the runs DB
(`backtesting/renquant_104/wash_sale_ledger.alpaca.jsonl` on the live
machine) — a data-path placement, not code ownership; it moves with the
state plane whenever the execution-repo migration relocates it.

### 3.3 Ledger specification

Append-only JSONL, one broker **fill event** per row — sells AND buys (the
block predicate needs both, §3.5); the broker activity feed is the truth
source. Per-broker file, like every other state artifact.

Row schema:

```
{
  "seq":                monotonically increasing int,
  "row_sha":            sha256 over (prev_row_sha + canonical row body),
  "prev_row_sha":       row_sha of the previous line ("" for genesis),
  "broker_activity_id": broker activity/order id — idempotency key,
  "symbol": str, "side": "sell"|"buy", "qty": float, "fill_price": float,
  "fill_timestamp_utc": broker timestamp (raw),
  "fill_trade_date_ny": NY trade date via _ny_trade_date_from_aware_timestamp (#428),
  "realized_pnl":       float|null (sells; compute_recent_realized_pnl lineage),
  "source":             "broker_reconciler" | "runner_provisional" | "backfill",
  "supersedes":         row_sha|null, "supersede_reason": str|null,
  "recorded_at_utc":    str, "producer_run_id": str
}
```

Rules (the "erasure impossible by construction" set):

- **INSERT-only.** No row is ever mutated or deleted; the file never
  shrinks. Corrections/duplicates/mis-dates are handled by appending a
  supersession row (`supersedes` = old `row_sha`); a row is *active* iff no
  active row supersedes it.
- **Hash chain.** Each row commits to its predecessor; truncation, in-place
  edit, or a restored-older-copy is detected by the checker (§3.6, I-W3)
  against its independently stored `(last_seq, head_sha)` cursor.
- **Idempotent appends.** The reconciler keys on `broker_activity_id`;
  re-running never duplicates an active row.
- **No compaction.** Volume is trivial at this account's fill rate; if that
  changes, compaction = a new genesis segment referencing the old head sha,
  never a rewrite.
- A mirror table in the runs DB (INSERT-only — explicitly not the
  `INSERT OR REPLACE` pattern the snapshots use) may be added for query
  convenience; the JSONL file is the authority.

### 3.4 Nightly reconciler (broker truth in; #428 as the date foundation)

A `renquant-execution` module, invoked nightly by the orchestrator's
scheduled monitor (and runnable ad hoc), reusing the #428 toolkit verbatim
rather than re-implementing it: `broker.get_filled_orders(after=…)` with
`EXT_SELL_LOOKBACK_DAYS = 45` (runner_ext_sell.py:29), schema normalization
`normalize_fill_record` (:49-98 — both broker fill schemas),
`_ny_trade_date_from_aware_timestamp` (:165-210 — TZ-correct trade date,
fails closed on naive timestamps), and side confirmation `ext_sell_fill_date`
(:213-255). Each fetched fill not already active in the ledger is appended
as `source=broker_reconciler`. Same-day runner knowledge (a sell the runner
just executed; a STATE-EXT-SELL detection) is appended immediately as
`source=runner_provisional`; the nightly pass supersedes provisional rows
with their broker-truth twin — or pages if none arrives (I-W4). The #428
`no_fill_fallback` ("today" only when truly nothing is known) survives only
inside provisional rows and MUST be superseded within one session.

### 3.5 Gate derivation — the block decision as a pure function

`wash_view(ledger, asof) -> {symbol: last_sell_info}` (renquant-pipeline,
pure, unit-testable): per symbol, over *active* rows — the most recent sell
fill with `fill_trade_date_ny > asof − wash_sale_days(30)` and **no later
buy fill** (re-expressing today's buy-pop semantics, runner.py:1583-1587,
declaratively: a subsequent fresh buy consumes the clock; nothing is ever
popped). The view returns exactly the mapping shape
`WashSaleFilterTask` / `is_wash_sale_blocked_with_cost`
(`kernel/pipeline/task_candidates.py:63-77`, `kernel/selection.py:111-163`)
consume today, `realized_pnl` included so the cost-aware gate is unchanged.
**Invariant: ledger row ⇔ block decision** (I-W2) — the gate's verdict must
equal this pure function of the ledger; no side state may add or remove a
block.

Migration-period read rule (Phase 2, §3.7): the runner supplies the gate
with `merge(wash_view(ledger), live_state.last_sell_dates)` taking the
per-symbol **max** date — the union fails toward blocking, and every
divergence between the two sources is itself an alert (I-W6). Same-day
sells are covered by provisional rows, so the live_state term is
transitional belt-and-braces only.

### 3.6 Invariant set + the orchestrator checker

Nightly job in renquant-orchestrator (monitor layer; read-only against
broker API + ledger + run bundles), paging on failure:

- **I-W1 completeness**: every broker sell fill in the last 45d ⇒ exactly
  one active ledger row (broker-feed diff; would have caught the NFLX
  erasure on 06-26, within one day).
- **I-W2 gate faithfulness**: per session, recorded `blocked_wash`
  verdicts == `wash_view` recomputed from the ledger as-of that session —
  both directions (catches the NFLX under-block AND the GE over-block
  classes).
- **I-W3 durability**: hash chain verifies end-to-end; `(seq, head_sha)`
  strictly advances vs the checker's stored cursor; file never shrank. Any
  violation = CRITICAL (tamper/restore/truncation evidence).
- **I-W4 date truth**: no active `runner_provisional` row older than one
  session; every non-provisional active row's date derives from a broker
  timestamp (the #428 foundation).
- **I-W5 reconciler freshness**: newest `broker_reconciler` row or an
  explicit empty-pass marker ≤ 1 session old; else page — the gate then
  runs on `merge()` per §3.5, never silently on live_state alone.
- **I-W6 migration consistency** (Phases 1-2): symbol-level diff of
  `wash_view` vs `live_state.last_sell_dates`, reported daily.

### 3.7 Migration path from `live_state.last_sell_dates`

- **Phase 0 — backfill (no runtime change).** One-shot: fetch broker fill
  history (≥90d), build the genesis ledger, run the checker once. This
  mechanically establishes broker-truth dates for the H1/H3 mis-stamp class
  and restores the erased NFLX 06-25 row (its 30d window runs to ~07-25).
  Whether any live_state correction is applied *before* Phase 2 is a
  separate ask-first operator action (live-tree mutation preflight rule);
  this design changes nothing live.
- **Phase 1 — shadow.** Nightly reconciler + checker live; I-W1..6
  alerting; the gate still reads live_state. Zero behavior change. Advance
  criteria: ≥10 sessions with I-W1/I-W3 clean and every I-W6 divergence
  explained.
- **Phase 2 — consume.** Gate input becomes `merge(wash_view,
  live_state.last_sell_dates)`; runner sell / STATE-EXT-SELL events
  additionally append provisional rows. This is the only phase touching the
  umbrella runner — a read-merge + an append call, consumer glue, no new
  umbrella authority (R-PIN posture). Behavior can only add blocks the
  ledger can prove (union-max); the fail direction is disclosed and
  monitored via I-W6/I-W2.
- **Phase 3 — retire.** `last_sell_dates` writes removed; the key kept only
  as a generated debug mirror (or deleted); the four mutation sites (§3.1)
  collapse into ledger appends + the pure view. Requires ≥15 clean Phase-2
  sessions and agreement that the graduated `renquant-execution`
  persistence is the landing zone for the rest of live_state (out of scope
  here).

Each phase = its own PR + approval; Phases 0-1 are riskless and can land
immediately after this design is approved.

### 3.8 Interaction with Item 1

The two designs close one causal chain at both ends: D1 prevents the
incoherent exit that manufactured the loss sale; D2 makes the wash
consequence of any exit that DOES fire durable (protection sell fill ⇒
ledger row within one session, I-W1) — so neither a stale-plane whipsaw nor
a state-churn erasure can recreate the NFLX sequence (stale exit → loss
sale → erased stamp → near wash re-entry).

---

## 4. Owners and repo boundaries (summary)

| piece | owner | why |
|---|---|---|
| `ScoringPlaneIdentity`, coherence predicate, resolution order, strike integrity | renquant-pipeline | owns task_sell / model_protection / exits kernel |
| `admitted_by` stamp at entry; Phase-2 merge + provisional-append glue | umbrella runner (minimal diff) | current writer of record; glue only, no new authority |
| `plane_coherence` flag + stage config | renquant-strategy-104 | config plane |
| wash ledger writer + nightly reconciler | renquant-execution | broker truth + order audit; graduated live_persistence converges here |
| `wash_view` pure derivation | renquant-pipeline | gate consumer stays broker-agnostic |
| invariant checker I-W1..6; coherence shadow-diff reporting; pages | renquant-orchestrator | monitor/verification role; this design doc |

No model-training internals, no signal internals, no broker adapters land
in the orchestrator; nothing lands in the umbrella beyond consumer glue.

## 5. Review asks

1. Approve D1's hybrid fail-direction (defer-then-fail-closed) and the
   "same staleness contract as buys" bar (§2.4) — or direct pure
   fail-closed (§2.2's counterfactual prices what that costs: EQIX-class
   good saves).
2. Approve identity threading via `ScoringPlaneIdentity` incl. the
   shared-sha256 requirement (§2.5).
3. Approve execution-repo ownership of the ledger + orchestrator checker
   split (§3.2) and the phase gates (§3.7).
4. Say whether §2.6 (session-grain strikes) ships with Stage 2 or as its
   own PR — it changes exit timing even on coherent planes and is fully
   separable.

## 6. Known limitations

- §2.2 outcome labels are short-horizon (+5/+10/+20d against a 60d thesis)
  and truncated at the 07-10 data edge for 5 of 9 rows — they price the
  whipsaw error, not the exit rule's alpha. The counterfactual uses
  nearest-prior-run panel mu for 6 of 9 rows (1-6d old; disclosed per row
  by the sweep).
- The 06-26 erasure's exact trigger is `[GUESS]` among three
  verified-possible mechanisms (§3.1); the design removes the whole class
  rather than adjudicating.
- Wash-sale semantics here = the system's 30d re-entry gate (§1091
  hygiene), not a tax-lot-accurate §1091 engine (substantially-identical
  securities and partial-lot matching are out of scope).
- The panel-deferral mu can be up to one session old intraday (the panel
  does not run in `SellOnlyPipeline`); accepted — it is categorically
  fresher than the failure mode it replaces, and its age is stamped.
- Vintage-at-firing in §2.2 is log-verified per session; per-ticker
  metadata files have since been overwritten by the 07-09 retrain (current
  files all show train_end 06-23), which is itself an argument for the
  ledger-grade stamping in §2.5.

## 7. References

- #484 research: `doc/research/2026-07-11-zm-nflx-buy-bias-forensics.md`
  (§2 admissions, §7.1 exit timeline, §7.2 erasure, §8 fix mapping)
- #474: silent no-buy block registry (GE/HON/EQIX stamps; degradations 0%
  flagged at decision level)
- Umbrella RenQuant #428 (MERGED 2026-07-02): STATE-EXT-SELL fill-date
  truth (`backtesting/renquant_104/adapters/runner_ext_sell.py`)
- #473: §5 per-ticker vintage collapse; §8 monitor-alert sibling
- FilterStalenessTask (the fail-closed template, Codex-reviewed):
  `renquant-pipeline src/renquant_pipeline/kernel/pipeline/job_universe.py:119-158, 220-248, 267-342`
- Protection task/config:
  `renquant-pipeline src/renquant_pipeline/kernel/pipeline/task_sell.py:157-165, 467-562`;
  `kernel/model_protection.py:36-124`; strategy-104 pin `0e5d9891`
  `risk.model_protection`, `regime_params.*.stop_loss_pct`,
  `live.broker_side_stops`, `model_staleness_days`, `wash_sale_days`
- Firing-history sweep + code-plane map: read-only, this session; DB opened
  only as a scratchpad copy; evidence quoted inline in §2.1-§2.2, §3.1-§3.2
