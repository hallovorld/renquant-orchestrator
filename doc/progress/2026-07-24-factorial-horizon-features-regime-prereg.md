# 2026-07-24 — Prereg: horizon × features × regime, FACTORIAL (supersedes #573)

STATUS:    in-progress
WHAT:      Adds a design-only preregistration (`doc/research/2026-07-24-
           factorial-horizon-features-regime-prereg.md`) plus its (unwired,
           unrun) study script `scripts/research_factorial_hfr.py`. Supersedes
           PR #573's OFAT design with a 3×4×2 fully-crossed factorial (horizon
           × features × regime). No results; the study has not been executed.
           Fix pass 1: repaired this progress doc's C5 fields and rebuilt the
           branch's commit attribution to single-owner history. Fix pass 2:
           moved the fold-count anchor gate before the training sweep so an
           unvalidated `--n-splits` fails closed immediately instead of after
           the full ~87-minute run (MED finding, review 3).
WHY/DIR:   Three studies this session (regime-conditional feature selection,
           #573's feature dimensionality, label horizon) each varied one
           factor and held the rest constant — an OFAT design that cannot
           detect an interaction, and the label-horizon result is a concrete
           candidate (a 60d cross-sectional forecast is near-hopeless in
           BEAR/high-vol while BULL_CALM plausibly has better SNR at longer
           horizons; a pooled OFAT read would average that crossover into a
           flat main effect). This design makes the three interactions (H×R,
           F×R, H×F) the PRIMARY hypotheses instead of an afterthought,
           directly advancing the same standing "does the panel-LTR need 172
           features, and at what label horizon" question #573 opened.
EVIDENCE:
  artifact:      scripts/research_factorial_hfr.py `--probe` / `--help` output
                 against the real panel (feasibility/power table only)
  prod or exp:   design-only; no training run, no write
  existing data: matches the power table in the prereg (BULL_CALM ~24
                 independent blocks registrable, BEAR ~6 registrable,
                 BULL_VOLATILE ~3 / CHOPPY ~1 NOT registrable); the fold-count-
                 aware fail-closed anchor from #573's review is carried
                 forward unchanged
  best-known?:   n/a — this PR asserts no IC/Sharpe claim; no cell has been
                 trained, so no trained-arm result exists yet
  scope:         "feasibility/power probe + frozen design only, on the real
                 panel, descriptive; zero cells trained"
NEXT:      Two items outstanding, both design/research judgment calls, not
           mechanical fixes — deferred to explicit operator direction per
           `AGENT-RETROSPECTIVE.md` §5 (C3: unbounded/unchecked-pointed work
           is not something an agent starts autonomously in an unattended
           fix pass):
           (1) repo placement — `scripts/research_factorial_hfr.py` rebuilds
           folds/normalization and trains XGB cells, which is model-training
           research per the multi-repo code-placement rule; it needs to move
           to `renquant-model` before any run produces results.
           (2) the primary interaction tests (I1/I2/I3) and the Holm family
           must be frozen as executable analysis code in this PR — the
           contrast formulas, conditioning, bootstrap statistic, and p-value
           calculation — not deferred to the results PR.
           (3) [fixed, fix pass 2] the default execution path used to run
           the full ~87-minute sweep before the anchor check could fail
           closed; the fold-count gate now runs immediately after arg
           parsing (before the panel loads or any cell trains) so an
           unvalidated `--n-splits` VOIDs in seconds, not 87 minutes.
           Once (1) and (2) clear, the study itself is the next bounded action.

## What this PR is

A **preregistration only**. Design + script, **no results, study not run**.
Supersedes `doc/research/2026-07-24-feature-set-dimensionality-prereg.md`
(PR #573) — not because that question was wrong, but because its *design* was.

## Why #573 is superseded — the OFAT defect

Three studies ran or were designed this session. **Every one varied a single
factor and held the others at an arbitrary constant.**

| study | conclusion | held fixed | how it dies |
|---|---|---|---|
| regime-conditional feature selection | NULL (−4.1%/yr, p=0.634) | label `fwd_20d`, rank composite | may only pay at `fwd_60d`, or only inside the production XGB |
| feature dimensionality (#573) | not yet run | label `fwd_60d`, pooled | reduction may hurt pooled, help per-regime |
| label horizon | 20d > 60d at 5d/20d eval (Bonferroni-surviving) | all 172 features, pooled | **best horizon may differ by regime** |

The third is not hypothetical: in a BEAR/high-vol tape a 60-day cross-sectional
forecast is near-hopeless, while BULL_CALM plausibly has better SNR at longer
horizons. A pooled read averages a real crossover into "20d is slightly better
everywhere". **OFAT cannot detect that.**

So the primary hypotheses here are the **interactions**, not the main effects.

## Design

3 × 4 × 2 = **24 cells**, fully crossed:

- **H** (training label): `fwd_5d` / `fwd_20d` / `fwd_60d`
- **F** (features): `all_172` / `dedup_r70` (69, label-free) / `nontechnical_14` / `random_14`
- **R** (regime): `pooled` / `specialist`

`all_172` vs `dedup_r70` isolates **redundancy**; `nontechnical_14` vs
`random_14` isolates **selection at fixed count** (per D3, if they tie the
finding is about model capacity, not feature quality — precommitted to
reporting that either way).

## The measurement problem this design had to solve

**Each cell has its own leakage floor, so raw IC is not comparable across
cells.** Label autocorrelation at the gate shift: `fwd_5d` −0.0009,
`fwd_20d` +0.0093, **`fwd_60d` +0.0489** — the 60d label self-predicts.

**This is very likely why E35 (2026-05-08) chose 60d.** It ranked horizons by
raw IC (+0.066 / +0.040 / +0.024) on a metric that systematically rewards the
longest label; the autocorrelation was measured a month later and the horizon
comparison was never re-run.

Primary response is therefore **placebo-clean IC** — every cell carries its own
matched placebo (same horizon/features/regime/folds/seed, training labels
shuffled within date, validation labels real).

## Power was measured before registering, not assumed

Feasibility probe on the real panel:

| regime | specialist estimable | val dates | independent 60d blocks | |
|---|---|---|---|---|
| BULL_CALM | 5/5 folds | 1480 (68.6%) | ~24 | registrable |
| BEAR | 4/5 folds | 412 (19.1%) | ~6 | registrable |
| BULL_VOLATILE | 2/5 folds | 183 (8.5%) | ~3 | **NOT registrable** |
| CHOPPY | 2/5 folds | 82 (3.8%) | ~1 | **NOT registrable** |

**Precommitted: only BULL_CALM and BEAR may carry a per-regime verdict.** The
other two are reported for completeness and are invalid at any significance
level by construction. Runtime measured at **≈ 87 min**.

## Frozen decision rule

- **Primary = 3 interaction contrasts** (H×R, F×R, H×F). I1 significant ⇒ this
  session's horizon conclusion *and* E35's are both retracted. I2 significant ⇒
  #573 is void as designed.
- Main effects are **secondary** and read only after the corresponding
  interaction resolves; a main effect under a significant interaction is
  reported as "not interpretable marginally", not as a result.
- **Holm–Bonferroni over 7 registered tests**, family α = 0.10. Everything else
  is exploratory and may not reach `VERDICTS.md`.
- Block bootstrap with **block = the evaluation label's horizon** (not a
  constant 60), sensitivity at 2× reported.
- Multi-seed sign stability required.
- **All interactions null ⇒ the OFAT reads are rehabilitated.** That is a real
  possible outcome and would vindicate the earlier designs — it is not a
  failure of this study.
- **Carried from #573, hard:** an unaudited `nontechnical_14` / `sec_fund`
  result is precommitted **INCONCLUSIVE** for any feature-strategy claim until
  `renquant-base-data` fundamentals ingestion is PIT-audited. Those 5 columns
  carry 54.2% of booster gain — look-ahead there would manufacture exactly the
  result the study is looking for.
- **E42v2 clause:** a contrary IC result does **not** overturn E42v2's portfolio
  sim (fwd_60d APY +18.5%/Sharpe 0.52 vs fwd_20d +10.7%/0.14). Different metric;
  reconciling them needs a P&L study, named as successor, not claimed here.
- **No result authorizes a config change.** Changing the label is a *strategy*
  change (holding period, turnover, tax), per `2026-06-08-overlapping-label-and-gate-architecture` §2c.

## Carried forward from #573 review

Two Codex findings on the #573 branch are incorporated here rather than lost:

1. **Fold-count-aware anchor, fail-closed.** `ANCHOR_IC_EXPECTED` was validated
   only at 3 folds while the script defaults to 5 — comparing across fold
   counts could spuriously VOID a valid run or pass an unvalidated one. Now any
   non-validated fold count is VOID unless explicitly overridden, and that path
   is exploratory-only.
2. **H3 PIT guard hardened** from a caveat to the precommit above.

## Six questions for the reviewer

Listed in prereg §8. The two I am least sure of:

- **Is 24 cells over-fitting the design to the data?** With 7 registered tests
  and 24 cells there is room to tell a post-hoc story. Is the Holm set tight
  enough, or should cells outside the registered contrasts not be computed?
- Is `fwd_20d` the right primary eval horizon given the ~8d realized hold, or
  should primary be `fwd_5d`?

## Tests

`../RenQuant/.venv/bin/python -m pytest -q --ignore=tests/test_bundle_seal.py`
→ **4261 passed, 2 skipped**. `ruff check` clean. `--probe` reproduces the
power table above against the real panel.

`tests/test_bundle_seal.py` collection error is **pre-existing on `origin/main`**
(verified), not introduced here — this PR is additive (1 doc + 1 unwired script).

## Memory tier touched

None yet — no verdict exists. Script is not wired into any job and is read-only
against production (refuses output paths containing `artifacts/prod`,
`artifacts/sim`, `strategy_config`, `/data/`, `walkforward`, `panel-ltr`).
