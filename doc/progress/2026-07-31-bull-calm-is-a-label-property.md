# The criterion is satisfiable in ONE regime — and BULL_CALM fails its placebo leg, not its skill floor

**Bottom line `[本次实测 2026-07-31]`.** orch#673 ended with a question I set myself:
*"is `BULL_CALM`'s regime sanity criterion satisfiable by any model at all?"* It is —
**`BEAR` clears it on 11 of 11 artifacts**, with a placebo IC at **4%** of its real IC.
~~So both hypotheses #673 named are wrong.~~ **WITHDRAWN — see orch#680, merged.** That
demonstration comes from **55 dates in the panel's smallest regime**, which is
insufficient evidence of generalisability to the regimes that carry the panel, so the
exclusion does not follow. What survives is the decomposition below: in `BULL_CALM` and
`CHOPPY` a **60-day-shifted label out-ranks the aligned one**.

## The decomposition

The enforced conjunct is
`passed = mean_ic ≥ min_mean_ic AND |placebo_ic| ≤ max(0.005, 0.5·|aligned_real_ic|)`,
with `min_mean_ic = max(0.0, 0.25·|real_ic|)`.

| regime | placebo leg passes | median `placebo / real` |
|---|---:|---:|
| **BEAR** | **11 / 11** | **0.04** |
| BULL_CALM | **0 / 11** | **2.15** |
| CHOPPY | **0 / 11** | **6.61** |

`BULL_CALM`'s `mean_ic` is **positive on every artifact** (0.0211–0.0234), so it is **not
failing the skill floor** — it fails the placebo ceiling. The shifted label is doing
2.15× the ranking work the aligned label does.

## What that means, stated carefully — CORRECTED after orch#680

~~**Not "the gate is mis-specified."** BEAR passes it comfortably, every time, with the
same code and the same shift.~~ **WITHDRAWN.** One regime passing on 55 dates does not
exclude mis-specification; it excludes only the strictly weaker claim that the criterion
passes *nowhere*. orch#680 (merged) states this: *"#677's exclusion of the
mis-specification hypothesis does not stand."*

**Not "the models are bad"** — this half survives, and it is a decomposition fact rather
than an inference: `BULL_CALM`'s `mean_ic` is positive on every artifact (0.0211–0.0234)
and the failing conjunct is the **placebo ceiling**, not the skill floor.

~~> **It is a regime-local label property.** In BULL_CALM the cross-section is persistent
> enough that a label from 60 days ago still ranks it.~~ **WITHDRAWN — that is a
mechanism, and nothing here measures it.** A persistent cross-section would produce this
profile; so would other things. The measured statement is narrower and is all that is
claimed:

> **In `BULL_CALM` a 60-day-shifted label out-ranks the aligned one — median
> `placebo / real` = 2.15 — so the criterion fails on the placebo leg while the skill
> floor is met.** Why the shifted label ranks that well is **not established here**.

**Why these are struck rather than deleted.** This PR was open while orch#680 corrected
it and merged, so for a period `main` carried a document saying this one's conclusion did
not stand while this one still asserted it. That is the seventh instance on this
programme of a claim outliving its own correction, and the second where the correction
and the claim sit in different artifacts.

## The bar a model would have to clear by skill alone

The ceiling is `0.5·|aligned_real_ic|`, so passing against the observed placebo requires
`real_ic ≥ 2 × placebo_ic`. On the newest artifact that is **≈ 0.119** against today's
**0.025** — roughly **4×** the current real IC in that regime `[DERIVED from the frozen
CSV]`. That is the concrete, checkable target, and it replaces "the gate rejects
everything" with a number.

## Why this matters for GOAL-6

`BULL_CALM` carries **399–449 evaluation dates**, by far the largest regime in the panel.
A criterion that cannot certify the model's largest regime is what produces the 0-for-11
unaided pass rate #670 measured — and now the reason is specific enough to act on:
either raise real IC there by ~4×, or change what the placebo is being compared against.

**Neither is done here.** Changing an enforced gate constant is a capital-path decision
and needs its own preregistration.

Tests: 5, including the control that a passing regime must exist or the two hypotheses
stay indistinguishable.

---

## Guard added 2026-07-31 — the withdrawn sentences cannot return unmarked

`tests/test_regime_sanity_decomposed.py` now carries the corrected scope in its module
docstring, and the satisfiability test is renamed
`test_the_criterion_IS_satisfiable_SOMEWHERE` so the executable artifact stops asserting
the width the document retracted. A test named after a conclusion is a claim too.

---

## CORRECTION 2026-08-01 — the evidence became reproducible, and two published numbers moved

Reviewed `[codex on orch#677]`: *"the new evidence CSV is still an unproven snapshot: it
records only artifact names, with no source paths, immutable fingerprints, producer/run
identity, or extraction command, and the tests validate the CSV rather than its inputs."*

Correct. `ops/renquant104/regime_sanity_extract.py` now emits the table **from the
artifacts**, binding every row to its **source path** and **content sha256**, recording
**which key answered** (canonical vs legacy), and writing a manifest with the **exact
command**. `--verify` re-reads every path the CSV names and recomputes every digest.

### And that is how two of my own published numbers were caught

The original CSV was a hand-built **11-artifact subset**. The reproducible extraction
covers **30 artifacts × 4 regimes = 120 rows**, and the medians move
`[本次实测 2026-08-01]`:

| regime | published | reproducible (n=30) | verdict |
|---|---|---:|---|
| BULL_CALM | `> 2.0` | **1.98** | **below its stated bar** |
| CHOPPY | `> 6.0` | **2.63** | **far below** |
| BEAR | `< 0.10` | 0.046 | holds |

**The direction survives and is what the section claims** — a shifted label out-ranks the
aligned one in both failing regimes and does not in BEAR. **The magnitudes were an
artefact of the subset.** The tests now assert the measured values with a margin; moving a
threshold to fit would be the inverse of what this work was for.

### The skill floor, tested directly

The prose floor `max(0, 0.25·|real_ic|)` is now asserted per row, not proxied by
`mean_ic > 0` — a positive IC below the floor would have failed the conjunct while the
old test passed.

**Testing it surfaced a second thing**: the artifact also stamps its own `min_mean_ic`,
and **it is not the prose rule** — it varies per **artifact** (0.0136 … 0.02 across this
corpus), where the prose floor varies per **regime**. Both hold here. Both are now
asserted. Which rule generates the stamped value is **not** claimed: inferring a formula
from a value is the mistake this cycle already corrected twice.

### Three guesses of mine, corrected in one review cycle

1. Extractor field names (`aligned_real_ic`, `ceiling`) that **do not exist** in the gate
   block — the real key is `placebo_60_aligned_real_ic`, and `ceiling` is **derived** as
   `max_placebo_ratio × aligned`. The first emit wrote empty columns.
2. `stamped_min_mean_ic` asserted flat at `0.02`, read off the deployed artifact alone.
3. Row counts pinned at 11, from the subset.

Each was caught by running the thing rather than by reading it. **Derivation now comes
from the stamped thresholds in each artifact, never from a remembered constant** — and the
regenerated values match the original CSV to the last digit where they overlap.

Suite: **4837 passed, 2 skipped**.

---

## ROUND 3 — the analysis unit was wrong, and the "enforced" floor is not the enforced floor

Two blockers `[codex on #677]`, both correct, and the second is the sharper one.

### 1. Thirty names, twelve distinct byte contents

> *"the manifest contains repeated `content_sha256` values under many artifact names, yet
> the new medians are presented as a 30-artifact corpus… aliases/rollbacks of identical
> bytes can dominate a median."*

Measured `[VERIFIED — the committed CSV, 2026-08-01]`: **30 named artifacts, 12 distinct
content digests**, and **one digest appears under 13 names**. So a single set of bytes was
contributing 13 of 30 "observations".

**The analysis unit is now the unique content digest**, alias counts retained in
`analysis_unit.json` for audit. It moves the headline materially:

| regime | median `placebo/real` by NAME (n=30) | by DIGEST (n=12) | placebo leg |
|---|---:|---:|---:|
| BULL_CALM | 1.9826 | **2.1507** | 0/12 |
| BEAR | 0.0463 | **0.0441** | **12/12** |
| BULL_VOLATILE | 2.0623 | **2.4753** | 0/12 |
| CHOPPY | 2.6276 | **6.6059** | 0/12 |

`CHOPPY` moves by **2.5×**. The qualitative finding survives — `BEAR` clears on every
unique artifact and nothing else clears on any — but every published ratio was computed
over a multiset in which one artifact counted thirteen times.

### 2. `min_mean_ic = 0.25·|real_ic|` is NOT the enforced floor

> *"the document still calls `min_mean_ic = 0.25*abs(real_ic)` the enforced floor while
> the extractor shows the stamped floor is a different artifact-level value."*

**It matches 0 of 120 rows** `[VERIFIED — the committed CSV]`. The stamped
`sanity_regime_ic.min_mean_ic` is an **artifact-level constant** — identical across all
four regimes of a given artifact, taking **7 distinct values** across the corpus, most
commonly a flat **0.02**. For `panel-ltr.alpha158_fund.json` the stamp is `0.02` in every
regime while the formula would give 0.0867 / 0.0109 / 0.0080.

So the formula is **withdrawn as a statement about what is enforced**. What is verified is
the stamp itself:

- **enforced floor** = the artifact's stamped `min_mean_ic` (constant per artifact);
- **enforced placebo ceiling** = `0.5` — `stamped_max_placebo_ratio` takes exactly **one**
  value across all 120 rows, so that half of the conjunct *is* confirmed.

Where the formula came from is unidentified, and naming its producer is a prerequisite
before any document calls it enforced again. **This matters beyond bookkeeping: the
"bar by skill alone" arithmetic in this chain was computed from the unstamped formula, so
that number is unverified until it is recomputed against the stamped floor.**
