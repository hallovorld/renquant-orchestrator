# 13 more jobs measured on their real surface — and weekly-wf-promote IS running   (PR pending)

STATUS:    delivered
WHAT:      Assigns `evidence_glob` to the 13 remaining jobs that are the **sole occupant**
           of their log directory and write dated files. Read-only tooling change.
WHY/DIR:   GOAL-5 / GOAL-1. The liveness scan measures `StandardOutPath`, a proxy that
           never updates for a wrapper that redirects. #630 and #633 fixed five jobs;
           these are every remaining one where the assignment is provably unambiguous.
EVIDENCE:  §1.
NEXT:      17 jobs still measured by proxy. They share log directories (the `pit-*` trio)
           or write no dated files, and are **not** mechanically assignable.

## §1 EVIDENCE

`[VERIFIED — ops/launchd_liveness_scan.py --json, before and after]`

| | before | after |
|---|---|---|
| `EVIDENCE_FRESH` | 18 | **24** |
| `NO_EVIDENCE_STALE` | 20 | **14** |
| `measured_by_proxy` | 35 / 40 | **22 / 40** |

## §2 A CLAIM OF MINE THIS REFUTES

In #627 I singled out `weekly-wf-promote`: *"its log has not been written since
**2026-05-17** … every claim of the form 'the weekly retrain was admitted by the gate'
assumes that job runs."*

**Measured on its real surface: `EVIDENCE_FRESH`, 0 missed firings, last write
2026-07-29.** The job runs. That reading was a proxy artefact and the warning built on it
was wrong. Also corrected by the same measurement: `conditional-retrain104` (FRESH,
07-29) and `retrain-alpha158-linear` (FRESH, **today**).

**What survives:** `daily103` is still `NO_EVIDENCE_STALE` with **66 missed firings**,
last write 2026-04-28 — now measured on its *real* dated-file surface, so that staleness
is not a proxy artefact. Consistent with the retired 103 generation.

## §3 The assignment criterion, and what it refuses

A glob was assigned only where the job is the **sole occupant of its log directory**
across all 40 manifested plists. The `pit-c1-features` / `pit-estimate-snapshot` /
`pit-liveness` trio share one directory and report the same newest file; assigning a
directory-wide glob there would hand one job's evidence to two others. They stay
unassigned.

## §4 A test of mine that was wrong, and how

`test_no_shared_log_directory_was_assigned_a_glob` **failed** on first run. The
invariant I asserted was too strong: six rq105 jobs share `logs/rq105/` and three carry a
glob, but those globs key on a **unique filename stem** (`session_scheduler_*.log`), so
the shared directory is harmless. The real invariant is narrower — *a **directory-wide**
glob may only be used in a single-occupancy directory* — and the test now asserts that.

## §5 Suite

| tree | result |
|---|---|
| `origin/main`, separate worktree | 7 failed, 4579 passed, 5 skipped, 27 warnings in 120.51s (0:02:00) |
| this branch | 7 failed, 4582 passed, 5 skipped, 27 warnings in 116.56s (0:01:56) |

`[VERIFIED — python3 -m pytest -q in both worktrees, sibling checkouts on PYTHONPATH]`

## §6 Live-surface impact

None. `program_args` and `program_args_sha256` untouched, so no manifest drift. The scan
is read-only and still not wired into any scheduled job.

## Round 2 — CI was validating none of the 13 assignments

Codex found the assignment proof was neither durable nor sufficient. Three defects, and
the third is the one that mattered:

1. absent plists hit `continue`, so in CI the occupancy map was empty;
2. an empty map meant the assertion was **skipped entirely** — CI validated **none** of
   the claimed 13 assignments while reporting green;
3. occupancy was inferred from `StandardOutPath`, which **cannot establish ownership of
   the evidence directory at all**. These jobs exist precisely *because* their wrappers
   redirect real evidence away from `StandardOutPath`. The field says where launchd
   puts its own stdout, not where the job writes the artifact the scan measures.

(3) is why the local-plist check was **deleted rather than repaired**. Repairing (1) and
(2) would have produced a check that runs everywhere and still proves the wrong thing.

**The invariant does not need the local machine.** Every `evidence_glob` is committed in
the manifest, so *"no two manifested jobs can match the same file"* is decidable from
the manifest alone. That now runs in CI:

* `_globs_can_overlap()` — same directory, and either pattern's concrete witnesses match
  the other. `[0-9]` classes are collapsed to a literal and `*` is expanded both empty
  and non-empty, so a directory-wide glob is seen to collide with a stem-specific one.
* `test_no_two_manifested_globs_can_match_the_same_file` — all pairs. **Strictly stronger
  than the old string-equality check**: equality only catches two jobs claiming the
  identical pattern, while the real hazard is a directory-wide glob added to a directory
  another job already writes into. The strings differ, equality passes, and every dated
  file the neighbour writes is silently credited to the newcomer. Six rq105 jobs share
  `logs/rq105/`.
* `test_the_overlap_helper_can_actually_detect_an_overlap` — the helper itself, because
  one that always returned `False` would make the sweep pass forever.
* `test_standardoutpath_is_documented_as_insufficient_for_ownership` — anyone re-adding
  an occupancy check from that field has to read why it cannot work.

`[VERIFIED — this session]` 40 passed. Load-bearing confirmed by injecting a
directory-wide glob into the shared `logs/rq105/` directory: the pair test **fails**
with it and passes once reverted.

**Not claimed:** this proves globs cannot *collide*, not that each glob is tied to its
job's actual writer path. Tying them needs the wrapper's write target recorded in the
manifest, which is a separate change against the wrappers — asserting it from anything
readable here would just be `StandardOutPath` again under another name.

### Round 2 follow-up — a count is the wrong object, and the merge duplicated a test

Updating this branch against main turned it red:
`test_thirteen_more_jobs_have_an_evidence_glob` asserted a **global total of 18**
("3 + 2 + 13") and main now carries 19.

Two defects, one of them mine from the start:

* **The arithmetic was wrong.** The base was **6** globs, not 5, so the correct total
  was always 19 `[VERIFIED — glob sets diffed between origin/main and this branch, this
  session]`. I wrote "3 + 2 + 13" from the shape of the story rather than counting.
* **A global count is the wrong object anyway.** It is a *proxy* for "the 13 landed"
  that breaks whenever anyone adds an unrelated 14th — which is precisely what a
  concurrent change reaching main did. A test that fails on someone else's correct work
  is not protecting this PR's claim; it is protecting a coincidence.

Replaced with the claim itself: the **13 labels named individually**, asserted to have a
glob. That cannot be broken by legitimate growth elsewhere, and it fails for the right
reason if one of these thirteen loses its assignment. Paired with
`test_the_thirteen_are_thirteen_distinct_manifested_jobs`, because a typo'd label would
otherwise drop silently out of the check — an absent label simply has no glob to lose.

**Also fixed: the merge resurrected a deleted test.** The pre-fix
`test_thirteen_more_jobs_have_an_evidence_glob` and
`test_weekly_wf_promote_is_measured_on_its_real_surface` came back alongside their
replacements, leaving two definitions of each in one file — the later shadowing the
earlier, so the file silently ran only half of what it appeared to contain. Duplicates
removed. Worth naming: this is the twin-implementation shape the repo keeps hitting,
this time produced by a merge inside a test file.

`[VERIFIED — this session]` 41 passed. Load-bearing confirmed by deleting
`weekly-wf-promote`'s glob: the named-labels test fails and passes again on restore.

## Addendum 2026-07-30 — the review's two demands are not one demand

Codex asked for (a) a **deterministic source-of-truth mapping** for all manifested
jobs and (b) that each glob **"cannot overlap another manifested writer"**. Only (b)
is decidable from what exists today, and conflating them would have shipped a
half-answer as a whole one.

### (a) OWNERSHIP is not derivable by static parsing — measured, negative

I tried the obvious route: parse each wrapper for the expression it assigns its
dated log to. It resolves **4 of 31** wrappers
`[VERIFIED — regex over every manifest-named `.sh`, this session]`. The construction
varies too much — different variable names, `tee`, `exec >` redirection, per-module
loops that write several dated files per run. **Shipping a 4/31 parser as a "source
of truth" would be a guard that validates the wrong object for 27 jobs**, which is
the exact defect class this PR exists to fix.

Three routes that would actually close it, none of them a test, all needing their
own review:

1. **The wrapper declares its own evidence path at run time** — print
   `evidence_path=<...>` on start, and the scan reads it. Unfalsifiable, because it
   comes from the job. Costs a touch to ~31 wrappers and only helps after each next
   fires.
2. **The scan attributes by process** — record the writer pid at open time. Needs a
   change in every writer and does not work retroactively.
3. **Accept declaration + enforce non-collision** — what is shipped here. Does not
   prove a glob reads *its own* files; proves it cannot read a *sibling's*.

### (b) NON-OVERLAP is decidable, and is now enforced

`tests/test_evidence_glob_exclusivity.py` — 5 tests, both halves:

- **static**: no two globs share a directory **and** filename prefix
  (`logs/rq105/` holds six jobs; the prefix is the only separator);
- **dynamic**: no two globs match the same **file** on this machine — the thing
  itself, not the proxy;
- absoluteness (a relative glob resolves against a cwd launchd does not pin);
- an **anti-vacuity** control, since every assertion is trivially true over an empty
  list;
- an empty-glob census pinned to the one expected case
  (`rq104-model-freshness`, whose plist is not installed yet, #638).

Coverage on this branch: **19/41** jobs carry an `evidence_glob`, against **6/41**
on `main` `[VERIFIED — manifest parse of both]`. The 22 without one still fall back
to `StandardOutPath`, which #627 measured to give false stale readings — that is the
remaining gap, and it is a count, not a hope.
