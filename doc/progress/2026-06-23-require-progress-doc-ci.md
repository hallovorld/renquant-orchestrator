# CI gate: require a doc/progress record on every PR

STATUS:   merge-pending (PR). Additive CI gate + PR template; no runtime/production code touched.
WHAT:     scripts/require_progress_doc.py + .github/workflows/require-progress-doc.yml fail any PR
          whose diff adds/changes no doc/progress/<date>-<slug>.md; + a .github/pull_request_template.md
          checklist + a unit test for the matcher.
WHY-DIR:  on 2026-06-23 six PRs (#173–#178) were opened with no progress doc and all were denied on
          this single contract — a memory failure under throughput. Machine-enforce it so it cannot be
          forgotten, and keep the progress doc the single durable record (PR body short, not duplicated).
EVIDENCE: 6 matcher tests pass (present->ok; absent/research-doc/no-date->fail; docs-only-progress->ok;
          blank lines ignored); the workflow itself adds this very progress doc, so it self-satisfies the
          gate. `[VERIFIED — pytest tests/test_require_progress_doc.py]`
NEXT:     make the check a required status check in branch protection (operator/admin action).
