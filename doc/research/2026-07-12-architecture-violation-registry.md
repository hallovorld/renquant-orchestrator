# Architecture Violation Registry

Date: 2026-07-12 (original audit); **re-verified and revised 2026-07-12 in response to
Codex CHANGES_REQUESTED review** (round 2 — see "Revision history" below).
Scope: ALL RenQuant repos audited against the canonical subrepo operating model
(`RenQuant/doc/arch/subrepo-operating-model.md`) and pipeline architecture
(`renquant-common` Task/Job/Pipeline primitives).

> **Canonical boundary rules live in `RenQuant/doc/arch/subrepo-operating-model.md`
> — this document is an audit/evidence index against that canonical source, not
> itself an architecture decision record. Any cross-repo migration proposed here
> requires a separate ADR before implementation.**

> **Related, independently-produced audit trail**: a separate, already-merged
> 2026-07-10 synthesis audit exists at
> `doc/design/2026-07-10-architecture-compliance-registry.md` (this repo),
> backed by four raw evidence files under
> `doc/research/evidence/arch_audit_2026_07/audit_{A,B,C,D}_*.md` (1,065
> evidence lines, file:line verified, four parallel cluster audits). That
> document uses a different taxonomy (systemic themes T1-T7 + a remediation
> roadmap R0-R7) covering substantially overlapping ground for the
> umbrella/dual-home-kernel cluster (T1/T2 ≈ V-001/V-002/V-005/V-014 here) but
> does NOT itemize the GOAL-2/crypto-blocking cluster (V-006-V-013) to the
> same granularity this document does. Both documents are evidence indices
> against the same canonical operating model, not competing architecture
> decisions; this document cross-references that one extensively below rather
> than re-deriving already-established facts, and defers to it for the
> umbrella dual-home-kernel narrative (T1) where the two overlap.

Methodology: `git -C <repo> fetch origin main -q` then `git -C <repo>
grep`/`git -C <repo> show origin/main:<path>` against each repo's freshly-fetched
`origin/main` — never a working tree, since several sibling repos are on
non-main branches or have uncommitted changes (see "Audited commit" per entry
for the exact SHA verified). Evidence cited as `repo:file:line` with the exact
command run and the exact matched text today — not carried forward from the
prior round without independent re-verification. Two-agent split: the
umbrella/orchestrator/hygiene cluster (V-001–V-005, V-014–V-019, R-001–R-003)
and the GOAL-2/crypto cluster (V-006–V-013) were re-verified independently and
then reconciled into this single document.

## Revision history

- **2026-07-12 (round 1)**: original 19-violation + 3-resolved registry,
  produced by a 4-agent parallel audit.
- **Codex CHANGES_REQUESTED (2026-07-12T16:22:41Z)**: stale on facts already
  merged same-day (V-017, R-003); evidence not machine-verifiable (no audited
  SHA / exact command / path classification per entry); remediation presented
  as settled architecture rather than options; no rubric for severity; no
  concrete GOAL-2 acceptance tests; PR behind main.
- **2026-07-12 (round 2, this revision)**: every entry re-verified against a
  freshly-fetched `origin/main` of each relevant repo, in the structured
  evidence format below. Net effect (see Summary): V-017 RESOLVED (merged
  hours before this revision, exactly as Codex predicted); V-007, V-010
  RESOLVED (a 2026-07-10 crypto-RFC wiring wave the round-1 audit — despite
  being dated the same day — evidently audited against a pre-07-10 snapshot);
  V-009, V-019 reclassified NOT A VIOLATION; V-008 severity INCREASED (P1→P0
  — a net-of-cost primitive now exists and is trusted for live accounting,
  yet still isn't wired into the gate that most needs it); R-001 reopened as
  CONTESTED (canonical repos are unified, but the umbrella's separate
  dual-home kernel copy still runs its own independent fingerprint
  implementation feeding production — a live gap the round-1 "resolved" table
  hid); V-003/V-005/V-006/V-011/V-012/V-013/V-014/V-015/V-016/V-018
  recharacterized with materially different nuance (see each entry);
  V-001/V-002/V-004 re-verified essentially unchanged in substance. See
  per-entry "Disposition" fields for full detail.

## Summary (old vs. new severity counts)

| Severity | Old count | New count | Membership change |
|---|---|---|---|
| P0 | 5 | 4 (+1 mixed) | V-001, V-002 unchanged; V-005 DOWN to P1; **V-008 UP from P1** (worse on inspection); **V-014 split** — its tournament-retrain subset is P0-equivalent, bulk is P2 (see entry, not double-counted below); R-001 reopened with a live P0-equivalent remainder, tracked against V-001/T1, not double-counted as a new ID |
| P1 | 8 | 5 | V-003, V-005 in (moved from old P0); V-006, V-011, V-013 remain P1 (revised evidence); **OUT**: V-007 (resolved), V-009 (not a violation), V-010 (resolved) |
| P2 | 6 | 5 | V-004, V-015, V-016, V-018 remain; **V-012 IN** (downgraded from P1 — mechanism was mischaracterized); V-014's bulk-script component also P2 (not separately counted, see entry) |
| NOT A VIOLATION | 0 | 2 | V-009 (equity/crypto TIF genuinely isolated by construction), V-019 (annualization already asset-class-aware at both cited sites) |
| RESOLVED | 3 (R-001/002/003) | 5 | R-002, R-003 confirmed; **V-007, V-010, V-017 added** (V-017 merges into R-003's table entry); **R-001 downgraded to CONTESTED** (see entry — not a clean resolve) |

19 V-entries + 3 R-entries = 22, all accounted for below. Every entry carries
audited-commit, verification-date, exact-command, matched-evidence,
path-classification, disposition, rubric-scored severity, and a fact/proposed-remediation
split, per the methodology Codex required.

### Severity rubric (applied identically to every entry)

1. **Production safety** — risks incorrect LIVE TRADING behavior (wrong
   order/sizing/risk/money-losing) via an ACTIVE RUNTIME PATH, if unaddressed?
2. **Deployability** — blocks running on a different machine/checkout layout,
   independent of correctness?
3. **Correctness/drift risk** — two-copies-that-can-diverge or a fragile
   private-API cross-repo dependency, even if not immediately unsafe?
4. **Asset-class blocker (GOAL-2/crypto)** — specifically and COMPLETELY
   prevents crypto from functioning (a hard block, not a degradation)?

**P0** iff (1)=true AND path=ACTIVE RUNTIME PATH. **P1** iff (4)=true (hard
block) OR ((3)=true AND path=ACTIVE RUNTIME PATH). **P2** otherwise. Where
investigation shows a correct, isolated, asset-class-specific contract rather
than a violation: **NOT A VIOLATION**, not forced into a P-tier.

---

## P0 — active production paths, incorrect-live-trading risk

### V-001: Umbrella live/runner.py + adapters/runner.py is the active order-placing code

- **Audited commit**: RenQuant@16062b7b85 (origin/main); renquant-orchestrator@536cb91070
- **Verification date**: 2026-07-12
- **Command**: `git -C RenQuant show origin/main:live/runner.py | wc -l`; `git -C RenQuant show origin/main:live/runner.py | grep -n "adapters.runner import RunnerAdapter"`; `git -C RenQuant show origin/main:backtesting/renquant_104/adapters/runner.py | grep -n "broker.place_order"`; `git -C RenQuant show origin/main:scripts/daily_104.sh | sed -n '375,390p'`
- **Matched evidence**: `live/runner.py` = 1,200 lines. `live/runner.py:420` `from adapters.runner import RunnerAdapter`; `:526-535` constructs it and calls `adapter.commit(ctx)`. `backtesting/renquant_104/adapters/runner.py` = 2,311 lines (grew from 2,189 at a prior 2026-07-04 audit). `commit()` at `:1039`; real submissions at `:1177` (SELL) and `:1499` (BUY) via `broker.place_order`. `live/runner.py` imports only umbrella-local broker modules (`:32-36,178`), never `renquant_execution`. (Cross-checked against `RenQuant/doc/research/evidence/arch_audit_2026_07/audit_A_umbrella.md` §A1/A4, an already-merged 2026-07-10 read-only audit committed on renquant-orchestrator's own main — its file:line citations were independently re-run by me today and still match.)
- **Path classification**: ACTIVE RUNTIME PATH. Traced: `scripts/daily_104.sh:380-384` (default, `RQ_DAILY_RUNNER` unset → `multirepo`) invokes `python -m renquant_orchestrator daily-bridge --repo-dir ... --strategy renquant_104 --broker alpaca --once`, wired from `scripts/launchd/com.renquant.daily104.plist` (the actual scheduled entry point). Inside the orchestrator, `live_bridge.bootstrap_multirepo` only force-aliases `kernel.preflight`/`kernel.panel_pipeline` (+ a few named stems) to the pinned pipeline, then DELEGATES to `live.runner.main()` with the same argv — the umbrella's `live/runner.py` and `adapters.runner.RunnerAdapter` (not covered by the alias bridge at all) are what actually execute and place every real order. `RQ_DAILY_RUNNER=umbrella` is a documented rollback (`-m live.runner` directly, no bridge), but even the "modern" default path ends up running the identical runner/adapter code — only the module-resolution wrapper around it differs.
- **Disposition**: STILL PRESENT (re-verified, unchanged in substance). The entry-point wrapper changed 2026-06-03 to route through `renquant_orchestrator daily-bridge`, satisfying the ORIGINAL V-001 remediation's step 2 ("swap the launchd entry point") — but steps 1 and 3 ("prove feature parity via shadow comparison," "umbrella runner becomes a thin shim") are NOT done: the umbrella runner is still the code that runs, not a shim around an execution-owned equivalent.
- **Severity**:
  1. Production safety: TRUE — `adapters/runner.py:1177/1499` place real Alpaca orders; a defect here is a wrong-order/wrong-sizing/wrong-exposure risk on the live path.
  2. Deployability: TRUE — resolved via `sys.path` against this specific umbrella checkout, not through pinned/inventory-based resolution.
  3. Correctness/drift: TRUE — the 9,098-line `adapters/` package is bidirectionally diverged from `renquant-execution`'s broker stack (audit_A §A4: `alpaca_broker.py` diverged both directions — umbrella has AgentBreaker G2 caps + whole-share truncation, execution has fractional-order support; `paper_broker.py` has umbrella-only Z9 stop-sim protective features that would be LOST on a naive cutover).
  4. Asset-class blocker: FALSE — an ownership/duplication issue, not itself a crypto-specific hard block.
  - **P0** (production safety=true AND path=ACTIVE RUNTIME PATH).
- **Fact vs. hypothesis**:
  Observed: `live/runner.py` + `adapters/runner.py` place every live equity order today, reached via the orchestrator's `daily-bridge` default entry point, which is a thin dispatch wrapper around the umbrella code, not a reimplementation. This code does not import `renquant_execution` and is not covered by the pipeline kernel-alias bridge.
  Proposed remediation (NOT a decided architecture): migrate `RunnerAdapter`'s order dispatch onto `renquant-execution`'s existing-but-unwired `BrokerPort` Protocol seam (`order_state_machine.py`, `alpaca_broker_port.py`, `factory.py`), lifting the umbrella-only protective features (paper Z9 stop-sim, agent_breaker G2 caps) into execution FIRST so they are not lost, then cutting dispatch over leg-by-leg with behavior-invariance pins (the pattern PR #454 already used for order-sizing math). An alternative not evaluated here: formally deciding "runner" belongs permanently in the orchestrator as a native module rather than execution — that ownership choice needs an ADR, this audit only establishes the current fact pattern.

---

### V-002: daily_104.sh — partially bridged, but still owns undelegated policy + is the sole launchd target

- **Audited commit**: RenQuant@16062b7b85 (origin/main); renquant-orchestrator@536cb91070
- **Verification date**: 2026-07-12
- **Command**: `git -C RenQuant show origin/main:scripts/daily_104.sh | wc -l`; `git -C RenQuant ls-tree -r origin/main --name-only -- scripts/launchd/`; `git -C renquant-orchestrator show origin/main:src/renquant_orchestrator/scheduled_jobs.py | grep -n "migration_state\|native_replacement_job_id"`
- **Matched evidence**: `scripts/daily_104.sh` = 647 lines, unchanged count from the original claim. All 18 files in `scripts/launchd/` (incl. `com.renquant.daily104.plist`) invoke umbrella `.sh` scripts directly — none invoke `renquant-orchestrator run-job`. `scheduled_jobs.py` already registers `daily_live_runner_bridge`/`live_runner_bridge` jobs with `migration_state="umbrella_bridge"` and a `native_replacement_job_id="native_live_run_candidate"` + cutover command, while sibling jobs (weekly retrains, apy/promote monitors) are already `migration_state="native_multirepo"`.
- **Path classification**: ACTIVE RUNTIME PATH (it is the literal daily-run script, launchd-scheduled).
- **Disposition**: STILL PRESENT, but MORE PRECISELY CHARACTERIZED than the original doc: per line-range breakdown (independently re-traced against the current file), only ~120 lines are true host glue (env/log/notify setup, `/tmp` lock, launchd anchoring). The remainder — NYSE holiday gate, live-checkout guard, pin-align preflight, config-drift guard, system-doctor, model-age staleness alert, the inline WF-gate/preflight→sell-only fallback-decision parser (`:396-419`), and shadow-arm policy — duplicates logic the orchestrator ALREADY implements natively (`daily.py`'s Validate/Train/RunRuntime/Execute/Backtest/PersistDailyRunBundle Task classes; `live_bridge.main`) but the daily/live scheduling legs simply are not cut over to invoke it that way yet.
- **Severity**:
  1. Production safety: TRUE — this script IS the daily production run; a bug in its fallback-decision parser or drift guard directly changes whether real orders are placed.
  2. Deployability: TRUE — hardcodes `/Users/renhao/git/github/RenQuant` throughout (see V-004 for the orchestrator-side instance of the same problem; this script has its own).
  3. Correctness/drift: TRUE — duplicates already-implemented orchestrator Task logic (a second, shell-native implementation of the same policy that can silently diverge from the Python one).
  4. Asset-class blocker: FALSE.
  - **P0** (production safety=true AND path=ACTIVE RUNTIME PATH).
- **Fact vs. hypothesis**:
  Observed: the launchd scheduling layer (all 18 plists) exclusively targets umbrella shell scripts; the orchestrator has already-registered native replacement jobs for some (not all) of them with documented cutover commands.
  Proposed remediation (NOT a decided architecture): cut launchd over to the native jobs leg-by-leg, starting with the ones already `migration_state="native_multirepo"`; for `daily104`/`intraday104` specifically, this is gated on the same kernel-identity concern as V-001 (the native replacement must resolve to the same runtime kernel/version the umbrella script currently does, or the cutover is a silent behavior change disguised as a scheduling change) — see the umbrella repo's own 2026-07-10 synthesis audit (`doc/design/2026-07-10-architecture-compliance-registry.md`, finding T1/R1) for a fuller treatment of that specific hazard, which this document treats as a linked but separate audit trail rather than re-deriving.

---

### V-008: WF gate has no transaction-cost model (severity INCREASED on re-verification: P1 → P0)

- **Audited commit**: renquant-pipeline@b465000bf0; renquant-common@f5cb6ab2cf; renquant-model@62286996ea
- **Verification date**: 2026-07-12
- **Command**: `git grep -n "transaction_cost\|net_of_cost\|fee_pct\|slippage\|cost_model" origin/main -- src/renquant_pipeline/kernel/preflight.py src/renquant_pipeline/kernel/preflight_pipeline/tasks/gate.py`; cross-repo `git grep -ln "renquant_common.cost_model"` in pipeline/execution/backtesting/orchestrator/model
- **Matched evidence**: Pipeline's general WF gate (`kernel/preflight.py`, `kernel/preflight_pipeline/tasks/gate.py:31` `WfGateMetadataTask`, `:175` `RegimeLayeredICTask`) — zero hits for cost/fee/slippage terms; still gross-only. `rotation.py:129` `txn_cost = float(rotation_cfg.get("transaction_cost_pct", 0.0))` remains decision-time-only, not a gate check. New finding not in the original doc: `renquant-common/src/renquant_common/cost_model.py` exists (crypto RFC D-C8a) — a generic, asset-agnostic net-of-cost primitive explicitly designed so "the same cost-accounting math must be used IDENTICALLY by walk-forward-gate replay evaluation AND live runtime accounting." It is consumed by `renquant-execution/src/renquant_execution/account_cash_ledger.py` + `order_state_machine.py` (live accounting) and `renquant-model/src/renquant_model_crypto/fee_gate.py` (a crypto promotion diagnostic) — zero hits in `renquant-pipeline`, `renquant-backtesting`, or `renquant-orchestrator`. `fee_gate.py`'s docstring explicitly marks itself "a stamped diagnostic on tier-1 survivor-only evidence — NOT an enable path... `decision_grade: false`... Nothing in this repo flips a sleeve on."
- **Path classification**: ACTIVE RUNTIME PATH — `preflight.py`/`gate.py` run in the weekly WF-gate/promote pipeline (`weekly-wf-promote.plist`) that determines which model live-serves; this directly gates what trades real money even though it runs weekly rather than daily.
- **Disposition**: STILL PRESENT for the general (equity) WF gate — unchanged. PARTIALLY MITIGATED for crypto specifically via a new mechanism not in the original doc (`renquant_model_crypto/fee_gate.py` + `renquant_common.cost_model`), but that mechanism is diagnostic-only (`decision_grade: false`) and does not gate promotion, so it does not change the underlying risk.
- **Severity**:
  1. Production safety: TRUE — a model promoted on gross IC/return that is net-negative after realistic costs is exactly the failure class the D6 Governor replay already demonstrated live (frictions ate 86-100% of gross in that case per project history), and promotion directly determines what trades real money.
  2. Deployability: FALSE.
  3. Correctness/drift: TRUE — the generic cost primitive exists in `renquant-common` specifically so gate-evaluation and live-runtime cost accounting can't diverge, yet the gate that actually promotes equity models doesn't consume it.
  4. Asset-class blocker: FALSE — a quality/safety gap, not something that prevents crypto from running; crypto even has a non-gating diagnostic today that equity lacks.
  - **P0** (production safety=true AND path=ACTIVE RUNTIME PATH). Flagged explicitly as a severity increase over the original doc's P1: re-verification found the picture is WORSE, not better — the primitive now exists, is trusted for live accounting, and the highest-leverage consumer (the gate that decides what trades live money) still doesn't use it.
- **Fact vs. hypothesis**:
  Observed: `renquant_common.cost_model` exists, is already consumed by live execution accounting and a crypto-model diagnostic; the general pipeline WF gate does not import or reference it anywhere.
  Proposed remediation (NOT a decided architecture): add a cost-aware net-return check to the WF gate consuming `renquant_common.cost_model` directly (the primitive the original doc called for now exists, lowering remediation cost to "wire it in" rather than "build it"). Alternative: promote `fee_gate.py`'s pattern (diagnostic-first, `decision_grade` flag, Stage-0-attested costs before it can block) from model-crypto into the general pipeline gate, rather than building a separate equity-specific implementation.

---

### V-014: 274 Python scripts in umbrella — MIXED severity, not uniform hygiene

- **Audited commit**: RenQuant@16062b7b85
- **Verification date**: 2026-07-12
- **Command**: `git -C RenQuant ls-tree -r origin/main --name-only -- scripts/ | grep -c '\.py$'`
- **Matched evidence**: 274 (exact match, re-counted today).
- **Path classification**: MIXED — this entry bundles files with very different classifications and the original doc's flat "hygiene" framing undersells the worst subset. Specifically traced: `scripts/launchd/com.renquant.weekly-tournament-retrain.plist` → `train_104.py --skip-panel --force` → umbrella `kernel.pipeline.pp_training_full` → `training/*` (2,380 LOC) — this chain is ACTIVE RUNTIME PATH, launchd-scheduled weekly, and per the umbrella's own 2026-07-10 audit (`audit_A_umbrella.md` §A5, independently spot-checked by me: the plist and script names match) writes DIRECTLY to `models/<TICKER>/` with "no delegation, acceptance gate auto-disabled." The remaining ~270 scripts (including 30 training/fit-adjacent scripts not on this specific chain, plus ~62 unclassified research scripts per the same 07-10 audit's D8-9 finding) are a mix of research/dead-code/historical-shim — not independently classified script-by-script in this pass (274 files is out of scope to hand-classify individually here; deferred to the umbrella audit's own recommended triage).
- **Disposition**: STILL PRESENT, but the original doc's characterization needs correction: it is not "274 files of hygiene debt," it is "~270 files of hygiene debt PLUS one specific actively-scheduled training chain that writes live buy-admission models with its acceptance gate disabled" — a materially different risk profile than pure cleanup.
- **Severity** (scored separately for the two subsets, per the instruction not to force a blended tier that hides the worse case):
  - **Tournament-retrain chain subset**: (1) Production safety TRUE — writes per-ticker models that gate live buy admission (per project history: buy-admission gates on this legacy per-ticker tournament) with its acceptance gate auto-disabled; (2) Deployability FALSE; (3) Correctness/drift TRUE — renquant-model holds a diverged PARALLEL implementation (`renquant_model_gbdt/panel_trainer.py`, `renquant_model_patchtst/*`) under different names, not a migration; (4) Asset-class blocker FALSE. → **P0** (this is effectively the same finding class as V-001/T1 and arguably deserves its own ID rather than living inside "274 scripts" — flagged here rather than silently folded into a P2 bucket).
  - **Remaining ~270-script bulk**: (1) FALSE — dead/research code, no runtime consumer; (2) FALSE; (3) TRUE — general shadow-monorepo sprawl risk; (4) FALSE. → **P2**, unchanged from the original assessment.
- **Fact vs. hypothesis**:
  Observed: the script count and the tournament-retrain wiring (plist→script→umbrella-kernel-write, no gate) are directly confirmed. The 30-scripts/62-unclassified breakdown is cited from the cross-referenced umbrella audit, not independently re-derived line-by-line in this pass — flagged as a verification gap, not an independent finding.
  Proposed remediation (NOT a decided architecture): the original 4-bucket triage (active-production → owning repo; research-archival; migrated-duplicate; dead-code) remains reasonable for the bulk, but the tournament-retrain chain specifically needs its OWN remediation track (re-enable/redesign the acceptance gate, and/or delegate to renquant-model's parallel implementation once reconciled) sequenced with V-001, not folded into general script cleanup.

---

## P1 — asset-class hard blocks, or active-path duplication/reverse-dependency risk

### V-003: Pipeline imports from orchestrator (reverse dependency)

- **Audited commit**: renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-pipeline grep -n "from renquant_orchestrator" origin/main`
- **Matched evidence**: `src/renquant_pipeline/kernel/pipeline/task_decision_ledger.py:77`: `from renquant_orchestrator.decision_ledger import connect, write_verdicts` (exact match; the original doc's cited path was missing the `src/renquant_pipeline/` prefix but the file:line is otherwise identical and current).
- **Path classification**: `task_decision_ledger.py` is a `kernel/pipeline/` Task module invoked from the panel/preflight pipeline job graph, which IS on the default daily-bridge path (per V-001's tracing, the bridge aliases `kernel.preflight`/`kernel.panel_pipeline`+stems to the pinned pipeline). The import itself is deferred/lazy (function-scoped, not module-level), so it only executes when the ledger-write task actually runs. Classified ACTIVE RUNTIME PATH — not test-only or dead code — though I did not exhaustively trace every caller of this specific Task to confirm it fires on every daily-bridge invocation vs. only specific configs; flagged as a minor gap.
- **Disposition**: STILL PRESENT (re-verified, unchanged).
- **Severity**:
  1. Production safety: FALSE — a broken import fails-loud at ledger-write time (an operational/observability write), not a silent wrong-order/sizing corruption; no evidence this gates trade execution itself.
  2. Deployability: TRUE — pipeline cannot be installed/tested/deployed independently of orchestrator being importable, inverting the intended dependency direction.
  3. Correctness/drift: TRUE — creates an import-time circular risk (orchestrator→pipeline for inference, pipeline→orchestrator for ledger writes).
  4. Asset-class blocker: FALSE.
  - **P1** (correctness/drift=true AND path=ACTIVE RUNTIME PATH; production-safety false so it doesn't clear P0).
- **Fact vs. hypothesis**:
  Observed: the import is real, current, and lazy (function-scoped), so it does not break `import renquant_pipeline` itself, only the specific decision-ledger-write codepath.
  Proposed remediation (NOT a decided architecture — Codex explicitly flagged this needs a stated alternative, not a foregone conclusion): **Option A** — move `decision_ledger.connect`/`write_verdicts` into `renquant-common`; both orchestrator and pipeline import from common, restoring a one-directional dependency graph. **Option B** — pipeline owns persistence directly (a `renquant_pipeline.persistence` module) since pipeline produces the decisions being logged; orchestrator, if it also needs to write ledger entries, imports pipeline's public persistence API instead of the reverse. Trade-off: Option A adds a new stateful-persistence concept to common (today mostly primitives/contracts) but cleanly avoids ANY orchestrator↔pipeline coupling in either direction; Option B keeps persistence next to the domain that defines "what a decision is" but is a bigger diff (orchestrator's `decision_ledger.py` module would need to be deleted/relocated into pipeline). Neither is decided; requires an ADR before implementation.

---

### V-005: Orchestrator imports pipeline kernel internals (severity DOWN from old P0 → P1 under the new rubric)

- **Audited commit**: renquant-orchestrator@536cb91070
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-orchestrator show origin/main:src/renquant_orchestrator/native_context_hydration.py | grep -n "from renquant_pipeline.kernel"`; `git -C renquant-orchestrator show origin/main:src/renquant_orchestrator/train_gbdt.py | grep -n "from renquant_pipeline.kernel"`
- **Matched evidence**: `native_context_hydration.py:140` `from renquant_pipeline.kernel.data import LocalStore`; `:198` `from renquant_pipeline.kernel.data import (...)`; `:421` `from renquant_pipeline.kernel.exits import HoldingState`; `:422` `from renquant_pipeline.kernel.regime import RegimeState`; `:563` `from renquant_pipeline.kernel.pipeline.job_universe import (...)`. `train_gbdt.py:271` `from renquant_pipeline.kernel.persistence import record_training_run`. All lines match the original doc exactly, all still present.
- **Path classification**: ACTIVE RUNTIME PATH for `native_context_hydration.py` (used by the `native_live_run`/`native_context_hydration` modules — per T1-T7 audit_D, this is part of the "native" path that runs the pinned pipeline kernel for non-legacy-runner flows). `train_gbdt.py:271`'s import is inside a training code path; I did not independently verify `train_gbdt.py` specifically (as opposed to the umbrella's own `training.py`/`training_panel/`) is what a live launchd job actually invokes today, so I'm classifying this one occurrence as ACTIVE RUNTIME PATH with lower confidence than the other five — flagged as a verification gap rather than asserted as fact.
- **Disposition**: STILL PRESENT (re-verified, unchanged, same line numbers as the original doc).
- **Severity**:
  1. Production safety: FALSE — a `kernel.*` internal-path refactor breaking this import fails at import/startup time (loud outage), not a silent wrong-decision; scored false per the rubric's "wrong order/sizing/risk/money-losing" test even though it would cause real operational disruption.
  2. Deployability: FALSE — same-ecosystem (both pinned sibling repos resolved via the same subrepo runtime) coupling, not a cross-machine portability issue like V-004.
  3. Correctness/drift: TRUE — `kernel` is pipeline's internal implementation surface (not a declared public API); any kernel refactor can silently break the orchestrator at a layer pipeline's own tests wouldn't catch.
  4. Asset-class blocker: FALSE.
  - **P1** (correctness/drift=true AND path=ACTIVE RUNTIME PATH). Note: this moves DOWN from the original doc's P0 under the new rubric specifically because production-safety scores false (loud-failure-at-import is not the rubric's "incorrect live trading behavior" test) — this is an explicit, intentional consequence of applying the stated rubric literally, not an oversight.
- **Fact vs. hypothesis**:
  Observed: five call sites import directly from `renquant_pipeline.kernel.*` rather than any published public surface; no public-API re-export module was found during this pass (not exhaustively verified for every symbol).
  Proposed remediation (NOT a decided architecture): pipeline exposes the needed types via a public surface (top-level `__init__.py` re-exports or a dedicated `renquant_pipeline.types`/`renquant_pipeline.contracts` module); orchestrator consumes only that surface; add a CI import-boundary test in orchestrator rejecting `from renquant_pipeline.kernel` (the same mechanism V-018 finds missing in orchestrator/pipeline/execution — renquant-model already has a working template).

---

### V-006: ALLOWED_BROKERS duplicated in pipeline (2 copies)

- **Audited commit**: renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git grep -n "ALLOWED_BROKERS" origin/main -- '*.py'`
- **Matched evidence**: Two independent, currently byte-identical definitions — `src/renquant_pipeline/state_paths.py:29` and `src/renquant_pipeline/kernel/state_paths.py:29`, both `ALLOWED_BROKERS: frozenset[str] = frozenset({"paper", "alpaca", "alpaca-paper", "alpaca_paper", "alpaca-shorts", "alpaca_shorts", "alpaca_shadow", "alpaca_shadow_a", "alpaca_shadow_b", "ibkr"})`. No `alpaca_crypto`/crypto broker tag in either copy yet. A mechanical parity test already exists: `tests/test_shadow_arm_broker_tags.py:37` `test_allowlist_copies_stay_identical` (`assert top_state_paths.ALLOWED_BROKERS == kernel_state_paths.ALLOWED_BROKERS`) — new context the original doc didn't credit; drift would be CI-caught, not silent.
- **Path classification**: ACTIVE RUNTIME PATH. The kernel copy is imported by `kernel/preflight.py`, `kernel/preflight_pipeline/tasks/broker_fill_freshness.py`, `kernel/preflight_pipeline/tasks/state.py`, `kernel/pipeline/job_universe.py` — the live preflight gate chain (the `P-*` check names appear verbatim in `daily_104.sh`'s buy-side-preflight pattern match, confirming this runs on every live cycle).
- **Disposition**: STILL PRESENT (re-verified, unchanged structurally; the parity test is new mitigation, not a fix of the duplication itself).
- **Severity**:
  1. Production safety: FALSE — a name mismatch fails closed and the parity test catches accidental drift at CI time; no silent wrong-behavior path found.
  2. Deployability: FALSE.
  3. Correctness/drift: TRUE — two independently-editable literal copies of the same allowlist; the parity test detects drift after the fact, it doesn't make drift structurally impossible.
  4. Asset-class blocker: FALSE — no crypto broker tag exists yet, but that's an omission, not something the duplication itself blocks; adding one requires two synchronized (test-guarded) edits, not a hard stop.
  - **P1** (correctness/drift=true AND path=ACTIVE RUNTIME PATH).
- **Fact vs. hypothesis**:
  Observed: two byte-identical `ALLOWED_BROKERS` frozensets, both on the live preflight path, both missing any crypto broker tag today, guarded by one CI parity test.
  Proposed remediation (NOT a decided architecture): move `ALLOWED_BROKERS` to `renquant-common` as the single source, both pipeline modules import it. Cheaper alternative not previously considered: keep two files but make one a literal re-export (`from .state_paths import ALLOWED_BROKERS`) of the other — eliminates the duplicate literal without a common-repo move, at the cost of leaving pipeline (not common) as source-of-truth for a cross-repo broker-tag concept.

---

### V-011: Vol clips pin at equity levels — PARTIALLY RESOLVED, with a more precise residual defect than originally described

- **Audited commit**: renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git show origin/main:src/renquant_pipeline/kernel/panel_pipeline/job_panel_scoring.py | sed -n '3555,3570p'`; `git show origin/main:src/renquant_pipeline/kernel/asset_class.py | sed -n '213,218p'`; `git grep -n "compute_vol_target_scale(" origin/main -- src/`; `git show origin/main:src/renquant_pipeline/kernel/portfolio_qp/tasks.py | sed -n '1286,1300p'`
- **Matched evidence**:
  - **Per-name σ clip (job_panel_scoring.py) — RESOLVED**: `:3561-3568` now calls `from renquant_pipeline.kernel.asset_class import (resolve_asset_class, sigma_clip_bounds_for)`; `default_floor, default_ceiling = sigma_clip_bounds_for(asset_class)`; `ann_days = annualization_days_for(asset_class)`. `asset_class.py:213-217` `sigma_clip_bounds_for(asset_class)` looks up a per-class `SIGMA_CLIP_BOUNDS` dict, fail-closed on unknown class — no longer a single hardcoded `[0.05, 1.50]` for every asset class.
  - **Portfolio-level vol-target scale (vol_target.py + portfolio_qp/tasks.py) — genuinely still defective, more precisely than the original doc stated**: `portfolio_qp/tasks.py:1286-1298` `_compute_vt_scale` now threads `annualization_days=annualization_days_for(_ctx_asset_class(ctx))` (that specific original complaint is fixed) and `floor`/`ceiling` are config-driven, not hardcoded in code. **But the input series is unconditionally `ctx.spy_returns` regardless of asset class** — no crypto-index/BTC-proxy return series exists anywhere in this call chain. `vol_target.py`'s own docstring: "We proxy *portfolio* realized vol with SPY realized vol (β≈1 assumption)" — economically meaningless for crypto (β to SPY is not ≈1 and is regime-dependent), yet the code silently computes *some* scale factor and applies it to sizing rather than erroring.
- **Path classification**: ACTIVE RUNTIME PATH for both — `job_panel_scoring.py` runs in live per-name scoring; `ApplyExposureScalingTask` (`portfolio_qp/tasks.py`) runs in live QP sizing every cycle. The SPY-proxy defect specifically is LATENT (not yet exercised) — no crypto sleeve is live as of this audit, so it has not yet actually mis-sized a real position; it would fire on day one of a crypto sleeve going live with `vol_target.enabled=true`, with no additional code change required to trigger it.
- **Disposition**: CONTESTED / PARTIALLY RESOLVED — the original doc's specific citations (the `[0.05, 1.50]` per-name clip; "vol_target already accepts annualization_days parameter") are now resolved almost exactly as its own proposed remediation described. Re-verification surfaces a DIFFERENT, unremediated defect in the same subsystem the original remediation text did not address: the portfolio-level scale's input series is asset-class-blind even though its parameters are now asset-class-aware.
- **Severity** (residual SPY-proxy issue only — the per-name clip is resolved, not separately scored):
  1. Production safety: TRUE but conditional/latent — would silently misapply portfolio-level gross-exposure scaling to a live crypto sleeve (wrong sizing = wrong risk exposure) once GOAL-2 goes live; not currently producing wrong live behavior since no crypto sleeve exists yet.
  2. Deployability: FALSE.
  3. Correctness/drift: TRUE — a vol-targeting function whose parameters were made asset-class-aware but whose data input was not is an internally inconsistent contract.
  4. Asset-class blocker: FALSE — degrades (wrong-but-not-order-blocking scale factor) rather than hard-blocking.
  - **P1** (axis 3 true AND path=ACTIVE RUNTIME PATH, unconditionally for the function itself). Flagged as more precise AND in one sense worse than the original: the cited defects are fixed, but a related, not-previously-documented defect will silently activate the day GOAL-2 goes live rather than failing loudly.
- **Fact vs. hypothesis**:
  Observed: `sigma_clip_bounds_for(asset_class)` is real and wired at the per-name clip site; `compute_vol_target_scale`'s `annualization_days` is real and wired; its `spy_returns` input is not asset-class-dispatched anywhere in the current call chain.
  Proposed remediation (NOT a decided architecture): either (a) gate `vol_target.enabled` off by default for `asset_class="crypto"` sleeves until a crypto-appropriate proxy series exists (cheapest, fail-safe), or (b) add a crypto composite-index/BTC realized-vol input alongside `spy_returns`, dispatched the same way `sigma_clip_bounds_for` is. (a) is lower-risk as an interim measure since it needs no new data sourcing.

---

### V-013: Execution reconciliation filters US_EQUITY only — capability RESOLVED, production wiring STILL INCOMPLETE

- **Audited commit**: renquant-execution@59ae2ddc6b; renquant-orchestrator@536cb91070; renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git show origin/main:src/renquant_execution/alpaca_broker.py | sed -n '195,270p'`; `git grep -n "get_filled_orders(\|get_open_orders(" origin/main -- '*.py'` in renquant-orchestrator and renquant-pipeline
- **Matched evidence**: `alpaca_broker.py:223-251` `get_filled_orders(self, after=None, asset_class: str | None = ASSET_CLASS_EQUITY)` and `:255-270` `get_open_orders(self, asset_class: str | None = ASSET_CLASS_EQUITY)` — both now parameterized; default preserves old equity-only behavior; `asset_class="crypto"` or `None` (all classes) are supported. Docstring cites "crypto RFC §3.2 E3." Comment at `:207-210`: the OLD filter never worked at the Alpaca API level at all (`GetOrdersRequest` has no `asset_class` field, silently dropped) — filtering is now client-side on the returned `Order.asset_class` via `_order_matches_asset_class`. **Production call sites still don't pass it**: `renquant-orchestrator/src/renquant_orchestrator/native_live_snapshots.py:96` `broker.get_open_orders()` (no argument → default equity-only); `renquant-pipeline/src/renquant_pipeline/kernel/realized_pnl.py:53` `broker.get_filled_orders(after=after_str)` (no `asset_class` argument → default equity-only). No other production caller found in orchestrator or pipeline (backtesting/strategy-104 not exhaustively checked — flagged as a gap).
- **Path classification**: ACTIVE RUNTIME PATH for the broker methods and both call sites (`native_live_snapshots.py` is the live snapshot/reconciliation path; `realized_pnl.py` is live realized-P&L computation).
- **Disposition**: STILL PRESENT, but materially different from the original description — the broker-level capability the original remediation asked for ("pass an asset_class parameter... broker tag isolation handles separation") already exists and works; what's missing is that the two live callers found don't use it yet. This is the "abstraction exists but isn't wired at the call site" pattern recurring across this crypto-readiness effort (also seen in V-011, R-002).
- **Severity**:
  1. Production safety: TRUE, conditional/latent — same caveat as V-011: fires the day a crypto sleeve is live, not today.
  2. Deployability: FALSE.
  3. Correctness/drift: TRUE — a capability that exists but silently isn't used at its two natural call sites is itself a drift risk.
  4. Asset-class blocker: TRUE, hard — if these two call sites are the only production reconciliation/P&L paths (no crypto-specific reconciliation path was found anywhere in orchestrator or pipeline), fills and open orders would be COMPLETELY invisible to reconcile-before-emit and realized-P&L on day one of live crypto trading — a total blind spot, not a degradation.
  - **P1** (axis 4 true, hard).
- **Fact vs. hypothesis**:
  Observed: the broker-level asset-class filter parameter is implemented and default-safe; the two production call sites found do not pass it.
  Proposed remediation (NOT a decided architecture): update `native_live_snapshots.py` and `realized_pnl.py` to pass `asset_class=None` (all classes) rather than relying on the equity-only default, or have crypto-sleeve callers explicitly pass `asset_class="crypto"` alongside the existing equity call — cheaper than a design change since the capability already exists; a call-site update, not new architecture.

**Acceptance test spec (not implemented — audit-only)**:
- Given: a live Alpaca paper/prod account with one open crypto order (e.g. `BTC/USD` limit buy, GTC) and one crypto fill from earlier today, alongside normal equity activity.
- Command/trigger: `renquant_orchestrator.native_live_snapshots` calling `broker.get_open_orders()` (as currently called, no arguments) during a live snapshot cycle; separately, `renquant_pipeline.kernel.realized_pnl` calling `broker.get_filled_orders(after=<today's date>)` (as currently called).
- Expected WITHOUT remediation: `get_open_orders()` returns a `set[str]` of symbols that does NOT include `BTC/USD` (silently filtered by the `ASSET_CLASS_EQUITY` default via `_order_matches_asset_class`); `get_filled_orders(after=...)` returns a list omitting the crypto fill row entirely. No error, no warning — silent omission.
- Expected WITH remediation: both calls (updated to pass `asset_class=None` or an explicit crypto-aware caller) return results including the `BTC/USD` open order and fill respectively, alongside the existing equity rows.

---

## P2 — hygiene, non-runtime-path, or degrades-but-doesn't-block

### V-004: Orchestrator hardcodes umbrella paths in scheduled_jobs.py

- **Audited commit**: renquant-orchestrator@536cb91070
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-orchestrator show origin/main:src/renquant_orchestrator/scheduled_jobs.py | grep -c "/Users/renhao/git/github/RenQuant"`; `git -C renquant-orchestrator show origin/main:src/renquant_orchestrator/scheduled_jobs.py | grep -n "/Users/renhao/git/github/RenQuant\|CANONICAL_REPO_ROOT"`
- **Matched evidence**: exactly 13 occurrences (re-run today, matches the original claim exactly). `:13` `CANONICAL_REPO_ROOT = "/Users/renhao/git/github/RenQuant"`; further occurrences at `:19-20,78-79,98-99,116-117,309,311,320-321,369,371`.
- **Path classification**: ACTIVE RUNTIME PATH — `scheduled_jobs.py` is imported by `job_runner.py` (`job_runner.py:74` calls `main(["daily-bridge", *forwarded])`) and defines the job registry consumed for launchd/native scheduling.
- **Disposition**: STILL PRESENT (re-verified, unchanged; same line numbers as the original doc).
- **Severity**:
  1. Production safety: FALSE — a hardcoded-but-correct path doesn't misprice or misroute an order; a portability defect, not a correctness-of-decision defect.
  2. Deployability: TRUE — the orchestrator (whose stated purpose is to REPLACE umbrella coupling) cannot run on a machine with a different checkout layout without editing this file.
  3. Correctness/drift: PARTIAL — not duplicated-logic risk, but a fragile assumption that silently breaks (wrong log paths) rather than failing loudly if the layout changes.
  4. Asset-class blocker: FALSE.
  - **P2** (production-safety false; correctness/drift only partial, not the rubric's clean "true" needed for P1; deployability true alone isn't a P0/P1 trigger under this rubric).
- **Fact vs. hypothesis**:
  Observed: `deployment_manifest.load_runtime_inventory()` already exists (`deployment_manifest.py:723`) and is used elsewhere (`deploy_pin.py:468`) — but NOT by `scheduled_jobs.py`. Correction to the original doc: its claim that this API "is used by the stops-liveness pager" does not hold — the stops-liveness pager (`software_stops_registry_contract.py`) uses a DIFFERENT mechanism, `runtime_state_root()` / `RENQUANT_RUNTIME_STATE_ROOT` (see R-003), not `load_runtime_inventory`.
  Proposed remediation (NOT a decided architecture): replace `CANONICAL_REPO_ROOT` and the 13 hardcoded occurrences with `deployment_manifest.load_runtime_inventory()` lookups, following the pattern proven in `deploy_pin.py` — not the stops-pager's separate `runtime_state_root()` convention, which resolves a different concept (state-root vs. repo-root) and conflating the two would itself be a small architecture decision worth a one-line ADR note.

---

### V-012: Fundamentals hard-block has no asset-class bypass — STALE-CLAIM, original mechanism does not match current code (downgraded P1 → P2)

- **Audited commit**: renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git show origin/main:src/renquant_pipeline/kernel/preflight_pipeline/tasks/fundamentals_freshness.py` (full `FundamentalsFreshnessTask` + `classify_freshness`); `git show origin/main:src/renquant_pipeline/kernel/panel_pipeline/job_panel_scoring.py | sed -n '195,250p'`
- **Matched evidence**: `preflight_pipeline/tasks/fundamentals_freshness.py:263-297` `FundamentalsFreshnessTask.check()` reads ONE scalar `panel_max = _fund_max_date(path)` — the max date across the ENTIRE `sec_fundamentals_daily.parquet` feed — and hard-blocks buys only if that single feed-wide date is stale (`panel_max_date is None → skip`). This is a feed-freshness check, not a per-ticker "does this ticker have fundamentals" check. `panel_pipeline/job_panel_scoring.py:216-224` (`_apply_fund_features`) — for a ticker with no row in the fundamentals panel: `row[col] = value if value is not None else medians[col]` — fail-open, cross-sectional-median imputation, not fail-closed. A separate stale-feed check in the same function only `log.warning(...)`, does not raise or block.
- **Path classification**: ACTIVE RUNTIME PATH for both (preflight runs pre-`InferencePipeline`; `_apply_fund_features` runs in live panel scoring).
- **Disposition**: STALE-CLAIM — the specific mechanism described ("panel fails closed without fundamentals... every crypto buy would be hard-blocked") does not match current code. The feed-level preflight gate would only block buys (of ANY asset class, equity included) if the WHOLE daily fundamentals feed goes stale — not crypto-specific, and would not fire merely because crypto tickers are absent from the feed. Per-ticker feature assembly explicitly fails open with median imputation, the opposite of the claimed fail-closed behavior. No third, per-ticker fundamentals-presence hard-block was found anywhere in the preflight chain (checked `P-FEATURE-COVER`/`feature_coverage.py` — a static artifact-metadata check on the model's declared `feature_cols`, unrelated to per-ticker data presence).
- **Severity**:
  1. Production safety: FALSE — no hard-block mechanism found that a crypto ticker would specifically trigger; behavior is fail-open (median-imputed).
  2. Deployability: FALSE.
  3. Correctness/drift: PARTIAL — every crypto ticker would silently receive cross-sectional-median-imputed values for every fundamentals-derived feature (economically meaningless for crypto — no P/E ratio exists), degrading model input quality with no flag distinguishing "genuinely missing, imputed" from "real value."
  4. Asset-class blocker: FALSE — does not prevent crypto from functioning; degrades signal quality silently.
  - **P2** (data-quality hygiene, not a blocker — a real severity DOWNGRADE from the original P1, driven purely by the mechanism being mischaracterized, not by anything actually improving).
- **Fact vs. hypothesis**:
  Observed: the preflight fundamentals gate is feed-level, not ticker-level; per-ticker missing fundamentals are median-imputed, not blocked.
  Proposed remediation (NOT a decided architecture): if crypto features should never include fundamentals-derived columns (economically meaningless for crypto), the cleaner fix is excluding fundamentals columns from the crypto feature set upstream (config/model-card driven) rather than letting them silently median-impute — a data-contract fix, not a gate-bypass fix, since there's no hard gate to bypass here.

---

### V-015: Stale strategy_config.json copies — confirmed diverged, but default runtime path is safe

- **Audited commit**: RenQuant@16062b7b85; renquant-strategy-104@16c2fb6baf
- **Verification date**: 2026-07-12
- **Command**: `git -C RenQuant ls-tree -r origin/main --name-only | grep -i "strategy_config.*\.json$"`; cross-checked against `audit_A_umbrella.md` §A8 (byte sizes cited from that 2026-07-10 source, not independently re-run byte-for-byte in this pass — see gap note below).
- **Matched evidence**: the file inventory matches the original doc's category (backtesting/renquant_101-104 canonical configs, `_archive/` snapshots, `golden`/`shadow`/`sim_*`/`codex_*`/`whatif_*` variants) but the actual count today is 90+ files, MORE than the original "10+" undercount. Per the cross-referenced audit_A §A8: umbrella's live working copy `backtesting/renquant_104/strategy_config.json` = 47,880 bytes vs. pinned `renquant-strategy-104/configs/strategy_config.json` = 57,835 bytes — genuinely diverged (missing keys: `live, intraday_decisioning, decision_ledger, sleeve, sizing, bear_defensive_sleeve, sdl_skip_if_trailing_armed`).
- **Path classification**: NOT on the default ACTIVE RUNTIME PATH — the key correction to the original doc. Per audit_A §A8 (independently spot-checked against `scripts/daily_104.sh:113-120`): `daily-bridge`'s default path rewrites argv to load the PINNED strategy-104 config, and `daily_104.sh` itself resolves `PROD_STRATEGY_CONFIG` pinned-first with `RENQUANT_STRICT_SUBREPO_PATHS` fail-closed. The stale umbrella copy is loaded ONLY by `RQ_DAILY_RUNNER=umbrella` rollback mode, `run_sim_104.py`, and standalone analysis scripts — HISTORICAL SHIM/TEST-ONLY on the default path, but conditionally ACTIVE RUNTIME PATH (the rollback mode and sim/eval legs are real, occasionally-invoked paths).
- **Disposition**: STILL PRESENT, materially RECHARACTERIZED — the original doc implied general live risk; re-verification shows the default daily-full path is NOT exposed, only rollback/sim/analysis legs are.
- **Severity**:
  1. Production safety: PARTIAL — FALSE on the default path; TRUE-but-latent for `RQ_DAILY_RUNNER=umbrella` rollback mode specifically (if invoked in an emergency, it silently reads a diverged, missing-keys config — a landmine precisely when the operator is already in an incident).
  2. Deployability: FALSE.
  3. Correctness/drift: TRUE — 90+ config snapshots with no manifest reference back to a pinned version; classic two-copies-diverge risk, worse than the original "10+" count suggested.
  4. Asset-class blocker: FALSE.
  - **P2** (production-safety only partial/latent-on-a-non-default-path, not true on the active path — does not clear P0; correctness/drift is true but the active default runtime path is unaffected, so P1's "AND path=ACTIVE RUNTIME PATH" isn't met for the default path — the rollback-mode risk is real but conditional, hence P2 with an explicit callout rather than P1).
- **Fact vs. hypothesis**:
  Observed: default daily-full path resolves the pinned config; rollback/sim/analysis legs read the stale umbrella copy; the umbrella copy is missing several keys present in the pinned config.
  Proposed remediation (NOT a decided architecture): sim/analysis entrypoints should resolve the pinned config by default (matching daily-bridge); the umbrella working copy should be deleted or explicitly demoted/labeled experiment-only so rollback mode isn't silently exposed to stale policy; the 90+ snapshot sprawl should be archived to a clearly non-default location. Byte counts (47,880/57,835) not independently re-verified in this pass — cited from the cross-referenced audit; flagged as a minor gap since strategy config changes frequently.

---

### V-016: base-data has verbatim-copied pipeline feature code — parity test already exists, downgraded from the original framing

- **Audited commit**: renquant-base-data@29a3e3f375
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-base-data show origin/main:src/renquant_base_data/alpha158_ops.py | grep -n "Moved verbatim"`; `git -C renquant-base-data show origin/main:src/renquant_base_data/alpha158_qlib_panel.py | sed -n '1,30p'`; `git -C renquant-base-data show origin/main:tests/test_alpha158_ops.py | grep -n "identity"`
- **Matched evidence**: `src/renquant_base_data/alpha158_ops.py:204,306` still carry "Moved verbatim from..." comments (exact match). BUT `alpha158_qlib_panel.py:22-24`: "Feature operators live in the ONE shared train/serve module (campaign B8). The serve side (renquant_pipeline .../alpha158_features.py) imports the SAME objects; tests/test_alpha158_ops.py pins the identity." `tests/test_alpha158_ops.py:86` `def test_panel_builder_uses_shared_ops_by_identity():` exists.
- **Path classification**: ACTIVE RUNTIME PATH (`alpha158_qlib_panel.py` builds the production feature panel), now covered by a mechanical identity test (TEST-ENFORCED, not just documentation).
- **Disposition**: PARTIALLY RESOLVED / RECHARACTERIZED, not STILL PRESENT as originally framed. The original "Moved verbatim" copy (base-data copied code rather than importing from a shared location) is real and unchanged; but since that copy, `renquant_pipeline`'s serve-side module now imports base-data's copy directly as the SAME Python objects (not a re-implementation), and `test_panel_builder_uses_shared_ops_by_identity` mechanically pins this — the "can drift silently" risk the original doc worried about is largely closed, just via "one side imports the other's objects directly + a pinned identity test" rather than "extract to common."
- **Severity**:
  1. Production safety: FALSE — the identity test would fail loudly (CI) on drift, not silently corrupt a live decision.
  2. Deployability: FALSE.
  3. Correctness/drift: PARTIAL — the underlying ownership shape (base-data's copy is canonical; pipeline imports FROM it, rather than both importing from a neutral common location) remains slightly unusual, but is mechanically drift-tested today.
  4. Asset-class blocker: FALSE.
  - **P2** (hygiene/ownership-shape observation; the drift risk that would have justified P1 is mechanically mitigated).
- **Fact vs. hypothesis**:
  Observed: base-data owns the canonical `alpha158_ops` implementation; pipeline's serve-side imports the SAME objects; a same-identity pytest exists (not independently confirmed wired into a CI workflow file in this pass — flagged as a gap).
  Proposed remediation (NOT a decided architecture): may not need remediation beyond documentation — the "Moved verbatim" comment now reads as if a copy risk still exists and could be updated to describe the current shared-identity arrangement. Extracting to `renquant-common` remains an option if a cleaner ownership shape is wanted, but current evidence doesn't support the urgency the original doc implied.

---

### V-018: No CI lint for cross-repo import boundaries — partially stale, a working template already exists in renquant-model

- **Audited commit**: renquant-orchestrator@536cb91070; renquant-pipeline@b465000bf0; renquant-execution@59ae2ddc6b; renquant-model@62286996ea
- **Verification date**: 2026-07-12
- **Command**: `git -C <repo> ls-tree -r origin/main --name-only | grep -i "boundary\|import_lint\|forbidden_import"` run against orchestrator, pipeline, execution, common, base-data, strategy-104, model, backtesting; `git -C renquant-model show origin/main:tests/gbdt/test_import_boundaries.py`
- **Matched evidence**: orchestrator, pipeline, execution, common, base-data, strategy-104, backtesting have NO matching file (matches the original claim for those repos). `renquant-model` DOES have `tests/gbdt/test_import_boundaries.py` and `tests/patchtst/test_import_boundaries.py` — e.g. `test_model_gbdt_root_import_does_not_pull_execution_runtime()` imports `renquant_model_gbdt` then asserts none of `sys.modules` starts with `("alpaca","backtesting","ib_insync","kernel","live","renquant_execution")`.
- **Path classification**: TEST-ONLY PATH (correct classification for a CI lint by design — confirming this is a real test mechanism, not dead code or documentation).
- **Disposition**: STALE-CLAIM, PARTIALLY — the original blanket "No repo has a test or CI check that enforces import boundaries" is factually wrong as written: `renquant-model` has exactly this, for two family boundaries (gbdt, patchtst), just not for the repos that carry this audit's LIVE violations (orchestrator↛pipeline.kernel per V-005, pipeline↛orchestrator per V-003). RESOLVED for "does the pattern exist anywhere," STILL PRESENT for "does it exist where it's actually needed" — the more important question, and a real remaining gap.
- **Severity**:
  1. Production safety: FALSE — a missing lint doesn't itself misprice anything; a governance gap that lets other violations go undetected.
  2. Deployability: FALSE.
  3. Correctness/drift: TRUE — without this, V-003/V-005-class violations can be reintroduced or worsen with no CI signal (renquant-model proves the mechanism is cheap and already viable in this codebase).
  4. Asset-class blocker: FALSE.
  - **P2** (correctness/drift=true but path is TEST-ONLY, not ACTIVE RUNTIME PATH — a preventive/governance gap, not itself an active violation).
- **Fact vs. hypothesis**:
  Observed: a working, cheap, already-proven-in-this-codebase template exists (`renquant-model/tests/*/test_import_boundaries.py`) and is not applied to orchestrator, pipeline, or execution — the three repos where this audit found live reversed/internal-API import violations (V-003, V-005, and the now-resolved V-017).
  Proposed remediation (NOT a decided architecture): port the `renquant-model` pattern to orchestrator (forbid `renquant_pipeline.kernel`), pipeline (forbid `renquant_orchestrator`), and execution (forbid `renquant_pipeline.kernel`/private pipeline modules generally, now that the public `software_stops` contract exists per V-017/R-003) as three small, independent PRs — the same sys.modules-prefix-assertion technique renquant-model already uses, not a new design.

---

## NOT A VIOLATION — reclassified on investigation

### V-009: Execution TIF hardcoded to DAY for equities — NOT A VIOLATION

- **Audited commit**: renquant-execution@59ae2ddc6b
- **Verification date**: 2026-07-12
- **Command**: `git grep -n "TIF=DAY only\|_crypto_tif_enum\|def place_order\|def place_stop_order" origin/main -- src/renquant_execution/alpaca_broker.py`; manual trace of `place_order()` control flow
- **Matched evidence**: `src/renquant_execution/alpaca_broker.py:272` `def place_order(self, symbol, action, quantity, *, time_in_force=None, asset_class=None)`. Inside, at `:293-299`:
  ```python
  if classify_asset_class(symbol, asset_class) == ASSET_CLASS_CRYPTO:
      return self._place_crypto_market_order(
          symbol=symbol, action=action_u, requested_qty=requested_qty,
          time_in_force=time_in_force,
      )
  if time_in_force is not None and str(time_in_force).strip().lower() != "day":
      raise ValueError(f"equity place_order is TIF=DAY only, got {time_in_force!r} for {symbol}")
  ```
  The crypto branch RETURNS IMMEDIATELY — the DAY-only hard-reject on the line right below is textually unreachable for any order classified as crypto. `_place_crypto_market_order` (containing `_crypto_tif_enum(tif)`, confirmed at `:483`) is a fully separate method with its own increment-snapping, min-order-size, and no-short checks; it never calls or falls through to `place_order`'s equity branch. Code comment at `:290-296`: "Asset-class seam (crypto RFC §3.2 E1/E2)... The equity path is TIF=DAY by construction — a caller-supplied non-DAY TIF on an equity order is a wiring error and fails loud, never silently remapped."
- **Path classification**: ACTIVE RUNTIME PATH — `place_order` is the live order-submission entry point for both asset classes.
- **Disposition**: STALE-CLAIM — the original finding characterized this as an architecture violation ("equity and crypto code paths share no TIF abstraction"), but tracing the actual call graph shows the opposite: `place_order` is a clean dispatcher with two genuinely isolated branches sharing nothing but the outer method signature. No shared internal function that both paths funnel through exists, so there's nothing a future equity-GTC need would have to "rework" — crypto already has its own private submission method.
- **Severity**: **NOT A VIOLATION — architecturally correct, isolated equity-specific contract.** Per Codex's explicit hint on this item, this is exactly that case: the DAY-only rejection is a deliberate equity invariant, unreachable from the crypto path by construction (early-return dispatch, not discipline/convention). All 4 axes false/not-applicable: no production-safety risk (isolation is real), no deployability impact, no drift risk (nothing duplicated — genuinely different order semantics), no crypto blocker (crypto has GTC/IOC via its own `_crypto_tif_enum` branch already).
- **Fact vs. hypothesis**:
  Observed: `place_order()` dispatches on `classify_asset_class()` before either TIF-handling branch is reached; the equity DAY-only hard-reject is unreachable from the crypto branch.
  Proposed remediation: none — no change needed. If a future equity GTC need arises (e.g. protective stops, which already use GTC via `place_stop_order`), it should be added as its own explicit branch/method following the same isolation pattern, not by loosening the shared `place_order` DAY-only check.

---

### V-019: Annualization factor 252 hardcoded — NOT A VIOLATION at both originally-cited sites (already resolved 2026-07-10)

- **Audited commit**: renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-pipeline show origin/main:src/renquant_pipeline/kernel/vol_target.py | grep -n "252\|annualization"`; `git -C renquant-pipeline show origin/main:src/renquant_pipeline/kernel/portfolio_qp/tasks.py | grep -n "252\|TRADING_DAYS_PER_YEAR\|annualization"`
- **Matched evidence**: `kernel/vol_target.py`'s `compute_vol_target_scale(...)` still has `annualization_days: float = 252.0` as a DEFAULT parameter (not a hardcoded constant with no override — different from the original "hardcoded" framing). `kernel/portfolio_qp/tasks.py:477` still has `TRADING_DAYS_PER_YEAR = 252.0  # equity; crypto resolves 365 via asset_class` — BUT at `:491` and `:1290`, the actual production call sites do `from renquant_pipeline.kernel.asset_class import annualization_days_for` and pass `annualization_days=annualization_days_for(_ctx_asset_class(ctx))` — the module-level `TRADING_DAYS_PER_YEAR` constant is NOT what's used at either flagged call site; it's shadowed by an asset-class-aware resolution. Both sites cite "crypto RFC 2026-07-10 P4" — this wiring landed 2026-07-10, two days before this audit's nominal date, meaning the original 4-agent audit (also dated 2026-07-12) should have caught this and did not.
- **Path classification**: ACTIVE RUNTIME PATH — `portfolio_qp/tasks.py` is the live QP sizing task.
- **Disposition**: RESOLVED at the two specifically-cited call sites (both asset-class-aware via `annualization_days_for`); the original doc's "Impact: Low... Crypto config will pass 365" undersold how far this had already progressed by the audit's own stated date — it already resolves 365 automatically, no explicit config pass required. Not exhaustively swept for other bare-`252` occurrences elsewhere in pipeline beyond the two originally-cited sites — this disposition is scoped to those two only.
- **Severity**: **NOT A VIOLATION at the two originally-cited sites** — architecturally correct: sensible equity-default parameters with an asset-class-aware override applied at the real call sites. All 4 axes false/moot: production safety false (already resolved), deployability false, correctness/drift false (default fallback provably not what production uses), asset-class blocker false (real call sites already override it). Residual P2-hygiene note: the unused-in-practice `252.0` defaults could mislead a future direct caller who doesn't realize they must pass `annualization_days_for(...)` explicitly — a documentation/API-ergonomics nit, not a violation.
- **Fact vs. hypothesis**:
  Observed: both flagged call sites already resolve the annualization factor per asset class as of a 2026-07-10 change; raw `252.0` values remain only as defaults, not what live code executes.
  Proposed remediation (optional polish, not a decided architecture, likely unnecessary): could change the default parameters to require an explicit `annualization_days` argument (no default) to make "must supply an asset-class-aware value" a call-time requirement — optional, not a live risk.

---

## Resolved violations (re-verified this round)

Quick-reference table (full per-entry evidence in the same structured format
as every other entry follows below the table):

| ID | Violation | One-line resolution | Verified |
|---|---|---|---|
| V-007 | NYSE calendar hardcoded in pipeline exits | Asset-class dispatch wired at both the exits/streak clock and the actual live freshness gate; crypto RFC 2026-07-10 P1/P2 | renquant-pipeline@b465000bf0, 2026-07-12 |
| V-010 | Wash-sale engine is equity-only | §1091 bypassed for validated crypto pairs; crypto RFC 2026-07-10 P5 | renquant-pipeline@b465000bf0, 2026-07-12 |
| V-017 | Execution imports pipeline private API | pipeline#192 published public contract, execution#30 consumes it — merged ~4h before this revision | renquant-pipeline@b465000bf0, renquant-execution@59ae2ddc6b, 2026-07-12 |
| R-001 | Triple-implementation fingerprint | **CONTESTED** — canonical repos unified, umbrella still runs a 4th independent copy | see full entry |
| R-002 | asset_class concept missing | Landed and grown; per-site wiring now itemized in V-006/007/009/010/011/012/013 | see full entry |
| R-003 | Umbrella dependency in stops-liveness pager | Neutral runtime-state-root implemented, PR #481 merged; staged dark (not yet launchd-active) | renquant-orchestrator@536cb91070, 2026-07-12 |

---

### V-007: NYSE calendar hardcoded in pipeline exits — RESOLVED

- **Audited commit**: renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git show origin/main:src/renquant_pipeline/kernel/exits.py | grep -n "_is_nyse_trading_day\|def is_trading_day\|asset_class"`; `git show origin/main:src/renquant_pipeline/kernel/pipeline/task_data_freshness.py`; `git grep -n "TypedDataFreshnessGate" origin/main`
- **Matched evidence**:
  - `kernel/exits.py:79-89` `def is_trading_day(d, *, asset_class="us_equity")`: `if is_crypto(asset_class): return True`, else `return _is_nyse_trading_day(d)`. Comment: "crypto RFC 2026-07-10 P2." `_is_nyse_trading_day` (the originally-flagged function, still at `:54`) is now only the equity-branch implementation detail, not called unconditionally.
  - `kernel/exits.py:92-115` `trading_days_between(start, end, *, asset_class="us_equity")` similarly dispatches: crypto counts raw calendar days, equity delegates to `nyse_trading_days_between`.
  - Threading confirmed to real config, not just a default: `kernel/pipeline/task_sell.py:181` calls `check_model_sell(..., asset_class=resolve_asset_class(tc.config or {}))`; `kernel/pipeline/soft_exit_guards.py:47,112` thread `asset_class` further into `trading_days_between`/`trading_holding_days`.
  - **Correction to the original doc's second citation**: `kernel/typed_past/typed_data_freshness.py:32-83` (`TypedDataFreshnessGate`) has an `asset_class` param and correctly dispatches, but is **never instantiated anywhere in `src/`** (`git grep -n "TypedDataFreshnessGate(" origin/main -- src/` = no hits) — referenced only from `tests/test_asset_class_policy.py`. It is dead/unwired code, not the live gate. The actual production-active freshness gate is a different class the original doc didn't cite: `kernel/pipeline/task_data_freshness.py::DataFreshnessGateTask`, documented as "Wired into `InferencePipeline.run()` BEFORE `RegimeJob`" — it already does the identical asset-class dispatch (`resolve_asset_class(ctx.config)` → `is_crypto()` → `last_completed_always_open_session()` vs `_last_completed_nyse_close()`), comment-tagged "Crypto RFC 2026-07-10 P1."
- **Path classification**: ACTIVE RUNTIME PATH for `exits.py` (per-ticker sell/streak decisions) and for `task_data_freshness.py::DataFreshnessGateTask` (wired pre-`RegimeJob` in the live `InferencePipeline`). TEST-ONLY PATH for `typed_past/typed_data_freshness.py::TypedDataFreshnessGate` (the original doc's citation) — dead code, no production caller.
- **Disposition**: RESOLVED. Landed via crypto RFC 2026-07-10 P1/P2 wiring (2 days before this audit's nominal date) — the remediation the original doc proposed is already implemented and threaded from real per-ticker config in both the exits/streak path and the actual live data-freshness gate. The original doc's second citation pointed at unwired dead code rather than the real gate — a citation error independent of whether the underlying issue was fixed.
- **Severity**: Not applicable — resolved. If still open: axis 1 partial (stale-clock wrong-exit-timing) + axis 4 true (hard block on crypto exits) → would have been P1.
- **Fact vs. hypothesis**:
  Observed: both the per-ticker exit/streak clock and the production data-freshness gate are asset-class-aware; NYSE-only behavior is preserved byte-identically for `us_equity` (explicit design goal per comments), crypto handled via a real always-open-calendar path.
  Proposed remediation: none needed for the core finding. Housekeeping (not a decided architecture): delete `TypedDataFreshnessGate` or complete its cutover and retire `DataFreshnessGateTask` — two independently-maintained freshness gates, one live and one dead-but-tested, is itself a minor instance of the T3 duplicated-contract pattern (see the linked 2026-07-10 T1-T7 registry) and could drift if someone edits the wrong one.

---

### V-010: Wash-sale engine is equity-only — RESOLVED

- **Audited commit**: renquant-pipeline@b465000bf0
- **Verification date**: 2026-07-12
- **Command**: `git show origin/main:src/renquant_pipeline/kernel/pipeline/task_candidates.py` (full `WashSaleFilterTask`); `git show origin/main:src/renquant_pipeline/kernel/selection.py | grep -n "def is_wash_sale_blocked_with_cost" -A 40`
- **Matched evidence**: `kernel/pipeline/task_candidates.py:22-89` `WashSaleFilterTask.run()` now calls:
  ```python
  from renquant_pipeline.kernel.asset_class import (resolve_asset_class, resolve_validated_crypto_spot_pairs)
  ...
  blocked, reason, cost_npv = is_wash_sale_blocked_with_cost(
      ..., asset_class=resolve_asset_class(tc.config or {}),
      validated_crypto_pairs=resolve_validated_crypto_spot_pairs(tc.config or {}),
  )
  ```
  `kernel/selection.py:111-151` `is_wash_sale_blocked_with_cost(..., asset_class="us_equity", validated_crypto_pairs=None)` docstring: "If `asset_class="crypto"` → §1091 does NOT apply (crypto is PROPERTY, IRS Notice 2014-21)... never blocked, zero cost. Crypto RFC 2026-07-10 P5 — keyed per asset class, never a global disable; the `us_equity` default keeps the equity path byte-identical." The bypass additionally requires the ticker be an explicitly validated crypto spot pair (`resolve_validated_crypto_spot_pairs`/`wash_sale_applies_for_ticker`, "pipeline#183 P5 hardening") — `asset_class` alone is insufficient, a deliberate anti-spoofing hardening.
- **Path classification**: ACTIVE RUNTIME PATH — `WashSaleFilterTask` runs in the per-ticker candidate pre-screen stage of the live `InferencePipeline`.
- **Disposition**: RESOLVED — pipeline PR #183 (crypto RFC 2026-07-10 P5), landed 2 days before this audit's nominal date. Contradicts the original doc's "currently applies to everything uniformly" — that was already false when the 2026-07-12 registry was written.
- **Severity**: Not applicable — resolved. If still open: axis 4 true (hard block: a legitimate crypto re-entry after a loss would be wrongly denied) → would have been P1.
- **Fact vs. hypothesis**:
  Observed: the wash-sale gate is asset-class- and pair-validation-aware; equity behavior is explicitly preserved byte-identical.
  Proposed remediation: none needed.

---

### V-017 / R-003: Execution software_stops_liveness — RESOLVED (merged hours before this revision, exactly as Codex predicted)

- **Audited commit**: renquant-execution@59ae2ddc6b (PR #30, merged 2026-07-12T12:22:47Z); renquant-pipeline@b465000bf0 (PR #192, merged 2026-07-12T12:21:02Z); renquant-orchestrator@536cb91070 (PR #481, merged 2026-07-12T12:33:23Z)
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-execution grep -n "validate_software_stop_snapshot\|_pipeline_stops_api\|_validate_snapshot" origin/main`; `git -C renquant-pipeline grep -n "def validate_software_stop_snapshot" origin/main`; `git -C renquant-execution show origin/main:src/renquant_execution/software_stops_liveness.py | sed -n '130,165p'`; `gh pr view 192 --repo hallovorld/renquant-pipeline --json state,mergedAt,mergeCommit`; `gh pr view 30 --repo hallovorld/renquant-execution --json state,mergedAt,mergeCommit`; `gh pr view 481 --repo hallovorld/renquant-orchestrator --json state,mergedAt,mergeCommit`
- **Matched evidence**: `renquant-pipeline/src/renquant_pipeline/software_stops.py:206` now defines a PUBLIC `def validate_software_stop_snapshot(raw: Any) -> dict:` (top-level module, not under `kernel/`). `renquant-execution/src/renquant_execution/software_stops_liveness.py:145-158`'s `_pipeline_stops_api()` (an EXECUTION-repo-local private helper name — not a re-import of a pipeline-side private symbol) does:
  ```python
  from renquant_pipeline.software_stops import (  # noqa: PLC0415
      DEFAULT_REGISTRY_PATH,
      compute_staleness,
      registry_path_for,
      validate_software_stop_snapshot,
  )
  ```
  i.e. it imports the PUBLIC `validate_software_stop_snapshot` from the PUBLIC `renquant_pipeline.software_stops` module — not `renquant_pipeline.kernel.software_stops` and not a `_validate_snapshot` private name. The module's own docstring at `:36-37,92,140-141` explicitly documents this was fixed per Codex review on renquant-execution#30 (2026-07-12T11:57:53Z) and cross-references `renquant-pipeline#192`. `gh pr view` confirms both PRs MERGED today with merge commits matching current `origin/main` HEAD of each repo exactly. Separately, `renquant-orchestrator#481` ("software-stop liveness pager package, staged dark") also merged today (2026-07-12T12:33:23Z, merge commit = current orchestrator origin/main HEAD) and implements `software_stops_registry_contract.py`'s `runtime_state_root()` / `RENQUANT_RUNTIME_STATE_ROOT` neutral-runtime-state-root convention, matching R-003's original claim.
- **Path classification**: for the execution↔pipeline import itself: the code exists and is correct, but the pager it's part of is explicitly "staged dark" per the PR title. Traced: `scripts/install_stops_pager.sh` is an echo-first/dry-run-by-default installer requiring an explicit `--apply` (a separately-granted operator landing step per this project's "landing actions ask-first" convention) to actually bootstrap the launchd job; no `scripts/launchd/*.plist` for `com.renquant.stops-liveness` exists in the repo (only a `deploy/com.renquant.stops-liveness.plist` template the installer would copy). So: the CODE is correct and merged, but as of this verification it is NOT an active, launchd-scheduled runtime path — it is STAGED / MERGED-BUT-NOT-YET-DEPLOYED. This is a distinct classification from "ACTIVE RUNTIME PATH," "TEST-ONLY PATH," "HISTORICAL SHIM," or "DOCUMENTATION-ONLY" as literally defined by the methodology; recorded as **MERGED, NOT YET DEPLOYED (pre-active)** and flagged as a case the four-way taxonomy doesn't cleanly cover, per this project's own "deployed-but-dark is not done" convention — the import-boundary FIX is real and correct, but claiming full production-safety credit for it would overstate the current state.
- **Disposition**: RESOLVED — the exact import-boundary violation V-017 flagged (execution reaching into pipeline's private API) no longer exists; it now goes through pipeline's public contract, exactly as Codex's review predicted would happen once pipeline#192 and execution#30 merged. R-003 (umbrella dependency in stops-liveness pager) is independently RESOLVED — orchestrator#481 merged with the neutral runtime-state-root implementation as claimed. Merged into one entry per the coordinator's original instruction.
- **Severity**: not scored under the P0/P1/P2 rubric — RESOLVED items are not live violations. For historical reference, had V-017 still been present: production-safety FALSE / deployability FALSE / correctness-drift TRUE / asset-class-blocker FALSE → P2, consistent with the original doc's P2 placement — so even before resolution this was never a high-severity item under the new rubric.
- **Fact vs. hypothesis**:
  Observed: all three PRs (pipeline#192, execution#30, orchestrator#481) show `state: MERGED` via the GitHub API as of this verification, with merge commits byte-identical to each repo's current `origin/main` HEAD (i.e. not stale claims — they landed in the last few hours relative to this audit). The execution-side docstring self-documents the Codex-review chain that produced this fix.
  Proposed remediation (largely moot since resolved): the only open item is deployment, not architecture — the pager needs an explicit operator `--apply` landing step to go from "staged dark" to "actually monitoring." An operational decision (see "landing actions ask-first" convention), out of scope for this audit-only document.

---

### R-001: Triple-implementation fingerprint — RESOLVED in the pinned pipeline repo, CONTESTED for the umbrella's dual-home kernel copy

- **Audited commit**: renquant-common@f5cb6ab2cf; renquant-pipeline@b465000bf0; renquant-model@62286996ea; RenQuant@16062b7b85
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-common show origin/main:src/renquant_common/model_fingerprint.py | sed -n '1,20p'`; `git -C renquant-pipeline grep -n "from renquant_common.model_fingerprint" origin/main -- src/`; `git -C renquant-model grep -n "from renquant_common.model_fingerprint import model_content_sha256" origin/main -- src/`; `git -C RenQuant show origin/main:backtesting/renquant_104/kernel/panel_pipeline/panel_scorer.py | grep -n "def model_content_sha256"`
- **Matched evidence**: `renquant_common/model_fingerprint.py` defines schema-v1 `model_content_sha256` (`:471`), explicitly documenting the prior conflicting implementations it unifies (pipeline's SUBTRACTIVE denylist approach, model's ADDITIVE allowlist approach). `renquant-pipeline/src/renquant_pipeline/kernel/panel_pipeline/fingerprint_dispatch.py:65` imports FROM `renquant_common.model_fingerprint`. `renquant-model/src/renquant_model_gbdt/fit_calibrator_alpha158_fund.py:22` imports `model_content_sha256` directly from `renquant_common.model_fingerprint`. HOWEVER: `RenQuant/backtesting/renquant_104/kernel/panel_pipeline/panel_scorer.py:108` STILL defines its OWN local `def model_content_sha256(payload: dict[str, Any]) -> str:` — a third, independent, non-unified implementation, confirmed present today.
- **Path classification**: the pipeline-repo and model-repo call sites are ACTIVE RUNTIME PATH (per V-001's tracing, these are on the pinned-kernel-alias portion of the default daily-bridge path, and model's calibrator-fit is on the training chain). The umbrella's OWN copy at `panel_scorer.py:108` is ALSO an ACTIVE RUNTIME PATH per the umbrella's own 2026-07-10 audit (audit_A §"Duplication census": "stale local copy feeding the PRODUCTION calibrator fit + WF stamping" — i.e. this is not dead code, it's what sim/WF-gate/promote actually execute today, since those legs run the umbrella kernel wholesale rather than the pinned pipeline per the T1 finding referenced throughout this document).
- **Disposition**: CONTESTED — the original table entry ("Unified into `renquant-common.model_fingerprint` (PR #M6)") is TRUE for the canonical `renquant-pipeline`/`renquant-model` repos but FALSE for the umbrella's dual-home kernel copy, which is a live, independently-maintained fourth(-ish) copy still computing its own fingerprint value for the production calibrator fit and WF stamping. Marking this RESOLVED without qualification, as the original doc's table did, is inaccurate. This is not a new finding by me — it mirrors the umbrella's own 2026-07-10 audit finding (there tagged F-10, P0) — but the original V-doc's resolved-violations table did not carry this caveat forward, which is exactly the kind of staleness Codex flagged.
- **Severity** (scored for the STILL-UNRESOLVED umbrella-copy component, since the canonical-repo component is genuinely resolved and doesn't need scoring):
  1. Production safety: TRUE — this fingerprint feeds fail-closed no-trade gating (three prior fail-closed no-trade incidents traced to fingerprint disagreement per project history); a divergent umbrella-local implementation can reintroduce exactly that incident class on the sim/WF-gate/promote leg.
  2. Deployability: FALSE.
  3. Correctness/drift: TRUE — a fourth independent implementation of the same value, by definition.
  4. Asset-class blocker: FALSE.
  - **P0** (production safety=true AND path=ACTIVE RUNTIME PATH, for the umbrella-copy remainder specifically). This changes R-001 from the original doc's "resolved, no severity" to carrying a live P0 remainder — a meaningful correction.
- **Fact vs. hypothesis**:
  Observed: the pipeline/model/common triangle is unified; the umbrella's separate kernel copy is not, and per the umbrella's own recent audit it feeds the production calibrator fit and WF stamping — directly entangled with the T1 "the WF gate promotes models on code the live path does not execute" finding this document cross-references throughout.
  Proposed remediation (NOT a decided architecture): the same remediation shape as V-001/T1 generally — either delete the umbrella's local kernel copy and have sim/WF-gate/promote import the pinned pipeline module (the "kernel cutover" already sequenced as R2 in the umbrella's own synthesis roadmap), or, as an interim step, make the umbrella's local `model_content_sha256` a thin re-export of `renquant_common.model_fingerprint.model_content_sha256` rather than a re-implementation (much smaller diff, doesn't wait on the full kernel cutover, but doesn't fix the broader dual-home problem either).

---

### R-002: asset_class concept — landed and grown; wiring status now addressed per-site by V-006 through V-013

- **Audited commit**: renquant-pipeline@b465000bf0; renquant-common@f5cb6ab2cf; renquant-execution@59ae2ddc6b
- **Verification date**: 2026-07-12
- **Command**: `git -C renquant-pipeline show origin/main:src/renquant_pipeline/kernel/asset_class.py | grep -n "^def "`; `git -C renquant-common ls-tree -r origin/main --name-only | grep -i market_calendar`; `git -C renquant-execution ls-tree -r origin/main --name-only | grep -i crypto`
- **Matched evidence**: `renquant_pipeline/kernel/asset_class.py` exists and is substantially richer than the original doc credited — it now exports `resolve_asset_class`, `is_crypto`, `annualization_days_for`, `settlement_days_for`, `wash_sale_applies`, `wash_sale_applies_for_ticker`, `sigma_clip_bounds_for`, `resolve_validated_crypto_spot_pairs`, `is_validated_crypto_spot_pair`, `_require_always_open_calendar`, `last_completed_always_open_session`. Note: the original doc's specific citation of an `is_trading_day` function at `:82-89` does NOT match current code — no function of that name exists; this specific sub-citation was already stale/wrong when the original doc was written, or the function was renamed/removed since. `renquant_common/market_calendar.py` exists. `renquant_execution/crypto.py` exists.
- **Path classification**: DOCUMENTATION-ONLY for this entry itself (it's a meta-summary row, not a single code location) — the underlying functions' path classifications are covered per-violation in V-006 through V-013 (see that cluster's write-up for whether each is actually wired at its specific flagged call site).
- **Disposition**: RESOLVED for "does the abstraction exist" (yes, and it's grown since the original audit); STILL PRESENT for "is it wired everywhere" as a blanket claim — the precise per-site wiring status is now itemized in V-007/V-010 (resolved), V-009 (not a violation), V-006/V-011/V-012/V-013 (open, with precise per-site gaps) rather than asserted in aggregate here, per this document's general policy of separating facts from aggregated claims.
- **Severity**: not independently scored — this is a summary/pointer entry; severity lives with the specific V-XXX items that trace actual call sites.
- **Fact vs. hypothesis**:
  Observed: the asset_class abstraction has grown substantially (11 functions today vs. what the original doc implied) and includes purpose-built bypass functions for wash-sale, vol-clip bounds, annualization, and calendar concerns that directly correspond to V-007/V-010/V-011/V-012/V-013's flagged gaps.
  Proposed remediation (NOT a decided architecture): none needed at the abstraction-definition level; remaining work, if any, is per-call-site wiring, itemized in the linked V-items.

---

### R-003: Umbrella dependency in stops-liveness pager — RESOLVED (merged as part of the V-017 fix wave; see the combined V-017/R-003 entry above for full evidence)

- **Audited commit**: renquant-orchestrator@536cb91070 (PR #481, merged 2026-07-12T12:33:23Z)
- **Verification date**: 2026-07-12
- **Disposition**: RESOLVED, with the "staged dark" caveat documented in the V-017/R-003 combined entry above (code correct and merged; launchd activation is a separate, not-yet-taken operational step). Not re-detailed here to avoid duplicating the same evidence twice in one document.

---

## Migration sequencing (recommended priority, re-sequenced by the NEW severity scores)

### Phase 1 — P0: active production-safety risks (highest priority regardless of GOAL-2)
1. **V-001** (umbrella runner/adapters places every live order, unpinned) — prove parity, lift protective features (paper Z9-sim, agent_breaker G2) into execution first, cut dispatch over leg-by-leg.
2. **V-002** (daily_104.sh sole launchd target, undelegated policy) — cut launchd legs to the already-registered native jobs where a same-kernel-identity cutover is provable; see the umbrella's own T1/R1 finding for the specific hazard of a naive cutover.
3. **V-008** (WF gate has no cost model; net-of-cost primitive now exists and is unused by the gate) — wire `renquant_common.cost_model` into `preflight.py`/`gate.py`; this is now "wire it in," not "build it."
4. **V-014's tournament-retrain subset** (writes live buy-admission models weekly with acceptance gate auto-disabled) — re-enable/redesign the gate, sequenced with V-001/A5 rather than folded into general script cleanup.
5. **R-001's umbrella-copy remainder** (a 4th independent fingerprint implementation still feeds production calibrator fit + WF stamping) — same remediation shape as V-001: either delete the umbrella's local copy in favor of importing the pinned pipeline module, or make it a thin re-export of `renquant_common.model_fingerprint` as a smaller interim step.

### Phase 2 — P1: asset-class hard blocks (GOAL-2 critical path) and active-path drift/reverse-dependency risk
6. **V-013** (crypto fills/open-orders invisible to reconciliation — hard block, capability exists, 2 call sites need updating) — cheapest GOAL-2 fix in this document; pure call-site update.
7. **V-011's residual SPY-proxy defect** (portfolio vol-target scale asset-class-blind input, will silently mis-size on crypto sleeve go-live) — gate `vol_target.enabled` off for crypto by default until a proper proxy exists.
8. **V-003** (pipeline→orchestrator reverse import) — needs an ADR deciding Option A (move to common) vs. Option B (pipeline owns persistence) before any code change.
9. **V-006** (ALLOWED_BROKERS duplication, CI-guarded but still duplicated) — cheap: move to common or make one file a re-export of the other.
10. **V-005** (orchestrator→pipeline.kernel internal imports) — pipeline exposes a public surface; pair with V-018's CI-lint port.

### Phase 3 — P2: hygiene, non-default-path, or already-mechanically-mitigated
11. **V-018** (CI import-boundary lint missing where needed) — port renquant-model's proven `test_import_boundaries.py` pattern to orchestrator/pipeline/execution; cheap, directly closes the detection gap for V-003/V-005 recurrence.
12. **V-004** (orchestrator hardcodes 13 umbrella paths) — swap to `deployment_manifest.load_runtime_inventory()`, the pattern already proven in `deploy_pin.py`.
13. **V-015** (stale strategy_config copies — default path safe, rollback/sim legs exposed) — pin-resolve sim/analysis entrypoints by default; demote or delete the umbrella working copy.
14. **V-012** (fundamentals fail-open median imputation for crypto — data-quality, not a gate) — exclude fundamentals columns from the crypto feature set upstream, once a crypto model is close to shipping.
15. **V-016** (base-data verbatim-copy comment, but mechanically identity-tested) — documentation-only fix; update the stale "Moved verbatim" comment.
16. **V-014's bulk ~270-script remainder** — the original 4-bucket triage (active-production/research-archival/migrated-duplicate/dead-code), lowest urgency in this document.

### Not a violation — no remediation needed
- **V-009** (equity/crypto TIF genuinely isolated by construction).
- **V-019** (annualization factor already asset-class-aware at both cited call sites, resolved 2026-07-10).
