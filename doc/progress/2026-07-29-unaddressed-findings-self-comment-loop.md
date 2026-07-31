# Progress: `has_unaddressed_findings` stopped matching the author's own comments

STATUS:   delivered

WHAT:     `has_unaddressed_findings()` (`src/renquant_orchestrator/agent_workflows.py`)
          scanned every plain PR comment for a `BLOCKER|HIGH|MED` tag, unfiltered by
          who posted it. Comments carry no head SHA, so once the PR author posted a
          `fixed by <agent>` comment quoting the resolved finding's text (or a later
          comment explaining the false positive, itself using the same severity
          words), that comment matched forever — the finding never cleared even
          though the reviewer's actual `CHANGES_REQUESTED` review was already
          superseded by a later `APPROVED` at the current head. Fix: the comment scan
          now excludes comments authored by the same GitHub login as the PR author;
          genuine findings are always posted by the *other* agent via a formal
          review (already covered by the `revs` / `commented_at_head` scan above
          this comment fallback) or, defensively, a plain comment from someone else.

WHY/DIR:  This is the root cause behind the `repos agent --as claude --workflow fix
          --repo all` queue re-listing `renquant-model` PRs #92/#94/#95 across 10+
          unattended passes on 2026-07-29 (see `renquant-orchestrator`
          `doc/memory/short-term-state.md`, "Session: rq-fix pass, unattended"). Each
          pass re-verified the same 3 already-approved, unchanged-head PRs as false
          positives, posted a near-duplicate clarifying comment, and made no forward
          progress — the short-term-state note explicitly flagged this as the next
          bounded action once the pattern repeated: fix the queue-builder instead of
          re-confirming again.

EVIDENCE:
artifact:      `src/renquant_orchestrator/agent_workflows.py::has_unaddressed_findings`
               + `tests/test_agent_workflows.py::test_authors_own_comment_quoting_a_resolved_finding_is_not_unaddressed`
prod or exp:   prod (this function gates every `--workflow fix` queue across all
               renquant repos)
existing data: `gh pr view 95 --repo hallovorld/renquant-model --json reviews,comments`
               shows the only `CHANGES_REQUESTED` reviews are pinned to stale commits
               (`7c72f73…`, `e638461…`), the current head (`fc95112…`) carries two
               `APPROVED` reviews, and the sole `BLOCKER`/`MED` text still present is
               inside two comments authored by `hallovorld` (the PR's own author
               login): the `fixed by claude` comment and a later `clarifying`
               comment. `[VERIFIED — gh pr view 95, this session]`
best-known?:   yes — no prior fix for this predicate landed; `doc/memory/short-term-state.md`
               documents 10+ prior passes that only re-verified the symptom.
scope:         this is a prod fix to the shared queue-builder predicate, applies to
               all `--workflow fix` queues across every renquant repo, not scoped to
               renquant-model alone.

NEXT:     none — re-run `renquant_orchestrator repos agent --as claude --workflow fix
          --repo all` after this merges; PRs #92/#94/#95 in renquant-model should drop
          out of the queue since their only remaining "finding" text lives in the
          author's own already-posted comments.
