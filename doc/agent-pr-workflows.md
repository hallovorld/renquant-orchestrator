# Orchestrator-driven multi-agent PR workflows

**Status**: replaces the GitHub-event / CI-CD review automation (the
`agent-review` / `agent-autofix` / `agent-review-classify` / `agent-auto-merge`
GitHub Actions stack in the umbrella). That stack is being deleted.

**Why the pivot**: the agents (Claude Code CLI, Codex CLI) *are* the LLMs.
Driving them from GitHub Actions meant re-invoking a model in the cloud,
which brought a chain of failure modes we kept patching — OIDC, quotas,
"green check ≠ approval", comment-vs-review-state, token gaps for
submitting reviews. None of that is needed when the agent runs locally and
already holds a model + a token. The orchestrator just has to tell each
agent *what* to act on, and merge the deterministic cases.

---

## The model

`renquant-orchestrator` owns **queues + policy + deterministic merge**.
The agent owns **judgment** (writing a review, writing a fix).

```
renquant-orchestrator agent-workflow --as <claude|codex> --workflow <review|fix|merge>
```

| workflow | queue (orchestrator resolves) | who acts |
|---|---|---|
| `review` | open PRs authored by the **other** agent, not yet approved, no stop label | agent reads diff → posts ONE review with its own token |
| `fix` | this agent's **own** open PRs with unaddressed findings (CHANGES_REQUESTED, or a BLOCKER/HIGH/MED tag at head) | agent reads findings → smallest fix → test → commit + push |
| `merge` | this agent's **own** open PRs that are APPROVED + at least one completed check + all checks green + no stop label | **orchestrator** comments `merged by <agent>`, then runs `gh pr merge` directly (`--execute`) |

`review` / `fix` print a JSON worklist for the calling agent to process.
`merge` executes (deterministic — no model needed).

## Identity & tokens

`--as <agent>` selects the gh token: `--token` → `RENQUANT_<AGENT>_GH_TOKEN`
→ `GH_TOKEN`/`GITHUB_TOKEN`. The safe operating procedure is:

1. store the Claude and Codex PATs in the local OS secret store;
2. expose them to the orchestrator only through short-lived wrapper commands;
3. never paste token values into chat, PR bodies, comments, commits, config, or
   `.env` files; and
4. rotate any token that was exposed outside the secret store.

Give each agent its **own** token so:

- commits / reviews / merges are correctly attributed, and
- GitHub's native **"you cannot approve your own PR"** rule enforces the
  review-separation invariant *for free*. An `APPROVED` review on a PR is
  therefore always a genuine second opinion — the orchestrator's `merge`
  queue can trust it without extra checks.

GitHub account attribution is not enough when both agents operate through an
operator account or co-authored commits. Every agent-written review/fix comment
must include visible text:

- `reviewed by <agent>` in review bodies;
- `fixed by <agent>` in fix comments;
- `merged by <agent>` posted by the orchestrator immediately before merge.

(If tokens are provided via MCP instead of env, the same precedence applies
— `--token` is the injection point.)

### Token SOP

Use distinct GitHub accounts or bot users:

| identity | purpose | required repo role |
|---|---|---|
| Claude token | Claude-authored PRs, Claude reviews, Claude comments | collaborator on all renquant repos |
| Codex token | Codex-authored PRs, Codex reviews, Codex comments | collaborator on all renquant repos |
| Owner/admin token | emergency owner override only | owner/admin; never used for normal review |

Use fine-grained PATs scoped only to the renquant repos. Normal agent tokens
need `Contents: read/write`, `Pull requests: read/write`, `Issues: read/write`,
`Metadata: read`, and `Actions: read`. Do not grant admin permissions to agent
tokens. Keep owner/admin override credentials separate.

On macOS, store the two agent tokens in Keychain:

```bash
security add-generic-password -U -s renquant-gh-token -a claude -w '<CLAUDE_PAT>'
security add-generic-password -U -s renquant-gh-token -a codex  -w '<CODEX_PAT>'
```

Create local wrappers outside every repo, for example `~/.local/bin/rq-gh-claude`
and `~/.local/bin/rq-gh-codex`:

```bash
#!/usr/bin/env bash
set -euo pipefail
export GH_TOKEN="$(security find-generic-password -s renquant-gh-token -a claude -w)"
exec gh "$@"
```

```bash
#!/usr/bin/env bash
set -euo pipefail
export GH_TOKEN="$(security find-generic-password -s renquant-gh-token -a codex -w)"
exec gh "$@"
```

Make them private and executable:

```bash
chmod 700 ~/.local/bin/rq-gh-claude ~/.local/bin/rq-gh-codex
```

For orchestrator calls, inject a token for the current process only:

```bash
CLAUDE_TOKEN="$(security find-generic-password -s renquant-gh-token -a claude -w)" \
  renquant-orchestrator repos agent --as claude --workflow review --token "$CLAUDE_TOKEN"

CODEX_TOKEN="$(security find-generic-password -s renquant-gh-token -a codex -w)" \
  renquant-orchestrator repos agent --as codex --workflow review --token "$CODEX_TOKEN"
```

Before any review or merge loop, verify that the accounts are different:

```bash
rq-gh-claude api user --jq .login
rq-gh-codex api user --jq .login
```

If both commands print the same login, stop. A single GitHub identity cannot
produce independent approvals, even if the token strings differ.

If a token is pasted into chat or appears in logs, immediately revoke it in
GitHub, create a replacement, update Keychain, and post a PR comment noting only
that the exposed token was rotated. Never quote the token value in the comment.

## Policy (encoded in `build_queue`, not in CI)

- an agent never reviews its own PR (review queue excludes self-authored);
- `merge` requires an `APPROVED` review **on the current head**, at least
  one completed check, all reported checks SUCCESS/SKIPPED/NEUTRAL, and **no** `agent:manual-hold` /
  `agent:cost-cap` / `agent:rebase-conflict` label;
- repos with intentionally no PR checks must either add a cheap required
  check or pass `--allow-no-checks`; the default is fail-closed so missing CI
  is not silently treated as green;
- a `CHANGES_REQUESTED` review on head blocks merge even if an approval
  also exists;
- merge first posts a visible PR comment containing `merged by <agent>` as a
  pre-merge audit marker and fails closed if that audit comment cannot be
  written;
- authorship is read from the canonical `agent:<name>` label, with a
  branch-prefix (`claude/…`, `codex/…`) fallback for older PRs.

## Triggering

The user — or a `/loop` — tells an agent to run a workflow. Examples:

```bash
# Claude reviews everything Codex wrote:
renquant-orchestrator agent-workflow --as claude --workflow review
#   → JSON worklist; the Claude session then posts each review.

# Codex fixes its own commented PRs:
renquant-orchestrator agent-workflow --as codex --workflow fix
#   → worklist; the Codex session edits + pushes each.

# Either agent merges its own approved+green PRs (deterministic):
renquant-orchestrator agent-workflow --as claude --workflow merge --execute
```

A hands-off loop is just the user (or `/loop`) periodically invoking these
three per agent. No webhooks, no Actions, no cloud model calls.

## What this is NOT

- Not a model runner — the orchestrator never calls an LLM. The agent does.
- Not a webhook server — it polls on demand via `gh`.
- Not a merge-policy bypass — `merge` only acts on genuinely approved+green
  PRs, and the human retains `gh pr merge --admin` for overrides.
