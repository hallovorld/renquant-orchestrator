# WF-gate calibration audit — pre-registration (is the gate, not the model, the binding constraint?)

**Question (operator-raised):** "a few weeks ago PatchTST made meaningful live trades; now the
gate has completely blocked it — is the gate the problem?"

## The timeline that motivates this `[VERIFIED — git log + live trades DB]`
- **2026-05-22:** PatchTST made **78 live buys** (the last live run with `n_buys>0`). commit `2b930ee`.
- **2026-05-24 → 06-06:** a wave of **fail-closed** gate additions landed in `run_wf_gate.py`:
  regime sanity (05-24), placebo-IC-vs-aligned comparison (05-24), **placebo threshold formula
  (05-25)**, trade-monotonicity gating (05-21/25), "fail closed on weak WF trade evidence" (05-25).
- **Since:** 0 live buys; every candidate (incl. the recent prune experiments) FAILs.

So the **bar moved right around when the model was trading**. Two readings, currently unresolved:
- **(A) gate over-blocks:** the retrofitted fail-closed checks reject a model that was usable;
  the placebo threshold is **ill-conditioned at IC≈0** (`max(0.005, 0.5·|aligned_real_ic|)` — the
  floor dominates when real IC is in the noise band, which it always is). [self-audit, PR #161]
- **(B) gate is correct, late:** the 05-22 model traded on placebo/leaked signal; the new checks
  catch exactly that. Its live record is only 35 trades, payoff 0.89, and the "76% win" was *sim*.

**This audit resolves A vs B. It does NOT loosen or bypass the gate** (that is a HARD rule). If
the gate is mis-calibrated, the output is a *proposed calibration fix* (itself reviewed/gated);
if the gate is correct, that settles the "model has no edge" reading. The audit informs; it never acts.

## Tests (pre-registered)

**T1 — decisive: run the EXACT 05-22 live model through TODAY's gate.**
Recover the live artifact at commit `2b930ee` (`git show 2b930ee:…/panel-transformer.{json,pt}`),
read-only. Run today's full WF gate. Record per-check pass/fail. **Falsification criterion:** for
"gate over-blocks" (A) to be supported, the 05-22 model must **pass the pre-05-24 checks but fail
specifically the post-05-24 additions** (regime sanity / placebo threshold / monotonicity). If it
also fails the older/core checks, that points to (B) — the model, not the new gate.

**T2 — placebo-threshold soundness.** Audit `max(0.005, 0.5·|aligned_real_ic|)`: at IC≈0 the 0.005
floor dominates → characterize its false-reject behavior. Is a fixed floor the right rule when the
real IC is in the noise band, or should the test be "insufficient power → abstain" rather than
"fail"? Compare the floor against the IC distribution of a known-acceptable reference model.

**T3 — regime-sanity / monotonicity power.** Is `BULL_CALM` monotonicity failing on **< the 30-trade
minimum** (a low-sample artifact) or on a genuine ≥30-sample negative spearman? Read `n_per_regime`
from the gate metadata across the recent runs.

## Reliability / constraints
- **Read-only recovery** of the 05-22 model via git; all eval in isolated `/tmp`; **no production
  path written**; **no gate code changed in this PR** (audit only).
- **Anti-bias guard:** the more *hopeful* answer is (A) "gate's fault" — so the falsification
  criterion for A is pre-committed above, to avoid motivated reasoning toward it.
- Any resulting gate-calibration change is a **separate, reviewed PR**, never a bypass.

## Decision after
- T1 shows model fails only the new post-05-24 checks + T2 shows the floor is ill-justified →
  **gate calibration is (part of) the binding constraint** → propose a reviewed calibration fix.
- T1 shows model fails core/old checks too, or T2 shows the threshold is sound →
  **the model genuinely lacks edge** → the lever is signal/features, and the gate is vindicated.
- This resolves the central ambiguity the whole effort has been stuck on: model-vs-gate.
