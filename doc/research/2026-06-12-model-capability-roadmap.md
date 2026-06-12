# Research — Model Capability Roadmap: Improving PatchTST, Alternatives, and Engineering Leverage

**Status:** research / awaiting review (no code change)
**Operator questions:** (1) how to improve PatchTST's capability; (2) is there
a better model; (3) how to engineer the system to extract the maximum from
whatever model we run.
**Evidence base:** this repo's own measurements (capability-boundary doc,
DOE logs from May 2026, today's PIT retrains), current literature, and
open-source benchmarks. Constraints honored: PatchTST stays primary, XGB
shadow-only, ensemble shelved (decision record 2026-06-12) — nothing here
re-litigates that; reopening triggers are unchanged.

---

## 0. The single most important framing fact

Our production PatchTST is **tiny and cheap**: 0.07M parameters (d_model=64,
2 layers, seq_len=24), 5 epochs, **26 minutes** to train on this machine.
Validation IC +0.071 (t=7.1) with strictly monotone deciles. We are nowhere
near any capability ceiling that requires exotic architecture research — the
cheap, measurable headroom is in **scale, the cross-stock variant we already
built, labels, data, and deployment engineering**. Every proposal below is
gated by the standard WF gate; nothing promotes on val-IC alone.

---

## 1. Q1 — Improving PatchTST itself (ranked by evidence × cost)

### 1.1 Cross-stock attention — highest-variance structural lead (already implemented)
`HFPatchTSTRanker` already implements `--cross-stock-attn`. In the May DOE
(`logs/hf_cross_stock_5cut_5seed_pt07`), the cross-stock variant reached
a winner-picked max of best_val_ic 0.2035; the FULL 25-point run averages **+0.0507 (std 0.0878, 12/25 negative, two regimes negative)** — a high-variance candidate, not a proven winner. It was never promoted (prod runs `cross_stock=False`), and any adoption requires the paired, DSR/PBO-controlled A/B defined in the errata. External literature agrees this is
where the juice is: **MASTER (AAAI 2024)** — the current reference stock
transformer — attributes its gains exactly to modeling *momentary and
cross-time stock correlation* ([paper](https://arxiv.org/pdf/2312.15235),
[code](https://github.com/SJTU-DMTai/MASTER)). Cross-sectional ranking is a
relative problem; per-stock encoders throw away the relative structure.
**Action:** re-run cross-stock under the strict_trainfit protocol (same
2024-11 cutoff, same val year) → if the IC lift survives the strict split,
send through the WF gate. Cost: ~30 min/run.

### 1.2 Scale the model (we are at 0.07M params)
d_model 64→128/256, layers 2→3-4, seq_len 24→48 (more than one quarter of
context), epochs 5→10 with early-stop. Each config ≈ 30–60 min. Tabular-DL
folklore says bigger ≠ better on small data — our panel is 346k rows — so
this is a measured sweep, not a belief; pre-register the grid, judge on the
strict split, gate the winner. Joint with 1.1 (cross-stock may want more
capacity).

### 1.3 Multi-horizon multi-task heads (labels already exist)
The panel already carries `fwd_5d/20d/60d_excess`. Auxiliary heads on 5d/20d
regularize the 60d head (shared encoder, weighted losses) — standard
multi-task lift on small data, and directly attacks the M6 finding that
overlapping 60d labels dilute the training signal. Cost: small code change +
30-min runs.

### 1.4 Label engineering (already approved as WS-5)
Triple-barrier labels (match how positions actually exit), overlap-aware
sample weighting (de Prado sample uniqueness). Pairs with 1.3.

### 1.5 Feature expansion (already approved, §2.5 of the boundary doc)
Analyst revisions / options IV (already collected daily!) / short interest
(collector live since 2026-06-11) / broader quality factors — each gated by
the per-group regime-conditional IC screen. The dead-window evidence
(asset_growth IC −0.23 while the model bled) says the calm-window fix is
more likely here than in architecture.

### 1.6 Seeds
3-seed average at promotion time (each +26 min). Cheap variance reduction;
fold into the quarterly retrain recipe.

### What NOT to do
FiLM regime conditioning underperformed cross-stock in our own DOE
(0.142–0.165) — deprioritized. No architecture-of-the-month hopping: each
candidate gets one strict-split shot, the gate decides.

---

## 2. Q2 — Is there a better model than PatchTST?

Honest answer: **maybe at the margin, but nothing in the literature suggests
a step-change for THIS problem**, and our binding constraints are data scale,
label quality, and regime deployment — not the encoder.

| Candidate | What it is | Verdict for us |
|---|---|---|
| **MASTER** (AAAI'24, SJTU, Qlib-native) | market-guided stock transformer; cross-stock + cross-time attention; beats Qlib baselines incl. strong XGB on CSI300/800 | **The serious candidate.** MASTER supports the cross-sectional-mixing HYPOTHESIS; our `cross_stock_attn` flag is a smaller ablation, NOT an approximation of MASTER's market-guided gating + cross-time architecture. Cheapest path: test our ablation first (1.1); only if it confirms does a faithful MASTER port run as a challenger, with DLinear+GBDT baselines under the same purged WF protocol |
| **Time-series foundation models** (TimesFM, Chronos, Moirai, Time-MoE) | 50M–200M-param pretrained forecasters | **Low prior as ranker.** Univariate, point-forecast oriented; recent finance evaluations find specialist models match or beat them in most tasks ([survey](https://arxiv.org/html/2507.07296v1), [revisit](https://arxiv.org/html/2511.18578v1)); low prior as DIRECT rankers for this use case; evaluate only as frozen feature/embedding baselines under the same purged WF protocol (no claim that the class cannot encode cross-sectional information) |
| Mamba/SSM hybrids (e.g. market-guided Mamba) | linear-time sequence models | Emerging; no finance-benchmark dominance yet; revisit in 6 months |
| DLinear (already tried) | linear baseline | Our DOE: 0.128–0.153 val_ic — useful sanity floor, not a successor |
| GBDT (XGB) | tabular | Shadow-only per decision record; the shadow monitor produces the ongoing comparison |

**Recommendation:** spend Q2 budget on 1.1 (the cheapest test of the cross-sectional-mixing hypothesis) before importing any new architecture. One genuinely new
external test worth 1 day: MASTER's official Qlib implementation on our
panel as a *challenger*, same strict split, same gate.

---

## 3. Q3 — Engineering to extract the maximum (Grinold: IR = IC · √BR · TC)

The model supplies IC. Engineering supplies **breadth (BR)** and **transfer
coefficient (TC)** — and this week proved engineering moves the realized
number more than modeling: the same model went from "sell-only book" to a
functioning system purely via gate/exit/deployment fixes.

Ranked engineering program (largely already approved, consolidated here):

1. **Freshness institutionalized** — quarterly (or monthly; training is 26
   min) fresh-cutoff retrain on the weekly_wf_promote rail + the staleness
   preflight reading `effective_train_cutoff_date` (not trained_date).
   Measured stake: the 3–6mo band ICs +0.187 vs −0.086 at 12–16mo (same
   pipeline A/B showed ~6–7 IC pts of it is real freshness effect).
2. **Daily data pipeline** (approved) — nightly panel append + PIT collectors
   (analyst/IV/short-interest) + provenance stamps (dataset_sha256, pin
   digest). Converts every retrain into a true 26-minute operation and is the
   only way the PIT feature datasets can ever exist.
3. **Deployment gates that match the signal** (mostly shipped this week):
   trend-gated BEAR detector (#112), quantile breadth floor (#113), uniform
   max_hold backstop (#27), model-protection exits (#110/111), shadow monitor
   (#114). Remaining approved item: **HMM/Markov-switching regime engine**
   (RFC #93) — better regime posteriors deploy the same IC into more
   tradeable days; shadow-first.
4. **Breadth — gated experiment, NEGATIVE internal prior.** Universe
   expansion (142→200) may proceed only as a pre-registered experiment
   measuring marginal IC of the added names, per-sector heterogeneity,
   fillability, and transfer coefficient — E5/E17/E34/E45 all measured IC
   degradation on expansion, so no uplift is assumed.
5. **TC later**: the shorts Phase-B 110/10 efficiency sleeve (design under
   review) raises the transfer coefficient without any new alpha — the
   literature-preferred use of shorting for this account.
6. **Experiment infrastructure**: wire the existing Optuna rail to the
   strict-split objective with a fixed budget (e.g. 20 trials/quarter) so
   hyperparameter search is systematic, pre-registered, and stops being
   ad-hoc; all runs stamped with code/data/pin provenance (gap already
   documented in the boundary doc §3).

## 4. Proposed sequencing (everything gate-judged)

- **Now (this week):** 1.1 cross-stock strict re-run (30 min) ‖ 1.2 scale
  sweep (pre-registered 6-cell grid, ~4 h total) ‖ finish WS-2 gate retake
  (in progress tonight).
- **Next retrain ride-along:** 1.3 multi-horizon heads + 1.4 labels + 1.5
  screened features + 1.6 3 seeds + universe 200.
- **Next 2–4 weeks:** Q2 MASTER challenger (1 day) only if 1.1 confirms the
  cross-stock effect; HMM shadow (RFC #93); Optuna budget wiring.
- **Continuous:** daily pipeline build-out, provenance stamps, quarterly
  retrain rail.

## Sources
- [MASTER: Market-Guided Stock Transformer (AAAI 2024)](https://arxiv.org/pdf/2312.15235) · [official code](https://github.com/SJTU-DMTai/MASTER)
- [PatchTST overview & benchmark standing](https://www.emergentmind.com/topics/patchtst)
- [TSFMs for multivariate financial forecasting (2025)](https://arxiv.org/html/2507.07296v1) · [Re(Visiting) TSFMs in Finance](https://arxiv.org/html/2511.18578v1) · [TimesFM vs Chronos vs Moirai for finance](https://paperswithbacktest.com/course/timesfm-vs-chronos-vs-moirai)
- [Market-guided Mamba for stock prediction](https://www.sciencedirect.com/science/article/pii/S1110016824012821)
- Internal: capability-boundary doc (2026-06-12), May DOE logs (cross-stock full-run mean +0.0507 with winner-picked max 0.2035 / FiLM 0.165 / DLinear 0.153 / base 0.188 — per-cut details in errata), decision record (PatchTST primary), Grinold & Kahn (1999).


---

# ERRATA & CORRECTIONS (post-merge strict review, 2026-06-12 — codex)

The four HIGH findings are accepted. Corrected claims supersede the body text:

1. **Cross-stock attention is a HIGH-VARIANCE candidate, not "the strongest
   lead."** The 0.203 was winner-picked from 25 cut/seed points. Full DOE
   summary (`logs/hf_cross_stock_5cut_5seed_pt07/driver.log`): mean
   best_val_ic **+0.0507**, std 0.0878, min −0.0594, max +0.2035,
   **12/25 points negative**; per-cut means: covid +0.113, fed −0.042,
   inflpk +0.012, svb +0.187, unwind −0.015. Required before any
   implementation: paired A/B vs plain PatchTST on identical cuts/seeds with
   mean/std, min-regime IC, **DSR/PBO** (Bailey–López de Prado), shuffle and
   time-shift controls — per the repo's own pre-registered protocol
   (2026-05-19 improvement plan §600-618).
2. **"Mechanism ≈ MASTER" overstated.** Our flag is a single cross-stock
   attention layer (`use_cross_stock_attn`), not MASTER's market-guided
   gating + cross-time interaction architecture, and MASTER's CSI300/800
   benchmark does not transfer to our 142-name US long-only gated path.
   Corrected: MASTER supports the *hypothesis* that cross-sectional mixing
   matters; our flag is a smaller ablation and is evaluated as such.
3. **The mechanical "+19% IR from 142→200" claim is RETRACTED.** Our own
   logs falsify the independence/stable-IC assumptions: E5 103→227 names
   IC −44%; E17 expansion negative; E34 "NO-GO for Grinold breadth at this
   scope"; E45 291→1640 implied IR ratio 0.64× baseline. Universe expansion
   is a gated experiment measuring marginal IC, sector heterogeneity,
   fillability and TC — with a negative prior from four internal attempts.
4. **Provenance of "+0.071 (t=7.1)":** computed in-session from
   `pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_val_preds.parquet`
   (strict trainfit split, 254 d, daily cross-sectional Spearman; t = mean/std·√n).
   It is **background evidence**, not a gate-admitted baseline: the
   2026-06-05 promotion was operator-directed; the artifact's WF-gate
   verdict is currently FAILED (2026-06-11), and the selection-metric
   best_val_ic of the same training run is +0.0307. All roadmap claims
   should cite this appendix, not the body's framing.


## Acceptance contracts for the remaining candidates (codex MED findings)

- **Multi-horizon / triple-barrier work (1.3/1.4):** horizon-specific
  embargoes (5d/20d heads embargo at their own horizons, not 60d);
  label-overlap uniqueness/dependence statistics reported (de Prado sample
  uniqueness); loss weights FIXED before training (no post-hoc tuning);
  judged against the single-horizon baseline on the same purged WF split.
- **Any alternative model (TSFM, MASTER port, Mamba):** must run with
  DLinear and GBDT as REQUIRED baselines under the identical purged
  walk-forward protocol — same cuts, seeds, costs, controls. Baseline
  parity is a merge gate, not optional commentary.
