# CI gate: require a doc/progress record on every PR

STATUS:   merge-pending (PR). Additive CI gate + PR template; no runtime/production code touched.
WHAT:     scripts/require_progress_doc.py + .github/workflows/require-progress-doc.yml fail any PR
          whose diff adds/changes no doc/progress/<date>-<slug>.md; + a .github/pull_request_template.md
          checklist + a unit test for the matcher.
WHY-DIR:  mechanically enforces LONG-ledger binding agreement #6 / C5 ("Every PR carries
          doc/progress/<date>-<slug>.md; no progress doc ⇒ Codex rejects", 2026-06-17; also CLAUDE.md #3).
          On 2026-06-23 six PRs (#173–#178) were opened with no progress doc and all were denied — a
          binding, already-written-down constraint violated under throughput. Per CLAUDE.md ("don't mistake
          'it's in CLAUDE.md' for 'enforced'; enforcement is Codex + mechanical hooks") the fix is a
          MECHANICAL hook, not more prose: this adds the hook and does NOT restate the rule (the LONG ledger
          is the operator-only single source of truth).
EVIDENCE: 6 matcher tests pass (present->ok; absent/research-doc/no-date->fail; docs-only-progress->ok;
          blank lines ignored); the workflow itself adds this very progress doc, so it self-satisfies the
          gate. `[VERIFIED — pytest tests/test_require_progress_doc.py]`
NEXT:     make the check a required status check in branch protection (operator/admin action).
