# Pin CI's pipeline checkout so the GOAL-3 record's provenance claim is satisfiable

STATUS:    Implemented. Unblocks orch#896 and orch#897, both APPROVED and red for
           this reason alone.

WHAT:      `.github/workflows/ci.yml` now passes an explicit `ref:` to the
           `renquant-pipeline` checkout, and the GOAL-3 record gains the
           `VERIFIED-AT` line for that revision.

WHY/DIR:   `test_the_RECORD_names_the_revision_that_was_actually_measured`
           requires the measured pipeline revision to appear in the record's
           `VERIFIED-AT` list. Its docstring says *"CI checks the PINNED pipeline
           out"* — CI did not. `actions/checkout@v4` with no `ref:` takes the
           default branch, so CI measured pipeline `main` HEAD **at job time**, a
           value nobody can write down in advance. Three revisions were observed
           inside one hour on 2026-08-07: `3d1f40bf` (CI), `e64960fa`,
           `316d7250` (local, before and after a fetch).

           The record already carried FOUR `VERIFIED-AT` shas from four prior
           re-derivations. Each passed only because CI happened to run before the
           next pipeline merge. **A fifth append buys hours**, which is why this
           fixes the binding rather than the symptom.

           The guard is codex's, from orch#833, and its intent is right: without
           it a stale provenance claim rides green. **It is not weakened here** —
           pinning makes its own stated premise true, and advancing the pin now
           requires re-deriving 20/19/0 and adding the VERIFIED-AT line in the
           same reviewed PR. That is the review step the floating checkout had
           silently removed.

EVIDENCE:  artifact:      `.github/workflows/ci.yml` pipeline checkout `ref:`;
                          `doc/progress/2026-08-05-goal3-public-export-resolution.md`
                          `VERIFIED-AT repo revision 7477978c2ff4dc9747be220f82ab63fe84917751`
           prod-or-exp:   CI configuration only. No runtime, config, or kernel path.
           existing-data: re-derived AT the pinned revision, in a detached worktree
                          of `renquant-pipeline` at `7477978`, with pytest's ini
                          `pythonpath` OVERRIDDEN so the measurement could not fall
                          back to the sibling checkout:
                            `SRC .../pl-main/src/renquant_pipeline/__init__.py`
                            `REV 7477978c2ff4dc9747be220f82ab63fe84917751`
                            `DUP 20  ELSEWHERE 19  COUNTERPART 0`
                          `[VERIFIED — pytest -o pythonpath=..., 2026-08-07]`
           best-known?:   yes for making the assertion satisfiable. It does NOT
                          make CI test against the code the daily run imports —
                          see NEXT item 2.
           scope:         the first attempt at this measurement silently measured
                          the SIBLING checkout (`69bf711`) because a `PYTHONPATH`
                          env var loses to pytest's ini `pythonpath`. Recorded
                          because the same trap will catch the next person
                          re-deriving this number.

NEXT:      1. Advancing the pin is now a reviewed act: re-derive 20/19/0 at the
              new sha and add its VERIFIED-AT line in the same PR.
           2. NOT FIXED, and worth deciding separately: the checkouts the DAILY
              RUN imports are not on `main`.
              `[VERIFIED — git rev-parse --abbrev-ref HEAD, 2026-08-07]`
                renquant-pipeline      branch `fix/score-drift-role-filter`,
                                       HEAD 69bf711 — NOT an ancestor of main
                                       (squash-merged, so the branch commit is
                                       not on main at all)
                renquant-strategy-104  branch `fix/concentration-40pct-8-slots`
              The strategy-104 one is a stale BRANCH NAME, not stale content: its
              `BULL_CALM.max_position_pct` reads `0.3`, matching the operator's
              final directive and `origin/main`. Checked before raising it.
              `renquant-pipeline` sitting on a squash-merged branch is why this PR
              pins CI to a main sha rather than to the tree the daily run uses —
              the latter is not reachable from the remote.
           3. orch#902 (`.subrepo_runtime/repos/` unreachable in production, 381
              commits stale) is the sibling problem: three checkout families, only
              one of which is authoritative for any given consumer.
