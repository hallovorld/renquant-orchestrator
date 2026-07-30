# AC6 R4: which bundle can carry override provenance — measured   (PR pending)

STATUS:    delivered
WHAT:      Adds `ops/run_bundle_schema_audit.py`, a read-only tool that measures
           persisted run bundles against the shared `LiveRunBundle` schema, and
           records what it found on the 7 bundles that exist. Answers the design
           question AC6 R4 left open instead of arguing it.
WHY/DIR:   GOAL-5 AC6 R4 (issue #564) asks which bundle should carry the governed
           override's provenance and notes that no validator currently rejects a
           bundle missing it. Picking a home by inspection would have been a guess;
           the measurement below makes one of the two candidates clearly wrong.
EVIDENCE:  §1. No production behaviour changes — the tool is read-only and is not
           wired into any run path.
NEXT:      R4 can now be specified: the daily bundle needs its own schema with
           `extra="forbid"`, or `LiveRunBundle` must declare the provenance fields.
           Wiring either into the daily path is a separate PR with its own A/B,
           because a fail-closed validator on a live run surface can stop a run.

CORRECTIONS: the first revision inferred `would_validate` from the presence of the
`is_required()` fields and never invoked the shared validator. Codex BLOCKER, and
correctly: a bundle can carry every required key and still fail on a field type or a
cross-field rule, which would have made the central measurement --- and the schema
decision resting on it --- unsound. The audit now calls
`validate_live_run_bundle` and records its error text.

**The headline numbers did not change** (7 of 7 still fail to validate, 0 conformant),
but they are now MEASURED by the validator instead of inferred
`[VERIFIED — ops/run_bundle_schema_audit.py on .subrepo_runs, exit 1]`.

**And running the real validator immediately found something the approximation had
hidden, which strengthens §1's conclusion rather than weakening it:** the
`is_required()` set (`source`, `decision_trace`, `order_intents`) **does not validate
on its own.** `LiveRunBundle` carries a cross-field rule — *"requires at least one
state source: state_mutations, execution_audit, or submitted_orders"*
`[VERIFIED — validate_live_run_bundle on a required-fields-only dict]`. So the
schema's real admission condition is strictly larger than its required-field list,
and any future "just add the field and validate" patch would have been reasoning
against a requirement it could not see. `test_required_fields_alone_do_NOT_validate`
now pins exactly that gap.

## §1 EVIDENCE

Measured on every persisted bundle that exists — 7 of them, read-only
`[VERIFIED — ops/run_bundle_schema_audit.py /Users/renhao/git/github/RenQuant/.subrepo_runs, exit 1]`:

| finding | value |
|---|---|
| bundles examined | 7 |
| would pass `validate_live_run_bundle` | **0** (measured by the validator, not inferred) |
| reason | all 7 lack the required `source` field |
| the schema's real admission condition | larger than its required-field list — see the CORRECTIONS block |
| fields present in the daily bundle | 18 |
| fields the schema would **silently discard** | **13 of 18 (72%)** |
| conformant (validates AND keeps its fields) | **0** |

The discarded 13 are `account_snapshot, artifact_manifest, backtest_report,
data_manifest, dry_run, market_snapshot, output_files, run_id, run_type,
serving_bundle, stage_trace, strategy_config_hash, strategy_manifest` — that is
**every provenance field in the bundle**.

### Why that decides R4

`LiveRunBundle` does not set `extra="forbid"`
`[VERIFIED — LiveRunBundle.model_config, read in ops/run_bundle_schema_audit.py::schema_drops_unknown_keys]`,
so Pydantic drops undeclared keys. Therefore, had the override-provenance field
simply been added to the daily bundle and validated through this schema, the
result would have been a **green check over a discarded field** — the validator
would certify a document after throwing away the very thing it was added to
check. That is the same shape as every other guard-that-validates-the-wrong-object
on this programme: a missing or ignored input makes the check pass.

So R4's answer is not "wire the existing schema in". It is one of:
1. give the daily bundle its **own** schema with `extra="forbid"`, so an
   undeclared key is an error rather than a silent loss; or
2. **declare** the provenance fields on `LiveRunBundle` — in which case the
   daily bundle also has to start emitting `source`, since 7 of 7 lack it.

Either is a real change to a live run surface and belongs in its own PR with a
behaviour-invariance argument, which is why this PR stops at the measurement.

## §2 A claim I nearly made and retracted before writing it

While tracing this I found `PersistDailyRunBundleTask` referenced only from tests
by name, and was about to report that the orchestrator's bundle task has no
production caller. **That was wrong** — it is constructed in the `DailyRunPipeline`
task list at `src/renquant_orchestrator/daily.py:308`
`[VERIFIED — grep of src/renquant_orchestrator/daily.py]`. The grep that
suggested otherwise had excluded the definition line and happened to exclude the
call site too.

The related fact that IS true and bounded: the newest persisted bundle is dated
**2026-07-21** and only 7 exist
`[VERIFIED — mtime listing of .subrepo_runs/*/run_bundle.json]`. That is
consistent with `DailyRunPipeline` being the orchestrator's own contract-run path
while the production 104 daily runs through the umbrella's scripts — two different
runners. **Whether the production 104 daily persists a run bundle at all is NOT
established here** and is not claimed; `ops/daily_104.sh` does not exist in this
repo. Worth its own check, since CLAUDE.md makes persisting a bundle for every
full run a hard boundary.

## §3 Tests

13 new, in `tests/test_run_bundle_schema_audit.py`. Both failure modes are paired
with the negative case that proves the report comes from the defect and not the
fixture: a bundle missing `source` is rejected **and** a bundle with every
required field validates; a bundle carrying `override_provenance` is flagged as
losing it **and** `test_the_drop_hazard_is_read_from_the_schema_not_assumed` pins
`schema_drops_unknown_keys() is True` so that if the schema ever sets
`extra="forbid"` the test fails loudly and this recommendation gets re-derived
rather than silently outliving its basis.

Exit codes are tested too: an unreadable bundle and an empty sweep both return 2,
so a broken invocation cannot read as a clean audit. That mattered in practice —
my first check of the tool's exit code was piped through `tail` and reported 0
when the real code was 1.

## §4 Suite

| tree | result |
|---|---|
| `origin/main` @ 679af192, separate worktree | 5 failed, 4457 passed, 5 skipped |
| this branch | 5 failed, **4467** passed, 5 skipped |

`[VERIFIED — python3 -m pytest -q in both worktrees, all sibling checkouts on PYTHONPATH]`.
Same 5 pre-existing failures; delta is exactly the 10 tests added. Note the full
suite does not collect without `renquant_execution` and `renquant_model_gbdt` on
`PYTHONPATH` (12 collection errors identically on both trees otherwise) — an
environment fact, not a regression.

## §5 Live-surface impact

None. The tool is read-only, opens files and writes nothing, never invokes git,
and is not called from any run path.
