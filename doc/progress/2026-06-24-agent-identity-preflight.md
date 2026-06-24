STATUS: ready for review

WHAT:
- Added `scripts/check_agent_gh_identity.sh` to verify the active GitHub actor
  for an agent before manual PR review/merge work.
- Added `make agent-identity-codex` and `make agent-identity-claude`.
- Documented the Codex identity preflight in `AGENTS.md` and
  `doc/agent-pr-workflows.md`.

WHY/DIR:
- The agent PR control-plane depends on distinct GitHub actors. A manual
  `gh pr review` or `gh pr merge` from the ambient `hallovorld` account can
  misdiagnose branch-policy failures and waste review cycles.
- This turns the RFC agreement into a local command that fails before the PR
  is touched.

EVIDENCE:
- artifact: local validation
- prod or exp: prod workflow guard
- existing data: RFC token SOP in `RenQuant/doc/ops/agent-token-storage.md`
- best-known?: yes
- scope: shell guard, Makefile target, docs only

NEXT:
- Use `make agent-identity-codex` at the start of every Codex review/merge loop.
