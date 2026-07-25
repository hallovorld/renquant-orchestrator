# 2026-07-24 — Prereg: horizon × features × regime, FACTORIAL (supersedes #573)

STATUS:    superseded (relocated)
WHAT:      This PR originally added a design-only preregistration plus its
           (unwired, unrun) study script for a 3×4×2 fully-crossed
           horizon×features×regime factorial, superseding #573's OFAT
           design. Six review rounds fixed every other finding (progress-
           doc shape, single-owner commit history, the anchor-gate
           ordering, the previously-unfrozen I1/I2/I3+M1-M3 interaction/
           Holm analyzer) but one structural finding persisted across all
           six: `scripts/research_factorial_hfr.py` rebuilds folds/
           normalization and trains XGB cells via
           `renquant_model_gbdt.panel_data` / `panel_trainer` — model-
           training research, which `renquant-orchestrator/CLAUDE.md`'s
           hard boundary ("do not implement model training internals
           here") forbids in this repo.
           **This fix pass completes the relocation.** The prereg doc
           (`doc/research/2026-07-24-factorial-horizon-features-regime-
           prereg.md`), the runner (`scripts/research_factorial_hfr.py`),
           and the analyzer tests
           (`tests/test_research_factorial_hfr_analyzer.py`) are removed
           from this PR and now live, byte-for-byte (only the test's
           `_SPEC_PATH` relative-path depth changed for its new
           `tests/gbdt/` home), in
           [`hallovorld/renquant-model#67`](https://github.com/hallovorld/renquant-model/pull/67).
           This PR is reduced to this progress doc alone — it carries no
           training-internals code and no longer needs to.
WHY/DIR:   Three studies this session (regime-conditional feature
           selection, #573's feature dimensionality, label horizon) each
           varied one factor and held the rest constant — an OFAT design
           that cannot detect an interaction; full design rationale now
           lives with the study in `renquant-model#67`. The repo-placement
           question this PR could not resolve in six rounds is the umbrella
           multi-repo code-placement rule: new code goes in the repo that
           owns the subject (model research -> `renquant-model`), never
           the orchestrator baseline. Once `renquant-model#67` is
           reviewed/approved and the study is eventually run there,
           `renquant-orchestrator` may coordinate the resulting sealed,
           versioned run bundle — but must not re-implement the study
           itself.
EVIDENCE:  n/a — this PR now carries no code and makes no IC/Sharpe or
           model claim. The relocated artifact's own evidence block
           (`--probe`/`--help` against the real panel, 6/6 analyzer unit
           tests passing) is recorded in `renquant-model#67`'s progress
           doc (`renquant-model:doc/progress/2026-07-24-factorial-horizon-
           features-regime-prereg.md`).
NEXT:      (1) Review/merge `renquant-model#67` — the study's actual home
           now. (2) Once that lands, this now-empty orchestrator PR either
           closes with no further action, or the reviewer directs a
           minimal orchestrator-side coordination stub (out of scope for
           this fix pass — a new design decision, not a mechanical
           follow-up). (3) Running the study itself (an actual `--out`
           run, ~87 min at the exploratory 5-fold default or the anchor-
           validated 3-fold default) still requires explicit operator
           direction, not an autonomous unattended fix pass
           (`AGENT-RETROSPECTIVE.md` §5, C3) — unchanged from before this
           relocation.

## What this PR is now

A **progress-doc-only record** of the relocation decision. The
preregistration, runner, and analyzer tests moved to `renquant-model#67`
per that repo's ownership of model-training research (umbrella multi-repo
code-placement rule). See `renquant-model#67` for the full design
rationale, the frozen decision rule, and the study's own evidence block.

## Tests

No code remains in this PR to test. The relocated runner/analyzer were
re-verified in their new home (`renquant-model#67`): `python -m py_compile
scripts/research_factorial_hfr.py` passes, `python
scripts/research_factorial_hfr.py --help` exits 0, and `pytest
tests/gbdt/test_research_factorial_hfr_analyzer.py` — 6 passed.

## Memory tier touched

None yet — no verdict exists; the study has not been run.
