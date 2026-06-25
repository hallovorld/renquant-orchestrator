# 2026-06-24 — Codex GitHub auth operation guard

STATUS: ops rule update after a repeated identity-preflight miss.

WHAT:
- Codex must use the `haorensjtu-dev` GitHub token stored in Keychain as
  `renquant-gh-codex`.
- The required review/merge preflight is:

```bash
source /Users/renhao/git/github/RenQuant/scripts/agent_gh_env.sh codex
gh api user --jq .login
make agent-identity-codex
```

The login must be `haorensjtu-dev` before any `gh pr review`, `gh pr merge`, or
cross-repo PR loop.

WHY/DIR:
- The earlier failure was operational, not token provisioning: the token was
  present and resolved to `haorensjtu-dev`, but the workflow inspected ambient
  `gh auth status` first and reasoned from the active `hallovorld` account.
- `gh auth status` is not an agent-identity preflight. It is only background
  state and may show a different active account than the token loaded by
  `agent_gh_env.sh`.

EVIDENCE:
- artifact: Keychain service `renquant-gh-codex`
- prod or exp: prod PR review/merge operation
- existing data: `agent_gh_env.sh codex` resolves `gh api user --jq .login` to
  `haorensjtu-dev`
- best-known?: yes
- scope: documentation/ops guard only

NEXT:
- Start every Codex PR turn by loading `agent_gh_env.sh codex` and verifying
  `haorensjtu-dev`.
- If `make agent-identity-codex` is unavailable in a stale worktree, use the
  direct `agent_gh_env.sh codex` + `gh api user --jq .login` check rather than
  falling back to ambient `gh auth status`.
