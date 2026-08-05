# 2026-08-05 — GOAL-4 step 1: the Arm A harness, built on the gate's own statistics

## Where this sits

The GOAL-4 census (orch#807/#809) ended with one ordered next step: **stamp
per-regime evidence for the slow momentum residual, the one other PROD member.**
The design for that measurement is frozen in
`doc/research/2026-08-05-goal7-momentum-per-regime-prereg.md` (orch#810). This
lands the harness that executes it. **It has not been run.**

## What I nearly built, and why I did not

My first plan was to reuse `renquant_model_momentum.evaluate_momentum_artifact`.
Reading it stopped that: its estimand is a **block-t on a candidate series** with
frozen positive/negative controls, gap-blocks and an MDE — a different question
from the registered one (mean per-date Spearman IC per regime). Forcing Arm A
onto it would have been the substitute-instrument error the ledger already
records: the retraction is honest, the substitute is the same error in new words.

My second thought was to write the statistics myself. Checking first — rather
than asserting absence — found that **the registered estimand already has an
implementation, and it is the gate's own**, the same code that produced the
BEAR/BULL_CALM numbers this whole line of work rests on:

| need | existing implementation |
|---|---|
| production regime per date | `build_regime_series(dates)` |
| per-regime mean of the per-DATE Spearman IC, plus median/std/hit-rate/`n_dates` | `regime_diagnostics(val, mu, label, regimes)` → `summarize_ic` |
| the 2× shifted-label placebo, per regime | `regime_shift_diagnostics(..., shifts=(120,))` |

**Not an exact identity, and the difference is named** `[codex on orch#816]`:
`regime_diagnostics` feeds `summarize_ic` the label as `g[label].clip(-0.5, 0.5)`.
§2 of the registration defines `E1(R)` against `fwd_60d_excess` and **does not
freeze that clipping step**. Clipping can create ties and so can move a Spearman
coefficient. So the correct statement is: *the gate's helpers compute the
registered quantity up to a label-clipping step the registration does not
specify* — which has to be resolved (adopt the clip in an amended registration,
or pass an unclipped label) **before Arm A is run**, not after seeing its number.

## Provenance is enforced at RUNTIME, not asserted in prose

An earlier version of this harness accepted any JSON from any source while the
write-up claimed it was "built on the gate's own statistics", and its test only
grepped the source — so a docstring mention satisfied it `[codex on orch#816]`.
The runner now REFUSES a payload whose `provenance.producers` does not name all
three gate helpers, and the refusal is tested per-missing-producer.

## What it enforces

§6's four conditions, transcribed and **individually** testable
(`n_dates(BULL_CALM) ≥ 30`, `E1 > 0`, `E1 > max_k shuffle_ic_k` — the WORST of
the five fixed-seed replications — and `E1 > placebo_shift`).

**And §3's arm boundary, which the first version did not actually hold.** It took
an `arm` argument and returned `CERTIFIED` for `arm="B"` — the frozen
distinction undone by passing a string, in an Arm-A-named runner, exposed on the
CLI `[codex on orch#816]`. There is now **no `arm` parameter, no `--arm` flag and
no Arm B path**: the outcome is always `EXPLORATORY — NOT A CERTIFICATION`, and
`certify()` **always raises**, including on a hand-built Arm B verdict. Arm B is
the served ledger, calendar-blocked to roughly 2027; its runner does not exist
and must not be faked here.

## What is NOT here

- **The run.** Arm A is a compute batch over historical OHLCV and it is a
  separate, deliberate act; the harness exists so that act is one command and is
  reviewable against the registration beforehand.
- **Arm B.** Calendar-blocked: the served ledger has one row (cutoff 2026-08-02),
  labels mature ~2026-10-27, and the ≥30 BULL_CALM floor pushes certification to
  roughly 2027.

Suites: 20 tests · 5642 passed, 2 skipped repo-wide `[VERIFIED — measured after the change]`.
