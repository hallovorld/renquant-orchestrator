# Deep Plan v2 — Engineering & Architecture Uplift (concrete contracts edition)

**Status:** design — awaiting review (no code change)
**v2 vs v1:** v1 was correctly diagnosed by the operator as refactoring
hygiene, not system design. v2 keeps the measured diagnosis (§1–§2) and
replaces the prescription with **concrete artifacts**: a deterministic
replay/parity harness (the centerpiece), exact data contracts (pydantic
models, table DDL, function signatures), a broker-reconciliation state
machine, the PIT data-layer format, and a numbered first-ten-PRs plan with
rollback per stage.

---

## 1. Current state, measured (unchanged from v1)

| Metric | Value |
|---|---|
| `job_panel_scoring.py` / `runner.py` / `run_wf_gate.py` | 3,476 / 2,958 / 2,658 LOC |
| `strategy_config.json` | 1,275 lines; 875 keys; 76 `_reason` prose keys |
| Tests with source-string scans | 177 files |
| Touch points to add ONE live-state field | **9** (measured, PR #294) |
| `buy_blocked = True` writers | **12 sites** |
| State | `live_state.alpaca.json` git-tracked in the code repo |
| Already installed, unused for the purpose | pydantic v2 (state/config), MLflow (registry), sqlite (`live_state_snapshots` table exists, local DB empty) |

## 2. Incident → root cause (8 production incidents, 7 days — unchanged from v1)

protection_breaches 9-site mirror → schema-less state · shadow dead a week →
two artifact resolvers · fundamentals 121d stale → identity-by-path data ·
false-BEAR zero-buys → 12 uncoordinated gate writers · MU max_hold →
implicit current-regime fallback · merged≠deployed ×2 → dual runtime ·
PatchTST unstamped at promotion → metadata-by-sidecar · live-state git revert
→ state/code commingling.


---

## 0. THE bottleneck, profiled — and the redesign that maximizes model effectiveness

> Operator directive: solve ONE thing deeply — engineering that extracts the
> model's maximum. This section is that thing. Everything below is measured
> from the 2026-06-11 live run and read from the code, with file:line cites.

### 0.1 Measured profile of the daily full (2026-06-11, 14:05:11→14:18:03)

| Stage | Time | Share |
|---|---|---|
| **`prepare_inference_panel_frames` (feature build, 142 tickers)** | **680 s** | **88%** |
| PatchTST scoring incl. per-day sequence-panel assembly (3,408×24×172) | 56 s | 7% |
| Everything else (regime, sell job 0.11s, candidates 1.2s, QP, persist) | 36 s | 5% |

Same machine, same day, the **retrain** path built features for **292
tickers in 139 s** (0.48 s/ticker) — the inference path runs **~10× slower
per ticker** (4.8 s/t) for a superset chain.

### 0.2 Root causes (file:line, all verified today)

1. **Fake parallelism.** The per-ticker chain (13 task invocations: alpha158
   + hourly + minute + macro/FRED β + embeddings + neutralization) runs in a
   `ThreadPoolExecutor` (`training_panel/pipeline.py:270,362`) — GIL-bound
   pandas in threads ≈ serial execution with lock overhead.
2. **Process-wide BLAS lockdown.** `shadow_scoring.py:56` sets
   `OMP_NUM_THREADS=1` **at import time for the whole daily process**
   (imported unconditionally by `job_panel_scoring`) — every numpy matmul in
   the entire run is single-threaded because one shadow task once needed it.
3. **A cache that can never hit day-over-day.** `_inference_frame_cache_key`
   hashes per-ticker `rows` + `max_date` (`training_panel/pipeline.py:132-155`)
   → any new trading day guarantees a MISS (verified: today was `cache WRITE`,
   no HIT). The cache only accelerates same-day re-runs.
4. **Recompute-the-decade-to-add-one-bar.** Features are deterministic
   functions of OHLCV history, yet each day rebuilds every rolling window
   over the full history for all 142 names to append **one** new row.
5. **The hottest path is unlifted umbrella glue.** This 541-line module lives
   in `backtesting/renquant_104/training_panel/`, hand-mirroring the training
   chain with "symmetry guard" tests (`pipeline.py:300-326` comments document
   four past parity bugs) — the exact Sculley training/serving-skew pattern.

### 0.3 The redesign: an incremental, content-addressed feature store

```
nightly (event-driven, after OHLCV/news/fundamentals land):
  for each ticker:
    fstore append: compute features for NEW bars only
      (max rolling window = 60d ⇒ recompute needs only the trailing window)
    key: (ticker, feature_version, last_bar_date, input_sha)
  build sequence tensors for the scorer (24-bar windows, float32, memmap)
  → artifacts: data/fstore/<ticker>.parquet + tensors/<date>.pt + manifest

daily run (and any intraday re-score):
  load tensors → torch forward on MPS → gates/QP → orders
```

- **Train/inference unification:** the SAME store feeds the training-panel
  builder and live inference — the hand-mirrored chain and its symmetry-guard
  test class are deleted, killing the skew pattern at the root (this also
  collapses the "panel rebuild = hours" cost item from the capability
  roadmap to zero — retrains read the store).
- **Parallelism:** bulk rebuilds (version bumps) use `ProcessPoolExecutor`;
  the nightly append is so small it needs none. Scope `OMP_NUM_THREADS=1`
  to the torch scoring context only (a context manager, not a process env).
- **Cache key fixed by design:** content-addressing per (ticker, version,
  inputs_sha) means a new day APPENDS instead of invalidating.
- **Scoring path:** pre-assembled sequence tensors remove the 56-s Python
  panel assembly; the forward pass itself is ~seconds on MPS.

### 0.4 Expected effect (and why this maximizes MODEL effectiveness)

| Metric | Today | After |
|---|---|---|
| Daily full wall-clock | ~13 min | **< 90 s** |
| Intraday full re-score | infeasible (13 min) | **< 30 s** → the operator's 12-minute model-protection cadence and short-side μ confirmation become REAL options |
| Decision-to-order latency before close | signal computed 13 min after trigger | ~1 min (less slippage vs the prices the model scored) |
| Retrain data prep ("hours" in the capability roadmap) | panel rebuild | **0** (reads the store) |
| Experiments per day (capability roadmap §1.1/1.2 sweeps) | bottlenecked by panel prep | bottlenecked only by 26-min training |

Grinold framing: this is pure **transfer-coefficient and breadth-of-
experiments** work — same IC, more of it reaching orders, and a 10×
faster research loop on the same box.

### 0.5 Implementation slice (replaces "PR 11-15 someday"; can start now)

| PR | Change | Gate |
|---|---|---|
| A | `fstore` module in renquant-pipeline (append/compute/read, content-addressed manifest, ProcessPool bulk builder) | unit + golden parity: store output ≡ today's `prepare_inference_panel_frames` output for 2026-06-11 (DRPH case) |
| B | nightly builder job on the existing launchd rail + staleness preflight integration | shadow week: store vs live chain diff = 0 daily |
| C | live path reads the store behind `inference_frame_cache.mode: "fstore"` (flag, default off) | replay diff = 0; then flip after clean week |
| D | sequence-tensor pre-assembly + scoped OMP context manager | scoring stage < 10 s measured |
| E | delete the umbrella chain + symmetry-guard tests (strangler completion) | corpus green |

Risk: feature drift between store and legacy chain → controlled by PR A's
golden parity requirement and PR B's shadow week, both mechanical via DRPH.

---

## 3. Centerpiece: the Deterministic Replay & Parity Harness (DRPH)

**Why this first:** every other change (god-file decomposition, gate
consolidation, typed state) is only safe if we can prove behavior identity.
And the same harness is the quant-specific capability the system lacks:
**bit-reproducible decision replay** = backtest/live parity measurement,
regression CI, and one-command incident forensics. This is the difference
between refactoring hygiene and a system you can change at speed.

### 3.1 Design

```
ReplayCase (frozen on disk, content-addressed):
  inputs/
    panel_slice.parquet      # features for D-seq_len..D
    ohlcv_slice.parquet      # prices incl. SPY
    live_state.json          # state snapshot at open of D
    strategy_config.json     # exact config
    artifacts.lock           # {name: sha256} for model/calibrator/gmm
  expected/
    decisions.json           # canonical output (below)

Canonical decision output (sorted keys, fixed float precision):
  {
    "run_fingerprint": {config_sha, panel_sha, state_sha, artifact_shas,
                        code_pin_digest},
    "regime": {...},
    "gates": [ {gate, scope, verdict, reason, inputs} ... ],   # §4.2
    "scores": {ticker: {raw, rank, mu, sigma}},
    "orders": [ {ticker, intent, qty, attribution} ... ],
    "state_after": "sha256 of canonical serialized LiveStateV2"
  }
```

- `replay run <case>` executes the full InferencePipeline against frozen
  inputs with the broker mocked (fills at frozen prices) and network banned
  (socket guard), then byte-compares `decisions.json`.
- **Determinism contract:** fixed seeds; torch deterministic mode; sorted
  iteration orders; wall-clock reads injected through one Clock object
  (`ctx.today` already exists — finish the job).
- **Golden-day corpus v1 (5 cases, all from real history):**
  1. 2026-06-11 false-BEAR day (cascade regression),
  2. a normal buy day (post-fix behavior),
  3. the MU `max_hold` day (exit-chain regression),
  4. an earnings-blackout veto day,
  5. a protection-exit firing day (validated μ path from the diag script).
- **CI rule:** every pipeline/umbrella PR runs the corpus. A diff fails CI
  unless the PR title carries `behavior-change:` AND regenerates goldens —
  behavior changes become *explicit review objects*, never side effects.
- **Effort:** the sim adapter already executes a day from frozen parquets
  and the run bundle already snapshots config/state; DRPH is ~600–900 LOC of
  glue + canonicalizer, not a new engine.

### 3.2 What it buys, concretely
- God-file decomposition (§6) becomes mechanical: extract → replay → diff 0.
- Live/backtest skew becomes measurable: feed yesterday's live inputs to the
  sim path and diff the decisions — the skew IS the diff (Sculley's
  training/serving skew, made visible).
- Forensics: this week's false-BEAR autopsy took ~3 hours of log
  archaeology; with DRPH + ledger it is `replay run 2026-06-11` + one SQL.

## 4. Exact contracts (the "parse, don't validate" edge)

### 4.1 `LiveStateV2` (renquant-pipeline `kernel/state.py`)

```python
class HoldingStateV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_price: float
    entry_date: date
    shares: float
    high_watermark: float | None = None
    sell_streak: int = 0
    protection_breaches: int = 0
    entry_regime: str | None = None     # max_hold anchor — stamped at entry
    entry_rank_score: float | None = None
    lots: list[TaxLot] = []

class LiveStateV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = 2
    as_of: date
    regime: str
    regime_confidence: float
    holdings: dict[str, HoldingStateV2] = {}
    book: BookState                     # hwm, last_sell_dates, stop orders…
    regime_state: RegimeStateV2

    @classmethod
    def parse(cls, raw: dict) -> "LiveStateV2": ...  # v1→v2 migration, ONE place
    def canonical_json(self) -> str: ...             # sorted keys, fixed precision
```

**The 9-site mirror dies:** the adapter does
`state = LiveStateV2.parse(json)` / `file.write(state.canonical_json())`.
A new field = one line in the model; round-trip guaranteed by the hypothesis
property `parse(canonical(s)) == s`. **Worked example:**
`protection_breaches` migrates first — its 9 hand-written sites in
`runner.py` are deleted in the same PR; the replay corpus proves identity.

### 4.2 `GateRegistry` (kills the 12 writers)

```python
class GateVerdict(NamedTuple):
    gate: str                  # "drawdown_breaker"
    scope: str                 # "book" | ticker
    verdict: Literal["allow", "block", "halve"]   # graded, not binary
    reason: str                # "dd=5.94% > halt=5%"
    inputs: dict[str, float]   # the numbers that decided

class GateRegistry:
    def submit(self, v: GateVerdict) -> None: ...
    def book_blocked(self) -> tuple[bool, list[GateVerdict]]: ...
    def ticker_blocked(self, t: str) -> tuple[bool, list[GateVerdict]]: ...
```

Pipeline rule, enforced by a lint test: **no task assigns
`ctx.buy_blocked`** — tasks submit verdicts; only the pipeline aggregates.
Graded verdicts ("halve") replace binary funnels — the architectural fix for
the funnel pathology, not merely its observation.

### 4.3 Decision ledger (forensics → SQL)

```sql
CREATE TABLE decision_ledger (
  run_id  TEXT, as_of DATE, scope TEXT,      -- 'book' or ticker
  gate    TEXT, verdict TEXT, reason TEXT,
  inputs_json TEXT,
  PRIMARY KEY (run_id, scope, gate)
);
-- The false-BEAR autopsy, afterwards:
-- SELECT gate, verdict, reason FROM decision_ledger
--  WHERE as_of='2026-06-11' AND scope='book';
```

Written by the GateRegistry aggregation step; lives in the existing sqlite
next to `ticker_daily_state` (same retention).

### 4.4 `ArtifactResolver` (kills resolver divergence)

```python
def resolve_artifact(ref: str, *, strategy_dir: Path, repo_root: Path,
                     expect_kind: str | None = None) -> ResolvedArtifact:
    """strategy_dir-first, repo_root fallback. Returns
    ResolvedArtifact(path, sha256, source, kind). Fail-closed if missing.
    EVERY artifact load (primary/shadow/calibrator/gmm/gate) calls this."""
```

A lint test bans `Path(...)` artifact construction outside this module. The
`sha256` flows into the run fingerprint (§3.1) and the registry (§7).

## 5. Broker reconciliation as a state machine (today: improvised warnings)

The runner currently improvises (`STATE-EXT-SELL: GE disappeared from
broker…`). Specify it:

```
expected(LiveStateV2) ⨝ broker.positions →
  MATCH           → ok
  EXT_SELL        → position gone: stamp wash-sale clock, GC state, ledger row
  EXT_BUY/UNKNOWN → position appeared: QUARANTINE ticker (no orders), alert
  QTY_DRIFT       → partial external fill: adopt broker qty, ledger row
  BUY_IN (short)  → forced cover: hard-risk exit semantics, ledger row

Invariants: broker is the source of truth for POSITIONS;
LiveStateV2 is the source of truth for INTENT/derived state
(streaks, anchors, clocks).

Idempotent orders: client_order_id = sha1(run_id, ticker, intent, qty)
  → a crash between submit and persist cannot double-submit
    (Alpaca deduplicates on client order id).
```

~300 LOC module + table-driven tests; replaces improvised runner code and
makes crash-recovery semantics explicit.

## 6. God-file decomposition — now mechanical

With DRPH (§3) + contracts (§4): extract `state_store` / `broker_sync` (§5)
/ `order_emit` / `reporting` from `runner.py`; move `job_panel_scoring.py`
tasks into `scoring/`, `calibration/`, `admission/`, `telemetry/` modules.
Every extraction PR: **zero replay diff required.** String-scan tests retire
only as their subject gains a typed contract (net test count never drops).

## 7. Artifact lifecycle: MLflow registry (installed, unused)

- Register every trained artifact with lineage params:
  `dataset_sha256, config_fingerprint, subrepos_pin_digest, wf_verdict`.
- Stages `None → Staging → Production → Archived`; **the WF gate is the only
  code path calling the transition API**; the daily run loads the
  Production stage through the resolver — the `*.staging.json` /
  `weekly_*` / `rollback_*` filename zoo becomes append-only history.
- The "PatchTST reached production without a WF stamp" class dies: an
  artifact cannot reach the Production stage without the gate writing its
  verdict into the registry.

## 8. PIT data layer (right-sized; no new infra)

```
data/pit/<source>/manifest.jsonl     # one row per append:
  {"date": "...", "rows": N, "sha256": "...", "collected_at": "...",
   "source_version": "...", "publication_lag_days": K}

Reader API:  pit_read(source, as_of) -> frame visible at as_of
             (enforces publication-lag joins — the FINRA/E5 rule generalized)
```

Nightly append per source (ohlcv / fundamentals / sentiment / IV /
short-interest / analyst). The panel builder consumes **only** `pit_read`,
making look-ahead a type error instead of a review-checklist item. (Qlib's
PIT idea reduced to one box and JSONL.)

## 9. First ten PRs (concrete, ordered; S1 ≈ PR1–6, S2 ≈ PR7–10)

| # | Repo | Change | ~LOC | Merge gate |
|---|---|---|---|---|
| 1 | pipeline | `kernel/state.py`: LiveStateV2 + parse/canonical + hypothesis round-trip | +400 | unit + property |
| 2 | umbrella | runner consumes LiveStateV2; **delete the 9 `protection_breaches` sites** (worked example) | −250/+60 | replay diff = 0 |
| 3 | pipeline | DRPH runner + canonicalizer + case format | +700 | self-test |
| 4 | umbrella | golden corpus v1 (5 cases incl. 2026-06-11) + CI wiring | +300 | corpus green |
| 5 | pipeline | ArtifactResolver + migrate primary/shadow/calibrator/gate loads + lint ban | +350 | replay diff = 0 |
| 6 | strategy | config pydantic schema (warn-only week 1 → fail-closed) + generated reference doc replacing `_reason` prose | +500 | schema CI |
| 7 | pipeline | GateRegistry + migrate 12 writers + lint ban + ledger DDL/writes | +600 | replay: aggregate unchanged, ledger new |
| 8 | umbrella | broker-reconciliation state machine + idempotent client_order_id | +300 | table-driven tests |
| 9 | umbrella | runner decomposition step 1: state_store + broker_sync | −800/+850 | replay diff = 0 |
| 10 | pipeline | job_panel_scoring decomposition step 1: scoring/ + admission/ | −1200/+1250 | replay diff = 0 |

S3 (registry stages, runtime-fallback deletion, state out of the repo)
follows as PRs 11–15 after two clean weeks.

**Rollback per stage:** S1 contracts are additive (legacy dict path kept one
release behind a flag); DRPH is dev/CI-only; GateRegistry runs a
`legacy_buy_blocked` shadow-compare for one week (log-only divergence
alarm); decomposition PRs are pure moves gated by replay-zero.

## 10. Non-goals & ML Test Score target

No microservices / cloud / k8s; no kernel rewrite; no new config language;
no mass test deletion. Breck self-score today: Data 2/7 · Model 4/7 ·
Infra 3/7 · Monitoring 4/7 → after S3: **≥5/7 each**, the deltas coming
specifically from the PIT reader (Data), registry lineage (Infra), and the
decision ledger (Monitoring).

## References
Sculley et al. 2015, *Hidden Technical Debt in ML Systems* (pipeline
jungles; configuration debt; training/serving skew) · Breck et al. 2017,
*The ML Test Score* · Fowler, *Strangler Fig* & *Branch by Abstraction* ·
King 2019, *Parse, Don't Validate* · Microsoft **Qlib** (PIT data,
recorder) · **MLflow Model Registry** · **Hypothesis** property-based
testing · Alpaca client-order-id idempotency · internal primary sources:
the 8 incident reports of 2026-06 (§2), the sim/run-bundle infra, the
`live_state_snapshots` schema.

## 11. Change-safety doctrine: containing problems at the task level

> Operator questions: how do we guarantee the migration introduces no new
> problems; how is blast radius contained at task level; does every task need
> input/output validation? Answers below are binding for every PR in §0.5/§9.

### 11.1 You don't "guarantee" — you bound. Five independent layers

| Layer | Mechanism | Catches |
|---|---|---|
| L1 task contract | declared IO + tiered validation (§11.2) | a task corrupting state outside its declared scope — **by construction** |
| L2 behavior identity | DRPH byte-diff on the golden corpus, required per PR | any decision change, even 1 ulp |
| L3 shadow period | new path runs alongside old, diff logged daily (fstore week, GateRegistry legacy-compare week) | drift the corpus didn't cover |
| L4 flagged rollout | every swap behind a config flag, default off; one-release rollback kept | production surprises — bounded to one flag flip |
| L5 runtime invariant monitors | ledger-derived anomaly checks (gate counts/day, score-distribution drift, state-field ranges) on the existing ntfy rail | slow-burn regressions after rollout |

A defect must pass ALL five to reach money. That is the honest engineering
answer to "如何确定" — probability × blast-radius engineering, not certainty.

### 11.2 Task-level containment: declared IO + tiered validation

Current reality: every task mutates a god-context (`Task.run(ctx)` may read/
write anything) — blast radius is unbounded, which is WHY this week's bugs
were pipeline-wide. The fix is a contract decorator, mechanical to adopt
task-by-task during the §6 decomposition:

```python
@task_contract(
    reads={"candidates", "config.ranking.panel_scoring"},
    writes={"candidates", "counters.panel_vetoed", "_blocked_by_ticker"},
    pre=[nonempty("candidates"), finite_or_none("candidates[].rank_score")],
    post=[subset("candidates", "pre.candidates"),       # a veto may only REMOVE
          ledger_reason_for_every_removed()],
)
class VetoWeakBuysTask(Task): ...
```

- **`reads`/`writes` enforcement**: in CI/replay mode the ctx is wrapped in a
  guard proxy — touching an undeclared field raises. In prod the proxy is a
  no-op (zero overhead). Blast radius is now a reviewable property of the
  diff: a PR that widens `writes` is visibly a bigger change.
- **Input validation — YES, every task, tiered:**
  - **T1 (always on, prod):** cheap structural preconditions — presence,
    dtype/shape, finiteness, date monotonicity. Microseconds. Failure ⇒
    structured `ContractViolation` ledger row + the task-class policy below.
  - **T2 (CI/replay/shadow only):** full pydantic deep-parse + hypothesis
    properties. Free where it runs; never in the intraday hot path.
- **Output validation — yes, but defined ONCE:** a task's postcondition IS
  the next task's precondition, so contracts live on the **data interface**
  (e.g. `Candidates`, `GateVerdicts`, `LiveStateV2`), not duplicated per
  task pair. The framework checks outputs in T2 mode and **samples** in prod
  (1-in-N runs full check) to catch drift without paying full cost daily.
- **NaN policy is part of the contract**, not ad-hoc: this repo has already
  shipped two fail-OPEN NaN bugs (quality-floor Issues 23/24: `NaN <= 0` is
  False ⇒ candidate passes). Contracts default **fail-closed**: a field
  declared `finite` that arrives NaN blocks that scope, with a ledger row.

### 11.3 Failure semantics by task class (what "contained" means)

| Task class | On contract violation |
|---|---|
| Risk/safety (stops, gates, reconciliation) | **abort the run** (no-trade beats wrong-trade) |
| Signal/enrichment (features, sentiment, shadow) | degrade: skip the enrichment, mark affected tickers `blocked_by=contract:<field>`, continue |
| Persistence (state write) | abort before write — never persist a state that failed its own schema |

### 11.4 Why this doesn't rot

- Contracts are executable (decorator), not prose — they fail CI when stale.
- DRPH corpus grows by rule: every production incident adds its day as a
  golden case (2026-06-11 is case #1) — the regression suite is the incident
  history.
- The ledger makes L5 monitors queries, not new infra.

References: Meyer, *Design by Contract* (preconditions/postconditions/
invariants); King, *Parse Don't Validate* (validate at edges, types inside);
Google SRE (canarying, error budgets); Hypothesis (property-based contracts);
internal: quality-floor NaN fail-open Issues 23/24 (2026-05-04 audit).

## 12. Concurrent audit sidecar (operator proposal — adopted as containment layer L6)

**Proposal:** self-auditing tasks judge upstream outputs while downstream
tasks run concurrently — early anomaly detection, early alarm.

**Adopted, with two design decisions that make it safe and effective:**

### 12.1 Concurrency with a money barrier
Audits run on a background executor (they are small-frame numpy — threads
fine) in parallel with downstream compute, BUT the pipeline **joins all
audits before order emission** (the one irreversible step). Post-§0 redesign
the whole run is <90 s, so a bounded audit budget (≤5 s at the barrier) is
free latency-wise. Verdicts: `INFO/WARN` never block; `CRITICAL` blocks
order emission for the affected scope (book or ticker) with a ledger row —
same fail-closed semantics as risk tasks (§11.3).

### 12.2 Audit catalog v1 (each mapped to a real incident it would catch)

| Audit (async, after stage) | Method | Would have caught |
|---|---|---|
| Input-recheck: regime feeds | independently recompute 5d/20d vol+ret from raw OHLCV; compare to detector inputs | feed corruption class; false-BEAR forensics instantly |
| Staleness sweep | max-date lag per source vs publication-lag budget | fundamentals 121d (it WARNED daily — see 12.3 for why it still failed) |
| Score-distribution drift | PSI/KS vs trailing 20-day baseline from score_db (already recorded) | calibrator saturation, silent model regressions |
| Shadow-liveness | shadow scores present & corr(primary,shadow) in band | shadow dead-for-a-week (#114) |
| Cross-field consistency | holdings ⨝ broker positions counts; state field ranges | live-state revert class |
| Gate-profile anomaly | today's gate verdict vector vs trailing distribution | funnel regressions (12 blocks where median is 2) |

Baselines come from tables we already write (`score_db`,
`ticker_daily_state`, ledger) — no new storage.

### 12.3 The lesson the existing warnings teach: escalation lifecycle
The system ALREADY had ad-hoc versions (CALIBRATOR-SATURATED,
`fundamentals feed STALE` — fired daily for ~4 months, ignored). Detection
without lifecycle = noise. Each audit alert carries state:
`new → ntfy WARN → unacknowledged N days → escalate to CRITICAL
(blocks orders for affected scope) → resolved`. Dedup by (audit, scope,
cause-hash) so a 121-day-old condition is ONE escalating incident, not 121
identical warnings. Acknowledgement = an operator command writing to the
ledger; thresholds and N per audit class live in config (schema-validated).

### 12.4 Interface

```python
class AuditTask(Protocol):
    stage: str                 # runs after this stage's output snapshot
    severity_policy: dict      # condition → INFO/WARN/CRITICAL
    def run(self, snapshot: StageSnapshot, baseline: Baseline) -> AuditVerdict
# Scheduler: submit on stage completion; join-all at order barrier;
# verdicts → decision_ledger (audit=True) + alert lifecycle table.
```

This is containment layer **L6** in the §11.1 stack: L1–L5 bound change
risk; L6 bounds **data/runtime risk on unchanged code** — the two failure
families this week actually exhibited.

## 13. Build-vs-adopt policy (operator directive: mature libs first, binding)

**Rule:** every component in this plan MUST adopt a maintained library/OSS
solution unless none fits three criteria: (a) actively maintained,
(b) battle-tested (major-org or wide adoption), (c) local-first (no server
to operate — one box, one operator). Hand-rolled code is restricted to thin
domain glue. PR review enforces: any hand-rolled component needs a one-line
"no mature lib because…" justification.

| Plan component | Adopt (mature) | Hand-roll remainder |
|---|---|---|
| State/config/typing (§4.1) | **pydantic v2** (already a dep) + **pydantic-settings** | field definitions only |
| DataFrame contracts T1/T2 (§11.2) | **pandera** (pydantic-style schemas for pandas, pytest integration) | our field lists |
| Property tests (§11.2) | **hypothesis** | invariant lambdas |
| Design-by-contract decorator (§11.2) | **deal** or **icontract** (pre/post/invariant decorators, maintained) | the reads/writes ctx-guard proxy (~100 LOC, no lib does god-ctx scoping) |
| Golden/snapshot diffing in DRPH (§3) | **pytest-regressions** / **syrupy** for canonical-JSON snapshots; **pytest-socket** for the network ban | the ReplayCase loader + canonicalizer (~200 LOC domain glue) |
| Feature store storage + PIT reads (§0.3, §8) | **ArcticDB** (Man Group, columnar versioned store with native `as_of` snapshots — PIT reads become a library call) — fallback plain parquet+manifest if its MPS/py3.10 fit disappoints in a 1-day spike | feature compute functions |
| Feature DAG / incremental pipeline (§0.3) | **Hamilton** (DAGWorks) — declarative pandas feature dataflow, per-column lineage, fits the alpha158 chain | column functions |
| Bulk parallelism (§0.3) | **joblib** (loky backend — solves the pickling pain that pushed the repo to threads) | none |
| Drift/distribution audits (§12) | **scipy.stats** KS + PSI (10 lines) now; **evidently** if reports wanted later | thresholds in config |
| Audit/alert lifecycle (§12.3) | **ntfy** (already) + sqlite state; consider **healthchecks.io**-style dead-man for the nightly jobs | the escalation state machine (~150 LOC; no local-first OSS does exactly this) |
| Artifact registry & lineage (§7) | **MLflow** registry (already installed) | the WF-gate transition caller |
| Decision ledger (§4.3) | **sqlite** (already); no ORM needed | DDL + writer |
| Idempotent orders (§5) | **Alpaca native client_order_id** dedup | the sha1 key derivation |
| Job orchestration (nightly rail) | keep **launchd** for S1–S2; evaluate **Dagster** in S3 (its asset freshness-policies + sensors natively solve the staleness-escalation problem) — explicit go/no-go after a 1-day spike, not a default adoption | cron plists |

Net effect on the ten-PR plan (§9): PR1 gains pandera/deal; PR3 gains
pytest-regressions/pytest-socket; fstore PR A starts with the ArcticDB
spike day; estimated hand-rolled LOC drops ~35% from the v2.1 estimates.

## 14. Multi-repo version control (measured pain → mature tooling)

This week's incidents: merged≠deployed ×2; lock pins lagging subrepo mains
by 99 commits; cross-repo coupled changes (pipeline #112 + strategy #25 +
umbrella pin) requiring hand-ordered PRs with crash hazards if mis-paired
(`adaptive_quantile` on an old pipeline = ValueError); three actors
(operator, claude, codex) racing on shared branches.

**Diagnosis:** `subrepos.lock.json` is a hand-rolled re-implementation of
**git submodules** — without the native tooling (diffable SHA bumps, atomic
umbrella commits, `git submodule status`, IDE/CI support).

**Adopt (per §13 policy):**
1. **Renovate bot** to automate pin advancement: it natively supports git
   submodule (and can regex-manage our lock file as-is) — opens a pin-bump
   PR automatically when a subrepo main goes green. Kills the merged≠pinned
   lag class without ceremony changes.
2. **Compatibility contracts as code:** coupled changes declare
   `requires: {renquant-pipeline: ">=5b65f2a"}` in the consuming repo's
   config/manifest; an umbrella CI matrix test loads each pinned pair and
   fails on mismatch — replacing the hand-written "do not pin X with
   pre-Y" PR warnings.
3. **Decide submodules-vs-lock in a 1-day spike** (S3): if submodules, the
   preflight/doctor collapse into `git submodule status --recursive`; if
   lock stays, Renovate manages it. Either way the policy (pins = audited
   production set; humans merge) is unchanged.
4. **Honest monorepo note:** for one box + three agents, a monorepo with
   path-scoped CI would erase the entire class (atomic cross-repo changes,
   one SHA = whole-system version). Migration cost is real; revisit only if
   the Renovate+contracts setup still bleeds after a quarter.

## 15. "There are ~100 more bugs" — finding them systematically, then keeping them out

Agreed, and we can even locate where they live: this week's 8 bugs ALL came
from four code patterns, and the census says those patterns are everywhere:
**205 broad `except Exception` sites** (pipeline kernel + adapters) and
**2,310 dict `.get()` sites** in the kernel alone (each a potential silent
fallback like the max_hold anchor bug).

### 15.1 The hunt (ordered by expected bugs-per-hour, all mature tooling)
1. **Historical differential replay** — THE engine: run DRPH over the last
   60 trading days and diff recomputed decisions vs what production actually
   did. Every mismatch is a deploy-drift artifact or a live bug. (Proof the
   method works: today's hand-pipeline vs native-pipeline scoring diff,
   −0.0054 vs −0.0915 on identical inputs, is exactly such an unexplained
   discrepancy — bug #1 of the 100, already queued.)
2. **Property campaign on money math** (hypothesis + pandera): exits never
   widen stops, Kelly ∈ [0,cap], veto only removes, wash-sale only blocks
   losses, calibrator monotone. The NaN fail-open family (Issues 23/24) is
   exactly what this catches; expect double digits from 205+2310 sites.
3. **Static sweep baseline**: ruff (full rule set), mypy --strict on
   kernel/ (gradual), vulture (dead code), bandit. One day, repeatable in CI.
4. **Mutation testing (mutmut) on the kernel's top-10 money modules** —
   measures whether the 589 test files actually bite; surviving mutants mark
   where bugs hide untested.
5. **Targeted incident-class greps** (each past bug becomes a query): every
   `.get(..., default)` on config/state in decision paths; every broad
   except that swallows; every `Path(` artifact join outside the resolver;
   every NaN comparison. Output: a ranked review queue, not a 2,310-item
   slog — decision-path hits first.

### 15.2 Keeping them out (prevention = §11–§13 plus)
- **Bug-class lints:** every incident class becomes a custom ruff/AST rule
  or lint test (ban naked broad-except in kernel, ban dict-fallbacks outside
  parsers, ban artifact Path joins) — the linter remembers so reviewers
  don't have to.
- **Incident → golden case, mandatory:** DRPH corpus grows with every bug
  found in 15.1; the regression suite becomes the bug history (§11.4).
- **Coverage ratchet:** mutation score and mypy-strict coverage only ratchet
  up per PR (no new untyped/unkilled-mutant code in kernel paths).
- **Weekly differential replay** on the rail: yesterday's decisions re-run
  and diffed — drift alarms within a day, not after an operator loss.

## 16. CAPSTONE — Unified Platform Architecture ("everything is a pipeline")

**Census (2026-06-12):** the umbrella carries **253 Python scripts + 66 shell
scripts + 14 launchd plists**; the daily entrypoint is **595 lines of bash**.
Top script families: run(26) train(24) build(19) fetch(15) analyze(12) wf(11).
Each is an unmanaged pipeline: no contracts, no lineage, no retries, no
provenance, invisible to scheduling. The operator is right that this is the
general disease — §0–§15 were treating its organs.

**The unifying design: software-defined assets.** Every computation in the
system — data pull, feature build, training, calibration, WF gate, daily
decision run, audit, experiment, report — is a **typed node in one DAG**:
declared inputs (upstream assets + versions), declared outputs
(content-addressed), contracts (§11), provenance stamps, and a freshness
policy. The Dagster asset model is the reference; a 2-day spike decides
Dagster-itself vs a thin local equivalent (launchd stays as the timer either
way). Scripts migrate by category: fetch/build → data assets (PIT store);
train/wf → model assets (MLflow stages); run/daily → decision jobs (DRPH-
replayable); analyze/diag → audit assets (L6); shell glue (595-line bash) →
job graph definitions. Migration is incremental: new work MUST be an asset;
existing scripts convert when touched (strangler rule), census tracked in CI.

**Five planes (where every §0–§15 component lives):**
- **Data plane:** PIT store (ArcticDB/parquet+manifest), collectors,
  dataset content-addressing. (§0.3, §8)
- **Compute plane:** feature DAG (Hamilton), training, scoring tensors,
  joblib bulk. (§0.3, §13)
- **Decision plane:** GateRegistry, QP/Kelly, order emission, broker
  reconciliation state machine. (§4, §5)
- **Control plane:** pins/Renovate (§14), MLflow registry (§7), config
  schema (§4.1 #6), flags, **secrets** (below).
- **Observability plane:** decision ledger, audit sidecar L6, DRPH, alert
  lifecycle, lineage. (§3, §12)

### 16.1 Database design
Today: one sqlite per broker context (runs.alpaca.db) + score/state tables,
schema-less JSON columns, no migrations. Design: **stay sqlite** (one box;
mature, transactional) with (a) **schema migrations via Alembic** (mature,
works with sqlite) — every DDL change versioned; (b) table taxonomy split by
write pattern: append-only EVENT tables (decision_ledger, audit_events,
order_events — never UPDATE), snapshot STATE tables (live_state_snapshots —
keyed by run_id, already designed), derived ANALYTICS tables (rebuildable,
excluded from backup SLO); (c) JSON columns get pandera/pydantic check
constraints at the writer; (d) WAL mode + busy_timeout (three agents + cron
contend today).

### 16.2 Rollback mechanisms (per layer, mostly already designed — unified here)
| Layer | Mechanism |
|---|---|
| Code | pins; revert-PR (proven: #102); Renovate re-pin |
| Model | MLflow stages — demote Production→Archived, previous Production reactivates (one API call); artifacts immutable |
| Config | git revert + schema validation on load; golden semantic-diff |
| Data | content-addressed PIT appends are immutable — "rollback" = pin reads to a manifest version (as_of read); bad append = tombstone row, never delete |
| State | live_state_snapshots per run_id → restore-from-DB already exists (#144 path); plus daily file backup (16.3) |
| DB schema | Alembic downgrade scripts mandatory per migration |

### 16.3 Backup
Today: ad-hoc (data/state_backups exists, stale since April). Design:
**restic** (mature, encrypted, deduplicating) on the nightly rail —
tier 1 (every run): live state + sqlite DBs + lock/pins (tiny, minutes RPO);
tier 2 (nightly): artifacts/prod + MLflow registry + PIT manifests;
tier 3 (weekly): full data/ (parquets are rebuildable; weekly is enough).
Targets: second local disk + one off-box (restic→S3/B2, cheap). **Restore
drill is a scheduled asset** (monthly: restore to temp dir + checksum
verify) — a backup that is never restored is a hypothesis, not a backup.

### 16.4 Secrets management
Today: `.env` file sourced by bash (plaintext, in repo dir — excluded from
git but one `git add -f` away from disaster; also readable by every script).
Design: (a) move secrets to **macOS Keychain** (`security` CLI — native,
encrypted at rest, per-item ACL) with a 20-line accessor in renquant-common;
`.env` dies; (b) **detect-secrets** (Yelp) or **gitleaks** pre-commit + CI
scan on all 10 repos including history audit (one-time `gitleaks detect` on
full history — if any key ever leaked into a commit, rotate it NOW);
(c) Alpaca keys: separate paper/live keys, live key marked "trading-only"
scope where the broker supports it; rotation runbook (quarterly + on any
suspicion) documented as an asset job; (d) secrets never in config/ledger/
logs — a pandera-style log scrubber assertion in CI greps run logs for key
patterns.

### 16.5 What "done" looks like (the professional bar)
One graph, five planes; every computation an asset with contracts, lineage,
freshness, and provenance; scripts count trending 319→<50 domain glue;
every layer independently rollback-able; backups restore-drilled monthly;
secrets in Keychain with leak scanning in CI; the daily run <90 s; bugs
located by differential replay instead of operator anger. Each piece is a
small PR on the §9/§0.5 rails — no big bang, no new servers.
