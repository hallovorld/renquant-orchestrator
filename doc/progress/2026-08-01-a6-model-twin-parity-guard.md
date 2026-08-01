# A6's model twin: named, measured, and finally under the tripwire (GOAL-3, orch#728)

## The gap (#728)

The twin drift guard covered registry item C3 (four broker twins, pinned divergence)
while A6 — "15.4k LOC training umbrella-resident + diverged model twin", the OTHER P1
twin — had no guard, and its twin pair had never even been NAMED.

## Named and measured `[本次实测 2026-08-01]`

Across the umbrella's **284** `scripts/*.py` and the model repo's **188** `.py`
basenames there is exactly **ONE** same-name pair:

```
scripts/fit_calibrator_alpha158_fund.py            (umbrella, 575 lines)
src/renquant_model_gbdt/fit_calibrator_alpha158_fund.py  (model,   354 lines)
DIVERGED — 655 diff lines
```

It is the calibrator fitter — the component class behind the four fingerprint
fail-close incidents (the 25-minute playbook file), which makes silent drift here a
live-trading risk, not a style problem. Same-basename is a deliberately narrow net:
renamed twins are NOT claimed covered; #728's registry question (retire vs pin) stays
open for the operator.

## The guard

* `MODEL_DIVERGED_TWINS` spec + `model_diverged_twins` manifest section (dual pinned
  shas, exactly like the broker twins) + `check_model_diverged_twins` wired into the
  run; either side changing against the pin FAILs with the re-pin instruction.
* `resolve_repos` gains the `model` sibling; manifest build now requires it.
* Regenerated manifest committed (+8 lines) — the deliberate review act.

Live run: **24 pass / 0 fail / 0 skip** (was 14 before the kernel-shelf sections, 23
before this). Tests: twin files 36 passed (+3: manifest shape asserts the pair IS
diverged; drift on the umbrella side fails; drift on the model side fails). Full suite
**5391 passed, 2 skipped** `[本次实测]`.
