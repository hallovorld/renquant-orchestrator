# Deep Plan — Engineering & Architecture Uplift for RenQuant

**Status:** research/design — awaiting review (no code change)
**Companion to:** `2026-06-12-model-capability-roadmap.md` (#106). That doc
answers "what to do to the model"; this one answers the operator's harder
question: *our code quality and architecture need a researched, mature,
implementable uplift plan that survives challenge.*
**Method:** measured current state (not vibes) → incident-to-root-cause
mapping from THIS WEEK's production incidents → target architecture with
literature/industry backing → strangler-fig staged migration with effort and
risk per stage.

---

## 1. Current state, measured (2026-06-12)

| Metric | Value | Reading |
|---|---|---|
| `job_panel_scoring.py` | **3,476 LOC** | god-module: scoring + calibration + veto + telemetry + shadow in one file |
| umbrella `adapters/runner.py` | **2,958 LOC** | god-adapter: state load/save + broker sync + order emit + GC + wash-sale + reporting |
| `run_wf_gate.py` | 2,658 LOC | the promotion authority is a single script |
| `strategy_config.json` | 1,275 lines, **875 keys, 76 `_reason` prose keys** | configuration debt: schema-less; documentation lives inside production config; golden-file lockstep enforced by tests |
| renquant-pipeline | 188 files / 53k LOC | mid-migration: "functional-lift slice N" comments show an unfinished umbrella→kernel extraction |
| Tests | 498 (umbrella) + 91 (pipeline) files; **177 contain source-string-scan / read_text contract checks** | tests that grep the source pin wiring but can't catch behavior bugs; brittle to refactors — they actively tax the decomposition this plan needs |
| Adding ONE live_state field | **9 manual touch points** (measured: `protection_breaches`, PR #294) | schema-less dict state with hand-written round-trips |
| `buy_blocked = True` writers | **12 sites** across the kernel | the funnel pathology has no architectural owner |
| Typing | `HoldingState` = plain dataclass ("no imports by design"); **pydantic v2 already a dependency** in renquant-common but unused for state/config | the cure is already installed |
| Artifact lifecycle | 12+ `*.staging.json` / `weekly_*` / `rollback_*` filename conventions in `artifacts/prod/`; MLflow installed (6,239 runs) but **not** used as a registry | stage-by-filename instead of stage-by-registry |
| Operational state | `live_state.alpaca.json` is a **git-tracked file in the code repo working tree** | state/code commingling — directly caused an incident this week |

## 2. Incident → architectural root cause (one week of production evidence)

| Incident (all June 2026, all real) | Root cause | Target fix |
|---|---|---|
| `protection_breaches` cross-day persistence needed a 9-site mirror (#294) | schema-less dict state, hand round-trips | **S1: typed state schema** |
| Shadow scorer silently dead for a week (#114) | two artifact-path resolution authorities (primary vs shadow) | **S1: single ArtifactResolver** |
| Fundamentals 121 days stale (base-data #22) | dataset identity = file path; stale file shadowed fresh one | **S1: content-hash provenance** (already approved) |
| False-BEAR cascade → zero buys (#92) | 12 independent `buy_blocked` writers, OR-of-thresholds, no attribution requirement | **S2: GateRegistry + decision ledger** |
| MU force-sold by `max_hold` (#94/#27) | implicit fallback to *current*-regime value; entry anchor never stamped | **S1: fail-safe defaults in typed state** |
| "Merged ≠ deployed" + runtime-root drift (twice) | dual code-resolution (PYTHONPATH siblings ‖ pinned runtime) | **S3: single pinned runtime** |
| PatchTST had no WF-gate stamp at promotion | artifact metadata fragmented across mergeable sidecars; promotion contract not enforced at train time | **S3: MLflow registry stages** |
| Live-state accidentally reverted during a git sync | operational state lives in the code repo's working tree | **S3: state out of the repo** (DB-canonical exists; `live_state_snapshots` infra present but the local DB is empty) |

This table is the answer to "缺乏对当前情况的具体认知": every proposal below
traces to a production incident from the last seven days.

## 3. Literature & industry anchors (旁征博引, each load-bearing)

1. **Sculley et al. 2015, "Hidden Technical Debt in Machine Learning
   Systems" (NeurIPS)** — names our exact diseases: *pipeline jungles* (the
   task chains + 12 gate writers), *configuration debt* (875 keys, prose in
   config), *glue code* (runner.py), *undeclared consumers* (sidecar
   metadata read by preflight, gate, promotion). The uplift plan is
   structured as debt paydown, not a rewrite.
2. **Breck et al. 2017, "The ML Test Score" (Google)** — production-ML
   rubric. Self-score today: Data ~2/7 (no data versioning/tests beyond
   freshness gate), Model ~4/7 (WF gate is strong; no staleness-by-cutoff
   check until this week), Infra ~3/7 (no single registry, dual runtime),
   Monitoring ~4/7 (ntfy + shadow + drift warns). Target: ≥5/7 each after S3.
3. **Fowler, Strangler Fig / Branch-by-Abstraction** — the only migration
   style compatible with a live-money system: every stage ships behind the
   existing gates, old path kept until parity is proven. (The repo's own
   "functional-lift" slices already follow this instinct; we finish the job.)
4. **"Parse, don't validate" (King 2019)** — typed boundaries: state, config
   and artifacts get parsed into versioned pydantic models at the edge;
   interior code never touches raw dicts. Pydantic v2 is already a dependency.
5. **Qlib's PIT database & workflow recorder (Microsoft)** — the
   domain-standard answer to point-in-time correctness and experiment
   recording; our daily-pipeline + provenance proposals are a lightweight
   equivalent (content-hash manifest instead of a PIT DB — right-sized for
   one box).
6. **MLflow Model Registry** (already installed) — replaces the
   `staging-filename zoo` with explicit stages
   (**aliases** (champion / candidate / shadow) + immutable version tags + WF-verdict metadata (MLflow stages are deprecated per RFC mlflow#10336)) and stamped lineage; the WF gate
   becomes the only transition authority.
7. **Hypothesis (property-based testing)** — replaces a tranche of
   string-scan tests with executable invariants (examples in §5.3).
8. **cvxportfolio (Boyd et al.)** — reference for the portfolio layer's
   cost-aware objective (already cited in QP work; borrow costs land here in
   shorts Phase B).

## 4. Target architecture (delta-only; what changes, what stays)

**Stays (deliberately):** the pinned-subrepo operating model (it caught real
drift twice this week — operator skepticism about umbrella docs noted, but
the pin mechanism itself earned its keep); the WF gate as sole promotion
authority; the Task/Job pipeline shape; file-based artifacts on one box (no
cloud services added).

**Changes:**

```
                       ┌─ S1: TYPED EDGES ──────────────────────────┐
 live_state.json ───►  │ LiveStateV2 (pydantic, schema_version,     │
 (cache only)          │ single serializer, auto field round-trip)  │
 strategy_config ───►  │ StrategyConfig schema (descriptions replace│
                       │ _reason prose; semantic-diff replaces      │
                       │ golden lockstep)                           │
 artifacts ─────────►  │ ArtifactResolver (ONE authority,           │
                       │ strategy_dir-first, content-hash stamped)  │
                       └────────────────────────────────────────────┘
                       ┌─ S2: ONE DECISION CHOKE POINT ─────────────┐
 12 × buy_blocked ──►  │ GateRegistry: gates REGISTER verdicts      │
                       │ {gate, verdict, reason, inputs}; the       │
                       │ pipeline reads ONE aggregate; ledger row   │
                       │ per decision (extends ticker_daily_state)  │
 god files ─────────►  │ runner.py → state_store / broker_sync /    │
                       │ order_emit / reporting (<600 LOC each)     │
                       │ job_panel_scoring.py → score/ calibrate/   │
                       │ admit/ telemetry modules                   │
                       └────────────────────────────────────────────┘
                       ┌─ S3: SINGLE RUNTIME & LIFECYCLE ───────────┐
 PYTHONPATH siblings─► │ pinned .subrepo_runtime is the ONLY        │
                       │ execution path (preflight enforces today;  │
                       │ delete the fallback)                       │
 staging filenames ──► │ MLflow registry stages; WF gate = the only │
                       │ stage-transition caller                    │
 state in repo ──────► │ DB-canonical live state (infra exists);    │
                       │ JSON demoted to cache outside the repo     │
                       └────────────────────────────────────────────┘
```

## 5. Staged migration (strangler-fig; every stage independently shippable)

### S1 — Typed edges (1–2 weeks, highest value/risk ratio)
1. **LiveStateV2**: pydantic model + `schema_version` + ONE
   serialize/deserialize pair in the pipeline (umbrella adapter consumes it).
   Acceptance: adding a field = **1 line**, proven by porting
   `protection_breaches`; old JSON auto-migrates (missing → defaults);
   round-trip property test (hypothesis: `parse(serialize(s)) == s`).
2. **ArtifactResolver**: one function, strategy-dir-first, returns
   `(path, sha256, source)`; primary, shadow, calibrator, gate all call it.
   Acceptance: #114-class divergence becomes impossible by construction.
3. **Config schema**: pydantic `StrategyConfig` generated from current keys;
   `_reason` prose moves to field `description`s (rendered into a generated
   reference doc); golden-lockstep test replaced by schema validation +
   semantic diff. Acceptance: config typos fail at load, not mid-trade.
   Risk control: schema is *additive* first (warn-only), fail-closed after
   one clean week.

### S2 — One decision choke point + god-file decomposition (2–4 weeks)
4. **GateRegistry**: gates stop writing `buy_blocked` directly; they register
   `(gate_name, verdict, reason, inputs)`. The pipeline computes the
   aggregate; every decision writes a ledger row (extend the existing
   `ticker_daily_state`/decision-trace tables). Acceptance: this week's
   false-BEAR forensics — which took hours of log archaeology — becomes a
   single SQL query; funnel audits become continuous telemetry.
5. **Decompose `runner.py`** (state_store / broker_sync / order_emit /
   reporting) and **`job_panel_scoring.py`** (tasks already exist — move
   them to modules; no logic change). Each extraction: behavior-identical PR
   gated by the replay harness (one fixed historical day reproduced
   bit-identically before/after — the sim infra already supports this).
6. **Test ladder rebalance**: for each extraction, retire the string-scan
   contract tests covering it in favor of (a) typed-contract tests and
   (b) hypothesis invariants (e.g. *stops never widen intraday*, *Kelly
   weight ∈ [0, cap]*, *cover-only short exits*, *veto floor admits exactly
   top-q under ties*).

### S3 — Single runtime & artifact lifecycle (4–8 weeks, paced)
7. **Delete the PYTHONPATH sibling fallback**: `.subrepo_runtime` becomes the
   only execution path (the preflight already aligns it; the fallback is now
   pure drift risk). Acceptance: "merged ≠ deployed" class closed.
8. **MLflow Model Registry**: artifacts registered with lineage
   (dataset_sha256, config_fingerprint, pin digest, WF verdict); the WF gate
   is the only code path that transitions stages; the staging-filename zoo
   becomes append-only history. (MLflow already installed; zero new infra.)
9. **State out of the repo**: `live_state_snapshots` DB becomes canonical
   (the table exists; today's local DB is empty — wire the writes), JSON
   demoted to a cache under `data/state/` (outside git). Acceptance: a git
   operation can never again touch live trading state.

### Explicitly NOT doing (scope discipline, anticipating challenge)
- No microservices, no cloud migration, no Kubernetes — one box, one
  operator; the failure modes here are correctness, not scale.
- No rewrite of the Task/Job kernel — it is sound; it needs owners and edges.
- No new config language (Hydra etc.) — pydantic schema over the existing
  JSON is the minimum-motion fix.
- No mass test deletion — string-scan tests retire only as their subject
  gets a typed contract.

## 6. How this feeds model capability (closing the loop to #106)

- S1 provenance + typed config ⇒ every experiment comparable (the
  capability-boundary work was nearly invalidated twice by untracked
  pipeline drift).
- S3 registry + daily panel append ⇒ retrain cycle = 26 minutes true cost ⇒
  the quarterly freshness rail (measured 6–7 IC pts) becomes monthly-capable.
- S2 ledger ⇒ gate-level attribution telemetry ⇒ funnel regressions caught
  in days, not via operator anger.
- Grinold framing: none of this raises IC; all of it raises the **transfer
  coefficient** between IC and realized PnL — which this week proved is
  where the money was being lost.

## 7. Effort & sequencing summary

| Stage | Effort | Risk | Ships value alone? |
|---|---|---|---|
| S1 typed edges | ~1–2 wk | low (additive, warn-first) | yes — kills 3 incident classes |
| S2 choke point + decomposition | ~2–4 wk | medium (mitigated by replay-parity gating) | yes — forensics + funnel telemetry |
| S3 runtime + lifecycle + state | ~4–8 wk | medium (paced, one leg at a time) | yes — closes deploy-drift class |

All PRs small, reviewed, pin-flow deployed; experiments stay on the epic
branch; the WF gate and the operator remain the only promotion authorities.

## References
Sculley et al. (2015) *Hidden Technical Debt in ML Systems*, NeurIPS ·
Breck et al. (2017) *The ML Test Score*, IEEE BigData · Fowler, *Strangler
Fig Application* & *Branch by Abstraction* · King (2019) *Parse, Don't
Validate* · Microsoft **Qlib** (PIT data & recorder) · **MLflow Model
Registry** docs · **Hypothesis** property-based testing · Boyd et al.,
**cvxportfolio** · de Prado (2018) AFML (evaluation discipline) · plus the
eight internal incident reports of 2026-06 (cited in §2), which are the
primary sources of this plan.


---

# ERRATA, REPRODUCIBILITY & HARDENING APPENDIX (post-merge review — codex)

**A. Reproducibility of Part I.** Accepted: every census number must carry
its command + commit SHA. Corrected current values (codex recount,
2026-06-12): config = 1,230 lines / 841 recursive keys / 39 reason-keys
(earlier 1,275/875/76 was measured pre-cleanup with a broader `_`-prefix
count); `buy_blocked` assignment sites = **16** in canonical pipeline via
`rg 'ctx\.buy_blocked\s*=\s*True|setattr\(ctx, "buy_blocked", True\)'`
(12 was a narrower grep). Action: Part-I table gets a "command + SHA" column
in the next revision; metrics tracked by a CI census script, not by hand.

**B. MLflow lifecycle.** Stages wording replaced throughout with
alias/tag/version lifecycle (champion/candidate/shadow aliases; the WF gate
is the only alias-mover). Refs: MLflow registry docs; RFC mlflow#10336.

**C. GateRegistry verdict algebra (formal spec, required before extraction).**
- Verdict lattice: `allow < halve < block` (totally ordered).
- Aggregate per scope = **max** (join) over submitted verdicts ⇒ gates are
  **risk-monotone**: adding a gate can never increase permissiveness.
- `halve` composes multiplicatively with sizing (0.5^k for k halvers),
  applied BEFORE caps; `block` zeroes; risk-class exits are outside the
  lattice (they act on positions, not admissions).
- Determinism: aggregation order-independent (max + product are commutative).
- DDL: as §IV ledger. Property tests (hypothesis): (i) permissiveness
  monotone non-increasing in gate set; (ii) aggregate invariant under
  submission order; (iii) lint: zero direct `buy_blocked` writers
  (the 16 sites enumerated and migrated).

**D. LiveStateV2 acceptance matrix (replaces "1 line = done").** Adding a
field requires green on: v1→v2 migration tests (golden v1 fixtures),
unknown-field policy test (forbid + quarantine file, never silent drop),
rollback-read test (old code reading new state must not corrupt),
atomic write test (tmp+rename, crash-injection), DB-snapshot parity test
(JSON ⇄ `live_state_snapshots` round-trip), hypothesis round-trip.

**E. DB-canonical migration gate (blocker, not footnote).** Before JSON is
demoted: (1) full broker-isolated backfill of `live_state_snapshots`;
(2) restore-from-DB rehearsal on a copy; (3) JSON-vs-DB parity over ≥5 real
runs (diff = 0); (4) written rollback (JSON re-promotion) procedure.
