# RenQuant System — Feature Map, Roadmap & Pending Discussion

> **Canonical living inventory of the whole system.** Supersedes the two
> single-topic research docs:
> - `doc/research/2026-06-12-model-capability-roadmap.md` (PR #106)
> - `doc/research/2026-06-12-engineering-architecture-deep-plan.md` (PR #108)
>
> Those remain in git history as the original rationale; this is the rolling
> source of truth for *what exists, what's next, and what's deferred* across all
> RenQuant repos — not just #106/#108.

**Status legend:** ✅ LIVE (running in production daily) · 🟢 BUILT (merged, in
the codebase; may not yet be wired/active) · 🧪 EXPERIMENTAL (research / epic
branch / single-run evidence) · 📋 PLANNED · ⏸️ SHELVED (decided against / paused)

Last updated: 2026-06-16.

---

## 0. Architecture

10 pinned repos in a **model-factory** flow (see `RENQUANT_REPOS.md`,
`RenQuant/doc/arch/multirepo-sop.md`):

`base-data` → (`common` + `pipeline` shared code) → `model` factory
(`renquant_model_gbdt`, `renquant_model_patchtst`) → `artifacts` registry →
consumed by `strategy-104`, `pipeline` (runtime), `backtesting`, `orchestrator`;
`execution` does broker actions; `RenQuant` umbrella pins the assembly in
`subrepos.lock.json` and is the permanent rollback source. Consumers reference
models by `artifact_path` only — never import the factory.

The live strategy is **renquant_104**; primary scorer **PatchTST**
(`pt07`), with a GBDT `alpha158_fund` shadow.

---

## 1. Existing Features (by category)

### 1.1 Data & Feature Engineering
| Feature | Status | Notes |
|---|---|---|
| base-data manifests + freshness/fingerprint contracts | ✅ | `renquant-base-data` |
| alpha158 feature panel (178 cols: K-bar, MA/STD/ROC/BETA/CORR/RSQ/QTL/RANK/SUM/VMA…) | ✅ | source `data/alpha158_291_fundamental_dataset.parquet`, → 2026-03-18, 292 tickers |
| transformer_v4 wl200 clean panel (142-ticker curated universe) | ✅ | live training panel; quality-selected beats raw 292 |
| Fundamentals, earnings surprise, insider trades, news sentiment, FRED macro, per-ticker macro, correlation | ✅ | `fundamentals.py`, `earnings_surprise.py`, `insider_trades.py`, `news_sentiment.py`, `fred_macro.py` |
| Data cache w/ negative cache (`skip_tickers`), coverage guards (data/feature/row) | ✅ | thin/illiquid tickers skipped, not crashed |
| PIT (point-in-time) reader | 🟢 | leakage-safe historical reads |
| **feature_drift_audit** — per-feature aligned-vs-shifted IC, drift-family ranking | 🟢 | new (#137/#138); finds placebo-driving features to prune |

### 1.2 Model Factory (`renquant-model`)
| Feature | Status | Notes |
|---|---|---|
| GBDT family (alpha158_fund XGBoost, alpha158 linear) | ✅ | shadow + sim recipe |
| PatchTST family (`hf_patchtst`, distributional Student-t head) | ✅ | live primary |
| Cross-stock attention (iTransformer / MASTER) flag | 🧪 | #126 3/3 positive; now loadable live (#380) |
| FiLM regime conditioning flag | 🧪 | built, identity-at-init |
| Training recipe: CSRankNorm + train-fit winsorize, per-day batched, margin-ranking + NLL loss, multi-seed, per-regime-IC early stop | ✅ | |
| `--val-days` fixed trailing val window | 🟢 | root-cause fix for stale train-cutoff (#378) |
| `--exclude-feature-prefixes` slow-factor ablation knob | 🟢 | new (#379) |
| Walk-forward calibrators (platt/isotonic, per-scorer) | ✅ | `fit_walkforward_calibrators` |

### 1.3 Scoring & Calibration (live inference)
| Feature | Status | Notes |
|---|---|---|
| PanelScorer (GBDT), HFPatchTSTPanelScorer (sequence), regime-router, ensemble scorers | ✅ | |
| Per-scorer panel-rank calibration | ✅ | |
| Cross-stock / FiLM layer reconstruction on load + fail-closed on missing weights | 🟢 | bug fixed (#380/#382) — was silently mis-scoring |
| model_acceptance gate (sanity placebo, monotonicity, entry-IC) | ✅ | |

### 1.4 Regime Engine
| Feature | Status | Notes |
|---|---|---|
| HMM regime labels (BULL_CALM/VOLATILE/STRONG, BEAR, CHOPPY, LOW/MED_NORMAL/SPIKED) | ✅ | `regime_hmm.py`, SPY-driven |
| regime_resolver, transition window / flip cooldown, entry-regime anchor | ✅ | |
| Markov-switching engine upgrade (RFC #93) | 📋 | see §3 |

### 1.5 Pre-flight Gates & Decision Trail
| Feature | Status | Notes |
|---|---|---|
| Pre-flight: P-WF-GATE (HARD), P-REGIME-IC (HARD), P-MODEL-STALENESS (SOFT) | ✅ | sell-only fallback if WF metadata absent |
| market_gates, net_safety, drawdown breaker, bear-override, transition window, kelly-sizing gate | ✅ | |
| decision_trace per-run | ✅ | |
| **GateRegistry** verdict algebra (allow<halve<block, risk-monotone, block-dominant) | 🟢 | new (#133) |
| **decision ledger** (append-only, "why sell-only" = 1 SQL query) | 🟢 | new (#133); not yet wired to live gates |

### 1.6 Portfolio Construction
| Feature | Status | Notes |
|---|---|---|
| Kelly sizing (σ-scaled), vol-target, max positions / per-sector caps | ✅ | |
| Selection, rotation, convex rotation (QP) | ✅ | |
| portfolio_qp Step-4 convex optimizer + placebo replay verdicts | 🧪 | §7.2 A/B replay |

### 1.7 Exits & Risk
| Feature | Status | Notes |
|---|---|---|
| Triple-barrier, σ-scaled SDL, BB14 stops, cross-sectional panel-conviction exit | ✅ | |
| Meta-label protection (classifier vetoes SDL), breach counter + cross-day persistence | 🟢 | |
| Unified max-hold backstop, risk_metrics, realized_pnl | ✅ | |

### 1.8 Shorting
| Feature | Status | Notes |
|---|---|---|
| model_acceptance_short, short-candidate job | ✅ (gated off) | very high bar: bottom-5% + N-of-N μ breach + confirmed BEAR + all vetoes; max 2 concurrent; sub-PDT multi-day |

### 1.9 Execution & Broker
| Feature | Status | Notes |
|---|---|---|
| Alpaca broker adapter, order attribution, order dedupe, fill-freshness guard | ✅ | live account 212830627 |
| Intraday cadence + intraday wash-sale guard | 🟢 | |
| T+2 settlement, PDT guard | ✅ | |
| Native live execution payload / read-only offboard rehearsal / cutover bridge | 🟢 | codex track (#121–#130) |

### 1.10 Walk-Forward Gate & Promotion
| Feature | Status | Notes |
|---|---|---|
| run_wf_gate (3-cut sim + §5.2 sanity battery: shuffle + time-shift placebo + monotonicity) | ✅ | |
| weekly_wf_promote trust-boundary chain | ✅ | |
| Recipe-fingerprint validation + manifest auto-discovery | ✅ | |
| **WF corpus regen + per-window calibrators** (R4) | 🟢 | new (#383); fixed lost-artifact gate crash |

### 1.11 Audit & Reliability
| Feature | Status | Notes |
|---|---|---|
| **L6 score-drift audit (PSI), AlertBook lifecycle escalation, reconciliation SM** | ✅ LIVE | deployed 2026-06-14 (#367/#370/#371/#373/#377) |
| DRPH (disaster-recovery preflight), env_fingerprint, artifact_contract/snapshot | ✅ | |
| Tier-1 backup + restore drill | ✅ | |
| Engineering census + gate-writer ratchet enforced in CI | ✅ | #118/#119 |

### 1.12 Engineering Rails (#108 strangler-fig)
| Stage | Item | Status |
|---|---|---|
| **S1 typed edges** | LiveStateV2 (1-line field adds, lossless v1 migration) | 🟢 #132 |
| | ArtifactResolver (single fail-closed resolution authority) | 🟢 #131 |
| | config_schema (typed dangerous top level) | 🟢 #134 |
| **S2 choke point** | GateRegistry + decision ledger | 🟢 #133 |
| | god-file decomposition: sim_nav / sim_price / sim_cash extracted + invariant tests | 🟢 (partial) #376/#375/#366/#365/#362 |

### 1.13 Orchestration & Automation
| Feature | Status | Notes |
|---|---|---|
| Daily orchestration (daily104), run bundles, pinned `subrepos.lock.json` | ✅ | |
| launchd agents: daily104, intraday104, weekly_wf_promote, conditional/panel/linear retrain, backup, news-sentiment, iv-snapshot, screen-watchlist, preopen-cancel-gate | ✅ | |
| anomaly_triggers (SPY/VIX → retrain) | ✅ | |
| **Autonomous PR loop** (codex/claude review→fix→merge, every 300s) | ✅ | restored (#381) after stash-loss |
| Native live bridge / scheduled cutover | 🟢 | codex track |

### 1.14 Eval & Research Tooling
| Feature | Status | Notes |
|---|---|---|
| **model_sanity_compare** (reproducible promotion-evidence table) | 🟢 | new (#136) |
| **feature_drift_audit** (next-prune-target finder) | 🟢 | new (#137/#138) |
| analyze_manifest_sanity_placebo, run_wf_gate diagnostics, DOE sweeps, WF forensics | ✅ | |

---

## 2. Roadmap

### 2.1 Near-term — unblock live trading (the sell-only fix)
1. **Get a gate-passing model.** Evidence chain: pruning the slow-drift feature
   family is the dominant lever (B2 placebo ratio 25.5→2.84; gate needs <2.0).
   **B5** (targeted prune of BETA/ROC/CORR/CORD/QTLD/SUMN/SUMD/SUMP, guided by
   feature_drift_audit) is the current shot. If it clears <2.0 → live candidate.
2. **Deploy R4** (#383 merged) → green `weekly_wf_promote` + the two retrain jobs.
3. **PatchTST WF regen** for the Sharpe stamp once a model passes sanity → stamp
   `wf_gate_metadata` → pre-flight unblocks buys.
4. **Promote + deploy** the passing model to the live pins.

### 2.2 Near-term — engineering wiring (#108 follow-ups)
- Wire the **runner** to use LiveStateV2 / ArtifactResolver (behind a flag).
- Submit live pre-flight / WF / buy-block gates to a per-run **GateRegistry** and
  persist verdicts to the **decision ledger** (live "why sell-only" = 1 query).
- Wire `config_schema` validation into the config-load path.

### 2.3 Mid-term
- S2 **god-file decomposition** continued (replay-parity gated, multi-PR).
- Model **scale sweep** (0.07M params / fast trains → nearly free).
- **Fresh-feature pipeline with quality selection** (the curated wl200 beat raw
  292; rebuild the selection on fresher data + admit CRWV/RKLB/SPCX once they
  have ≥ seq_len history).
- **Intraday cadence + governors + validation** (#26).

### 2.4 Model-capability program (#106, all WF-gate-judged)
- **cross-stock attention** A/B/C promotion decision (#126); now deployable
  (#380). Evidence: helps but doesn't pass alone; does not stack on top of
  pruning (B3 < B2).
- **Freshness rail**: daily data pipeline + provenance (partly covered by R4
  regen + ArtifactResolver sha256).
- PatchTST-primary / no-ensemble decision honored.

---

## 3. Pending Discussion (短期不做 / 以后要改)

These need an explicit decision or a larger effort before starting:

- **S3 (#108):** single pinned runtime + MLflow model-stage registry + live
  state out of git. Large; needs an architecture decision (runtime image,
  MLflow adoption, state store).
- **HMM regime engine RFC #93:** Markov-switching upgrade to the regime engine —
  needs RFC sign-off (`doc/research/2026-06-11-regime-detection-hmm-markov-switching-rfc.md`).
- **Optuna budget wiring:** hyperparameter search budget — not built.
- **Universe expansion strategy:** raw 292-ticker training *underperformed* the
  curated 142 (A1 experiment) — expansion must be quality-selection-driven, not
  raw count. Open question: how to re-run wl-quality selection on fresh data.
- **Ensemble primary:** ⏸️ SHELVED per the scorer-lineup decision
  (`doc/decisions/2026-06-12-scorer-lineup-decision.md`); PatchTST primary, XGB
  shadow-only. Reopen only on defined triggers.
- **Shorting activation:** built but gated off behind a very high bar; turning it
  on is a risk decision (sub-PDT, max 2 concurrent).
- **god-file full decomposition:** the 3,476-LOC scorer + 2,958-LOC runner —
  incremental strangler-fig, many PRs, each replay-parity gated.
- **TSFMs (TimesFM/Chronos/Moirai):** low-prior as rankers per 2025 finance
  evals — not pursued.

---

## 4. Engineering-before-model-research stance

Per `doc/decisions/2026-06-12-engineering-before-model-research.md`: model
evidence is only trustworthy once the rails are green. The recent campaign
honored this — the WF gate that produces all model evidence was itself broken
(lost WF artifacts, recipe mismatch, a scorer that silently dropped cross-stock
weights); those were fixed (R4 #383, scorer #380/#382) *before* the model
conclusions (pruning > freshness > architecture) were trusted.
