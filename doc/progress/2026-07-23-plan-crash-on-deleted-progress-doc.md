# Progress — fetch_open_prs crashed the whole repo's plan on a deleted progress doc

## STATUS:
Delivered. Found and fixed live: `renquant-orchestrator PR #570` (a revert PR
that deletes `doc/progress/2026-07-23-g4-ensemble-existence-evidence.md` as
part of reverting #569) had been silently taking down plan-building for the
ENTIRE `renquant-orchestrator` repo — not just #570 — for roughly 2 hours
before this fix, discovered during a routine autonomous-loop status check.

## WHAT:
`fetch_open_prs()` (`src/renquant_orchestrator/agent_workflows.py`) fetches a
PR's progress-doc content via the GitHub contents API at the PR's head ref,
for every PR whose diff touches exactly one `doc/progress/*.md` path. When
that path was DELETED at head (a revert PR removing the file it's reverting),
the contents API 404s; `_gh_json` turns any nonzero `gh` exit into an
uncaught `RuntimeError`, which propagated out of `fetch_open_prs` with no
handling at any call site up through `run_agent_workflow`. The per-repo
`except Exception` isolation in `repos.py` (`# isolate per-repo failure`)
caught it one level up, but that meant the WHOLE repo's plan became
`{"repo": ..., "error": "..."}` — zero queue entries, not just for the
offending PR, for any PR in that repo — silently, every 5-minute loop cycle,
for as long as the offending PR stayed open.

Fix: wrap the `_gh_file_text` call in a `try/except RuntimeError`, leaving
`progressDocContent` unset on failure rather than letting it propagate.
`progress_doc_findings()` already has the correct behavior for an unset
`progressDocContent` — it reports `"progress doc content unavailable for
<path>"`, which is exactly the right, actionable finding for a PR that
references a progress-doc path but doesn't have fetchable content there
(deleted, or otherwise inaccessible). No new code path was needed, just
routing the failure into the one that already existed.

## WHY/DIR:
Ground-truthed via the autonomous loop's own status checks, not guessed:
`repos agent --as claude --workflow review --repo renquant-orchestrator`
returned `{"error": "gh api repos/hallovorld/renquant-orchestrator/contents/
doc/progress/2026-07-23-g4-ensemble-existence-evidence.md?ref=codex/revert-
g4-existence-evidence failed (rc=1): gh: Not Found (HTTP 404)"}` — a 404, not
a real ambiguity. `gh pr view 570 --json files` confirmed every file in the
diff (including that progress doc) is a deletion, matching the PR body's own
description ("this revert only deletes #569 artifacts/docs"). No existing
test exercised `fetch_open_prs`'s real logic against `_gh_json` (all prior
tests mock `fetch_open_prs`/`fetch_merged_prs` wholesale, bypassing this
code path entirely) — a genuine untested gap, not a known-and-accepted
limitation.

Impact while broken: every open PR in `renquant-orchestrator` (not just
#570) was invisible to the `codex-review`/`claude-review`/`*-fix` steps of
`agent_pr_loop.py` for the ~2 hours #570 was open with this shape — a
narrower but real instance of the same class of bug fixed earlier today in
`RenQuant#526` (a stdout-truncation bug that killed the entire loop the same
way: one bad code path with no isolation, silently eating every cycle's
work). `[[merged-is-not-deployed]]` doesn't apply here (this fix ships
straight to the dev checkout the loop already runs from), but the general
lesson does: a control-plane fetch that can legitimately fail (deleted file,
private repo, rate limit) must degrade to a per-PR finding, not an
uncaught exception that erases every sibling PR's visibility.

## EVIDENCE:
`[VERIFIED]`
- Two new regression tests in `tests/test_agent_workflows.py`:
  `test_fetch_open_prs_survives_a_deleted_progress_doc` (pins the fix: a
  mocked `_gh_json` that 404s on the contents-API call for a path present in
  `files` must not raise out of `fetch_open_prs`, and the resulting PR dict
  must produce the `"progress doc content unavailable"` finding) and
  `test_fetch_open_prs_still_fetches_progress_doc_content_when_present`
  (behavior-invariance: a normal PR with a real, fetchable progress doc
  still gets `progressDocContent` populated, unchanged).
- Confirmed the new test FAILS against the pre-fix source (`git stash` the
  fix, re-run — `RuntimeError` propagates exactly as it did live) and PASSES
  after.
- Full suite: `tests/test_agent_workflows.py` 55/55 passed;
  `tests/test_repos.py` + `tests/test_cli.py` 47/47 passed (3 unrelated
  pre-existing failures in `test_cli.py` — `test_daily_contract_cli_*` /
  `test_parking_sleeve_cli_*` — confirmed present on unmodified `origin/main`
  in the same worktree before this change, unrelated env/path issues, not
  touched here).
- Ran the ACTUAL broken command against the ACTUAL live PR #570 with the fix
  applied: `repos agent --as claude --workflow review --repo
  renquant-orchestrator` now returns `error: None` and queues #570 with note
  `"progress doc content unavailable for
  \`doc/progress/2026-07-23-g4-ensemble-existence-evidence.md\`; mixed
  GitHub commit attribution..."` — the crash is gone and the PR is now
  visible to the review workflow.

## NEXT:
Merge → the live dev checkout (`/Users/renhao/git/github/renquant-orchestrator`,
what `agent_pr_loop.py` runs `PYTHONPATH=<this>/src` against) picks this up
immediately, no separate deploy step. Next loop cycle should surface #570 in
the review queue instead of silently erroring every 5 minutes.
