# model freshness monitor — per-recipe label horizon (amends #213, #423 round-3)

STATUS:   shipped for review (2026-07-02). Observe-only code (no promotion, no trading impact, no
          pin change). 62/62 unit tests green (was 58 pre-change: 5 new, 6 existing fixtures
          updated) on `RenQuant/.venv` python 3.10; full `renquant-orchestrator` suite (1075 tests)
          green alongside. Implements amendment A1 of
          `doc/design/2026-07-01-104-105-design-review-amendments.md` (#223, merged) against the
          shipped `src/renquant_orchestrator/model_freshness_monitor.py` (#213).

WHAT:     `_expected_lag_calendar_days` (the function that widens the panel fast-axis tiering
          thresholds for the `label_observation_cutoff` axis, umbrella #423 round-3) previously
          keyed the widening width on a single hardcoded module constant
          (`_LABEL_OBSERVATION_LOOKAHEAD_BDAYS = 60`), applied to EVERY artifact this monitor reads
          regardless of which of the three populations (per-ticker tournament, prod XGB panel,
          shadow PatchTST panel) produced it. #223 amendment A1 requires "each model family
          declares its label horizon in its recipe ... not hardcoded to one constant" — a future
          model family with a different fwd-label horizon would silently get the fwd_60d assumption
          applied to it, mis-widening its threshold in either direction.

          Fix: `read_artifact_freshness` now reads the artifact's OWN stamped `lookahead_days`
          field (stamped by `hf_patchtst_scorer.py` / `train_production_model.py::build_artifact`
          in the RenQuant umbrella repo — confirmed by reading both call sites directly, not
          assumed) and threads it into `_expected_lag_calendar_days`, which now returns
          `(compensation_lag, diagnostic_lag)`: `compensation_lag` is the value actually used to
          widen a tier, and is `None` whenever the binding axis needs compensation but the artifact
          did not stamp a valid positive `lookahead_days` — the caller then fails CLOSED to
          `TIER_UNKNOWN` rather than guessing the documented 60-BD default, consistent with this
          module's existing "trained_date must never certify freshness" discipline (module
          docstring). `diagnostic_lag` is always computed (using the default when the stamped value
          is missing/invalid) and surfaced in the `unknown`-tier `detail` string purely for
          troubleshooting ("what the widened threshold would have been if the fwd_60d default were
          assumed") — never used to certify a tier. `ArtifactFreshness` gained a
          `lookahead_days_stamped: int | None` field (echoed in `as_dict()`) so the actual per-
          artifact value used is observable, not just inferred from the detail string.

          Mirrors an equivalent fix landed in RenQuant's `shadow_scoring.py` (PR #426 round 5,
          same Codex-review-driven pattern: a missing/invalid stamped horizon must not be silently
          assumed to be fwd_60d) — same review-driven bug class hit twice in two sibling codebases
          this session, now closed in both with a consistent shape.

WHY/DIR:  operator directive is per-recipe axis semantics (#223 A1: "the expected-lag widening is
          derived per recipe (fwd_60d panel != per-ticker tournament != any future short-horizon
          model), not hardcoded to one constant"). Today only the prod XGB panel binds on
          `label_observation_cutoff` in practice (the per-ticker tournament binds on
          `live_train_end`/`trained_date`; the shadow panel binds on
          `effective_selection_cutoff_date`, which has no inherent lag), so this fix has NO observed
          effect on the current live populations as long as the prod panel's `lookahead_days` is
          stamped (confirmed: `train_production_model.py::build_artifact` stamps it unconditionally,
          derived from `infer_label_lookahead_days(label_used)`) — the change only matters the
          moment an artifact's stamped horizon is missing/wrong, or a future model family with a
          different horizon starts flowing through this same axis, at which point it now fails
          closed instead of silently mis-widening.

EVIDENCE: `PYTHONPATH=<sibling repos>:src RenQuant/.venv/bin/python -m pytest
          tests/test_model_freshness_monitor.py -q` -> 62 passed. New tests:
          `test_missing_lookahead_days_fails_closed_not_guessed` (the exact regression: same
          fixture as the existing healthy-panel test minus `lookahead_days` now reads `unknown`,
          not `healthy`), `test_invalid_lookahead_days_fails_closed_not_guessed` (0 / negative /
          non-numeric all fail closed, never coerced to 0-lag or the 60d default),
          `test_per_recipe_lookahead_scales_the_widened_threshold` (a 20-BD-horizon artifact widens
          by its OWN 28-calendar-day lag, not 84d — proven by a raw age that reads WARN under a
          20-BD widening but would read HEALTHY under the 60-BD default, i.e. the per-artifact
          value is actually BINDING, not merely threaded through unused),
          `test_axis_without_inherent_lag_ignores_lookahead_days` (a non-label-observation binding
          field is unaffected by a missing `lookahead_days` — only the axis that actually needs
          compensation fails closed). Six existing fixtures
          (`test_label_observation_cutoff_is_the_freshness_axis`,
          `test_label_observation_cutoff_lag_threshold_boundary`,
          `test_frozen_label_observation_cutoff_breaches_despite_lag_widening`,
          `test_fresh_unlabeled_rows_do_not_improve_panel_freshness`,
          `test_main_cli_panel_fresh_on_label_cutoff_with_lag_accounted`) updated to stamp
          `lookahead_days: 60` — matching what a real fwd_60d prod XGB artifact actually carries —
          so they keep testing the widening/tiering behavior they were written for, independent of
          the new fail-closed-when-unstamped concern.
          `PYTHONPATH=... RenQuant/.venv/bin/python -m pytest -q --continue-on-collection-errors`
          (full repo) -> 1075 passed, 3 skipped, no new failures. `python3 -m py_compile` clean.

SCOPE:    observe-only, unchanged from #213. No change to any model, pin, config, or the daily run;
          no change to which populations bind on which field (`DATA_CUTOFF_FIELDS` priority order
          untouched) — only HOW the label-observation axis's widening width is derived once it
          binds.

NEXT:     none required by this PR. If a future model family with a genuinely different label
          horizon is added to any of the three populations, this fix is what makes its freshness
          read correctly (or fail closed if its recipe forgets to stamp `lookahead_days`) without
          further code changes here.

## Round 2 (Codex CHANGES_REQUESTED — self-declared horizon was unvalidated and unbounded)

Codex: "The replacement still lets an unvalidated artifact value determine its own freshness
allowance. `read_artifact_freshness` coerces `lookahead_days` with `int(...)` and then adds the
resulting business-day lag directly to every threshold. Therefore `true`, `60.9`, `'60'`, and an
accidental `6000` are all accepted; a stale artifact can certify itself healthy by stamping an
arbitrarily large horizon. ... Bind the horizon to a known recipe/provenance schema: validate an
exact JSON integer (reject bool, floats, strings), require a recognized recipe/schema ID, verify
that recipe's expected horizon or an explicit allowed range."

Correct finding: round 1 fixed the MISSING/invalid-type-but-falsy case (`0`, negative, non-numeric
strings via the `try: int(...) except` fallback to `0`) but never rejected a value that
successfully coerces via `int(...)` — `int(True) == 1`, `int(60.9) == 60`, `int("60") == 60` all
silently passed, and there was NO upper bound at all, so a corrupted/tampered `lookahead_days` of
any size would widen every threshold by that many business days.

**Fix.** New `_validate_lookahead_days(value)`: strict `isinstance(value, int) and not
isinstance(value, bool)` type check (rejects bool, float, str, None outright — no coercion
attempted), AND an explicit plausible-range check (`_MIN_PLAUSIBLE_LOOKAHEAD_BDAYS=1`,
`_MAX_PLAUSIBLE_LOOKAHEAD_BDAYS=120` — 2x the documented fwd_60d convention). This repo's
artifacts carry no existing recipe/model-kind identifier field this monitor could bind an
expected-horizon lookup against (confirmed: grepped the whole file for any `kind`/`recipe`/
`family` concept — none exists; all three populations this monitor covers currently use fwd_60d
in practice), so the explicit-range approach is the most defensible available binding today — a
per-recipe expected-value table is the natural follow-up once/if artifacts gain a real recipe
identifier (mirrors the training-side `provenance_schema_version`/`recipe_id` stamping landing
concurrently in RenQuant's `shadow_scoring.py`, PR #426). Both call sites (`_expected_lag_calendar_days`
and `read_artifact_freshness`) now route through this single validator — no separate coercion
logic left in either. `ArtifactFreshness` gained `horizon_validated_against` (e.g.
`"explicit_range[1,120]bdays"`), echoed in `as_dict()`, so the validation basis is part of the
observable record for whichever artifact certified a tier under a stamped horizon, not just an
internal pass/fail.

**Evidence:** `PYTHONPATH=<sibling repos>:src RenQuant/.venv/bin/python -m pytest
tests/test_model_freshness_monitor.py -q` -> 64 passed (was 62; +2). New tests:
`test_lookahead_days_rejects_non_int_types_and_implausible_magnitude` (bool `True`/`False`, float
`60.9`, numeric string `"60"`, implausible `6000`, and boundary `-1` all fail closed to
`TIER_UNKNOWN` with `lookahead_days_stamped is None` and `horizon_validated_against is None` —
proving none of them silently widen a threshold), `test_lookahead_days_accepts_valid_in_range_int_and_records_validation_basis`
(a genuine in-range int still validates and widens correctly — regression check — and the exact
upper bound `120` is accepted while `121` is rejected, pinning the boundary precisely).
`py_compile` clean on both changed files.

**Scope:** unchanged — observe-only, no model/pin/config change. The explicit-range bound (120
business days) is itself a judgment call, not derived from any per-recipe contract (there isn't
one yet); documented in-code as the reason and the natural upgrade path.

## Round 3 (Codex CHANGES_REQUESTED — the range itself was still not validation)

**Finding.** Round 2's `[1, 120]` range closed malformed/unbounded self-certification, but a
broad "plausible" range is not validation against the recipe that actually produced the artifact:
any artifact could still stamp e.g. `120` and receive roughly 2x the legitimate freshness
allowance, entirely self-declared, with nothing checking it against that artifact's real recipe.
Since every population this monitor currently covers (per-ticker tournament, prod XGB panel,
shadow PatchTST panel) uses the documented fwd_60d convention, the only value that can actually
be validated as legitimate right now is exactly `60` — not a range around it.

**Fix.** `_validate_lookahead_days` now requires the value to equal `_EXPECTED_LOOKAHEAD_BDAYS`
(= `_LABEL_OBSERVATION_LOOKAHEAD_BDAYS` = 60) exactly, on top of the existing strict-type check
(bool/float/str still rejected outright). `_MIN_PLAUSIBLE_LOOKAHEAD_BDAYS`/
`_MAX_PLAUSIBLE_LOOKAHEAD_BDAYS` removed (no longer a range concept). `horizon_validated_against`
now records `"exact_fwd60d_interim[60]bdays"`. Documented explicitly, in-code, as a TEMPORARY
INTERIM with a named upgrade path: once this repo's artifacts carry a verified recipe/schema
identifier (mirroring RenQuant PR #426's `provenance_schema_version`/`recipe_id` stamped at
training time and bound into the artifact's own immutable fingerprint), replace the single
hardcoded 60 with an explicit `_EXPECTED_HORIZON_BY_RECIPE` map keyed on that verified id.

**Tests.** `test_lookahead_days_accepts_valid_in_range_int_and_records_validation_basis` narrowed
to just the exact-60 acceptance case (the old 120/121 boundary assertions no longer apply — there
is no boundary anymore). New `test_lookahead_days_non_exact_60_fails_closed_even_when_plausible`:
every one of `61, 59, 1, 120, 20, 90` — values round 2's range would have accepted — now fails
closed to `TIER_UNKNOWN` with `lookahead_days_stamped is None`. New
`test_non_exact_60_lookahead_is_not_silently_widened`: proves the interim is actually BINDING on
the widening computation (not just a separate flag) by picking a raw age (48d) that reads
`TIER_WARN` under a genuine 60-BD widening but `TIER_UNKNOWN` when the artifact stamps a
self-declared 20-BD horizon instead — same raw age, different stamped horizon, different (and
correct) disposition. The old `test_per_recipe_lookahead_scales_the_widened_threshold` (which
demonstrated a 20-BD artifact getting its own scaled widening) is superseded — that scaling
capability is exactly what round 3 removes until real recipe-binding exists; the RenQuant #426
fingerprint-bound pattern is where per-recipe scaling should return once this repo has it.

**Evidence:** `PYTHONPATH=<sibling repos>:src uv-managed-python3.10 -m pytest
tests/test_model_freshness_monitor.py -q` → 65 passed (was 64; net +1: one test narrowed to a
strict subset, two new tests added, one obsoleted test replaced). `py_compile` clean. (Local
verification required a scratch `uv venv --python 3.10` — the checked-out system `python3` is
3.9, which cannot even import this repo's own `renquant_common` dependency chain due to `str |
None` PEP 604 union syntax requiring 3.10+; this is a pre-existing environment fact, not
introduced by this round — CI itself runs on a correctly-versioned interpreter and stays the
authoritative check.)

**Scope:** unchanged — observe-only, no model/pin/config change.
