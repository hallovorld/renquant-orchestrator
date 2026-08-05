# 2026-08-05 — a stray symlink turned an isolated test root into the live umbrella

## I filed this wrong, and the correction is the finding

I opened orch#834 titled *"main is RED"* after a local suite run. **`main` is not
red.** CI is green on every PR in flight `[VERIFIED — `test:SUCCESS` on the open
PRs]`. The failure was **local to this workstation**, and I asserted a repo-wide
state from a one-machine observation — the exact move I keep catching elsewhere.

## What was actually happening `[VERIFIED — this session]`

`tests/test_scheduled_jobs.py::test_inventory_localizes_repo_root_paths` sets
`RENQUANT_REPO_ROOT=/private/tmp/RenQuant` and then asserts the rendered
inventory contains no `/Users/renhao/git/github/RenQuant`.

On this machine:

```
/private/tmp/RenQuant -> /Users/renhao/git/github/RenQuant   (symlink, created 11:56 today)
```

`default_repo_root()` ends in `.resolve()`, which **follows symlinks**. So the
"isolated" fixture root *was* the live umbrella, the inventory rendered live
paths, and the assertion failed for a reason that has nothing to do with
localisation. No code in this repo creates that symlink — it was made by hand.

## The part that is not a test artefact

> An operator who sandboxes a job with `RENQUANT_REPO_ROOT=/tmp/RenQuant` —
> a natural thing to do — is operating on the **live tree**, and nothing says so.

That is a live blast radius, not a pytest inconvenience.

**Production is unaffected today, and that was checked rather than assumed:**
8+ wrappers export `RENQUANT_REPO_ROOT`, every one to the real umbrella path,
and `/Users/renhao/git/github/RenQuant` is not itself a symlink `[VERIFIED]`.

So I have **recorded the behaviour rather than changed it**. `.resolve()` cannot
simply be dropped — tests point `RENQUANT_REPO_ROOT` at roots that do not exist,
and that must keep working (pinned by its own test). Changing a resolver eight
scheduled jobs depend on, at the end of a long session, on a hazard with no
current production exposure, is not the trade I want.

## What lands

- **Both hardcoded roots become real temp directories** — *created*, not merely
  named. The first version of one of them only built the string:
  `Path.resolve()` is non-strict, so it passed without ever establishing the
  isolation the record claimed `[codex on orch#835]`. A test that passes without
  establishing its stated condition is the same green-over-nothing this branch
  exists to close, arriving inside the fix for it.
- **A guard test** fails if any test re-introduces a `RENQUANT_REPO_ROOT` outside
  the tmp tree, so this cannot come back quietly.
- **The hazard is pinned as behaviour**: a symlinked root resolves to its target,
  a plain root does not change, and a non-existent root still works. If the
  redirect ever stops holding, the test says to re-derive this record rather
  than delete it.

Local suite: **5856 passed, 0 failed** (was 1 failed) · the symlink itself is
**left alone** — it is not mine, it appeared at 11:56 today, and deleting
another session's scratch is not a repair.

## Next

If the sandbox-redirect is judged worth closing, the candidate is a refusal (or
a loud record) when `RENQUANT_REPO_ROOT` resolves somewhere other than where it
points. That is a behaviour change to a load-bearing resolver and wants its own
review, with the eight wrappers measured first.
