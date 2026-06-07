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
→ `GH_TOKEN`/`GITHUB_TOKEN`. Give each agent its **own** token so:

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

### Where those tokens come from (storage SOP)

The two PATs must belong to **different GitHub accounts** and are **stored in
the OS Keychain**, never in `.env`, a dotfile, or chat. Canonical procedure:
[`RenQuant/doc/ops/agent-token-storage.md`](https://github.com/hallovorld/RenQuant/blob/main/doc/ops/agent-token-storage.md).

Before running the orchestrator, load both agent tokens into the env vars the
precedence above reads (`RENQUANT_CLAUDE_GH_TOKEN`, `RENQUANT_CODEX_GH_TOKEN`) —
the loader reads the Keychain and never prints the token:

```bash
# RenQuant sits beside this repo; the loader is canonical there.
source ../RenQuant/scripts/agent_gh_env.sh --orchestrator
python -m renquant_orchestrator ...   # picks up RENQUANT_<AGENT>_GH_TOKEN per --as
```

Tokens are inserted by the **operator** (interactive Keychain prompt, see the
SOP) — never pasted into an agent session. A token exposed anywhere (including a
transcript) is rotated immediately. If both tokens resolve to the same GitHub
login, stop: GitHub will still treat agent approvals as self-approval.

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
