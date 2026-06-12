# Research — PatchTST Capability Boundary (measured) + Training Cost/Value Optimum + Experiment Provenance

**Status:** proposal / awaiting review (no code change here)
**Data:** every number below comes from real data — `hf_patchtst_all_seed44_val_preds.parquet`
(36,068 rows, 254 trading days, 2025-02→2026-02, ~142 names/day), real SPY OHLCV,
the actual training log (`pt07_strict_trainfit_embargo60_seed44_20260522.log`),
the WF-gate metadata (stamped FAIL 2026-06-11), and the training panel
`data/transformer_v4_wl200_clean.parquet` (346k rows, 2016-01→2026-02).
**Companions:** `2026-06-12-model-edge-recovery-plan.md` (WS-1/2/3 approved and started).

---

## 1. Capability boundary — what the model can and cannot do (measured)

### 1.1 It has genuine skill (full validation year)

| Quantity | Value | Reading |
|---|---|---|
| Daily cross-sectional Spearman IC | **+0.071, t=+7.1, 68% of days > 0** | statistically unambiguous real signal |
| Realized 60d excess by prediction decile | strictly monotone; **top−bottom = +37.5%** | excellent ranking (year-averaged) |
| σ vs realized error | Spearman **+0.27** | σ genuinely ranks risk (Kelly input is usable) |
| μ calibration | level biased negative (known −0.198 offset); **rank-order perfectly monotone** | use ranks / μ-gate, never raw levels |
| Long side vs short side (within-half IC) | +0.032 / +0.023 (both significant) | symmetric skill; not just a junk-detector |

### 1.2 Boundary #1: performance decays with distance from the training cutoff — with a major caveat

IC bucketed by months past the training cutoff (2024-11-13):

| Months past cutoff | Mean daily IC |
|---|---|
| 3–6 | **+0.187** |
| 6–9 | **+0.158** |
| 9–12 | +0.036 |
| 12–16 | **−0.086 (negative)** |

Spearman(distance, daily IC) = **−0.56**.

**Important correction (after operator review):** the 2024-11-13 cutoff is **not
neglect** — it is the deliberate `strict_trainfit` design (90/10 tail validation
+ 60d embargo). The 36k validation predictions used in this study exist
*precisely because* the cutoff was held back. Furthermore, on a single model,
"months past cutoff" is **perfectly collinear with calendar time/regime** — the
table above is equally consistent with "edge decays with distance" and with
"late-2025/early-2026 was simply a hard period for this signal." **Single-model
evidence cannot distinguish the two; the discriminating experiment is WS-2's
point-in-time retrains (different cutoffs evaluated over the same calendar
window).**

What survives regardless of attribution: the production model has learned
nothing after 2024-11, and its OOS IC in the most recent period (the one most
like today's tape) is negative — which supports "fresh-cutoff retrain + run the
gate" as the first experiment (cheap, fast, falsifiable either way).

### 1.3 Boundary #2: the "BULL_CALM failure" is confounded

Dead months (2025-10→2026-01, IC −0.09): SPY 20d vol 11.5%, 100% of days above
the 200-DMA — a calm bull, **and** 11–15 months past cutoff. Strong months
(2025-03→08, IC +0.19): vol 20.4%, 67% above the 200-DMA, only 4–9 months past
cutoff. **The two factors are fully entangled** — no attribution should be
asserted until WS-2's discriminating evidence lands (an earlier version of this
doc over-claimed staleness as dominant; corrected).

Dispersion-quintile ICs (D1..D5: +0.02 / +0.12 / +0.13 / −0.00 / +0.08) show no
clean "low dispersion ⇒ no skill" pattern — the dispersion-starvation
hypothesis (WS-4a) is **demoted**.

### 1.4 Boundary summary

The model is a **genuinely skilled cross-sectional ranker** (strong ordering,
usable risk estimates, level calibration needs anchoring, symmetric across
sides) whose OOS performance deteriorates jointly with *distance-from-cutoff ×
calendar regime*. Separating those two factors is the most important open
question; WS-2 is the discriminating experiment.

---

## 2. Training cost/value optimum (the operator's question)

### 2.1 Real costs (measured on this machine, not estimated)

| Item | Cost |
|---|---|
| One full training run (`train_runtime`) | **1,575 s ≈ 26 minutes** |
| Calibrator fit | minutes |
| Full WF-gate evaluation | ~30 minutes |
| **One retrain → evaluate → promote-or-discard cycle** | **< 1.5 h wall-clock, $0 cloud** (plus hours of panel rebuild when the dataset must be extended — see ① below) |

### 2.2 Marginal value / marginal cost per lever

| Lever | Marginal value | Marginal cost | Value/cost |
|---|---|---|---|
| **① Fresh-cutoff retrain** | If the decay hypothesis holds, IC returns from −0.09 to the +0.19 band (**Δ≈0.28 — a falsifiable hypothesis, not a measurement**); if it fails, the decay hypothesis is cleanly falsified — both outcomes are valuable | 26 min training + **panel rebuild** (the training parquet ends 2026-02-10 and must be extended to the present; this is the real cost item, hours) | ★★★★★ |
| **② Quarterly retrain cadence** (cutoff = T−90d) | keeps the model permanently inside its 3–9-month high-IC band | ~1.5 h per quarter | ★★★★★ |
| ③ **Information expansion** (§2.5: analyst ratings / estimate revisions / options IV / short interest / broader fundamentals) + universe 142→200 | quality/attention factors measurably retain IC in the dead window (asset_growth −0.23) — aimed exactly at the model's weakest spot; breadth mechanically +19% IR | per-group IC screens + ride the next retrain; IV data already being collected daily | ★★★★★ (upgraded) |
| ④ Longer training history (currently 2.5y; add the 2022 bear) | regime coverage, robustness | linear; training still minutes | ★★★ |
| ⑤ Multi-seed ensemble (3 seeds) | IC-variance reduction (magnitude TBD by WF evidence) | +2 × 26 min | ★★★ (ride-along) |
| ⑥ Architecture / label research (WS-4/5) | unknown | weeks of effort | ★★ — wait for ①②③ results first |

**The optimum is unambiguous: ① + ②.** A 26-minute retrain has higher expected
information value than any architecture research, and institutionalizing a
quarterly cadence permanently removes the staleness failure class. ③④⑤ ride
along on the next retrain.

### 2.3 A guard hole found on the way

`model_staleness_days: 60` checks **trained_date** (2026-05-22 — "fresh"), but
skill is governed by **effective_train_cutoff_date** (2024-11-13). The May
training was a deliberate strict-OOS design, yet the staleness guard cannot see
the "new training, old cutoff" combination — the question it should answer is
*"how old is the newest data the model has ever seen?"*
**Proposal:** the staleness preflight reads the cutoff distance instead —
warn > 9 months, fail buys > 12 months.

---

## 2.5 Information expansion — operator-directed, now measured, upgraded to first-class

> The first draft of this doc reduced "expand tickers / add data" to one table
> row and omitted new information sources entirely — that was wrong. Measured
> on the real panel, the evidence supports the operator's instinct:

**Key measurement (the dead window 2025-10→2026-01 — the same period where the
model's IC is −0.09):**

| Information | Single-feature IC in the dead window | Reading |
|---|---|---|
| `asset_growth` (quality/investment factor) | **−0.234** | the **strongest** cross-sectional signal in the calm window |
| `roe` | +0.064 | fundamentals keep working in calm tape |
| `n_articles_log` (news volume) | −0.065 | attention signal stays alive |
| Technical-group mean abs IC | 0.065 (vs 0.054 in the strong window) | **the raw information is not dead — the model's combination of it is** |

**Conclusion: the calm failure is a combination failure, not an information
vacuum.** The model's representation is momentum-heavy; in calm tape the
cross-section is driven by slow-moving quality/fundamental/attention variables —
and those occupy only ~6 of the 172 features, with the fundamentals feed frozen
for 121 days on top (WS-1 fix in progress).

**Information-expansion proposal (ranked by availability; all free sources):**
1. **Analyst ratings & price-target revisions** (yfinance recommendations /
   targets, daily) — among the best-documented calm-period cross-sectional
   signals (revision drift).
2. **EPS estimate revisions** — the slow complement to earnings surprise.
3. **Options-implied information** (put/call, IV skew) — `logs/iv_snapshot`
   shows a **daily IV collection job already running**; the data is in hand but
   never entered the feature set. Near-zero integration cost.
4. **Short interest** (FINRA, bi-monthly).
5. **Broader fundamentals**: only roe/asset_growth-class columns exist today;
   extend to margins / cash-flow / accruals (standard quality family).
6. **Universe 142→200** (the training set is already wl200; expand the trading
   watchlist to match) — mechanically +19% IR (Grinold breadth), and a thicker
   calm-period cross-section is directly more rankable.

**Validation protocol:** each new information group must first pass the
per-group, regime-conditional IC screen (as in the table above); survivors enter
the next retrain's feature set; the WF gate renders the final verdict. No
gut-feel admissions.

---

## 3. Experiment provenance status (the operator's code/data-SHA question)

**Recorded, but with gaps:**

| Item | Status |
|---|---|
| Code commit SHA | ✅ sidecar `training_contract.git_head` (full SHA); MLflow auto-tags `mlflow.source.git.commit` (present on all 6,239 runs) |
| Hyperparams / seed / splits / preprocessing | ✅ complete in `training_contract` |
| Config fingerprint | ✅ `config_fingerprint` (sha256) |
| **Data version** | ❌ recorded as a **path only** (`data/transformer_v4_wl200_clean.parquet`) — the file can be silently rebuilt and the lineage breaks |
| **Multi-repo pin set** | ❌ a single `git_head` is recorded, not the `subrepos.lock.json` pin set (which of the 9 repos at which commit) |
| Eval-data version | ❌ `wf_gate_metadata` carries no fingerprint of the evaluated data |

**Proposal (small change, large value):** stamp at train *and* eval time —
(a) `dataset_sha256` + row count + date range; (b) a digest of the active
`subrepos.lock.json` pins; (c) the same into `wf_gate_metadata`. Only then are
any two experiments strictly comparable — capability-boundary research needs
this foundation.

---

## 4. Proposed execution order (pending review)

1. **Now:** fresh-cutoff retrain (panel rebuild to present → cutoff ≈ T−90d,
   60d embargo, same recipe, wl142) → run the WF gate. Either it rewrites the
   verdict or it falsifies the decay hypothesis — both outcomes advance us.
2. WS-2: two point-in-time retrains (26 min each) → full 3-cut evidence **and**
   the §1.2/§1.3 staleness-vs-regime discriminating experiment.
3. **Staleness preflight fix** (read cutoff distance, not trained_date) +
   institutionalize the quarterly retrain on the existing weekly_wf_promote rail.
4. Next retrain rides along: §2.5 information groups that pass the IC screen,
   universe→wl200, longer history, 3 seeds.
5. Provenance stamps (§3) land together with #3.
6. WS-3 (regime-conditional allocation) kept as insurance — if a *fresh* model
   still fails calm-window IC, enable "hold SPY in calm" with measured evidence.

## References
- Grinold & Kahn (1999), *Active Portfolio Management* — IR = IC·√BR (breadth argument).
- López de Prado (2018), *AFML* — embargo / evaluation discipline.
- Qian & Hua (2004) — IC horizon decay; industry practice of quarterly–semiannual
  rolling retrains for cross-sectional alpha models (e.g. Qlib's rolling-retrain default).
- Jegadeesh & Titman (1993); Moskowitz–Ooi–Pedersen (2012) — momentum payoff structure.
- Cooper, Gulen & Schill (2008) — the asset-growth effect (the factor that dominates our dead window).
- Womack (1996); Jegadeesh et al. (2004) — analyst recommendation/revision drift.
