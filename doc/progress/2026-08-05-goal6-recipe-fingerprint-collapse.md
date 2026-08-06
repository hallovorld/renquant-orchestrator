# GOAL-6: the gate's admission key hides 36 artifacts and 8 different skill levels behind one identity

**Date:** 2026-08-05
**Lane:** GOAL-6 (model capability)

## Bottom line

GOAL-6 has been marked hard-blocked on bt#109 for 15 rounds. bt#109 **is** still
blocked (`OPEN | REVIEW_REQUIRED | reviews=0`). But the lane's central question —
*can the evaluation path distinguish model capability?* — is measurable without
it, and the answer is no `[VERIFIED — this session]`:

| | measured |
|---|---:|
| artifacts carrying `wf_gate_metadata` | 37 |
| distinct `candidate_recipe_fingerprint` | **2** |
| artifacts sharing `sha256:cfdd6cb8e950da0f` | **36** |
| `candidate_artifact_used` | **`false` on 37 of 37** |
| distinct `sanity_placebo_genuine_ic` under that one fingerprint | **8** |

The eight values: `+0.000791, +0.002093, +0.002888, +0.003288, +0.005251,
+0.005767, +0.008094, +0.009239`.

**The artifacts demonstrably differ. The key the gate admits on does not see it.**
36 candidates with eight distinct measured skill levels are, to the admission
logic, one thing. And `candidate_artifact_used=false` on every single one means
the gate has never scored a candidate's own booster — it evaluates the *recipe*,
then admits the *artifact*.

## Anchor corrections

- **"四工件同哈希" is wrong by 9×.** It is **36**, not 4.
- **`genuine_ic=+0.00079` is the MINIMUM of eight observed values**, not the
  recipe's number. Quoting it as *the* genuine IC states the most favourable-to-a-
  kill reading of a distribution as if it were a scalar. The max is `+0.009239`.
- Even that max is **less than half** the v3 criterion (`genuine_ic > 0.02`), and
  that criterion is `sanity_placebo_gate_mode=absolute_ceiling_enforced_v3_shadow`
  — **shadow-only, `sanity_placebo_v3_gating=false`, not enforced.**

## What this does NOT establish

**Not which artifact is better, and not that any of them is good.** The genuine_ic
spread proves the candidates *differ*; it does not clear any of them. Every
observed value is far below the (unenforced) bar. A reader must not take "the gate
cannot discriminate" as "there is something good the gate is missing" — the
spread is between +0.0008 and +0.0092, which is a spread between two small
numbers.

## The near-miss, recorded because it is the recurring one

My first scan looked for `recipe_hash`, `recipe_sha256`, and `hash`. All three
returned `None` from all 37 artifacts, and the scan printed **"distinct recipe
hashes: 1"**. I was one step from reporting *one hash across 37 artifacts* — more
dramatic than the truth and **entirely an artifact of field names I invented**.

The real key is `candidate_recipe_fingerprint`. This is the sixth time an
unverified key has produced a silent `None` that read like a measurement. The
probe now names every field it reads as a module constant, and a test asserts a
missing fingerprint surfaces as `<MISSING>` rather than collapsing into the
`None` bucket.

## Delivered

`ops/renquant104/wf_gate_discrimination_probe.py` + 11 tests. Reports
`discriminates=False` only when artifacts sharing one key carry **differing**
genuine_ic — sharing a key is not itself a defect when the things behind it are
identical, and a test pins that distinction. Refuses (exit 2) on zero artifacts
rather than reporting perfect discrimination from an empty scan. Excludes
`/diagnostics/` and `/bundle/` copies, with a test, after archived snapshots
inflated a reachability count 47× earlier today.

Live: **`NO DISCRIMINATION`**, exit 1.

## Next

1. This is the concrete reason GOAL-4 (ensemble) and GOAL-6 (capability) are both
   stalled on evidence: there is no admission path that can rank two candidates.
   Fixing bt#109 wires *real labels* into Stage-2 — necessary, and it does not by
   itself make the fingerprint discriminate.
2. The fingerprint should incorporate the candidate artifact's own content digest,
   or `candidate_artifact_used` should stop being `false` — the gate currently
   certifies a recipe and admits an artifact, and those are different objects.
