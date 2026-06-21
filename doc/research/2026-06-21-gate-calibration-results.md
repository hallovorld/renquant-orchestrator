# WF-gate calibration audit — interim results (T2/T3 done; T1-exact pending)

Results for the pre-registered audit (`2026-06-21-gate-calibration-audit.md`, PR #162).
**The evidence so far does NOT support the hopeful "gate over-blocks a good model" reading —
it leans toward "the model genuinely lacked cross-sectional edge; the gate correctly enforces a
standard the old path didn't check."** I raised the gate-doubt myself, so I am flagging that the
data is going against my own hypothesis, on purpose, to avoid motivated reasoning.

## The honest reconciliation of the operator's observation
The operator is **right that the gate is the proximate cause**: the bar moved. PatchTST made 78
live buys on 2026-05-22; the placebo / regime-sanity / monotonicity fail-closed checks landed
2026-05-24/25; 0 buys since. `[VERIFIED — git log + live trades DB]`

**But "the bar moved" ≠ "a good model was killed."** What the new checks newly *enforce* is
cross-sectional skill, and the live model never had it:

- **The 05-22 live model's OWN recorded `oos_mean_ic = −0.0246`** (negative) — it measured negative
  cross-sectional IC at its own training time (05-17, `panel-transformer`). `[VERIFIED — artifact json]`
- A fresh rebuild of the same 60d recipe also failed: `real_ic = −0.0227`. `[VERIFIED — gate log]`
- So the model that traded was already negative-IC; the old buy path (raw-score threshold) let it
  trade **without** a cross-sectional-IC check; the new checks add that check. **It is not
  over-blocking a skilled model — it is enforcing skill the model never had.**

**How did a negative-IC model win ~83% of 35 live trades?** Most likely **market beta + early exits
+ tiny sample**, not stock-picking skill: cross-sectional IC measures *relative ranking* of names;
a model can ride a rising market and cut winners early (payoff 0.89) and win most trades while
ranking names no better than chance. The "76% win" headline was **sim**, not live. (35 live closed
trades is far too few to claim skill either way.)

## T3 — BULL_CALM monotonicity is REAL, not a low-sample artifact (my hypothesis REFUTED)
I hypothesized BULL_CALM monotonicity might fail only on `<30` samples (sparse corpus). The data
refutes that: across the 3 WF cuts, **n = 93** BULL_CALM round-trips, **spearman(entry_rank_score,
realized pnl) = −0.24** — a genuine *inversion* (higher model score → lower realized return), well
above the gate's `min_n = 30` and `small_n_inversion_min_n = 10`. So the monotonicity failure is a
real ranking inversion in BULL_CALM, not an artifact. `[VERIFIED — round_trips.csv, n=93]`

## T2 — placebo-threshold floor is ill-conditioned at IC≈0, but it is a SYMPTOM not the cause
`threshold = max(0.005, 0.5·|aligned_real_ic|)`. In every run `|aligned_real_ic| < 0.01`, so the
0.005 floor dominates and the placebo-ratio test is ill-conditioned — **true**. But the reason the
real IC is in the noise band is that the **models have ~zero cross-sectional signal**; no threshold
rule would cleanly *pass* a model with no signal. The floor isn't wrongly failing a good model; it
is failing models that have nothing to distinguish from placebo. *(Possible refinement: at low
power the gate could explicitly "abstain / insufficient evidence" rather than "fail" — a labelling
nicety, not a model-admitting change.)*

## Verdict so far (honest, against the hopeful reading)
- **The gate looks vindicated, not broken.** The live model recorded negative IC itself; the new
  checks enforce cross-sectional skill it never had; the monotonicity inversion is real (n=93).
- **NOT yet done — T1-exact:** running the **exact live weights** (`panel-transformer.pt`, kind
  `panel_transformer`) through today's *full* gate needs a recipe-matched WF corpus (a build).
  Launching it for confirmation. Its own recorded IC already indicates the result.

## Implication for the real lever
This points the binding problem **upstream to signal/features/label**, not to a mis-calibrated gate
and not to the horizon. The honest next step remains a **properly-powered signal-existence
diagnostic** — does any extractable cross-sectional edge exist in this feature set at all? — not
loosening the gate. **No bypass.**
