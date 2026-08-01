# GOAL-7 — "deployed to shadow" is four mechanical preconditions, and now they are checkable

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-7 (standalone momentum → shadow)

## Why

GOAL-7's three model-side PRs are waiting on review, so the model half is blocked. The
**path-to-live** half is not, and this programme's own rule says design it or do not ship:
a lane that is deployed but unseen is worth nothing, and its silence is indistinguishable
from health.

Each precondition below is one this programme has already watched fail somewhere else.

| # | precondition | where it was seen to fail |
|---|---|---|
| 1 | declared in the config the **runner** reads | twin-registry **R5** — two configs, inverted, runner takes the pinned one |
| 2 | the artifact resolves — **and under which base** | orch#694 — 3 declared paths, 2 bases, **no single base** resolves all three |
| 3 | the **sentinel** can see the lane name | orch#689 — an unmatched lane is silent, and silence reads as health |
| 4 | the artifact **loads** | a booster that cannot load is a skip, not an error |

## Measured on the two lanes that exist `[本次实测 2026-07-31]`

```
topdecile_clf_blend_leg                          PASS PASS PASS PASS   rc=0
hf_patchtst_pt07_strict_seed44_previous_primary  PASS PASS PASS SKIP   rc=0
a_new_momentum_lane (hypothetical)               FAIL FAIL FAIL FAIL   rc=1
```

The `.pt` checkpoint is **SKIPPED, not passed**, on check 4 — this checker only loads JSON
boosters, and reporting a pass it did not establish is the green-check-over-an-unread-field
failure in miniature.

### A negative result, stated because I expected the opposite

The sentinel's clf lane takes its name from
`os.environ.get("RQ104_CLF_LANE_NAME", "topdecile_clf_blend_leg")`, and that variable is
set in **no** installed plist — the same shape as the fail-closed flags measured in
orch#695, where the unset default was the *unsafe* one. **Here it is not:** the default is
exactly the name the pinned config declares, so unset is harmless.

That is true only by coincidence of the default matching, which is precisely why check 3
exists: a lane renamed in config and not in the sentinel's default would go invisible with
nothing to say so.

## What a passing preflight does NOT mean

It is **mechanical**. Passing says nothing about whether the model is any good, whether it
should be deployed, or whether the lane will produce a usable signal — and **a skipped
check is not a pass**. Both sentences are printed by the tool and asserted by tests,
because "4 PASS" is exactly the kind of line that gets quoted as a readiness verdict.

## For GOAL-7 specifically

A brand-new momentum lane fails all four today, and **that list is the work**: declare it
in the pinned config, place the artifact under a base that resolves, name it so the
sentinel matches it — exactly, or as `hf_patchtst_<suffix>` if it rides that lane — and
ship a loadable artifact. None of that is done here; the point is that it is now
enumerable instead of discovered from a silence.

Read-only: opens configs and artifacts, writes nothing, never invokes git, installs
nothing.

## Tests

17, mostly about this preflight's own failure modes — the ways it could hand out a green
light it did not establish: a missing config **fails** rather than passing vacuously;
multiple resolving bases are **reported, not silently chosen**; a prefix without the
separator (`hf_patchtstXYZ`) does **not** count as decorated; a JSON artifact with no
booster fails while a `.pt` is **skipped**; `main` **refuses to run** with no watched lanes,
since check 3 against an empty set would mean nothing; and the two "what this does not
mean" sentences are asserted present.

Suite: **5080 passed, 2 skipped** — run before the push.

---

## CORRECTION 2026-08-01 — two green paths that were not established

Reviewed `[codex on orch#699]`. Both correct, and both the same shape: **a check reporting
PASS on evidence it had not established.**

### 1. Ambiguity passed, then silently chose

`check_artifact` recorded multiple resolving bases **and returned `ok=True`**; `preflight`
then took `resolves_under[0]` and could exit `0`. That directly contradicts this module's
own sentence — *"which one the loader uses is not established here"*. **A check cannot both
refuse to name the authoritative base and quietly pick one.**

Now: more than one resolving base and no `--loader-base` → **`ok=None`, SKIPPED, not
passed**. Supplying `--loader-base` resolves it, and a declared base that does **not**
resolve the artifact **fails** even when other bases do — a lane that resolves only where
the loader does not look is not served.

### 2. "Loads" meant "the field is non-empty"

`check_loadable` tested that `booster_raw_json` was present and truthy. That is
**structural presence**, not loadability: a truncated or wrong-version booster passes it
and fails at serving time.

It now invokes the **canonical loader** — `xgboost.Booster.load_model` — on the artifact's
own bytes. If xgboost is unavailable the result is **SKIPPED with the distinction stated
in the message**: structural presence confirmed, loadability **not**.

**A fixture had to change with it, and that is the point.** `_artifact()` wrote
`{"booster_raw_json": "{}"}` — present and unloadable. It passed while the check only
looked at the field; the real loader correctly refuses it. A fixture that cannot load must
not be called *"fully wired"*, so the helper now trains a real 2-round booster.

### Live result

The clf lane still passes all four checks, now including a **real load**. `rc=0`.

24 tests (was 17). Suite: **5094 passed, 2 skipped**.

### A worktree hazard worth recording

`git stash pop` in this worktree restored a stash belonging to a **different branch**
(`goal4/ensemble-existence-evidence`), leaving a `DU` conflict and four unrelated G4
evidence files. Committing with `-A` would have pulled another lane's work into this PR.
Resolved by removing only the foreign index entry and committing **explicit paths** —
never `-A` when the working tree has residue whose origin is not certain.
