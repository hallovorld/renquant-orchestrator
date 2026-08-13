# orch#799 — FEASIBILITY & POWER FINDING: why the option-B prereg cannot be written yet

STATUS: **NOT a preregistration. This document authorizes nothing.** An earlier
revision was titled and presented as a FROZEN preregistration for the
blend-substitution WF promote gate. It could not be one: the decisive paired
decision rule cannot be frozen today, and the measurement in §3.1 is why.

**Any future option-B implementation needs a NEW, complete, independently
reviewable preregistration. It inherits nothing from this document** — not the
rule sketch, not the thresholds, not the acceptance list. The unclosed findings
recorded here are recorded as *defects*, not as specification.

What this document IS: the measured feasibility result for the option-B
estimand, plus the defects found while attempting to freeze it. It is kept
because that result exists nowhere else in the repo — closing the branch would
strand it, and the conditional reference-rule recommendation
(`doc/design/2026-08-11-orch799-blend-prod-reference-rule.md`, orch#972) neither
carries it nor should, since its scope is the reference *rule* and not the power
of testing it.

## 3.1 THE BLOCKER — the decision rule is not testable at usable power

Measured from the pinned manifest
`backtesting/renquant_104/artifacts/sim/walkforward_manifest_gbdt_prod_recipe_calibrated.json`
(sha256 `4febb6af7155a468…`)
`[VERIFIED — read 2026-08-12; key is `retrains`, not `rows`/`folds`]`:

| | |
|---|---|
| declared `cadence_days` | 21 |
| observed consecutive cutoff gaps | min 21, median 21, max 21 (uniform) |
| span | 2023-10-02 → 2026-03-02, 882 days |
| manifest rows | 43 |
| `lookahead_days` (label horizon `h`) | **60**, on every row |

**21-day spacing against a 60-day forward label means each fold overlaps two to
three neighbours in outcome window, so 43 rows are not 43 independent trials.**
Under a deterministic non-overlapping subsample — start at the earliest cutoff,
greedily take the next cutoff ≥ `h` days later, no phase choice and no tuning:

| | nominal | independent |
|---|---|---|
| n | 43 | **15** |
| one-sided exact sign test, α ≤ 0.05 | k ≥ 28 | **k ≥ 12** |
| actual α | 0.0330 | **0.0176** |
| power at true win-rate 0.65 | 0.56 | **0.17** |
| power at true win-rate 0.80 | 0.99 | **0.65** |

**Power 0.17 at a plausible effect.** An earlier revision of this document
quoted 0.56; that figure assumed 43 independent units and is **retracted**.

**Two escape routes were considered and deliberately NOT taken here**, because
each is a design decision needing its own preregistration rather than a
paragraph in this one:

1. **Block-aware paired resampling** would use the overlapping folds more
   efficiently, but reintroduces the distributional assumptions this repo has
   been bitten by — block length must exceed `h` (a block length equal to the
   horizon is the known defect) and ρ₁ must be estimated, not assumed.
2. **Prospective accumulation** costs ~60 days per additional independent unit,
   so reaching even n_eff = 30 is roughly 2.5 years.

**Consequence.** A promotion gate may legitimately accept under-promotion — its
error is the status quo, which never promotes at all. What it may not do is
present an independence calculation that does not hold as a valid rejection
threshold. Until an inference unit is chosen that respects the overlap, and its
α and power are stated for a declared minimum effect, the option-B gate change
should not be implemented.

## Defects recorded (NOT specification)

- **`W` / `N` are fictions.** An early draft froze "z-blend weights W" and
  "z-normalization params N". `BlendPanelScorer.score` is an *unweighted* sum of
  per-component cross-sectional z-scores, `ddof=0`, computed at scoring time;
  `ranking.blend_weights` is absent from the served config. The object to pin is
  the pipeline commit supplying the combine rule.
- **The evaluation surface is mutable.** `_resolve_manifest` globs
  `walkforward_manifest*.json`, keeps `recipe_validated` ones, and sorts by
  `manifest_rows_checked` **descending** (`run_wf_gate.py:860-877`) — two of the
  four present manifests have 43 rows and two have 39, so a new file changes the
  comparison surface with no code change. Any future prereg must pin the
  manifest by digest, resolved once and stamped in the receipt.
- **The placebo bar was mis-transcribed.** Both placebo verdicts are computed but
  the authoritative one is selected by mode; under `DEFAULT_PLACEBO_MODE =
  "absolute"` the decision rests on the time-shift ceiling alone, while `margin`
  and `real_ic_floor` feed the opt-in `difference` verdict only
  (`run_wf_gate.py:276,500-520`). An early draft listed all three together,
  freezing a hybrid the gate has never applied.


---

## What was deleted, and why deletion rather than fencing

An option-B rule sketch (problem statement, option-A rejection, the
blend-substitution rule, a no-leakage protocol, an implementation-feasibility
gate, and an acceptance list) stood here across earlier revisions.

**It is deleted, not fenced.** Twice I tried to keep it as "background, clearly
marked not-frozen", and twice normative text survived inside it — "this document
freezes them", "This prereg preserves the current bar", "If it can, implement
§3", "Acceptance (when implemented)". A divider does not neutralise sentences
that contradict it, and each round left something that could be read as the
specification this document says it is not.

**Nothing of value is lost.** Per the STATUS above, a future option-B
implementation needs a NEW, complete, independently reviewable preregistration
that inherits nothing from here — so a sketch it may not inherit is not
background, it is a hazard. What the next author needs is above the divider: the
measured feasibility blocker (§3.1) and the recorded defects, which is exactly
what this branch established and what a fresh prereg must start from.

The full sketch remains in this branch's git history for anyone who wants it.
