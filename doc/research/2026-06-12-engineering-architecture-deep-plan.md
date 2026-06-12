# RenQuant Engineering Uplift — System Design & Migration Program (v4)

**Status:** design program — awaiting review · **Supersedes:** the accreted
v1–v3 of this document (content preserved, reorganized) · **Scope:** the
operator's mandate — engineering that extracts the model's maximum; code
quality; architecture; pipeline soundness/concurrency; multi-repo version
control; bug discovery/prevention; DB/rollback/backup/secrets; full
umbrella retirement.

## Table of contents

- **Part I — Diagnosis (measured)**
  - I.1 System census · I.2 Daily-run performance profile
  - I.3 Incident → root-cause register (8 incidents, 7 days)
  - I.4 Maturity self-score (ML Test Score)
- **Part II — Principles & theory**
  - II.1 First principles: agent-native engineering, evidence velocity
  - II.2 Containment theory: six layers · II.3 Literature anchors
- **Part III — Target architecture (five planes)**
  - III.1 Overview · III.2 Data plane (PIT store, DB, backup)
  - III.3 Compute plane (feature store — the 88% fix)
  - III.4 Decision plane (GateRegistry, reconciliation, disaster guards)
  - III.5 Control plane (pins/Renovate, registry, config, secrets, umbrella retirement)
  - III.6 Observability plane (DRPH, ledger, audit sidecar)
- **Part IV — Quality doctrine**
  - IV.1 Task contracts & tiered validation · IV.2 DRPH specification
  - IV.3 Systematic bug hunt · IV.4 Build-vs-adopt policy
- **Part V — Execution program**
  - V.1 Sequencing (disaster guards first) · V.2 PR backlog with merge gates
  - V.3 Rollback matrix · V.4 Success metrics

---

# Part I — Diagnosis (measured, 2026-06-12)

## I.1 System census

| Metric | Value | Implication |
|---|---|---|
| Scripts in umbrella | **253 .py + 66 .sh**, 14 launchd plists, 595-line bash daily entrypoint | 300+ unmanaged pipelines: no contracts, lineage, retries, provenance |
| God modules | scoring 3,476 LOC · runner 2,958 · wf_gate 2,658 | change risk concentrated, untestable units |
| Config | 1,275 lines · 875 keys · 76 prose `_reason` keys | schema-less; docs inside prod config |
| Tests | 589 files; **177 grep-the-source style** | wiring pinned, behavior not |
| State | live_state git-tracked; 1 new field = **9 touch points** (measured, #294) | schema-less dict state |
| Gates | **12** independent `buy_blocked` writers | funnel pathology has no owner |
| Failure-prone patterns | **205** broad `except Exception` · **2,310** kernel dict `.get()` | the four patterns behind 8/8 incidents, at scale |
| Installed-but-unused cures | pydantic v2, MLflow (6,239 runs, no registry), sqlite snapshot table (empty) | adoption, not procurement |
| Env/secrets | shared mutable .venv; plaintext `.env` | irreproducible runs; one `git add -f` from disaster |

## I.2 Daily-run performance profile (live run 2026-06-11, 772 s total)

| Stage | Time | Share | Cause (file:line) |
|---|---|---|---|
| Feature build (`prepare_inference_panel_frames`, 142 names) | **680 s** | **88%** | GIL-bound pandas chain in ThreadPoolExecutor (`training_panel/pipeline.py:270,362`); process-wide `OMP_NUM_THREADS=1` set at import (`shadow_scoring.py:56`); cache key hashes `max_date`+`rows` ⇒ guaranteed daily MISS (`pipeline.py:132–155`); full-history recompute to append ONE bar |
| Scoring incl. Python sequence assembly | 56 s | 7% | per-day panel assembly in Python (3,408×24×172) |
| All else (regime, sell 0.11s, candidates 1.2s, QP, persist) | 36 s | 5% | healthy |

Control: the retrain path builds **292 names in 139 s** (0.48 s/name) on the
same box — the inference path is ~10× slower per name for a superset chain,
and the hot path is **unlifted umbrella glue** hand-mirroring the training
chain (4 documented historical parity bugs = Sculley training/serving skew).

## I.3 Incident → root-cause register (all June 2026, all production)

| # | Incident | Root cause | Fixed by |
|---|---|---|---|
| 1 | new state field needed 9-site hand mirror (#294) | schema-less dict state | III.4 LiveStateV2 |
| 2 | shadow scorer silently dead 7 days (#114) | two artifact-resolution authorities | III.5 ArtifactResolver |
| 3 | fundamentals 121 d stale (base-data #22) | dataset identity = file path; stale file shadowed fresh | III.2 PIT store |
| 4 | false-BEAR → zero buys (#92) | 12 uncoordinated gate writers; OR thresholds; no attribution | III.4 GateRegistry |
| 5 | MU force-sold by max_hold (#94/#27) | implicit current-regime fallback; anchor never stamped | IV.1 fail-safe contracts |
| 6 | merged ≠ deployed (×2) | dual code resolution (siblings ‖ pinned runtime) | III.5 single runtime |
| 7 | PatchTST promoted without WF stamp | metadata-by-sidecar; contract unenforced at train time | III.5 MLflow stages |
| 8 | live-state reverted by a git sync | operational state in the code repo working tree | III.2 state out of git |

## I.4 Maturity self-score (Breck et al., ML Test Score)

Data **2/7** · Model 4/7 · Infra **3/7** · Monitoring 4/7 → target ≥5/7 each
(deltas: PIT reader → Data; registry lineage → Infra; ledger → Monitoring).

---

# Part II — Principles & theory

## II.1 First principles
1. **Agent-native engineering.** This system is developed by AI agents
   (claude, codex) under one human operator. Optimal-architecture criteria
   shift: contracts must be machine-checkable (reviewers are AIs); debugging
   must be query-driven (ledger/replay — agents have no intuition); docs must
   be executable (prose drifts); every incident must auto-become a regression
   case (agents don't accumulate scar tissue — the system must).
2. **Evidence velocity is the north-star KPI.** The system exists to run
   validated experiments per week. Every investment below is justified by its
   effect on that number (e.g. the 88% fix turns one experiment/day into ten).
3. **Bound, don't promise.** No change is "safe"; it is contained (II.2).
4. **Fail closed at money; degrade gracefully at signal.**
5. **Mature libraries first** — hand-rolling restricted to domain glue with a
   written justification (IV.4).

## II.2 Containment theory: six independent layers
| Layer | Mechanism | Bounds |
|---|---|---|
| L1 | task contracts: declared reads/writes + tiered validation (IV.1) | blast radius of a change, by construction |
| L2 | DRPH byte-identity on golden corpus per PR (IV.2) | any behavior change, to 1 ulp |
| L3 | shadow periods (new path beside old, daily diff) | drift the corpus missed |
| L4 | flag-gated rollout + one-release rollback | production surprise → one flag flip |
| L5 | runtime invariant monitors from the ledger | slow-burn regressions |
| L6 | concurrent audit sidecar w/ order-barrier join (III.6) | data/runtime anomalies on UNCHANGED code |
A defect reaches money only by passing all six.

## II.3 Literature anchors (each load-bearing)
Sculley 2015 *Hidden Technical Debt* (names our diseases: pipeline jungles,
configuration debt, glue code, training/serving skew) · Breck 2017 *ML Test
Score* (the maturity rubric) · Fowler *Strangler Fig / Branch by Abstraction*
(the only migration style for a live-money system) · King 2019 *Parse, Don't
Validate* · Meyer *Design by Contract* · Qlib PIT design · MLflow registry ·
Hypothesis · Google SRE (canarying, error budgets) · Daniel–Moskowitz/
Drechsler etc. for the domain decisions referenced herein.

---

# Part III — Target architecture (five planes)

## III.1 Overview
```
DATA          COMPUTE          DECISION            CONTROL           OBSERVABILITY
PIT store --> feature DAG  --> gates/QP/orders --> pins+registry --> ledger/DRPH/audits
(ArcticDB/    (Hamilton,       (GateRegistry,      (Renovate,        (decision_ledger,
 manifests,    fstore,          reconciliation,     MLflow stages,    golden corpus,
 collectors)   tensors)         disaster guards)    config schema,    audit sidecar,
                                                    Keychain)         alert lifecycle)
Everything is a typed asset/job in ONE DAG (software-defined assets; Dagster
model; 2-day spike decides Dagster vs thin-local). Scripts (319) migrate by
strangler rule: new work MUST be an asset; old converts when touched.
```

## III.2 Data plane
- **PIT store:** per-source `manifest.jsonl` {date, rows, sha256,
  collected_at, publication_lag_days}; reader `pit_read(source, as_of)`
  enforces publication-lag joins — look-ahead becomes a type error. Storage:
  ArcticDB (native `as_of`) or parquet+manifest (1-day spike decides).
- **DB design:** sqlite kept (one box) + Alembic migrations (downgrade
  mandatory); table taxonomy: append-only EVENT tables (ledger, orders,
  audits — never UPDATE) / STATE snapshots (by run_id) / rebuildable
  ANALYTICS; WAL + busy_timeout (3 agents contend).
- **Backup:** restic, 3 tiers (per-run: state+DBs+pins; nightly:
  artifacts+registry+manifests; weekly: full data) to second disk + off-box;
  **monthly restore drill as a scheduled asset** — an unrestored backup is a
  hypothesis.
- **State out of git:** DB-canonical live state (snapshot table exists,
  unwired); JSON demoted to cache under `~/renquant-data/` (incident #8 class
  dies).

## III.3 Compute plane — the 88% fix
**Incremental content-addressed feature store** keyed
(ticker, feature_version, last_bar_date, inputs_sha): nightly event-driven
append computes ONLY new bars (max window 60 d ⇒ trailing-window recompute);
pre-assembles 24-bar scoring tensors; the SAME store feeds training and
inference (the mirrored umbrella chain and its symmetry-guard tests are
deleted — skew dies at the root). Bulk rebuilds: joblib/loky processes;
`OMP_NUM_THREADS=1` scoped to a torch context manager, not the process.
**Effect:** daily 13 min → **<90 s**; intraday full re-score **<30 s** (the
operator's 12-minute protection cadence becomes real); retrain data prep → 0.

## III.4 Decision plane
- **LiveStateV2 / HoldingStateV2** (pydantic, `extra="forbid"`,
  schema_version, ONE parse/serialize pair, hypothesis round-trip): a new
  field = 1 line; worked example = porting `protection_breaches` and deleting
  its 9 sites in the same PR.
- **GateRegistry:** tasks submit `GateVerdict(gate, scope,
  verdict∈{allow,block,halve}, reason, inputs)`; only the pipeline
  aggregates; lint bans direct `buy_blocked` writes. **Graded verdicts are
  the structural fix for binary funnels.** Every verdict → `decision_ledger`
  row (DDL in IV) — the false-BEAR autopsy becomes one SQL.
- **Broker reconciliation state machine:** MATCH / EXT_SELL (stamp wash-sale,
  GC) / EXT_BUY (quarantine) / QTY_DRIFT (adopt broker) / BUY_IN (hard-risk
  cover); broker = truth for positions, state = truth for intent; idempotent
  `client_order_id = sha1(run_id,ticker,intent,qty)` (Alpaca dedups) ⇒ crash
  cannot double-submit.
- **Disaster guards (self-discovered; FIRST in sequencing):**
  G1 broker-resident GTC catastrophe stops (−20%) per position, synced on
  rebalance — positions are protected even if this box is dead;
  G2 adapter-level agent breaker: hard daily order-count + notional caps +
  a manual `TRADING_OFF` file checked below ALL pipeline logic.
- Clock/calendar: one injected Clock + `exchange_calendars`; box runs PT,
  market is ET — DST weeks are a standing hazard today.

## III.5 Control plane
- **Multi-repo:** the lock file is hand-rolled git-submodules; adopt
  **Renovate** auto pin-bump PRs (native submodule/regex support);
  compatibility contracts as code (`requires: pipeline>=5b65f2a`) verified by
  an umbrella CI matrix (kills mis-paired-pin crashes); 1-day
  submodules-vs-lock spike; honest monorepo note if friction persists a
  quarter.
- **Umbrella retirement (operator directive):** umbrella content splits
  three ways — CODE migrates into subrepos riding the SAME refactors (runner
  → execution/pipeline via LiveStateV2+reconciliation; training_panel →
  pipeline via the feature store; wf_gate → pipeline; scripts → assets);
  DATA/STATE/LOGS leave git entirely (III.2); CONTROL PLANE (pins,
  preflight, scheduling) moves to renquant-orchestrator as the new root.
  Cutover gate: doctor green + golden corpus green on the new layout + one
  parallel shadow week with daily diff = 0 → operator decision. The umbrella
  is then frozen read-only as the rollback archive (`never_delete` honored),
  not deleted.
- **Artifact lifecycle:** MLflow registry stages None→Staging→Production→
  Archived with lineage (dataset_sha256, config_fingerprint, pin digest, WF
  verdict); **the WF gate is the only stage-transition caller**; the
  staging-filename zoo becomes history. Incident #7 class dies.
- **Config:** pydantic schema; `_reason` prose → field descriptions rendered
  to a generated reference doc; warn-only week then fail-closed.
- **Secrets:** macOS Keychain accessor replaces `.env`; gitleaks full-history
  audit on all 10 repos (rotate anything ever committed) + pre-commit/CI
  scans; paper/live key separation; quarterly rotation runbook; log-scrubber
  assertion in CI.
- **Environment:** uv + per-repo lockfiles; env hash joins the run
  fingerprint (today's fingerprint is incomplete without it).

## III.6 Observability plane
- **DRPH** (spec in IV.2) — replay, parity, forensics.
- **decision_ledger** (append-only):
  `(run_id, as_of, scope, gate, verdict, reason, inputs_json)`.
- **Audit sidecar (L6):** async audits run concurrently with downstream
  compute, **join-barrier before order emission**; INFO/WARN never block,
  CRITICAL blocks affected scope. Catalog v1 (each mapped to a real
  incident): independent regime-feed recheck (false-BEAR); staleness sweep
  (121-day class); PSI/KS score drift vs trailing 20-day baseline
  (calibrator saturation); shadow-liveness (#114); state⨝broker consistency
  (#8); gate-profile anomaly (funnels). **Alert lifecycle** (the missing
  discipline — the stale warning fired daily for 4 months, ignored):
  new → WARN → unacked N days → CRITICAL (blocks scope) → resolved; dedup by
  cause-hash; acknowledgement = operator command writing to the ledger.
- **P&L attribution (self-discovered gap):** every order carries
  decision_id; realized P&L written back on close ⇒ "what did rule X earn/
  lose historically" is a query, not an audit project.
- Dual-source data check: yfinance vs Alpaca market data divergence audit
  (production currently depends on an unofficial scraper API).

---

# Part IV — Quality doctrine

## IV.1 Task contracts & tiered validation
Every task declares IO and is validated — tiered so the hot path stays hot:
```python
@task_contract(
  reads={"candidates","config.ranking.panel_scoring"},
  writes={"candidates","counters.panel_vetoed"},          # guard-proxy enforced (CI/replay); no-op in prod
  pre=[finite_or_none("candidates[].rank_score")],         # T1: always-on, structural, µs
  post=[subset("candidates","pre.candidates")])            # contract lives on the data interface, defined once
class VetoWeakBuysTask(Task): ...
```
T1 always-on structural checks (presence/dtype/finite/monotone dates) —
fail ⇒ ContractViolation ledger row; T2 deep pydantic/pandera + hypothesis in
CI/replay/shadow only; prod samples outputs 1-in-N. **NaN policy fail-closed
by default** (the repo shipped two fail-OPEN NaN bugs: quality-floor Issues
23/24). Failure semantics by task class: risk → abort run (no-trade beats
wrong-trade); enrichment → degrade + `blocked_by=contract:<field>`;
persistence → never write a schema-failing state.

## IV.2 DRPH — Deterministic Replay & Parity Harness
Content-addressed `ReplayCase` = frozen inputs (panel slice, OHLCV, state,
config, artifact SHAs) + canonical `decisions.json` (run fingerprint incl.
env hash, gate verdicts, scores, orders, state-after hash). Broker mocked,
network banned (pytest-socket), Clock injected, torch deterministic, sorted
iterations. **Golden corpus v1:** 2026-06-11 false-BEAR day; a buy day; the
MU max_hold day; an earnings-veto day; a protection-exit day. CI: corpus
must pass; diffs require `behavior-change:` title + regenerated goldens.
~600–900 LOC of glue over existing sim/run-bundle infra (pytest-regressions/
syrupy for snapshots). Corpus growth rule: **every incident and every bug
found adds its day** — the regression suite is the incident history.

## IV.3 Systematic bug hunt ("the next 100 bugs")
Ordered by expected bugs/hour: (1) **historical differential replay** — DRPH
over the last 60 trading days vs what production actually did; every
mismatch is drift or a bug (method already proven: the unexplained
hand-vs-native scoring gap −0.0054 vs −0.0915 on identical inputs is bug #1,
queued); (2) hypothesis+pandera property campaign on money math (stops never
widen; Kelly∈[0,cap]; veto only removes; wash-sale blocks losses only;
calibrator monotone) across the 205 broad-except and 2,310 `.get()` sites;
(3) static baseline: ruff full set, mypy --strict (kernel, gradual),
vulture, bandit; (4) mutmut on the top-10 money modules — surviving mutants
mark where tests don't bite; (5) incident-class greps as ranked review
queues (decision paths first). **Prevention:** each incident class becomes a
custom lint (ban naked broad-except in kernel, dict-fallbacks outside
parsers, Path joins outside the resolver); mutation/typing coverage
ratchets; weekly differential replay on the rail.

## IV.4 Build-vs-adopt policy (binding)
pydantic/pydantic-settings (typing+config) · pandera (frame contracts) ·
deal/icontract (DbC) · hypothesis (properties) · pytest-regressions+syrupy+
pytest-socket (DRPH) · ArcticDB or parquet+manifest (PIT; 1-day spike) ·
Hamilton (feature DAG, column lineage) · joblib/loky (processes) ·
scipy KS+PSI now, evidently later (drift) · MLflow (registry) · Alembic
(migrations) · restic (backup) · macOS Keychain + gitleaks (secrets) ·
Renovate (pins) · exchange_calendars (clock) · uv (env) · Dagster spike
(orchestration). Hand-rolled = domain glue only, with a written
"no mature lib because…" in the PR.

---

# Part V — Execution program

## V.1 Sequencing
```
Week 0   G1 broker GTC catastrophe stops + G2 adapter breaker   (disaster class first)
Weeks 1-2  S1: LiveStateV2 → runner consumes it → DRPH + corpus → ArtifactResolver → config schema
Weeks 3-6  S2: GateRegistry+ledger → reconciliation SM → runner & scoring decomposition → fstore A–E
Weeks 7-12 S3: MLflow stages → Renovate/pins → state out of git → secrets/backup/env → umbrella cutover shadow week → retirement decision
Continuous: bug hunt (IV.3), audit sidecar build-out, script→asset strangler
```

## V.2 PR backlog (each small, flagged, replay-gated)
G1 broker GTC sync (~120 LOC) · G2 adapter caps + TRADING_OFF (~100) ·
PR1 LiveStateV2 (+400, property tests) · PR2 runner consumes it, deletes 9
sites (−250/+60, replay=0) · PR3 DRPH (+700) · PR4 golden corpus + CI
(+300) · PR5 ArtifactResolver (+350, replay=0) · PR6 config schema (+500,
warn→fail) · PR7 GateRegistry+ledger (+600, aggregate-identical) · PR8
reconciliation SM (+300) · PR9 runner split step 1 (replay=0) · PR10 scoring
split step 1 (replay=0) · fstore A–E (golden parity, shadow week, flag flip,
tensor pre-assembly, delete umbrella chain) · PR11–15 S3 items.

## V.3 Rollback matrix
Code=pins+revert-PR (proven #102) · Model=MLflow stage demotion (1 call) ·
Config=git revert+schema · Data=manifest-pinned reads, tombstones never
deletes · State=run_id snapshot restore (#144 path) · Schema=Alembic
downgrade (mandatory) · Every behavior swap=flag flip.

## V.4 Success metrics (reviewed bi-weekly)
1. **Evidence velocity: validated experiments/week** (north star).
2. Daily run wall-clock: 772 s → <90 s; intraday re-score <30 s.
3. Census trend: 319 scripts → <50 domain glue; buy_blocked writers 12 → 1.
4. State-field touch points: 9 → 1. 5. ML Test Score ≥5/7 per pillar.
6. Bugs: found-by-system vs found-by-operator-anger ratio (target: 100% system).
7. Backup restore drill: monthly, green. 8. Secrets: gitleaks clean, .env deleted.

---

# Appendix — Incident register & census provenance
All Part-I numbers were measured on 2026-06-12 against the live tree (commands
preserved in session logs); incidents #1–#8 cite their PRs/audits inline. The
v1–v3 accreted sections this document supersedes remain in git history.
