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
