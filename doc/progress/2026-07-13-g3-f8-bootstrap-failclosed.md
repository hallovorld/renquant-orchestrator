# G3 F-8: bootstrap alias fail-closed

Date: 2026-07-13 (rounds 1-3), 2026-07-14 (round 4)
PR: fix(bridge): fail-closed bootstrap alias for pipeline kernel imports (#514)
Companion: renquant-pipeline PR #198 (kernel-ownership manifest)
Finding: F-8 from 2026-07-04 umbrella compliance audit (PR #444)

## Problem

`bootstrap_multirepo` catches all exceptions from pipeline kernel imports
and silently falls back to the umbrella copy. Only `kernel.preflight` and
`kernel.panel_pipeline` are force-aliased with fail-closed semantics. A
pipeline-side regression (missing dep, syntax error) silently reverts part
of the live run to umbrella code.

## Fix (r3: pipeline-declared ownership contract)

Removed both the `UMBRELLA_ONLY_STEMS` allowlist (codex r1) and the
directory-as-manifest + minimum-count heuristic (codex r2).

The redesign consumes `NON_OWNED_KERNEL_STEMS` declared by the pinned
`renquant_pipeline.kernel` package (companion PR pipeline #198):

- **Owned stems** (not in `NON_OWNED_KERNEL_STEMS`): imported from
  pipeline, fail-closed on any import error.
- **Non-owned stems** (e.g. `meta_label`): pipeline import is skipped
  entirely; routed to an explicit alias target (`renquant_backtesting.
  meta_label`), which also fails closed if unavailable.
- **Missing contract**: if the pinned pipeline does not declare
  `NON_OWNED_KERNEL_STEMS`, the run fails closed (can't verify ownership).
- **Uncovered non-owned stems**: if pipeline declares a non-owned stem
  that orchestrator has no alias target for, fails closed.
- **No owned modules**: empty pipeline kernel directory fails closed
  (replaces the arbitrary `_MIN_PIPELINE_KERNEL_MODULES = 10`).

## Tests (rounds 1-3)

7 tests:
- Owned module import failure → RuntimeError (fail closed)
- Umbrella-only module absent from pipeline dir → not aliased (OK)
- Multiple owned failures → all reported in the error
- Missing `NON_OWNED_KERNEL_STEMS` → RuntimeError
- Non-owned stem skips pipeline import, uses alias target
- Non-owned stem alias target failure → RuntimeError (fail closed)
- No owned modules discovered → RuntimeError
- Uncovered non-owned stem → RuntimeError

## Round 4: bind the path-identity check to the pinned package contract

Codex's round-2 review flagged a second, independent issue in the same
review that raised the `NON_OWNED_KERNEL_STEMS` inconsistency above:

> Also do not use the arbitrary `_MIN_PIPELINE_KERNEL_MODULES = 10` as a
> path-identity control. It permits any wrong directory with ten importable
> files and will become stale when the package layout changes. Bind the
> discovered module inventory to the pinned package contract instead.

Round 3 (a concurrent session on this same branch, commit `ff373c09`)
replaced the magic number `10` with a check for whether ANY owned modules
were discovered (`if not owned_stems: raise ...`). That is safer than a
hardcoded `10`, but it is still not what Codex asked for: a wrong pipeline
directory containing even one unrelated importable file would silently
satisfy `owned_stems` being non-empty, and the check still has no relation
to what the pinned pipeline actually claims to ship.

This round adds the real fix: **renquant-pipeline companion PR
https://github.com/hallovorld/renquant-pipeline/pull/198** adds
`renquant_pipeline.kernel.OWNED_KERNEL_STEMS` — the positive-side companion
to the already-existing `NON_OWNED_KERNEL_STEMS`, declaring every stem the
pinned pipeline guarantees to ship in `kernel/`. `bootstrap_multirepo` now
reads this declaration (`getattr(pipeline_kernel, "OWNED_KERNEL_STEMS",
None)`) and, after the existing owned-module-import-failure check has
already run, verifies the stems it actually discovered (and successfully
aliased) are a **superset** of everything pipeline declares owned. By this
point any owned stem that is present but broken has already raised via the
existing `failed` check, so a stem missing from this comparison means it
was never found in the directory at all — exactly the "wrong/empty
checkout" case Codex described, now tied to the real pinned contract
instead of a headcount.

**Fallback for older pins (round 4 only — REMOVED in round 5, see below)**:
if the pinned pipeline predates `OWNED_KERNEL_STEMS` entirely (`getattr`
returns `None`), there is no structural inventory to compare against.
Rather than either silently disabling the sanity check (treating "no
declaration" as "trust whatever is on disk") or hard-failing an otherwise-
valid older pin outright, this falls back to the coarse "no owned modules
discovered" guard that round 3 already had — it only catches the total-
emptiness case for a pin old enough to predate the declaration, everything
else is unaffected.

**This fallback was itself a fail-open gap and was removed in round 5 —
see "Round 5" below. Do not reintroduce it.**

### Tests (round 4)

- `test_bootstrap_fails_closed_on_missing_declared_owned_stem`: a kernel dir
  missing modules the pinned pipeline declares owned (via
  `OWNED_KERNEL_STEMS`) fails closed, naming exactly the missing stems (not
  a raw count) — the actual reproduction of Codex's complaint.
- `test_bootstrap_allows_complete_declared_owned_inventory`: a kernel dir
  that covers everything declared passes silently — proves this is a real
  equivalence check, not just a stricter failure mode.
- `test_bootstrap_fails_when_no_owned_modules` docstring updated to clarify
  it now exercises the legacy fallback path (no `OWNED_KERNEL_STEMS`
  declared at all), not the primary structural check. (Renamed to
  `test_bootstrap_fails_when_owned_stems_missing` in round 5 — the
  fallback it was documenting no longer exists; see below.)

### Cross-repo pairing verification

Ran a standalone script pairing this worktree against renquant-pipeline
PR #198's real worktree (both src roots on `sys.path`, no mocks): the real
`renquant_pipeline.kernel.OWNED_KERNEL_STEMS` (49 stems) against the real
`kernel/` directory (50 entries incl. `meta_label`) passes with zero
RuntimeError. Tampering with the real, imported `OWNED_KERNEL_STEMS` object
to add a stem absent from disk (`totally_made_up_stem_xyz`) makes
`bootstrap_multirepo` fail closed citing that exact stem name — proving the
check reads the pipeline's live declared attribute, not a hardcoded value.

### Full suite verification (round 4)

Both suites run under the umbrella's pinned interpreters (orchestrator:
`../RenQuant/.venv/bin/python`, Python 3.10; pipeline: its own
`.venv/bin/python`, Python 3.11 — matching each repo's own `Makefile`
interpreter resolution) with orchestrator's `pythonpath` pointed at
pipeline PR #198's real worktree content (not the stale default sibling
checkout) to exercise the real new pipeline declaration:

- **orchestrator**: 3730 passed, 5 skipped, 5 failed. The 5 failures
  (`test_cli.py::test_ledger_query_*`) and a further 8 pre-existing
  collection errors (ignored above) all trace to one unrelated root cause:
  the shared scratch `renquant-common` sibling checkout is stale (missing
  merged PRs #30/#31 that added `renquant_common.decision_ledger`).
  Reproduced identically with this round's diff stashed out — confirmed
  pre-existing and unrelated.
- **renquant-pipeline**: 1729 passed, 8 skipped, 3 failed. The 3 failures
  (2 in `test_replay_d6_conventions.py`, 1 in
  `test_xgboost_scorer_contract.py`) reproduce identically with this
  round's diff stashed out on the same worktree — pre-existing, unrelated,
  and already documented as such in round 3's verification.

### Note: companion PR renumbered #198 → #199

renquant-pipeline #198 merged the `NON_OWNED_KERNEL_STEMS`-only state
before this round's pipeline commit landed on that branch (a race between
this session's push and Codex's merge of the prior state, both against the
same branch this round). The `OWNED_KERNEL_STEMS` companion this round
depends on is carried by a fresh PR on the same branch instead:
https://github.com/hallovorld/renquant-pipeline/pull/199.

## Round 5: remove the round-4 fallback entirely (final)

Codex's round-5 review of the round-4 landing:

> The positive inventory is the correct replacement for the magic
> module-count check, but the rollout is still fail-open with respect to
> the very identity contract it introduces. When `OWNED_KERNEL_STEMS` is
> absent, r4 falls back to the r3 "nonzero owned modules" path. That
> permits an old pipeline pin, or a wrong package with one importable
> module, to start without the pinned inventory verification.
>
> Require `OWNED_KERNEL_STEMS` together with `NON_OWNED_KERNEL_STEMS`;
> absence of either must fail closed. Then land pipeline #199 (rebased onto
> #198), update the umbrella to pin #199 plus this orchestrator revision,
> and attach a real bootstrap smoke result against those exact pins. This
> is an atomic stable-interface migration. The temporary compatibility
> fallback and the claimed path-identity guarantee cannot coexist.

The round-4 "fallback for older pins" section above (only catching the
case where the kernel directory yields zero owned modules AND
`OWNED_KERNEL_STEMS` is absent) was exactly the gap: an old pipeline pin, or
a wrong package, that happens to have at least one importable "owned-
looking" module on disk and no `OWNED_KERNEL_STEMS` declaration would
silently skip the structural check entirely (`owned_stems` non-empty →
neither the `isinstance` branch nor the `elif not owned_stems` branch
fires). That is precisely the "count what's on disk instead of verifying
the pinned contract" failure mode this whole fix exists to close.

### Fix (commit `bb6ecf99`)

Removed the round-4 fallback unconditionally. `OWNED_KERNEL_STEMS` is now
required exactly like `NON_OWNED_KERNEL_STEMS` already was — absence of
either raises `RuntimeError` immediately, with no path that falls back to
counting modules on disk:

```python
owned_declared: frozenset[str] = getattr(pipeline_kernel, "OWNED_KERNEL_STEMS", None)
if owned_declared is None:
    raise RuntimeError(
        "[multirepo] fail-closed: pinned renquant_pipeline.kernel does not "
        "declare OWNED_KERNEL_STEMS — pin a pipeline version >= #199"
    )

missing_owned = sorted(frozenset(owned_declared) - set(owned_stems))
if missing_owned:
    raise RuntimeError(...)
```

There is no supported "older pin" case anymore: this is landed as an
atomic migration together with pipeline #199, so the pinned pipeline
commit orchestrator resolves against always declares both frozensets by
construction.

### Tests (round 5)

`test_bootstrap_fails_when_no_owned_modules` (which documented and
exercised the now-removed fallback) was renamed to
`test_bootstrap_fails_when_owned_stems_missing` and now asserts the
unconditional-requirement message instead of the old "no owned kernel
modules" message. The three tests that exercise non-owned-stem handling
(`test_bootstrap_umbrella_only_module_not_in_pipeline_dir`,
`test_bootstrap_non_owned_stem_skips_pipeline_uses_alias`,
`test_bootstrap_non_owned_stem_alias_target_fails_closed`) each gained an
explicit `OWNED_KERNEL_STEMS=frozenset({"sizing"})` in their mocked kernel
namespace — they were previously passing only because the round-4
fallback silently accepted their non-empty `owned_stems`, which is no
longer a valid basis for those tests to pass.

### Status: both PRs merged, pin bump prepared

- orchestrator PR #514 (this fix): merged 2026-07-14, commit `bb6ecf99` /
  merge `bfb935e4`.
- pipeline PR #199 (`OWNED_KERNEL_STEMS`, rebased cleanly onto pipeline
  main after PR #198 merged): merged 2026-07-14.
- Umbrella pin: `renquant-pipeline`'s pin was already advanced past #199 by
  a routine fleet bump. `renquant-orchestrator`'s pin was stale at PR #451
  (2026-07-10) and had not been advanced past #514 — the pin-bump PR
  closing that gap, with a real non-mocked `bootstrap_multirepo()` smoke
  test against the exact pin-target commits, is
  https://github.com/hallovorld/RenQuant/pull/481.
