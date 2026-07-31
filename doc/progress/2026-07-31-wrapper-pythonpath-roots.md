# Six scheduled jobs import a library from a feature branch, decided by `ls`

**Bottom line `[本次实测 2026-07-31]`.** Six `rq105` wrappers prefer a pinned run
checkout that **does not exist on this machine**, so all six silently fall back to the
dev checkout — which was sitting on branch **`fix/ntfy-non-ascii-title`**, **3 commits
behind `origin/main`**. Which vintage of `renquant_common` executes is decided by
**filesystem state**, not by anything reviewed.

## The idiom, verbatim

```sh
RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC"
```

with the comment *"pinned -run checkout preferred"*. Measured:

| | |
|---|---|
| `renquant-common-run/src` | **does not exist** |
| `renquant-common/src` | exists — branch `fix/ntfy-non-ascii-title`, clean, **3 behind origin/main** |
| wrappers taking the fallback | **6 / 6** (`batch_scores_export`, `liveness_check`, `postclose_loggers`, `quote_logger`, `session_scheduler`, `shadow_serving`) |

**The stated preference is unsatisfiable, and nothing said so.** That is
`asserted-instead-of-measured` sitting on a live run surface.

A fallback that fires is not automatically *wrong*. It is automatically
**unreviewed** — and that is the fact this makes loud.

## Why this is not a twin of `check_import_resolution`

That check pins the symbols resolved **in the scanner's own process**. A wrapper
builds its **own** PYTHONPATH, so a symbol can resolve exactly as reviewed inside the
scanner and differently inside the job. **Validating the scanner's environment
instead of the job's is itself the #623 shape** — different object, so this is an
addition, not a duplicate.

Note also `run_session_scheduler.sh` resolves siblings from a **third** root,
`$RQ_ROOT/.subrepo_runtime/repos` — so within rq105 the same library has two
different resolution strategies.

## Two of my own errors, both caught by the design

1. **My first regex used `[^"]*` for the path value.** The real wrappers write
   `X="$(dirname "$R")/…-run/src"`, whose value contains **nested double quotes**, so
   that class matched nothing and the check found **zero** sites. It did not read as
   clean — the residual assertion (*"no idiom found is a PROBLEM, not a pass"*) fired
   and told me. Pinned as a regression test.
2. **Adding this check broke 6 existing tests** that stub `main()`'s problem
   producers by hand — the eighth producer was not in their list. Same shape I hit
   before with the fifth and seventh. The stubs are updated, with a comment saying
   the *residual* assertion, not the hand-list, is what keeps them honest.

## This will alarm on day one — deliberately

The scan now reports 6 problems on this machine. Per the CONTAINMENT PROTOCOL that
is the designed reminder. Clearing it requires either creating
`renquant-common-run` or changing the wrappers — **both machine landings, both
needing operator authorization.** Not done here.

Tests: 6 new + 2 stub sites updated. Suite green.
