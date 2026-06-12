# Research — Model-Edge Recovery Plan (unblocking buys the honest way)

**Status:** research proposal / awaiting review (no code change here)
**Context:** the WF gate stamped the PatchTST primary `passed: false`
(2026-06-11). Evidence: the only executable cut (2025-04→2026-03) shows
**Sharpe +0.215 vs SPY +0.749 (ΔSharpe −0.534)**; regime-layered sanity IC
**fails exactly in BULL_CALM** (passes in BEAR / BULL_VOLATILE / CHOPPY);
cuts 2024-01 / 2024-07 are unexecutable (no point-in-time retrains). The
preflight buy-block is therefore *working as designed*. Unblocking buys means
**earning a passing artifact**, not loosening the gate.
**Companions:** `2026-06-11-false-bear-buy-suppression-cascade.md` (machinery
fixes, all shipped), M6 placebo verdict (overlapping-label confound),
2026-05-20 truly-OOS eval (BULL_CALM top-10 alpha ≈ −0.045, IC ≈ 0 — consistent
with today's gate evidence).

---

## 0. The evidence, compressed

| Fact | Source | Implication |
|---|---|---|
| Cut-3 Sharpe +0.215 vs SPY +0.749 | WF gate 2026-06-11 | model makes money but **loses to buy-and-hold** |
| Sanity IC fails **only** in BULL_CALM | `wf_gate_metadata.sanity_regime_ic` | the edge exists, but **not in the regime we trade most** |
| Fundamentals feed stale **121 days** | daily log warning | 5 features are a frozen snapshot on every live bar |
| Label `fwd_60d_excess` overlaps ~60× | M6 verdict | training/eval signal diluted; placebo confounds |
| Only one point-in-time retrain (cutoff 2024-11-13) | manifest | 2 of 3 WF cuts can never be evidenced |
| Weekly GBDT candidate also failed (Sharpe −0.077) | weekly_wf_promote 2026-06-11 | not a PatchTST-only problem |
| live scores: std 0.029, calibrator-saturated | daily log | weak cross-sectional dispersion to harvest |

---

## 1. Workstreams (ranked by cost → evidence speed)

### WS-1 — Data hygiene first (zero model risk, days)
**What:** refresh `sec_fundamentals_daily` (stale since 2026-02-10); audit the
sentiment join coverage (109 NaN-dropped rows at the tail edge); re-verify the
171-day-fresh OHLCV path post the data-verification task (#102).
**Why:** 5 of 172 features are frozen; garbage-in degrades live IC *relative to
training*, i.e. some of the BULL_CALM live-IC gap may be data, not model.
**Evidence test:** re-run the regime-IC sanity on refreshed data; live-vs-train
feature-distribution drift report (PSI per feature).
**Cost:** small; no GPU, no retrain.

### WS-2 — Complete the exam: point-in-time retrains (mechanical, GPU)
**What:** train PatchTST at two historical cutoffs (≈2023-10 for the 2024-01 cut
and ≈2024-04 for the 2024-07 cut, each with the 60d embargo recipe of pt07),
fit per-cutoff calibrators (the `walkforward_v2_20260602` infra already produces
per-cut calibrations), extend `walkforward_manifest_patchtst_seed44_pt07.json`
to 3 retrains, re-run `run_wf_gate.py`.
**Why:** without this, 2/3 cuts are unexecutable forever — the gate can never
pass on coverage grounds, regardless of model quality.
**Cost:** 2 GPU training runs of the existing recipe + calibrator fits — the
exact pipeline that produced pt07; no research risk.
**Honest caveat:** this *completes the evidence*; it does not improve the model.
If cut-1/2 come back SPY-lagging too, the verdict stays FAIL — and that is
information, not failure of the plan.

### WS-3 — Trade where the edge is: regime-conditional allocation (no training, high value)
**What:** the gate's own evidence says IC **passes in BEAR / BULL_VOLATILE /
CHOPPY and fails in BULL_CALM**. Proposal: a config-level allocation policy —
in BULL_CALM hold the benchmark sleeve (SPY) instead of model picks; run model
selection only in regimes where it demonstrates IC. (Structurally similar to the
existing `bear_defensive_slots` mechanism — this generalizes it.)
**Why it answers the actual failure:** "model loses to SPY" is dominated by
BULL_CALM periods (most of the calendar). SPY-in-CALM + model-elsewhere
mechanically converts the comparison from "model vs SPY" to "SPY + active alpha
in dispersive regimes vs SPY" — ≥ benchmark by construction, plus the regimes
where IC is real.
**Theory:** regime-switching allocation (Ang–Bekaert 2002); cross-sectional
momentum needs dispersion — calm low-vol uptrends have the least
(rank-signal-to-noise scales with cross-sectional spread); Grinold–Kahn: don't
spend breadth where IC≈0.
**Evidence test:** replay cut-3 with the policy toggled; the gate's
benchmark-relative criterion is the success metric. **No new model artifact
needed** — this can be evidenced immediately.

### WS-4 — BULL_CALM signal research (model iteration, weeks)
**What:** why does ranking die in calm bulls? Hypotheses to test in order:
(a) **dispersion starvation** — cross-sectional spread of fwd-60d excess
returns collapses in CALM; measure spread-conditional IC;
(b) **factor mismatch** — momentum/trend features dominate the 172; in CALM the
payoff rotates to quality/earnings-revision/carry-type signals (test by
IC-decomposing feature groups per regime);
(c) **horizon mismatch** — 60d theses in CALM get repriced by slow drift, not
events; test 20d/40d label variants.
Remedies, contingent on diagnosis: regime-conditional feature weighting or a
CALM-specialist head; NOT a full architecture change first.

### WS-5 — Label engineering (pairs with WS-4)
**What:** replace/augment `fwd_60d_excess` with (a) **triple-barrier labels**
(de Prado) so the label matches how positions actually exit (stops/protection),
and/or (b) non-overlapping or overlap-weighted sampling (M6 showed the 60×
overlap inflates apparent IC and confounds placebos), and/or (c) explicit
**ranking losses** on shorter horizons aligned to the rebalance cadence.
**Why:** the M6 verdict makes this the highest-confidence *training-signal*
defect we know about.

### WS-6 — Ensemble the scorers (cheap stabilizer)
**What:** mean-of-z(PatchTST, GBDT alpha158_fund, alpha158 linear) as a
candidate scorer; the shadow-scoring monitor (revived in pipeline #114) starts
producing the primary-vs-alt comparison data immediately.
**Why:** model averaging reliably stabilizes rank IC; we already maintain all
three families.

---

## 2. Recommended sequencing

**Phase A (this week, parallel):** WS-1 (data refresh) + WS-2 (two point-in-time
retrains) + WS-3 (regime-conditional allocation replay on cut-3).
Phase A alone can plausibly produce a **passing artifact**: refreshed data fixes
live-IC drag, complete cuts fix coverage, and the CALM→SPY policy directly
attacks the benchmark-relative criterion *where the model has no IC*.

**Phase B (next):** WS-4 diagnosis → targeted CALM remedy; WS-5 label work folded
into the next retrain; WS-6 ensemble evaluated via the shadow monitor data.

**Non-negotiables (unchanged):** every candidate goes through
`run_wf_gate.py` (3 cuts + sanity battery); promotion only via the weekly gate;
no gate loosening; the account trades nothing that hasn't beaten the benchmark
test. If Phase A+B still can't beat SPY net of costs, the honest terminal
conclusion is that this universe/horizon/cost structure has no harvestable edge
for these models — and the system should default to the benchmark sleeve while
research continues. That outcome is a success of the gate, not a failure of the
process.

## 3. Concrete deliverables (each as its own PR)
1. WS-1: fundamentals refresh run + feature-drift (PSI) report.
2. WS-2: 2 PIT retrains + extended manifest + fresh gate run (verdict attached).
3. WS-3: `regime_allocation` config proposal + cut-3 A/B replay evidence.
4. WS-4: spread-conditional IC + per-regime feature-group IC decomposition note.
5. WS-5: triple-barrier / overlap-corrected label spec for the next retrain.
6. WS-6: 4 weeks of shadow-monitor comparisons → ensemble decision memo.

## References
- Ang & Bekaert (2002) *International Asset Allocation with Regime Shifts*, RFS.
- Grinold & Kahn (1999) *Active Portfolio Management* (IR = IC·√BR; IC≈0 ⇒ no breadth spend).
- López de Prado (2018) AFML ch.3 (triple-barrier), ch.7 (overlapping labels / sample uniqueness).
- Moskowitz, Ooi, Pedersen (2012) *Time Series Momentum*, JFE (dispersion & momentum payoff).
- Bailey & López de Prado (2014) *Pseudo-Mathematics and Financial Charlatanism* (why the gate stays strict).
