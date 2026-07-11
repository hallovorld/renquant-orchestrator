# Design: Gate remediation + rerun — from fail-closed-and-stop to fail-closed-remediate-and-re-verify

STATUS: design / RFC for review (docs only — no code, config, broker, risk-cap, or sizing change
in this PR). Describe → Codex + operator review → per-item implementation PRs, shadow-first.
DATE: 2026-07-11
OPERATOR DIRECTIVE (2026-07-11): the system now has many fail-closed gates; some gate failures
should TRIGGER A REMEDIATION + RERUN instead of simply stopping the pipeline ("有一些 gate 应该
trigger rerun，而不是简单地停止 pipeline"). Research the full gate inventory, classify, and produce
a professional design.

Evidence base: the silent no-buy block registry (orchestrator #474, classes C1–C8 / invariants
I1–I10 over all 56 live sessions), the META no-buy forensics (#473), the 07-08 retrain-metadata
corruption incident record (#436) + umbrella issue RenQuant#453 (atomic retrain writes), the
just-merged pipeline gate stack (`DataAvailabilityGateTask` pipeline#187, `FunnelIntegrityTask`
pipeline#186), the orchestrator session-outage monitor (#480), and the manual-remediation history
in the memory ledger (calibrator re-stamp ×3, wash-sale broker-truth correction ×2, fundamentals
feed rebuild, 07-09 recovery retrain).

**REVISION NOTE (2026-07-11, Codex review r2 — P0 fix, this round personally authored, not
delegated):** the r1 draft's execution-safety state machine (§5.3) and its flagship worked example
(§6.1) assumed a same-day chained rerun could safely re-decide AND resubmit buy orders for a
session whose sell pass had already completed. A direct trace of the live order-submission path
(`RenQuant/live/runner.py` → `RunnerAdapter.commit()`) proved this false for the majority of T2
gates: order submission is synchronous and same-run, so by the time the post-hoc controller (§5.1)
ever looks at a completed run, its sells are already at the broker. This round splits remediation
into **Class A** (gate aborts before the sell pass — a genuine same-day chained rerun is safe) and
**Class B** (gate sets a soft block and the run completes normally — remediation repairs the input
same-day, but only the NEXT regularly-scheduled session resumes trading; no rerun, no new
`run_id`, no resubmitted order). §2 (P6), §4 (every gate table row), §5.2, §5.3.4/5.3.5/5.3.7, and
§6.1 are corrected to this model; §6.2 is unchanged in substance (it was already Class A) but now
says so explicitly. Also corrected this round: D4 (pipeline emits `preflight_verdicts.v1` directly,
no new umbrella forwarding path, per the umbrella's active deprecation), the `~/renquant-data` path
(standardized under the neutral R-PIN runtime root, §5.5), and R0 vendor-refetch eligibility
restricted to versioned/as-of-queryable sources (§5.6).

**REVISION NOTE r3 (2026-07-11, Codex's third review pass on this doc — two P0s + one P1,
personally authored; the progress doc's "Correction (r4)" section covers the same round — its
numbering tracks correction commits, not Codex review passes, hence the offset):** (1) the
r2 fix's "ownership of the stamp" paragraph traced `orders_submitted` to the umbrella's
`RunnerAdapter.commit()` as ground truth, but a forensic trace of legacy code cannot define the
DURABLE owner — new §5.1bis states the target ownership (renquant-execution owns lifecycle/
broker-submit idempotency; renquant-pipeline owns `preflight_verdicts.v1`/input snapshots;
renquant-orchestrator owns the controller/neutral state) and a concrete, machine-checkable
CUTOVER PREDICATE that must hold before any Class A rerun is enabled — §5.3.1 and §7's Stage
gates are corrected to reference it. (2) §4.3's rows 20-23 said "default to Class B until traced"
but still carried a live `RERUN`/`REMEDIATE` verdict, directly contradicting Class B's own
no-rerun definition — corrected to an explicit `SHADOW-ONLY` verdict until the trace (and now
also the cutover predicate, for whichever rows resolve to Class A) holds. (3) new §7bis
"Class B estimand" paragraph: a Class B `SELF_HEALED` episode must be reported as prevention of a
REPEATED failure (next-session comparator + explicit missed-session opportunity/cost), never as
recovered trading performance for the triggering session — closing a real risk of overclaiming a
prevention-only mechanism's value in the eventual acceptance decision.

---

## 1. Problem statement — the gates work; the SYSTEM stops where a machine could heal

The #474 registry establishes, over the full 56-session live history:

- **36/56 sessions (64%)** had the scheduled buy path fully dead for a non-economic,
  engineering cause; **31 of the 33 zero-buy sessions (94%) are engineering-attributable.**
- For at least four of the eight block classes, the fix eventually applied was a **known,
  mechanical, machine-runnable procedure executed by hand, days late**:

| Episode (registry class) | Gate that (correctly) fired | The manual remediation that fixed it | Latency cost |
|---|---|---|---|
| 07-08/09 staleness outage (C1d) | per-ticker admission staleness (`stale_76-80d_limit_60:live_train_end`, 129-133/145 skipped → buy scan 0/0) | **admission retrain** (`train_104 --skip-panel`, run manually 07-09) | 2 full sessions of zero buy capability, reported as a normal `no trade (no_candidates)` |
| Fundamentals freshness era (C4) | P-FUND-FRESHNESS (45d critical) — 41 intraday aborts on 06-29 | **feed rebuild** (`python -m renquant_base_data.sec_fundamentals --mode both`, ~431 s) — after the #26 axis fix, the rebuild is the recurring remediation for a stale feed | ~40 sessions of silently stale fundamentals before the gate existed; a full blocked day after it did |
| Calibrator fingerprint mismatch (C3) | `LoadGlobalCalibrationTask` calibrator/scorer fingerprint parity — fail-closed to sell-only | **re-stamp** the calibrator's scorer-fingerprint metadata against the pinned runtime algorithm — done manually **three times** (05-27, 06-22/07-01, 07-06) | one blocked session each time; 07-06 needed a same-evening human re-stamp + re-run to place 2 buys |
| Wash-sale mis-stamp (C2) | `DROP_WashSaleFilter` on a wrong `last_sell_dates` stamp | **broker-truth reconciliation** of `last_sell_dates` from `status=filled` sell fills — done manually twice (META 07-01; GE/HON/EQIX 07-11) | GE wrongfully blocked on 07-10; META would have been wrongly blocked ~24 extra days |

The gates were RIGHT to fail closed — every one of these was a real integrity violation, and
bypassing the gate would have been the actual disaster (the WF-gate lesson, the
never-bypass-branch-protection lesson). The failure is one level up: **the response to a red gate
is hardcoded to "stop and wait for a human", even when the remediation is known, idempotent,
bounded, and evidence-preserving.** The 07-09 manual recovery retrain IS the remediation this
design automates — it was simply executed by hand, a day late.

At the same time, the history contains the opposite lesson with equal force: the 06-29
P-FUND-FRESHNESS block was **structurally unsatisfiable** (serving axis clipped to the training
label — no number of feed rebuilds would have fixed it), the C6 threshold blocks were **scale
bugs** where the only "remediation" would have been moving a bar (data snooping), and the 07-06
retrain metadata corruption shows a remediation itself can be the destructive event when its
writes are not atomic (RenQuant#453). So this design is NOT "make gates self-clearing" — it is a
narrow, classed, budgeted, evidence-stamped remediation lane with a hard line around everything
identity-shaped, and an escalation path that makes a failed remediation LOUDER than the original
gate failure, never quieter.

## 2. Design principles (the hard lines)

**P1 — A remediation reconciles a derived artifact with its authoritative upstream source. It
never adjusts the world until the gate passes.** Every action in the registry must name its
authoritative source (vendor feed, broker fill history, pinned config, pinned runtime algorithm,
upstream training data) and be expressible as "regenerate/recompute the derived thing from that
source". "Lower the threshold", "widen the staleness budget", "skip the check once"
(`live_no_wf_gate_once`) are not remediations and are permanently out of scope. Gate thresholds
and decision logic are immutable to the controller.

**P2 — Identity / tamper / paired-world / freeze violations NEVER auto-remediate.** A failed
content-hash against a manifest, a pin/lock mismatch, a run-id/session-identity violation, a
freeze-drift detection in a preregistered experiment, a paired-world divergence — these mean the
world is not what it claimed to be. "Fixing" the world and rerunning destroys the evidence and can
mask corruption or an attack. Verdict: STOP, page, preserve state. Additionally (the poisoned-
session rule): **if any identity-class gate fails, the controller refuses to execute ANY
remediation for that session**, including otherwise-enabled ones — a world of unknown provenance
must not be modified by automation.

**P3 — Behavior-changing remediations (retrain, re-stamp) may auto-TRIGGER, but their output must
be consumed through the SAME gates as any other candidate.** An auto-retrain still passes
staleness, acceptance (#445), and fingerprint checks; it NEVER auto-promotes past a quality gate
(WF gate, tournament acceptance). If the remediation's product fails its gate, the rerun does not
happen and the escalation carries both failures. The remediation lane must never become a
promotion bypass.

**P4 — Bounded, idempotent, evidence-preserving, or not at all.** Every action declares: max
attempts per session (default 1), cooldown across sessions, wall-clock timeout, and a
prerequisite idempotency argument (re-running the action converges to the same state; the action
archives what it overwrites). Every execution stamps a remediation record into the run bundle and
decision ledger with evidence BEFORE and AFTER.

**P5 — Escalation is the success path for the residual.** A remediation that runs and the gate is
STILL red is the single most informative signal this design produces: it machine-distinguishes
"transient/stale-derivable" from "structural" (the 06-29 axis-clip bug would have been isolated on
day one: "feed rebuilt, max date still 2026-03-31 → the builder is broken, not the data"). That
escalation pages at OUTAGE priority with both evidence blocks attached and disables the action
until a human clears it.

**P6 — Sell/exit protection is senior to everything, and the controller never re-enters a session
that has already reached the broker.** Corrected 2026-07-11 (Codex review r2, P0 — the prior text
below described a same-day chained rerun that a real-architecture trace proved unsafe; see §5.3.4
for the full ground-truth citation and the two-class split it introduces). The remediation lane
exists on the buy side and must never delay, suppress, double-execute, or attempt to "reconcile
against" an exit: `TickerSellJob` and its downstream exit-refinement tasks (`DrawdownFlattenTask`,
`MetaLabelVetoTask`, `LimitSellsPerBarTask`, `ShortCoverStopLossTask`) always run, and the live
runner's `RunnerAdapter.commit()` submits BOTH the sell and buy legs of a completed run to the
broker SYNCHRONOUSLY, in the same process, seconds after `InferencePipeline.run()` returns
(`RenQuant/live/runner.py:531-535` → `.../adapters/runner.py` `commit()`, sells at line ~1177,
buys at line ~1509 — verified 2026-07-11, no file/DB queue or deferred-submission step exists
anywhere in this path). There is therefore NO code-level window, for any gate that fires after
`TickerSellJob` (which includes every soft-block T2 axis in §4 — `enforce_buy_block` is wired
strictly after the sell pass per §5.3.4), during which a post-hoc controller could still find the
session in phase (a). For that entire class, "remediation" fixes the INPUT only (retrain, refetch,
re-stamp) and never re-enters this session's decision or order flow — see §5.3.4's Class B. A
same-day chained rerun (Class A) is reserved for the rare gate that aborts the run BEFORE
`TickerSellJob` ever executes, where phase (a) is genuinely still open.

**P7 — Frozen experiment worlds are out of scope by construction.** The two-arm shadow A/B and
any preregistered replay run under freeze contracts; a red gate inside a frozen world is
freeze-drift (identity class, P2) and voids the arm — it is never remediated. The controller
binds to the production daily path only.

## 3. Taxonomy

Three classification dimensions, then the verdict-action mapping.

### 3.1 Transience (what kind of wrongness is this?)

| Code | Class | Definition | Registry classes |
|---|---|---|---|
| T1 | transient-data | The world is fine; an input has not arrived / a fetch failed / a process died. Time + retry fixes it. | C8 (run crash), OHLCV/vendor arrival lag |
| T2 | stale-derivable | A DERIVED artifact (feed, per-ticker model, calibrator stamp, state stamp, corpus) has drifted from its authoritative upstream, and a deterministic, machine-runnable procedure regenerates it. | C1 (admission staleness), C2 (wash stamps), C3 (calibrator binding), C4 (feed staleness) |
| T3 | identity-violation | A content/identity/freeze claim failed: artifact hash ≠ manifest, pin ≠ lock, paired-world divergence, freeze drift, run-id/session tamper. The world is not what it claimed. | P-RUN-ID, artifact sha mismatches, freeze-drift voids |
| T4 | structural | The gate is red because code/config/scale is wrong (unsatisfiable bar, config tangle, triple-implementation bug). No authoritative source exists to reconcile against; the fix is a design/code change via PR. | C5 (promote/WF tangle), C6 (threshold-scale), C7 (single-gate funnel kills), the 06-29 axis-clip root cause |

T2 is the only class where REMEDIATE+RERUN is ever on the table. T1 gets bounded RERUN (retry)
semantics without a remediation body. T3 is STOP, always. T4 is ALARM_ONLY/STOP — automation may
PREPARE evidence (and, in the existing roadmap/agent lane, draft a PR), never self-apply.

### 3.2 Remediation existence

For each gate: does a known, idempotent, machine-runnable fix exist TODAY? Values:
**yes** (a script/command exists and has been executed successfully, manually, at least once),
**partial** (procedure known but not encapsulated / has unmet safety prerequisites),
**no** (fix requires diagnosis or design). Only **yes** actions are automatable; **partial**
actions enter the registry dark, with their prerequisite named.

### 3.3 Remediation risk class (what does running the fix touch?)

| Class | Touches | Examples | Auto-execution bar |
|---|---|---|---|
| R0 read-only refetch | nothing durable; re-pull inputs from vendor/broker | OHLCV refetch, broker order-history re-read | lowest — first to enable |
| R1 artifact regeneration | derived data artifacts, non-production-state | fundamentals feed rebuild, corpus refresh, WF manifest rebuild | shadow-proven, then enable |
| R2 state mutation | production live state (with backup + bounded diff) | `last_sell_dates` broker-truth reconciliation | operator sign-off per action; backup + surgical-diff assertion mandatory |
| R3 behavior-changing | what the system will decide (models, calibrator stamps) | admission retrain, calibrator/panel fingerprint re-stamp | auto-TRIGGER only; product re-enters through the same gates (P3); per-action operator sign-off to enable |

### 3.4 Verdict actions

Every gate maps to exactly one of:

- **STOP** — fail closed, page, human required. T3 always; T4 where continuing is unsafe.
- **REMEDIATE** — execute the registered action under budget, then verify it out-of-pipeline. T2
  with remediation=yes only. Splits into two shapes per §5.3.4's ground truth (most gates are
  Class B; a same-day chained rerun is the exception, not the default — see §4's per-row tags):
  - **Class A (REMEDIATE+RERUN)** — for the rare gate that aborts the run before the sell pass
    executes: also chain a fresh same-day rerun through the SAME gates, new `run_id`.
  - **Class B (REMEDIATE, no rerun)** — for the common soft-block gate, where the run already
    reached `commit()` and submitted its sells: the action repairs the input; the NEXT
    regularly-scheduled session (not a special rerun) is what actually resumes trading on it.
- **RERUN** — no remediation body; bounded re-execution (crash/transient). T1.
- **DEGRADE+ALARM** — continue with reduced capability, loud. (Already a per-axis policy in
  data_availability.v1 — `degrade_with_alarm`.)
- **ALARM_ONLY** — nothing automatic is safe; make it loud and machine-attributed. T4 default.

## 4. Master gate inventory → verdict table

Inventory grounded by a read-only sweep of all three planes (renquant-pipeline `kernel/`,
umbrella `scripts/` + `backtesting/renquant_104/`, orchestrator `src/renquant_orchestrator/`),
2026-07-11. Notation: T = transience (§3.1), R = remediation risk class (§3.3). "Today" is the
current failure behavior. Verdicts are the PROPOSED policy.

### 4.1 Data-plane gates (renquant-pipeline)

| # | Gate | Detects | Today | T | Remediation (exists?) | R | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | `DataFreshnessGateTask` (`task_data_freshness.py:36`) | stale/missing OHLCV bars vs last NYSE session | **raises RuntimeError**, aborts run before `RegimeJob`/the sell pass ever start (OHLCV is their hard prerequisite); error text already says "run `scripts/refresh_panel_ohlcv.py` and retry" | T1 | OHLCV refetch (**yes** — the named script) | R0 | **Class A — REMEDIATE+RERUN** (flagship pre-abort case; the gate literally prescribes it today, to a human; `commit()` is never reached by the aborted run) |
| 2 | `DataVerificationTask` (aux feeds advancing) | frozen fundamentals/earnings/sentiment feeds (caught the 06-11 freeze) | warns; blocks only if `data_verification.hard_fail` | T2 | serving-feed rebuild (**yes** — `renquant_base_data.sec_fundamentals --mode both`, ~431 s) | R1 | **Class B (unconfirmed — "blocks" here reads as a soft flag, not a raise; needs the same abort-point trace §5.3.4 ran for row 5 before shipping) — REMEDIATE** when hard; DEGRADE+ALARM otherwise; no same-day rerun unless re-traced into Class A |
| 3 | `data_availability.v1` axis `ohlcv_bars`, `regime_inputs` | presence/vintage/coverage of price inputs | per-axis `fail_closed` → buy-block via `enforce_buy_block`; `degrade_with_alarm` → alarm | T1 | refetch (**yes**) | R0 | **Class B — REMEDIATE** (this axis fires via the SAME `enforce_buy_block` soft-block path as row 5, post-sell-pass — R0's LOW risk-class does not imply Class A; risk-class and phase-class are orthogonal, §5.3.4) |
| 4 | axis `fundamentals_serving_axis` | serving-feed staleness | same | T2 | feed rebuild (**yes**) | R1 | **Class B — REMEDIATE**, max 1 attempt — a second red is the 06-29 signature (structural axis bug) → escalate |
| 5 | axis `admission_model_metadata` | per-ticker admission cutoff collapse (the 07-08/09 signature; reuses `job_universe._classify_cutoffs`) | fail_closed buy-block; sells unaffected | T2 | admission tournament retrain (**yes** — `weekly_tournament_retrain.sh`, idempotent via #445 acceptance staging + marker) | R3 | **Class B — REMEDIATE** with the §6.1 consistency precondition, rewritten to the no-same-day-rerun shape; product re-enters through the same staleness+acceptance gates (P3) via the NEXT regular session |
| 6 | axis `panel_model_artifact` | production panel scorer staleness | policy-keyed | T2 | panel retrain exists but promotion is WF-gated and ~90 min weekly | R3 | **Class B — ALARM + async TRIGGER** (`anomaly_triggers` precedent); NO same-session rerun (already the case pre-r2, unchanged); promotion stays behind the WF gate — freshness governance (#210) owns the policy |
| 7 | axis `calibrator` | calibrator presence/vintage | policy-keyed | T2 | staged refit (**yes** — `monthly_calibrator_refresh.sh`: stage → quality gate → #425 binding check → atomic swap) | R3 | **Class B — REMEDIATE** (trigger the staged path; benefits the next regular session once its own acceptance passes) |
| 8 | axis `account_snapshot` | broker snapshot presence/vintage | policy-keyed | T1 | re-poll broker, read-only (**yes**) | R0 | **Class B — REMEDIATE** (same axis mechanism as rows 3/4/5/6/7; R0's low risk-class does not make this Class A) |
| 9 | `AXIS_UNVERIFIED` / `missing_contracts[]` | axis consumed with no reviewed contract | recorded; can never alarm or block | T4 | write the contract (PR) | — | **ALARM_ONLY** (weekly digest; contract authoring is human review by design — no phase-class applicable, no action fires) |

### 4.2 Runtime fail-closes and funnel diagnosers (renquant-pipeline)

| # | Gate | Detects | Today | T | Remediation (exists?) | R | Verdict |
|---|---|---|---|---|---|---|---|
| 10 | `LoadGlobalCalibrationTask` → `_assert_calibrator_matches_scorer` (`job_panel_scoring.py:2217`) | calibrator↔scorer fingerprint parity | **raises ValueError mid-pipeline** → run crash → sell-only fallback (07-06); error text prescribes "refit … re-stamp" | T2 | binding re-stamp (**yes** — manual ×3; §6.2 wraps it) | R3 | **Class A — REMEDIATE+RERUN** under the §6.2 preconditions; the crash propagates out of `run()` before `commit()` is ever called (that's WHY `daily_104.sh`'s sell-only fallback exists as a SEPARATE subsequent invocation, §4.5) — recurrence cooldown escalates to "fix the producer" |
| 11 | `panel_scorer_config_mismatch` (`_fail_closed_panel_scoring`, `job_panel_scoring.py:798`) | config↔artifact fingerprint drift | clears candidates, `skip_buys=True`, no raise | T2/T3 | re-stamp for the KNOWN benign signatures only (**yes** — `stamp_patchtst_fingerprint.py`, `restamp_prod_fingerprint.py`; both refuse on real drift, atomic, idempotent) | R3 | **Class B — REMEDIATE** only when the script's own fail-closed compatibility check passes (additive drift; explicit "no raise" ⇒ run reaches `commit()` normally); any real drift → **STOP** (identity) |
| 12 | `missing_global_calibration` / `_fail_closed_missing_calibrator` | calibrator absent | blocks all, no raise | T2 | staged refit (#7) | R3 | **Class B** — ALARM + TRIGGER; no same-day rerun, benefits next session behind the staged path's own gates |
| 13 | `RegimeModelAdmissionTask` (`panel_scoring.py:238`) | model lacks regime-conditional OOS evidence | `_block_all`, whole-funnel kill (the 06-01→04 era) | T4 | none (needs new evidence — retrain + WF eval) | — | **ALARM_ONLY** + async retrain trigger; never auto-clear an evidence floor (no phase-class applicable, no action fires) |
| 14 | `FilterStalenessTask` (`job_universe.py:267`) + `LoadArtifactsTask` `no_artifact` | per-ticker `stale_Nd_limit_60:<field>` / missing artifacts | **silent per-ticker skips** (the collapse that read as a normal no-trade) | T2 | aggregated by #5/#15; same retrain action | R3 | **Class B** — inherits #5 (same mechanism, same class); the per-ticker gate itself stays as-is (it is the detector, not the problem) |
| 15 | `FunnelIntegrityTask.universe_admission_collapse` | admitted/universe < floor, staleness-dominated | observe-only verdict `STRUCTURAL_BLOCK` in `funnel_integrity.v1` | T2 | carries the hint for #5's action | R3 | **Class B — REMEDIATE** (same action and class as #5); if `top_rejection_reasons` is `no_artifact`-dominated → **STOP** (possible artifact corruption/loss, the 07-06 class — never retrain over a corruption signature) |
| 16 | `.single_gate_funnel_kill`, `.threshold_scale_mismatch` | one gate kills 100%; bar > max achievable μ/ER (C6/C7) | observe-only | T4 | none — "moving the bar" is data snooping, permanently out of scope (P1) | — | **ALARM_ONLY** (STRUCTURAL page; fix = design PR) |
| 17 | `.fail_close_event` | any Phase-3 fail-close fired | observe-only | — | routes to the underlying action (#10/#11/#12) | — | delegate to the specific gate's verdict AND its phase-class |
| 18 | `.wash_sale_mass_block` | wash-sale drops above historical p99 (C2 signature) | observe-only | T2 | broker-truth `last_sell_dates` reconciliation (**partial** — pure functions extracted in `runner_ext_sell.py` (`lookup_ext_sell_fills`/`ext_sell_fill_date`/`ext_sell_stamp_decision`, fail-closed on direction, `unresolved_preserve` never clobbers); no standalone script yet) | R2 | **Class B (moot pre-Stage-4 — no action fires yet)** — **DEGRADE+ALARM** now; REMEDIATE (nightly reconcile job, inherently next-session/async by nature) only at Stage 4, operator-gated (§7); `status=filled`+`filled_at` only — the GE canceled-order lesson |
| 19 | `.zero_priced_candidates` | candidates carry no price | observe-only | T1 | refetch prices (**yes**) | R0 | **Class B — REMEDIATE** ("observe-only" ⇒ run reaches `commit()` normally with the affected candidates excluded, not an abort; R0's low risk-class does not make this Class A) |

### 4.3 Preflight P-* gates (renquant-pipeline `preflight_pipeline/`, consumed by umbrella `daily_104.sh` → sell-only fallback)

**Phase-class caveat (Codex review r2, corrected r3 — P0 internal contradiction).** This section's
header names the SAME sell-only fallback mechanism as row 10 (§4.2) — a preflight failure keeps
`daily_104.sh` from running the full `InferencePipeline`+`commit()` at all, and a SEPARATE,
subsequent sell-only pass covers exits instead. Whether that fallback pass itself already submits
sell orders BEFORE a remediation decision is made — which would foreclose a same-day full rerun
exactly like a Class B soft-block, since the rerun's own sell pass would then double-evaluate an
already-changed book (5.3.6) — has NOT been traced with the same rigor §5.3.4 applied to row 5. The
r2 draft correctly said "default to Class B until traced" but then left each row's VERDICT reading
`RERUN`/`REMEDIATE` — an enableable, rerun-capable action — which directly contradicts Class B's
own definition (no same-day rerun, §5.3.4/§3.4). Corrected: until the trace is done, rows 20-28 are
**SHADOW-ONLY** — no action is enabled at any stage; the controller may only log what it WOULD have
done (`SHADOW_WOULD_RUN`, §5.5), exactly like Stage 0 for every other row. This is in addition to,
not instead of, §5.1bis's cutover predicate — even a row that traces cleanly to Class A still
cannot enable a rerun until BOTH the trace AND the cutover predicate hold (§7's Stage 1 gate).

| # | Check | T | Remediation (exists?) | R | Verdict |
|---|---|---|---|---|---|
| 20 | P-BROKER-CONNECT | T1 | reconnect/backoff (**yes**, trivial) | R0 | **SHADOW-ONLY** (bounded retry, no remediation body; likely Class A since this almost certainly gates before the sell-only fallback can run either — but not enableable until BOTH that trace and §5.1bis's cutover predicate hold) |
| 21 | P-FUND-FRESHNESS | T2 | feed rebuild (**yes**) | R1 | **SHADOW-ONLY** pending the sell-only-fallback trace (default Class B) — the 06-29 axis-clip lesson (the rebuild would have proven the builder broken on day one instead of week five) motivates building this action, not enabling it early |
| 22 | P-SECTOR-MAP, P-WATCHLIST, P-CORR-METADATA | T2 | regenerate derived artifacts (**yes/partial**) | R1 | **SHADOW-ONLY** pending the sell-only-fallback trace (default Class B) |
| 23 | P-CONFIG-FP, P-PANEL-CONTRACT | T2/T3 | known-benign re-stamp only (#11) | R3 | **SHADOW-ONLY** pending the sell-only-fallback trace (default Class B, matches #11); a real (non-benign) drift signature is always **STOP**, unconditionally, regardless of shadow/enabled status |
| 24 | P-CALIBRATOR-HEALTH, P-CALIBRATOR-FLAT-REGION | T2 | staged refit (#7) | R3 | **Class B** (matches #7/#12) — ALARM + TRIGGER |
| 25 | P-MODEL-STALENESS (soft), P-META-LABEL | T2 | retrain, promotion-gated | R3 | **Class B** — ALARM + async TRIGGER (#210 policy); already no-same-session-rerun by design, unaffected by this section's caveat |
| 26 | P-WF-GATE, P-REGIME-IC | T4 (historically C5: config tangle) | none safe — the gate IS the protection | — | **STOP**; never auto-bypass, never auto-re-stamp WF metadata (`live_no_wf_gate_once` is a documented anti-pattern, not an action) |
| 27 | P-RUN-ID, P-STATE-FILE, P-MODEL-ARTIFACT, P-BEST-ITER | T3 | — | — | **STOP** (identity/state; poisoned-session rule applies) |
| 28 | P-KELLY-SIGMA-HORIZON, P-SIZING-GATE-KEYS, P-CONFIG-SCHEMA | T4 | config fix via PR | — | **STOP** |

### 4.4 Umbrella + orchestrator control-plane gates

| # | Gate | T | Verdict |
|---|---|---|---|
| 29 | Live-checkout guard #412; `preflight_pin_align.sh`; pin/lock drift; `check_model_bundle_consistency` (pre-deploy); `native_persistence_guard` (R5); `scorer_identity_monitor` boundary | T3 | **STOP** — identity plane, no exceptions (P2) |
| 30 | Drawdown circuit breaker / HARD-FLATTEN / `TRADING_OFF` / `agent_breaker` caps | — (economic risk controls, not faults) | **NEVER touched** — outside the controller's vocabulary entirely; a tripped breaker additionally makes the controller inert ("a tripped breaker is a stop, not a transient error" — `agent_breaker.py` contract) |
| 31 | `daily_104.sh` smoke test / LEAN export failures | T4/T1 | **STOP** (one external heartbeat-driven rerun allowed for a mid-run crash, #32) |
| 32 | Session heartbeat (registry I9: exactly one completed daily-full decision per NYSE session; the 06-05 SIGTERM class) | T1 | **RERUN** — external watchdog (cannot live inside the run it polices), single bounded re-invocation, then page |
| 33 | Wash-sale stamp integrity (registry I2, nightly: `last_sell_dates[t]` = a broker fill date ±1td) | T2 | detector: ALARM; repair: Stage-4 R2 (see #18) |

### 4.5 Structural notes

- **Nothing reruns today.** The pipeline has no rerun hook (`InferencePipeline.run` ends on
  abort; "rerun" = fresh cron invocation); the umbrella's only automatic re-invocation is the
  sell-only fallback (`daily_104.sh:393-426`); the orchestrator's sanctioned posture
  (`doc/design/2026-06-27-autonomous-ops-loops.md` §4.2) is diagnose-and-notify, never
  auto-change. This design explicitly supersedes that default for the classed lane, under the
  2026-07-11 operator directive (§8, open decision D7 records the required LONG-ledger update).
- **The house already owns one closed-loop precedent**: `scripts/promote_pin.py`
  (bump → `check_conviction_admits` verify → auto-`rollback` + re-sync). The controller
  generalizes exactly that shape — act → re-verify through the real gate → revert/escalate —
  plus the event-trigger precedent `conditional_retrain_104.sh`/`check_retrain_triggers.py`
  (SPY/VIX anomaly → WF retrain chain).
- **Economic gates are deliberately not in the table** (BuyGatesJob chain, conviction, tier,
  top_n, QP min_dw, rank-floor, vol/concentration gates): they fail by dropping names, and any
  "remediation" would be an outcome-directed knob change (P1 violation). Their pathological
  collective behavior is covered by #16 as ALARM_ONLY.

## 5. Mechanics

### 5.1 Ownership split (respects existing repo boundaries)

- **renquant-pipeline — gates EMIT structured remediation hints; they never act.** Publish a
  **new, separately-versioned** `remediation_hints.v1` block alongside (never inside) the
  existing v1 blocks — see the contract-compatibility note below for why this is a separate
  block rather than an additive field in `data_availability.v1`/`funnel_integrity.v1`:
  - Keyed by `(source_block, axis_or_invariant_name)` so a hint unambiguously maps back to the
    `data_availability.v1` axis or `funnel_integrity.v1` finding that triggered it, without
    touching either schema.
  - Preflight: `PreflightCheck.details` stays untouched; preflight verdicts get stamped into a
    THIRD new block, `preflight_verdicts.v1` (today they are only greppable from logs —
    `daily_104.sh` pattern-matching on log text is the current "API"). **Corrected 2026-07-11
    (Codex review r2, D4):** renquant-pipeline emits `preflight_verdicts.v1` directly into the
    shared run bundle the orchestrator already reads (the same artifact `data_availability.v1`/
    `funnel_integrity.v1` already ride); the orchestrator consumes it directly. No new umbrella
    forwarding code is added — the umbrella is being actively deprecated, and a new piece of
    forwarding logic there works against that trajectory, not with it. `daily_104.sh`'s log-grep
    stays as-is until it is retired outright; it is not upgraded into a forwarder.
    Preflight hints key off `preflight_verdicts.v1` the same way.

  Hint shape (declarative — the pipeline names an action, it never carries a command):

  ```json
  {
    "schema": "remediation_hints.v1",
    "as_of": "2026-07-08",
    "hints": [
      {
        "source_block": "data_availability.v1",
        "axis_or_invariant": "admission_model_metadata",
        "action_id": "admission_tournament_retrain",
        "risk_class": "R3",
        "transience": "T2",
        "hint_evidence": {"top_rejection_reasons": {"stale_76d_limit_60:live_train_end": 133}}
      }
    ]
  }
  ```

  **Contract compatibility (Codex review, r1 — reversed from an earlier additive-inside-v1
  draft):** an optional field added inside the EXISTING `data_availability.v1`/
  `funnel_integrity.v1` blocks is only safe if every current producer, consumer, and validator
  of those exact schemas is proven forward-compatible — this RFC has not audited every consumer
  across three repos, and asserting tolerance from one reader (`outage_monitor`) is not proof for
  the others (decision-ledger writers, run-bundle persistence, any future consumer). Rather than
  claim an unaudited compatibility property, the hint publishes as a **separate, additively
  versioned block**, `remediation_hints.v1`, keyed by the same `(axis_or_invariant_name)` the
  parent block already uses — never mutating `data_availability.v1`/`funnel_integrity.v1`
  themselves. A cross-repo compatibility test (renquant-pipeline emits both blocks against a
  fixture; renquant-orchestrator's existing `data_availability.v1`/`funnel_integrity.v1`
  consumers are re-run unmodified against that fixture and asserted byte-identical in their
  existing fields) is a **precondition for Stage 0**, not a nice-to-have — see §7bis. An
  axis/invariant with no corresponding `remediation_hints.v1` entry is implicitly STOP/ALARM;
  absence of a hint can never be less safe.

- **renquant-orchestrator — the remediation controller (net-new `remediation_controller.py`).**
  Consumes the failed run's bundle from the same source `outage_monitor` (#480) already reads
  (`run_bundle*.json` / `pipeline_runs.run_bundle_json`), resolves `action_id` against a static,
  reviewed **action registry**, enforces policy/budget, executes, re-verifies, requests the
  rerun, stamps the audit record. The controller is scheduled AFTER the daily run (same slot
  shape as the other monitors in `scheduled_jobs.py`), so it never sits inside the pipeline's
  fail-isolation domain.

- **umbrella / owning repos — the action BODIES.** Every action is an existing (or thinly
  wrapped) script in the repo that owns the subject: `weekly_tournament_retrain.sh`,
  `refresh_panel_ohlcv.py`, `sec_fundamentals --mode both`, `monthly_calibrator_refresh.sh`,
  the re-stamp scripts. The orchestrator invokes commands; it implements no training/broker
  internals (CLAUDE.md hard boundary; the 07-03 repo-boundary lesson).

### 5.1bis Execution/lifecycle ownership — target-state migration contract (Codex review r3, P0)

The phase-(a)/(b) safety machine's ENTIRE authority (§5.3) rests on the `orders_submitted`
lifecycle stamp, and the r2 fix (correctly) traced WHO stamps it TODAY —
`RenQuant/backtesting/renquant_104/adapters/runner.py`'s `RunnerAdapter.commit()`, in the
deprecated umbrella. That trace is accurate ground truth, but Codex correctly held that a
forensic trace of legacy code cannot define the DURABLE owner: per the adopted multi-repo model
(the same principle behind D4's `preflight_verdicts.v1` routing above, and independently
reaffirmed by Codex's review of the R-PIN evidence bundle, `artifacts#22`), the umbrella
(RenQuant) remains preserved as historical/rollback evidence but is never a runtime, deployment,
schedule, artifact, or orchestration authority. This design states the TARGET ownership and a
CUTOVER PREDICATE now, as a precondition this RFC records rather than assumes.

**Target-state ownership (durable, post-cutover):**
- **renquant-execution** owns lifecycle events and broker-submit idempotency: the
  `orders_submitted` stamp (5.3.1), the order-level dedup key (5.3.4), and the actual
  broker-submit call. This is the natural home — renquant-execution already owns "broker
  execution and order-audit," and `orchestrator#481`'s stops-liveness checker
  (`software_stops_liveness.py`) already lives there as a precedent for execution-owned runtime
  monitoring reached from this same orchestrator repo.
- **renquant-pipeline** owns `preflight_verdicts.v1` (D4, above) and the immutable input
  snapshot the fidelity contract requires (§5.6) — both are decision-plane artifacts, not
  execution-plane.
- **renquant-orchestrator** owns the remediation controller and its neutral state
  (`~/.renquant/remediation/`, §5.5) — unchanged from this section's existing split.
- **The schedule** invokes a multi-repo entrypoint composed from first-party imports across
  these three repos — never `daily_104.sh` or any other umbrella script directly.

**Cutover predicate** (the condition that must hold before this design's rerun-capable Class A
actions may be enabled past Stage 0 shadow, §7): a machine-checkable census — analogous to the
existing `renquant_orchestrator.engineering_census` AST-scan pattern already used for the
GateRegistry single-choke-point invariant — confirming (i) the ACTIVE production schedule
resolves to zero references to any umbrella (`RenQuant/...`) path, and (ii) `orders_submitted`
is stamped exclusively from within renquant-execution's own commit path. Until that census
passes, §5.3's state machine is DEFINED against today's actual umbrella-anchored runtime as the
necessary interim ground truth (§5.3.1 says so explicitly) — but no Class A rerun may be
ENABLED past Stage 0 shadow logging until the census passes (§7's Stage 1 gate is corrected to
require it explicitly). Building the census script and the execution-side stamping change are
their own future PRs — out of scope for this docs-only RFC, but named here as a concrete,
tracked precondition, not an aspiration.

### 5.2 Action registry (orchestrator, reviewed config — the only place commands live)

```
action_id -> {
  command, owner_repo, risk_class (R0-R3), timeout_s, cooldown_sessions,
  max_attempts_per_session (default 1),
  phase_class: "A" | "B",   # §5.3.4 — MANDATORY; A = pre-side-effect abort, genuine same-day
                            # chained rerun eligible; B = post-sell-pass soft block, input-fixing
                            # only, no rerun, no new run_id. An action with no phase_class is not
                            # eligible for any stage beyond Stage 0 shadow. Misdeclaring a Class B
                            # action as Class A is a P0-class bug (violates 5.3.4's ground truth).
  preconditions[],          # machine checks; ANY failure => SKIP + escalate
  evidence_before[],        # collectors run pre-action (gate evidence, counts, shas)
  verify[],                 # post-action checks — MUST include re-running the very
                            # check that fired, via its authoritative implementation
  archives[],               # what the action must back up before overwriting
  fidelity_contract: {...}, # §5.6 — MANDATORY; an action with no fidelity_contract is not
                            # eligible for any stage beyond Stage 0 shadow
  eval_protocol: {...},     # §7bis — MANDATORY; the falsifiable pre-registration this action's
                            # enablement decision is judged against
  enabled: false            # per-action kill switch; global remediation.enabled too
}
```

Seed registry (maps §4 verdicts): `ohlcv_refetch` (R0, Class A — `DataFreshnessGateTask` aborts
pre-Phase-2a), `broker_snapshot_repoll` (R0, Class A), `fundamentals_feed_rebuild` (R1, Class B —
soft `degrade_with_alarm`/`fail_closed` axis, run completes normally), `corr_metadata_rebuild` (R1,
Class B), `sector_map_regen` (R1, Class B), `admission_tournament_retrain` (R3, Class B, §6.1 —
the flagship example; `enforce_buy_block` fires after the sell pass, per 5.3.4's ground truth),
`calibrator_binding_restamp` (R3, Class B, §6.2), `calibrator_staged_refit_trigger` (R3, async,
Class B, no rerun by design regardless), `panel_retrain_trigger` (R3, async, Class B, no rerun),
`washsale_broker_truth_reconcile` (R2, Stage 4, default disabled, Class B), `session_rerun` (crash
retry, no body, Class A — a mid-run crash is by definition pre-completion; §4 row 31/32).

Every OTHER §4 row whose "Today" column reads "fail_closed buy-block", "policy-keyed", "clears
candidates, `skip_buys=True`, no raise", or similar (i.e. the run continues to `commit()`) is
Class B by the same reasoning as row 5 — the gate fires at or after `enforce_buy_block`'s position,
so the sell pass (if it had anything to sell) has already reached the broker by the time the
controller could act. Only rows whose "Today" column reads "raises ... aborts run" and whose abort
point is verifiably before Phase 2a are eligible for Class A; §4's verdict column is corrected
below to name the class per row.

### 5.3 Run lifecycle, idempotency, and the execution-safety state machine

Codex review (r1), P0: decision-ledger supersession (below) closes an ANALYTICAL duplicate-row
problem only. It does not, by itself, prevent duplicate broker orders, duplicate notifications,
duplicate artifact publication, or a rerun that observes a later external state than the
decision it is meant to re-derive. This subsection replaces the prior narrative treatment with a
mechanical state machine that is first-class and independently checkable.

**5.3.1 Run phases and the pre-side-effect cutoff.**

Every run (parent or child) passes through exactly these phases, in order, and the controller's
entire authority to act is scoped to phase (a):

| Phase | Definition | Controller may |
|---|---|---|
| (a) PRE_SIDE_EFFECT | No order intent has been formed, no broker submission has occurred, no operator-facing notification has been sent, and no shared artifact (run bundle, decision ledger row, remediation-hints/preflight-verdicts blocks) has been PUBLISHED (a partial in-memory or scratch-local write that never reached the shared store/ledger/ntfy is not a publish). | Execute a remediation action and/or request a rerun. |
| (b) SIDE_EFFECT_BEGUN | ANY of: an order was submitted to the broker (buy OR sell/exit — see 5.3.4), a notification was sent, or a shared artifact was published. | **Nothing.** The controller MUST NOT execute an action or request a rerun for a run once it has left phase (a), regardless of which gate is currently red. |
| (c) TERMINAL | The run has exited (success, crash, or STOP). | n/a — post-mortem only. |

**The pre-side-effect cutoff is the boundary between (a) and (b).** A run's own bundle carries a
monotonically-appended `lifecycle_events` list (`{event, at}` — e.g. `orders_submitted`,
`notification_sent`, `artifact_published`) stamped at the FIRST occurrence of each; the
controller's phase check is `bundle.lifecycle_events == []` ⇒ (a), else ⇒ (b). This is a stronger
predicate than the existing `funnel_integrity.funnel.n_buy_orders == 0` check (which only covers
buy orders) — see 5.3.4. **Ownership of the stamp — durable target vs. today's interim ground
truth (Codex review r2, corrected r3 — see §5.1bis for the full migration contract):**
`orders_submitted` MUST be stamped by the EXECUTION owner itself, synchronously, before or
atomically with the actual broker call, never inferred after the fact by the controller from a
separate log, an order count, or any controller-local bookkeeping. The DURABLE owner of this
stamp is renquant-execution (§5.1bis) — TODAY, before that migration lands, the only actual
broker-submit call site is `RunnerAdapter.commit()` in the deprecated umbrella
(`RenQuant/backtesting/renquant_104/adapters/runner.py`, sells ~line 1177, buys ~line 1509), which
this design cites as the necessary INTERIM ground truth for tracing the safety property, never as
the intended permanent home for the stamp. The controller's ENTIRE authority rests on reading this
one execution-owned stamp; if the stamp is unavailable (bundle missing, write failed,
execution-state reconciliation cannot be confirmed), the controller MUST refuse to act — a missing
stamp is treated as phase (b) (fail-closed), never defaulted to phase (a). Stamping the actual
commit-path call sites (wherever they durably live, post-migration) is a small execution-side PR
precondition, not assumed here; §5.1bis's cutover predicate gates when a Class A rerun may be
enabled on top of this stamp, separately from whether the stamp itself exists.

**Once a run is in phase (b), remediation is not offered.** A gate that turns red after the run
has already produced a durable external effect requires the operator's normal STOP+page path and
a manually reconciled execution-state review — never a generic "just rerun it" — because the
system can no longer prove what the world already contains as a result of the failed run. This is
the mechanical form of Codex's ask: "post-cutoff failures must STOP and require a reconciled
execution-state path, never a generic rerun."

**5.3.2 Idempotency key and single-writer lease (pre-cutoff retries only).**

Every remediation episode is keyed by `episode_key = sha256(as_of, parent_run_id, action_id)`.
Before executing an action, the controller must acquire an **exclusive, expiring lease** on
`episode_key` (a row in a new orchestrator-owned `remediation_leases` table/file, `INSERT ...
WHERE NOT EXISTS`-style compare-and-set, TTL = the action's `timeout_s` + a grace margin) —
this is the mechanism that makes "one remediation episode, chain depth 1" (§5.4) enforceable
against concurrent controller invocations (a second scheduled tick, a manual re-trigger, a
retried cron), not just a documented convention. A lease acquisition failure is a SKIP, not a
retry-with-backoff: at most one execution of `episode_key` is ever attempted. The lease is
released (or left to expire) only after the episode's `remediation.v1` record reaches a terminal
`outcome`; while held, a duplicate trigger for the same `episode_key` observes the lease and
no-ops.

**5.3.3 Decision-ledger supersession (prerequisite, not optional — unchanged from the prior
draft, restated here as one input to phase tracking, not the whole safety story).** Ledger PK is
`(run_id, scope, gate)` (`decision_ledger.py:28`) and the autopsy query `verdicts_for()` filters
by `as_of`+`scope` ONLY — after a rerun it would return both runs' verdicts interleaved with
nothing marking the loser. Before any rerun is enabled, the ledger needs explicit supersession (a
`superseded_by` stamp written by the controller when the chained rerun completes, or a
canonical-run view mirroring `tc_measurement._canonical_daily_runs`'s latest-per-day rule — which
is already the de-facto consumer behavior for the manual reruns of 06-09/06-10/07-06). Same for
the run-scoped-verdicts vs day-scoped-`decision_outcomes` asymmetry: outcomes must join the
CANONICAL run's verdicts. Coordinate with the S5 wiring PR (ledger is not live-wired yet —
cheapest moment to land this).

**5.3.4 Broker safety / book idempotency — buys AND exits, and the two-class split this forces.**

**Ground truth (Codex review r2, P0 — this replaces a prior claim that was checked against the
real architecture and found backwards).** The prior draft asserted T2/REMEDIATE+RERUN gates "fire
before/instead of the sell pass." A direct trace of the actual code proves the opposite for every
gate that sets `ctx.buy_blocked` via `enforce_buy_block` (the T2 admission/staleness axes that are
this design's flagship motivation, §6.1): `enforce_buy_block` is wired strictly AFTER
`TickerSellJob` and its downstream exit-refinement tasks
(`task_data_availability.py` docstring: "MUST be called AFTER the sell/exit pass has already
executed for this bar"; `pp_inference.py`'s own comment above the call: "strictly AFTER every
sell/exit-evaluating task above ... has already run for this bar"). Separately, and more decisive
for THIS subsection: the live path submits orders SYNCHRONOUSLY, same process, same run —
`RenQuant/live/runner.py:531-535` runs `InferencePipeline().run(ctx)` then immediately calls
`adapter.commit(ctx)`, and `RunnerAdapter.commit()` places BOTH the sell orders (`runner.py:1177`,
`broker.place_order(ticker, "SELL", ...)`) and the buy orders (`runner.py:1509`,
`broker.place_order(ticker, "BUY", ...)`) inline, seconds apart, in that one call — there is no
file/DB queue and no deferred-submission step anywhere in this path (verified 2026-07-11). A
`TimeInForce.DAY` order submitted after-close typically FILLS at the next session's open rather
than immediately, but it is already broker-submitted (open at Alpaca, cancelable only via the
separate 06:15 PT `preopen_cancel_gate`, never replaceable) — submission, not fill, is what
`lifecycle_events`/phase (b) tracks (5.3.1), and submission already happened.

Consequence: for any gate that fires at or after `enforce_buy_block`'s position in the pipeline
(every soft-block T2 axis in §4 whose "Today" behavior is "sets `ctx.buy_blocked`, run continues"
rather than "raises, aborts the run") — by the time `InferencePipeline.run()` + `commit()` returns
and the run is `TERMINAL`, sells (if any fired that day) have ALREADY reached the broker. Because
the remediation controller is deliberately scheduled AFTER the daily run (§5.1, "so it never sits
inside the pipeline's fail-isolation domain" — a reviewed choice this design does not reopen), it
can only ever observe such a run in phase (b) or later. The phase-(a)-only rule (5.3.1) therefore
mechanically forecloses a same-day chained rerun for this entire class — not as an edge case, but
as the NORMAL case, including the flagship 07-08/09 example (§6.1). This is the P0 contradiction
Codex's second review pass identified, and it is resolved by splitting T2 gates into two classes
rather than treating "REMEDIATE+RERUN" as one uniform shape:

- **Class A — pre-side-effect abort.** A gate whose CURRENT failure mode raises/aborts the whole
  run before `TickerSellJob` ever executes (§4 row 1, `DataFreshnessGateTask`: "raises
  RuntimeError, aborts run" — OHLCV bars are a prerequisite for `RegimeJob`/`DrawdownJob`/the sell
  pass itself, so this abort is structurally pre-Phase-2a). For this class ONLY, `lifecycle_events
  == []` is genuinely true at controller handoff, and a same-day chained rerun (new `run_id`, full
  `RENQUANT_REMEDIATION_PARENT`-linked re-invocation, 5.3.7) is safe exactly as originally
  described — the parent run submitted nothing, so there is no "later external state"/book
  divergence hazard (5.3.6) to reconcile.
- **Class B — post-sell-pass soft block.** A gate whose current failure mode sets `ctx.buy_blocked`
  and lets the run complete normally through `commit()` (§4 row 5 `admission_model_metadata` and
  every other axis/invariant sharing that shape — the large majority of the table). For this
  class, remediation is INPUT-FIXING ONLY: the action (retrain/refetch/re-stamp) runs same-day,
  post-run, exactly as designed, and its own re-verification (§5.2 `verify[]`) still confirms the
  fix works — but there is no same-day rerun, no new `run_id`, and no resubmitted order for the
  session that already ran. The healed input is simply what the NEXT regularly-scheduled session
  sees; §6.1 is rewritten to this shape. `SELF_HEALED` (§5.5) for a Class B action means "input
  repaired and reverified before the next scheduled invocation," not "this session's buys
  resumed."

Every action in the registry (§5.2) must declare which class it is in; an action with no class tag
is not eligible for any stage beyond Stage 0 shadow. Rerun precondition for Class A (checked
against the phase-(a) predicate in 5.3.1, not restated as a separate ad hoc check): the parent
run's `lifecycle_events` contains no `orders_submitted` event of ANY kind — this supersedes and
strictly subsumes the earlier buy-only `funnel_integrity.funnel.n_buy_orders == 0` check. If a
Class-A-tagged action's parent run somehow still executed an exit before the gate fired (a
tagging error, or a code change that moved the gate later), the phase-(b) rule in 5.3.1 makes this
a hard SKIP+page regardless — there is no separate carve-out for exits being "senior," and a
misclassified action is a bug to fix, not a case to special-case around. The 105 executor's
`parent_intent_id` dedup (excludes `run_id`) is the model for making order-level idempotency
contractual on the native path; for any future Class A rerun, the 104 wrapper needs the equivalent
explicit dedup key (`(as_of, ticker, side, intent_hash)`) recorded before broker submission, not
inferred after the fact from order counts.

**5.3.5 No duplicate notifications, no duplicate artifact publication.** This subsection's "rerun"
language applies to Class A only (5.3.4) — Class A remediation is scoped to phase (a) (5.3.1), so
the parent run — by definition — has not yet sent a notification or published a shared artifact
when the controller acts. The ONLY notification for a Class A episode is the child (rerun)'s own
terminal notification, tagged per §5.5 (`SELF-HEALED` / `REMEDIATION_FAILED` / `RERUN_STILL_RED`);
the parent run's notification path is suppressed for any run still in phase (a) at controller
handoff (a small wrapper-script change: `daily_104.sh` defers its own ntfy call until AFTER the
controller has had a chance to intercept — open item, tracked as an implementation-PR
precondition, not assumed here). Shared artifacts (run bundle, decision-ledger rows) are written
ONLY under the run's own `run_id` — a Class A rerun is a NEW `run_id` by construction (5.3.7), so
there is no shared mutable artifact path for a duplicate publish to collide with; the ONLY
cross-run write is the supersession stamp in 5.3.3, which is explicitly idempotent (repeated
stamping of the same `superseded_by` value is a no-op).

**Class B has no rerun, hence a simpler notification contract.** The parent run already published
its own notification and bundle before the controller (scheduled after the run, §5.1) ever acts —
there is nothing to suppress and no duplicate-publish risk to guard against, because there is no
second invocation. The controller's OWN `SELF_HEALED`/`REMEDIATION_FAILED` notification for a
Class B episode is a genuinely NEW, additional notification (not a replacement for the parent
run's), tagged distinctly so an operator never reads it as "today's trading resumed" — it means
"today's input is repaired and reverified; the next scheduled session should see it clean."

**5.3.6 The "later external state" hazard (data/model fidelity, cross-referenced from §5.6).**
A rerun that executes minutes-to-an-hour after its parent is, by construction, evaluating
whatever OHLCV/fundamentals/broker state is CURRENT at rerun time — which may differ from what
was available at the parent's original decision time if any R0/R1 action (refetch, feed rebuild)
ran in between, or if the operator or another process changed broker state independently. This
is NOT itself a bug (the point of a remediation+rerun is to re-derive the decision from CURRENT,
now-healthy inputs) but it must never be silently conflated with "the 13:55 PT decision, just
delayed" framing. Every `remediation.v1` record therefore also stamps `input_snapshot_delta`:
a diff between the parent's recorded input fingerprints (OHLCV as-of, fundamentals as-of, broker
snapshot as-of — already present in each gate's evidence per §5.6) and the child's, so a reviewer
can see exactly what changed between decision attempts. This is why §5.6 makes an immutable
failed-run input snapshot + fingerprint diff a MECHANICAL precondition for every action, not
optional forensics.

**5.3.7 Run identity.** Class A only: the umbrella `RunnerAdapter` mints `YYYY-MM-DD-live-<hex8>`;
a Class A rerun is a NEW run-id by construction — this is also what makes 5.3.5's "no shared
mutable artifact" claim true for that class. The chain is recorded twice: the controller's
remediation record carries `parent_run_id`, and the rerun invocation passes
`RENQUANT_REMEDIATION_PARENT=<id>` which the runner stamps into
`run_bundle_json.remediation_parent` (small umbrella PR). For 104 daily there is no separate
session id — `as_of` is the day key; the chain is `as_of + parent link`. Class B mints no run-id
at all — the `remediation.v1` record's `child_run_id` (§5.5) is always `null` for a Class B
episode, and `parent_run_id` alone identifies which session's input the action repaired.

**5.3.8 Timing.** The daily-full runs post-close (13:55 PT launchd). The remediation window is
post-close → a hard cutoff (default 21:00 PT same day); heavyweight actions (tournament retrain
≤ ~1 h at `parallel_ticker_timeout_seconds=3600`) fit comfortably in either class — for Class A
this is when the chained rerun itself must complete; for Class B it is when the input-fixing
action and its offline reverification must complete, so the fix is already promoted/staged before
the NEXT regularly-scheduled session starts. Intraday runs get NO remediation lane in v1
(exits-always-allowed only; intraday retry semantics are a renquant-105 question — and per
5.3.1/5.3.4, an intraday run has typically already executed exits well before any remediable gate
could fire, so nearly every intraday gate would be Class B at best, and the tight intraday cadence
leaves no "next session" gap large enough to matter — out of scope for v1 either way).

**5.3.9 Same-date bundle/monitor collisions are already handled:** `FunnelIntegrityTask`'s
monitor-state history REPLACES the same-date record on rerun (idempotent by design), and bundle
consumers pick latest-per-day.

### 5.4 Loop protection (hard, mechanical)

1. **Chain depth = 1 (Class A only — Class B has no rerun to chain, §5.3.4).** One remediation
   episode per session: failed run → (actions) → ONE rerun → terminal. If the rerun is red for
   ANY reason — same gate or a different one — the episode ends in escalation. No
   remediation-of-remediation, ever. For Class B, the equivalent hard stop is simpler still: one
   action attempt, one offline re-verification; if that re-verification is still red, the episode
   ends in escalation exactly the same way — there is no rerun step to depth-limit.
2. **Per-action `max_attempts_per_session` = 1** and `cooldown_sessions` (default 5): an action
   that fired within the cooldown window fires ALARM-ONLY instead — recurrence means the
   producer is broken (the monthly-calibrator lesson), and repeatedly patching the symptom
   would mask it.
3. **Per-session budget:** ≤ 2 distinct actions, total remediation wall-clock ≤ 90 min, hard
   cutoff time. Budget state is stamped in the audit record.
4. **Poisoned-session rule (P2):** any T3/identity failure anywhere in the parent bundle ⇒ the
   controller executes NOTHING that session, including otherwise-enabled actions.
5. **Breaker seniority:** `TRADING_OFF`, a tripped `agent_breaker`, an active drawdown halt, or
   an in-flight deploy (pin mid-bump) ⇒ controller inert.
6. **Kill switches:** global `remediation.enabled`, per-action `enabled`, env
   `RENQUANT_NO_REMEDIATION=1` (checked first, like `RENQUANT_NO_NOTIFY`).

### 5.5 Audit contract — `remediation.v1`

One record per episode, persisted three ways: sidecar JSONL in orchestrator state — corrected
2026-07-11 (Codex review r2): standardize under the neutral R-PIN runtime root rather than
introducing a separate authority; `~/.renquant/remediation/remediation_log.jsonl`, sibling to
R-PIN's `~/.renquant/deploy/` (deployment state) and the stops-liveness pager's
`~/.renquant/ops/stops-liveness/` (orchestrator#481 precedent) — never a bare `~/renquant-data`
path — embedded in the CHILD run's bundle (Class A only; Class B has no child run, §5.3.7), and a
decision-ledger verdict row (`gate="remediation:<action_id>"`, so the "why did today do X"
query surfaces it):

```json
{
  "schema": "remediation.v1", "as_of": "...", "episode_id": "...",
  "parent_run_id": "...", "child_run_id": "... | null",
  "trigger": {"block": "data_availability|funnel_integrity|preflight",
               "axis_or_invariant": "...", "reason": "...", "evidence_before": {}},
  "action": {"action_id": "...", "risk_class": "R0-R3", "attempt": 1,
              "command": "...", "code_identity": "<script repo+commit/sha256>",
              "started_at": "...", "finished_at": "...", "exit_code": 0,
              "archives": ["..."], "log_path": "..."},
  "verification": {"evidence_after": {}, "gate_recheck": "pass|fail"},
  "fidelity": {"input_snapshot_ref": "<immutable parent-run input snapshot id, §5.6>",
                "as_of_cutoff": "...", "source_fingerprints_before": {}, "source_fingerprints_after": {},
                "output_fingerprints_before": {}, "output_fingerprints_after": {},
                "input_snapshot_delta": {"changed": [], "unchanged": []}},
  "budget": {"actions_used": 1, "wallclock_s": 0, "cutoff": "..."},
  "episode_key": "sha256(as_of, parent_run_id, action_id)",
  "outcome": "SELF_HEALED | REMEDIATION_FAILED | RERUN_STILL_RED |
              SKIPPED_PRECONDITION | SKIPPED_BUDGET | SKIPPED_POISONED | SKIPPED_PHASE_B |
              SHADOW_WOULD_RUN"
}
```

Operator visibility rides the existing `outage_monitor` (#480) title-tag vocabulary, extended
with one tag: **`SELF-HEALED`** (severity between DEGRADED and NO-TRADE; never quiet) for a
clean terminal run after remediation; `REMEDIATION_FAILED`/`RERUN_STILL_RED` page at OUTAGE
priority (5) carrying BOTH evidence blocks. An auto-remediated session is by definition never
reportable as a plain no-trade — it inherits registry invariant I10's capability bill.

### 5.6 Data & model fidelity contract (mechanical precondition for EVERY action)

Codex review (r1), P1: an R0 refetch, R1 regen, or R3 retrain can change the information set the
rerun evaluates against. §6.1's "anti-07-06 consistency precondition" and §6.2's fingerprint
checks are correct EXAMPLES but were only narrated per-action; this subsection makes the
underlying contract a MECHANICAL, MANDATORY precondition every action registry entry must
satisfy — not a pattern to be reinvented per worked example. An action with no
`fidelity_contract` entry (below) is not eligible for any stage beyond Stage 0 shadow.

Every action registry entry (§5.2) carries a `fidelity_contract`:

```
fidelity_contract: {
  input_snapshot: <how the failed run's exact inputs are captured immutably before the action
                    runs — e.g. a content-addressed copy/manifest of the OHLCV/fundamentals/
                    model-artifact files the failed run actually read, sealed the same way
                    renquant-artifacts evidence bundles are sealed this session>,
  as_of_cutoff: <the authoritative as-of boundary the action's output MUST NOT cross — e.g.
                 admission retrain's cutoff is the ORIGINAL eligible training cutoff the failed
                 run itself was entitled to use, not "whatever is available now"; a retrain that
                 would pull in data past that cutoff is not eligible to run as a remediation
                 (it would be a different, unauthorized decision, not a re-derivation of the same
                 one)>,
  source_fingerprint: <hash/identity of the authoritative upstream source the action reconciles
                        against (vendor feed snapshot, broker fill history query, pinned config
                        commit, pinned runtime algorithm identity) — recorded BEFORE the action
                        runs>,
  output_fingerprint: <hash/identity of the regenerated artifact — recorded AFTER>,
  no_leakage_proof: <the mechanical check that no post-decision data or revised history entered
                      the rerun — e.g. for admission retrain, the §6.1 models-consistency scan
                      PLUS an explicit assertion that every per-ticker `live_train_end` in the
                      retrained output is <= the failed run's own recorded cutoff; for the
                      calibrator re-stamp, the weights-payload-digest-unchanged check already in
                      §6.2, generalized as the template for any "metadata-only" action>,
}
```

**This closes the loop with §5.3.6's `input_snapshot_delta`:** the audit record's fidelity block
(§5.5) is populated FROM each action's `fidelity_contract` fields, not hand-rolled per action.
**Auto-retrain specifically:** every R3 retrain action's `as_of_cutoff` is the ORIGINAL eligible
training cutoff (never "now"), and per P3 (§2) its output remains a CANDIDATE — it re-enters
through the normal quality/promotion gates (acceptance, WF gate, tournament) exactly like a
scheduled retrain; the fidelity contract governs what data the retrain is allowed to have SEEN,
not whether its output is trusted (that is still the promotion gate's job, unchanged).

**R0 vendor-refetch eligibility (Codex review, r2 — added constraint on `source_fingerprint` for
refetch-class actions specifically, e.g. `ohlcv_refetch`, `broker_snapshot_repoll`).** A refetch is
only eligible to run as a same-day remediation when the vendor source can supply a
VERSIONED/as-of-queryable snapshot — i.e. `source_fingerprint` can name a specific, reproducible
vendor response (a snapshot id, an as-of query parameter, or an immutable per-day file the vendor
publishes) that a later audit can re-fetch and compare byte-for-byte. If the vendor only exposes a
mutable "latest" endpoint with no as-of parameter and no snapshot identity, there is no
after-the-fact way to prove what the refetch actually saw (`no_leakage_proof` cannot be
constructed — the vendor could have silently revised its own "latest" between the failed run's
attempt and the remediation's), so that source/action pairing is INELIGIBLE for the same-session
remediation lane regardless of its Class A/B tag: reclassify it as next-session preparation only
(the refreshed data becomes available to whichever session runs next, with no fidelity claim about
what changed and why) — never a same-session remediation+rerun. Each refetch-class action's
registry entry (§5.2) must record which of these two shapes its vendor supports before Stage 0.

## 6. Worked examples (the two mandated replays)

### 6.1 The 07-08/09 staleness outage — `admission_tournament_retrain`

**What actually happened.** 07-06: weekly retrain wrote all 230 `policy-metadata.json` files
but not the matching weight files (#436) → universe 83→33. 07-08 10:23 PT:
`git checkout HEAD -- models/` restored a CONSISTENT but STALE metadata+weights pair →
`FilterStalenessTask` correctly rejected 129-133/145 (`stale_76-80d_limit_60:live_train_end`)
→ buy scan **0 from 0** on 07-08 AND 07-09, both rendered as a normal
`no trade (no_candidates)`. 07-09: manual recovery retrain. 07-10: 125/145 admitted, 4 buys.
Cost: 2 sessions of zero buy capability, silent.

**The designed flow (same facts, controller enabled) — Class B (§5.3.4, corrected 2026-07-11,
Codex review r2).** The prior draft of this walkthrough described a same-day chained rerun that
resubmitted buy orders for the 07-08 session itself. That is unsafe: `enforce_buy_block` fires
after `TickerSellJob`, and the live runner's `commit()` submits both legs synchronously in the
same call (§5.3.4's ground-truth citation) — so by 14:10 PT, when the controller (scheduled after
the run, §5.1) first looks at the bundle, 07-08's sells (if any fired) are already at the broker.
This action is Class B: it repairs the ADMISSION INPUT the same evening, and the very next
regularly-scheduled session (07-09's normal 13:55 PT run — not a special rerun) is what actually
resumes buying. The value delivered is still real and large: the historical incident took until
07-10 (a full extra day, plus a MANUAL 07-09 recovery retrain) because nobody noticed until
someone went looking; this flow notices and heals the same evening, so the very next scheduled
session already sees a healthy gate.

1. 07-08 ~14:10 PT, post-run (run already TERMINAL, `commit()` already executed): bundle carries
   `data_availability.axes.admission_model_metadata = violation (fail_closed)` and
   `funnel_integrity.verdict = STRUCTURAL_BLOCK` with `universe_admission_collapse` evidence
   `top_rejection_reasons = {stale_76d…: 133}` + the `remediation_hints.v1` entry
   `admission_tournament_retrain` (R3, Class B, §5.1).
2. Controller policy pass: no T3 failure in the bundle (checkout guard/pin-align were green —
   honest note: the mutation restored COMMITTED state, so no identity gate could have flagged
   it; the staleness gate IS the detector for this class); breaker quiet; action enabled; budget
   clean; lease acquired for this `episode_key` (§5.3.2). Note what this policy pass does NOT
   check: it does not need `lifecycle_events == []`, because a Class B action never touches this
   run's decision/order flow at all — the phase-(a) precondition (5.3.1) governs Class A reruns
   only.
3. **Precondition (the anti-07-06 check, formalized as this action's `fidelity_contract.
   no_leakage_proof`, §5.6):** a models-dir consistency scan — for every ticker, metadata-declared
   weight files exist and parse (`load_artifact` dry pass), PLUS the assertion that every
   per-ticker `live_train_end` the retrain WOULD produce is <= the failed run's own recorded
   training cutoff (`fidelity_contract.as_of_cutoff`). This distinguishes the two C1 sub-classes
   with opposite verdicts: **consistent-but-stale ⇒ retrain** (this case); **metadata-without-
   weights ⇒ STOP** (the 07-06 corruption — retraining over a corruption signature destroys the
   evidence of the producer bug, and the correct 07-06 response was human forensics + point-in-
   time restore, which is a live-tree mutation and therefore never automated — the
   live-tree-mutation-preflight lesson).
4. Evidence-before: admitted 12/145, per-cause counts, `live_train_end` histogram, incumbent
   metadata digests.
5. Execute `weekly_tournament_retrain.sh` (timeout 3600 s/ticker side-config). Safety comes
   from the target's own merged machinery, not from the controller: #445 acceptance
   (`tournament_acceptance.py` T1-T5, including T4's "candidate data-cutoff must not REGRESS vs
   incumbent `live_train_end`") verdicts BEFORE any write; staging + per-file `os.replace`,
   metadata promoted LAST (the RenQuant#453 pattern on the gated path); rejected candidates
   leave the incumbent byte-identical; marker attestation requires digest change. **P3 holds:
   nothing is promoted past a quality gate — acceptance is the same gate a scheduled Sunday
   retrain faces.**
6. Verify (offline, read-only, no rerun): re-run the axis checker (`_classify_cutoffs`)
   out-of-pipeline against the newly-promoted metadata → admitted ≥ floor (0.6×145).
   Evidence-after: 125/145. This confirms the FIX works; it does not re-derive or resubmit any
   07-08 decision.
7. **No rerun.** 07-08's session is done: whatever it sold, it sold; it bought nothing (buy scan
   0/145) and that outcome for 07-08 is final and un-replayed. What changes is 07-09: the
   INCUMBENT admission metadata is now the retrained, acceptance-passed set, so 07-09's normal
   13:55 PT scheduled invocation — no `RENQUANT_REMEDIATION_PARENT`, no special chaining, just the
   ordinary cron — sees a healthy `admission_model_metadata` axis and resumes buying on its own,
   the same way any other day's run would. There is no new `run_id` for this episode
   (`remediation.v1.child_run_id = null`, §5.3.7).
8. Bundle/ledger for the EPISODE (not a rerun's bundle — Class B has none) stamps `remediation.v1`
   (outcome `SELF_HEALED`); ledger row `remediation:admission_tournament_retrain`; ntfy title
   `RENQUANT-104 SELF-HEALED SESSION-INTEGRITY 2026-07-08` — worded so an operator reads it as
   "07-08's input is repaired; 07-09 should trade normally," never as "07-08's buys retroactively
   executed" (§5.3.5).
9. Counterfactual failure branches: retrain acceptance rejects all → incumbent untouched, no
   change to 07-09's starting state, OUTAGE page with the acceptance log attached; verify still
   shows admitted < floor after a passing retrain → `RERUN_STILL_RED` (name kept for §5.5's
   existing vocabulary, even though no rerun occurred) — action auto-disabled, page — which after
   ~1 day of human forensics is exactly the 07-09/#436 investigation, minus the silent day.
   Either way, 07-09 (not a rerun of 07-08) is the earliest session that can possibly resume
   buying — this design cannot and does not claim to recover 07-08's own lost trading day.

**Enablement prerequisites (recorded):** RenQuant#453 closed on the gated path (done — verify
the weekly script exclusively uses `_run_gated_export`) and the direct non-atomic `.save()`
writers confirmed off the auto-triggered path; the models-consistency precondition scan exists.

### 6.2 The calibrator fingerprint mismatch — `calibrator_binding_restamp`

**Class A (§5.3.4) — contrast with §6.1's Class B.** Both of this action's detection planes fire
before `commit()` is ever reached: the primary path is a pre-market preflight check (step 1,
before `InferencePipeline.run()` even starts), and the fallback path is the SAME mid-pipeline-raise
mechanism as §4.2 row 10 (`LoadGlobalCalibrationTask` crashes before Phase 2b/3 complete, so
`commit()` is never called for that attempt). This is why a genuine same-day chained rerun with a
new `run_id` is safe here, unlike §6.1's admission-metadata case where the run completes normally
and reaches `commit()`.

**What actually happened (×3: 05-27, 06-22/07-01, 07-06).** The monthly calibrator refresh fit
stamps `scorer_model_content_fingerprint` with a DIFFERENT hand-copied `model_content_sha256`
field set than the runtime checks (triple-implementation bug) → parity can never match by
construction → `LoadGlobalCalibrationTask` raised mid-pipeline → full-run crash → sell-only
fallback reading `no trade (no_candidates)`. Each time, the fix was a manual metadata-only
re-stamp using the RUNTIME-correct algorithm imported from the pinned pipeline, then a manual
re-run (07-06's landed its 2 buys at 00:23 next day).

**The designed flow:**

1. Detection moves pre-market per registry invariant I4: the pre-flight binding check is
   `verify_calibrator_scorer_binding.py` (#425), which exercises the runtime-authoritative
   `PanelScorer.load` + `_any_fingerprints_match` — imported, never reimplemented (the bug WAS
   reimplementation). Exit 1 emits the preflight failure with hint
   `calibrator_binding_restamp` (R3). If it still surfaces mid-run instead, the
   `fail_close_event` invariant carries the same hint — one action, two detection planes.
2. Preconditions (ALL machine-checked, ANY miss ⇒ STOP):
   a. the SCORER artifact's content hash matches its manifest (identity plane green — if the
      scorer itself is not what it claims, this is T3 and nothing runs);
   b. the calibrator's WEIGHT payload digest is unchanged since its acceptance receipt (the
      mismatch is confined to the metadata stamp);
   c. the mismatch signature matches the known benign class (both fingerprints present,
      well-formed, computed-over-different-fieldsets — vs. absent/corrupt stamps).
3. Evidence-before: expected vs found fingerprint values, calibrator weights sha256, active
   scorer identity.
4. Execute the re-stamp: archive the old stamp → recompute with the pinned runtime's
   `model_content_sha256` against the ACTIVE scorer artifact → atomic temp+rename write
   (the `stamp_patchtst_fingerprint.py` pattern: fail-closed compatibility check first,
   idempotent early-return if already stamped). Metadata-only by construction.
5. Verify: `verify_calibrator_scorer_binding.py` exit 0 AND weights sha unchanged
   (proving metadata-only). Evidence-after stamped.
6. Rerun chained; `LoadGlobalCalibrationTask` passes; the 07-06 session's 2 buys land in the
   13:55 PT run instead of 00:23 the next day, and the decision notification says SELF-HEALED
   instead of `no_candidates`.
7. Recurrence governance: `cooldown_sessions` means a THIRD fire inside the window pages
   "producer broken — fix the monthly job" instead of patching again. That is precisely what
   happened manually (#425 added the binding check to the monthly refresh acceptance); with
   #425 live, new mismatches should be blocked at fit time and this action becomes
   defense-in-depth, expected to fire ~never. An action whose fire-rate does not decay toward
   zero is a design failure, and the audit trail makes that measurable.

## 7. Staged rollout (shadow-first, per-class enablement)

Consistent with the house preregistration culture: every stage has pre-declared acceptance
criteria, every stage change is a PR + progress doc, and nothing executes before its shadow
record has been reviewed.

| Stage | What runs | Enablement gate |
|---|---|---|
| **0 — shadow** | Pipeline PR: emit `remediation_hints.v1` (§5.1) + the cross-repo compatibility test. Orchestrator PR: controller in shadow — full policy pass, writes `remediation.v1` records with `outcome=SHADOW_WOULD_RUN`, executes NOTHING (this applies uniformly, including rows 20-28's SHADOW-ONLY tag, §4.3). Weekly digest of would-have-remediated episodes PLUS the §7bis historical incident replay. | §7bis's full per-action acceptance criteria (below) — NOT just "≥10 sessions", which is necessary but not sufficient |
| **1 — R0 (+ crash rerun for the Class A subset)** | `broker_snapshot_repoll` (Class B — no rerun, no cutover-predicate dependency). `ohlcv_refetch` and heartbeat `session_rerun` (both Class A — same-day chained rerun) require §5.1bis's cutover predicate to hold, IN ADDITION TO Stage-0 review, before they may be enabled — not before Stage 0 shadow logging, which takes no action regardless of class. | Stage-0 review; **§5.1bis's cutover predicate for the Class A subset (`ohlcv_refetch`, `session_rerun`) specifically** — Codex review r3, P0: no rerun-capable action enables until the execution-owned lifecycle stamp is durable, not merely traced against today's umbrella-anchored interim ground truth; launchd wiring is machine-landing (ask-first, one grant per batch) |
| **2 — R1** | `fundamentals_feed_rebuild`, `corr_metadata_rebuild`, `sector_map_regen` — all Class B, no rerun, no cutover-predicate dependency. | ≥ 5 clean Stage-1 sessions, no budget breaches |
| **3 — R3 (per-action operator sign-off)** | `admission_tournament_retrain` (Class B, after its §6.1 prerequisites), `calibrator_binding_restamp` (Class A, §6.2 — ALSO gated on §5.1bis's cutover predicate), async triggers. | Ledger supersession landed; RenQuant#453 verified on the auto path; per-action sign-off (capital-risk-adjacent — the delegation memo's sign-off standard applies); cutover predicate for the Class A subset |
| **4 — R2 (may stay manual forever)** | `washsale_broker_truth_reconcile` as an EXECUTING nightly job (Class B). | Default recommendation: DON'T — ship it as detector + prepared one-click command (notify-not-approve), and let the operator decide if the fire-rate justifies automation |

Rollback at any stage = flip the per-action/global kill switch (config, no deploy). Any
`RERUN_STILL_RED` or precondition anomaly auto-disables the involved action until a human
re-enables it (breaker semantics, applied to the controller itself).

## 7bis. Falsifiable evaluation protocol (Codex review, r1, P1 — first-class, per-action)

The #474 registry's headline number — 36/56 sessions engineering-blocked — is INCIDENT
MOTIVATION for why this design exists. It is explicitly NOT an estimate that automation would
have safely restored 36 runs, and no acceptance decision in this RFC is allowed to cite it as
one. Every action requires its own pre-registered evaluation protocol, defined BEFORE any shadow
logging for that action begins (logging that runs before the protocol is registered does not
count toward it — matching this session's own precedent on preregistered shadow evaluations,
e.g. `doc/design/2026-07-11-freshness-override-regime-consequences.md` §4).

**Per-action pre-registration (`eval_protocol`, §5.2), required fields:**

- **Eligibility** — the exact machine-checkable condition under which this action is even a
  candidate (references the gate + transience class from §4).
- **Expected remediation result** — the specific, falsifiable outcome a correct remediation
  produces (e.g. "admitted fraction ≥ 0.6× watchlist post-retrain", not "the problem is fixed").
- **Forbidden side effects** — an explicit list this action must NEVER produce (e.g. "no order
  submitted by the parent run", "no promotion past the WF gate without its own pass") — these are
  the assertions the hermetic tests for the controller must encode.
- **Counterfactual comparator** — what this action's outcome is measured against (e.g. the
  session's outcome under the CURRENT stop-and-page behavior, or a matched historical incident
  from the same registry class) — never an uncontrolled before/after on the same incident.
- **False-positive rate target** — the maximum tolerable rate of the action firing on a session
  that did NOT need it (measured in shadow against sessions independently known to be healthy).
- **Rollback rule** — the exact condition that auto-disables the action (this RFC's default:
  any `RERUN_STILL_RED` or a false-positive-rate breach during shadow).

**Class B estimand (Codex review r3, P1 — experiment accounting).** A Class B action (§5.3.4 —
the common case; most of §4's table) repairs TOMORROW's input; it cannot and does not recover the
session whose exits already reached the broker. The evaluation plan must report a Class B
`SELF_HEALED` episode's value SEPARATELY from any trading-performance metric, as **prevention of a
repeated failure** — the correct comparator is the NEXT session's outcome (did the healed input let
the next regularly-scheduled run trade normally, vs. the counterfactual of the input staying broken
for however many additional sessions it historically took a human to notice, per the #474
registry's own per-incident duration) — never as recovered performance for the session that
triggered it. Every Class B `remediation.v1` record must also carry the ORIGINAL session's missed-
session opportunity/cost (whatever the standard no-trade-session accounting already produces
elsewhere, referenced not reinvented here) as an explicit, separately-reported field, so an
acceptance reviewer sees "session N lost, session N+1 recovered because of this action" rather than
a single blended number that could be misread as "the action made session N profitable." No
acceptance decision in this RFC (or any per-action `eval_protocol`) may count a Class B
`SELF_HEALED` outcome as recovered trading performance for the triggering session, full stop —
Class A's genuine same-day rerun is the only shape where a "recovered this session" claim is even
possible, and only for the sessions that actually enable Class A per §5.1bis/§7.

**Evaluation evidence, required for EVERY action before its stage-3+ enablement (§7):**

1. **Historical incident replay set** — every matching incident already in the #474 registry
   (or a superset built the same way) is replayed against the action's exact machine logic
   (offline, read-only, no live effect) to confirm the `eval_protocol`'s expected result would
   have been produced FOR THAT ACTION SPECIFICALLY. An action whose registry class has zero or
   one historical incidents (e.g. a rare failure mode) does not get a pass by default — its
   action-specific minimum event count (below) must still be met, even if that means an
   extended shadow period or an explicitly accepted "insufficient evidence, hold at Stage 0"
   verdict.
2. **Prospective shadow coverage** — live shadow logging (`SHADOW_WOULD_RUN`), continuing
   alongside (1), with an **action-specific minimum event count** (not a single blanket "≥10
   sessions" — an action whose trigger condition fires rarely needs a correspondingly longer
   shadow window; the registry's own historical frequency per class, §1's table, sets this
   number per action) and an explicit **holdout period** (a trailing window excluded from the
   acceptance decision and reviewed only AFTER enablement, to catch overfitting the shadow
   evidence to the exact incidents already known).
3. **Reported separately, per action** (never aggregated across actions — a good action must not
   hide a bad one and vice versa): precision/recall of the `remediation_hints.v1` declarative
   hint against the eligibility criterion, rerun determinism (does re-running the SAME failed
   input snapshot through the SAME action converge to the same output fingerprint), the page/
   response latency distribution, and the zero-side-effect invariant (§5.3's forbidden side
   effects, confirmed to have never fired in shadow).

**Nothing in §7's stage table advances an action past Stage 0 without all of the above on file.**
This is a stricter, per-action gate than the table's own "≥5 clean sessions" / "per-action sign-
off" language suggests in isolation — those remain necessary, but §7bis's evidence package is the
thing operator sign-off is actually reviewing.

## 8. Open decisions for operator / Codex

| # | Decision | Design default |
|---|---|---|
| D1 | R2 wash-sale reconciliation: auto-execute (Stage 4) or permanently notify+one-click? | one-click; revisit on fire-rate evidence |
| D2 | Ledger supersession shape: `superseded_by` column vs canonical-run view (latest-per-day)? Must land with/before the S5 wiring PR; also fixes the run-scoped-verdicts vs day-scoped-outcomes asymmetry. | explicit `superseded_by` stamp + canonical view for readers |
| D3 | Rerun buy-safety precondition — strict phase-(a)-only (§5.3.1/5.3.4: SKIP+page on ANY order, buy or sell) or allow partial-fill sessions with operator ack? Applies to Class A only, r2 — the strict rule is WHY most gates turned out to be Class B rather than Class A once the real submission timing was traced. | strict; no carve-out, per Codex review r1, unchanged by r2 |
| D4 | Preflight verdicts into the run bundle (replacing `daily_104.sh` log-grep as the detection API): pipeline PR or umbrella PR first? | **REVERSED (Codex review, r2): pipeline emits `preflight_verdicts.v1` directly into the shared run bundle; orchestrator consumes it directly — no new umbrella forwarding path, since the umbrella is being actively deprecated and a new forwarding code path there works against that trajectory** |
| D5 | Budget defaults: attempts=1/action, ≤2 actions/session, chain depth 1, wall-clock ≤90 min, cutoff 21:00 PT, cooldown 5 sessions. | as stated; revisit after Stage 1 |
| D6 | Hint field additive inside `data_availability.v1`/`funnel_integrity.v1` vs a separate versioned block? | **REVERSED (Codex review, r1): separate `remediation_hints.v1` block (§5.1), not an additive field in the existing v1 blocks** — no cross-repo consumer-compatibility audit exists to justify the additive claim |
| D7 | This design supersedes the autonomous-ops-loops §4.2 "diagnose-and-notify, never auto-change" default for the classed lane — needs an explicit LONG-ledger amendment (operator-only tier). | amend at Stage-1 enablement, not before |
| D8 | `panel_model_artifact` staleness stays async-trigger-only (no same-session rerun), governed by #210 freshness policy — confirm. | confirmed as designed |
| D9 | Lease store implementation (§5.3.2): a new lightweight file/SQLite table in orchestrator state vs. reusing an existing mechanism (e.g. the decision-ledger DB)? | new lightweight table, orchestrator-owned, alongside `remediation_log.jsonl` — keep the lease store dependency-free of the ledger's own wiring status |
| D10 | Historical incident replay set (§7bis) — build it as a superset of the #474 registry, or treat #474 itself as sufficient? | superset if any action's registry-class event count is too low for its minimum (§7bis item 2); #474 alone is a floor, not a ceiling |

## 9. Non-goals

- No gate is weakened, retuned, or bypassed; no threshold moves; no auto-promotion.
- No intraday (105) remediation lane in v1.
- No remediation inside frozen/preregistered experiment worlds (two-arm shadow A/B): a red
  gate there is freeze-drift → voids the arm (P7).
- No live-tree git operations of any kind by the controller (checkout/reset are what CAUSED
  07-08; point-in-time restores remain human, preflight-simulated, operator-authorized).
- Not a substitute for producer fixes: every action's fire-rate is tracked, and a
  non-decaying fire-rate is treated as a bug in the producer, not a win for the controller.
