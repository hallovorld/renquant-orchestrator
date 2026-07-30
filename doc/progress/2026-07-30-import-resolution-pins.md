# Which copy runs, answered by resolution instead of grep   (PR pending)

STATUS:    delivered
WHAT:      Adds `ops/import_resolution_check.py` + a committed pin file recording,
           for every public symbol this repo imports from a sibling package, the
           module and package-relative file the object is actually DEFINED in. Wired
           into the run-surface drift scan so a change in which copy runs alarms.
WHY/DIR:   GOAL-3's registry (#623, merged) named the real defect: *"the failure is
           not that duplicates exist — some duplication is deliberate. The failure is
           that nothing in the repo tells you which copy executes."* In four of its
           seven rows a defect was filed or a fix written against a copy that does
           not run, two of them by me in one session. A registry documents that; a
           resolution pin makes it mechanical.
EVIDENCE:  §1 (14 symbols resolved and pinned, suite A/B, the drift-scan wiring
           proven reachable by test).
NEXT:      The pin covers this repo's dependency surface. The sibling-internal twins
           (#623 R1 public-vs-kernel, R7 twin-ness inside one function) need the same
           treatment in the repos that own them — deliberately not done here, see §3.

## §1 EVIDENCE

14 symbols pinned, all resolving, zero errored entries
`[VERIFIED — ops/import_resolution_check.py --emit, then --verify exit 0]`.
A sample of what the pin actually records:

| symbol | defined in | file |
|---|---|---|
| `renquant_common.load_scorer` | `renquant_common.contracts.scorer` | `renquant_common/contracts/scorer.py` |
| `renquant_common.validate_live_run_bundle` | `renquant_common.contracts.schemas` | `renquant_common/contracts/schemas.py` |
| `renquant_common.model_fingerprint.model_content_sha256` | `renquant_common.model_fingerprint` | `renquant_common/model_fingerprint.py` |
| `renquant_execution.get_broker` | `renquant_execution.factory` | `renquant_execution/factory.py` |

`__module__` is where the object was **defined**, not where it was re-exported from.
That difference is the whole mechanism: a package `__init__` can map a documented
name onto a different implementation than the one a reader finds by that name, which
is #623 R1 exactly.

Three of this repo's own incidents were the same question — which implementation a
name resolves to. `load_scorer` decides which scorer the shadow path serves;
`model_content_sha256` is why a root-level `training_contract` raises and orch#620
had to nest the contract under `metadata`, which then made the WF gate's static
sanity read the wrong panel; and `validate_live_run_bundle` accepts a bundle after
discarding 13 of its 18 fields (#624), so *which* validator that name resolves to is
load-bearing.

### Suite

| tree | result |
|---|---|
| `origin/main` @ 679af192, separate worktree | 5 failed, 4457 passed, 5 skipped |
| this branch | 5 failed, **4479** passed, 5 skipped |

`[VERIFIED — python3 -m pytest -q in both worktrees, all sibling checkouts on PYTHONPATH]`.
Same 5 pre-existing failures; delta is exactly the 22 tests added.

### It is a gate, not a tool nobody runs

`check_import_resolution()` is called from `run_surface_drift_check.main()`
(`com.renquant.run-surface-drift`, a scheduled job), and
`test_the_drift_scan_actually_calls_the_check` asserts the call is reachable from
`main` rather than merely defined. End-to-end run confirms it contributes
`import-resolution OK — 14 symbols resolve as reviewed` as an INFO line
`[VERIFIED — python3 ops/run_surface_drift_check.py]`. The scan's own exit 1 comes
from pre-existing findings, not from this check.

**Behaviour change to be explicit about:** an unimportable sibling package now makes
the drift scan alarm. That is intended — the orchestrator cannot run without its
siblings, so an unimportable one is a real run-surface defect — but it is a new
alarm condition on a scheduled job and should be read as such, not as noise.

## §2 Two mistakes this PR caught, both mine

**A grep character class without digits.** I built the symbol list with
`[A-Za-z_, ]+`, which silently truncated `model_content_sha256` to
`model_content_sha`. The first `--emit` therefore recorded an `error` entry for it.
Had the pin file been allowed to keep that entry, it would have been a baseline that
could never be violated — a check passing forever on a symbol that never resolved.
`test_the_committed_pin_file_is_well_formed_and_has_no_errored_entries` now makes
that impossible.

**A patch that silently did nothing.** My first wiring attempt anchored the call site
on `check_sentinel_receipt()`, which exists only on a *different* branch, so the
`str.replace` was a no-op while the function-insertion assert still passed. I had
asserted the first replacement and not the second. The test caught it, and the patch
script now asserts the call is present inside `main()` after the edit. This is the
same shape as the defects #623 catalogues: the thing you believe you changed and the
thing that runs are different objects.

## §3 Scope, and what is deliberately NOT here

Only symbols **this repo imports**. `renquant_pipeline`'s public-symbol-vs-kernel
split (#623 R1) and the twin-ness inside `is_wash_sale_blocked_with_cost` (#623 R7)
are real, but they are not part of this repo's dependency surface, and encoding a
sibling's internals here would be the boundary violation that #623 R3/R4 came from
in the first place. `test_every_pinned_symbol_is_one_this_repo_actually_imports`
enforces that boundary mechanically so the pin cannot quietly grow into a cross-repo
registry.

Paths are pinned **package-relative**, not absolute: the scheduled jobs execute from
`renquant-orchestrator-run`, not the dev checkout, and an absolute pin would fail for
the wrong reason on the machine that matters.

## §4 Live-surface impact

No `program_args` change, so `program_args_sha256` in `ops/launchd_manifest.json`
still matches and this cannot cause manifest drift. `--emit` prints and never writes;
the pin file changes only through a reviewed PR, the same rule the launchd manifest
follows — a surface that can silently re-baseline itself is not a pin.
