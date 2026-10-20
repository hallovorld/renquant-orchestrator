# 2026-10-19 — fast-path eligibility check (implements the policy merged in #1133)

STATUS:   delivered, awaiting FULL review (touches `.github/`, so it is itself not fast-path eligible).
WHAT:     `scripts/fast_path_eligibility.py` (pure decision + CLI), `.github/workflows/fast-path-eligibility.yml`
          (publishes commit status `fast-path/eligible`), `doc/memory/fast-path-ledger.md`, 26 tests. The status is
          `success` only when the PR has label `fast-path` AND every changed path is docs/tests, none is protected,
          <=3 files, <=40 lines, and <3 fast-path merges in the last 24 h. Allow-list is the operator-chosen
          conservative one (docs + tests only; no ops text).
WHY/DIR:  mechanical, not author-judged: the workflow runs on `pull_request_target` and checks out the BASE sha,
          so a PR cannot edit the rules that judge it; every error path (unreadable files, missing size, merge
          count unavailable -> assumed over the limit) leaves the status failing. It waives nothing by itself.
EVIDENCE: n/a — governance tooling, no model/data claim. Tests: 26 passed, incl. every protected path from
          policy §1.2, rename-into-docs, empty/unparseable input, CLI exit codes, a parity test that every
          `PROD_PATH_RULES` pattern is covered by `PROTECTED`, and a workflow-text test pinning base-sha checkout.
NEXT:     operator, after merging this PR: in repo settings add the ruleset bypass so a green `fast-path/eligible`
          status (not the actor alone) allows merging without codex approval — the agent does not touch rulesets.
          Then LONG rows 1 and 7 need an amendment citing the policy (separate fully-reviewed PR). Roll out to
          other repos only after 2 weeks of clean audit.
