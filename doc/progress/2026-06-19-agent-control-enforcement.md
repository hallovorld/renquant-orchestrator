# agent control enforcement hardening

STATUS: delivered
WHAT: hardens `agent_workflows` so merge/review/fix queues fail closed on missing progress docs, malformed progress docs, protected production-path writes, missing `reviewed by` approval markers, and missing `fixed by` audit comments after prior findings. Adds CODEOWNERS groundwork and matching unit-test coverage.
WHY/DIR: turns the `#153` control contract from prompt-only policy into deterministic queue predicates and merge blockers.
EVIDENCE: n/a
NEXT: enable GitHub-side required-reviewer or CODEOWNERS enforcement in the live branch/ruleset settings so Codex-specific approval becomes mechanical, not just queue policy.
