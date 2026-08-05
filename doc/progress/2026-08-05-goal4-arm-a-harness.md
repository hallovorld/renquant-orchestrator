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
| per-regime mean/median/std IC, hit rate, `n_dates`, `n_rows` | `regime_diagnostics(val, mu, label, regimes)` → `summarize_ic` |
| the 2× shifted-label placebo, per regime | `regime_shift_diagnostics(..., shifts=(120,))` |

So the harness is deliberately **thin**: it supplies inputs and applies the
frozen decision predicate, and **computes no statistic of its own**. A test
asserts that — no `spearmanr`, no `corrcoef`, no local `summarize_ic` — because
a second statistical harness beside a reviewed one is how two answers to the same
question appear.

## What it enforces

§6's four conditions, transcribed and individually testable
(`n_dates(BULL_CALM) ≥ 30`, `E1 > 0`, `E1 > max_k shuffle_ic_k` — the WORST of
the five fixed-seed replications — and `E1 > placebo_shift`), plus §3's rule that
**Arm A can never certify**: `certify()` raises `ArmMisuse` on an Arm A verdict
even when all four conditions hold, and a test proves exactly that case.

`NOT CERTIFIED` carries its registered meaning — *the member did not meet this
evidence standard*, **not** *the signal is absent* — with the conservative
predicate named as the reason.

## What is NOT here

- **The run.** Arm A is a compute batch over historical OHLCV and it is a
  separate, deliberate act; the harness exists so that act is one command and is
  reviewable against the registration beforehand.
- **Arm B.** Calendar-blocked: the served ledger has one row (cutoff 2026-08-02),
  labels mature ~2026-10-27, and the ≥30 BULL_CALM floor pushes certification to
  roughly 2027.

Suites: 14 new tests · 5649 passed, 2 skipped repo-wide.
