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
| `merge` | this agent's **own** open PRs that are APPROVED + at least one completed check + all checks green + no stop label | **orchestrator** first verifies distinct Claude/Codex actors, then comments `merged by <agent>` and runs `gh pr merge` directly (`--execute`) |

`review` / `fix` print a JSON worklist for the calling agent to process.
`merge` executes (deterministic — no model needed).

**The `review` standard is [`AGENT-RETROSPECTIVE.md`](AGENT-RETROSPECTIVE.md) §7.1.**
A reviewer (Codex reviewing Claude's PRs, or vice-versa) withholds approval if the PR
violates the control contract: missing `doc/progress/<date>-<slug>.md` (C5); a
conclusion without its §4(b) evidence block; a write to a production path; a violation
of `AGENT-STATE.md` §A (binding ledger); or a claim over-stated as global from one
artifact. **Codex approval is the mechanical merge gate** — the operator does not review
every PR. (As of 2026-06-19 this is enforced: `.github/CODEOWNERS` + `require_code_owner_reviews`
+ `enforce_admins` require the other agent's approval; admins can't override — see
`AGENT-RETROSPECTIVE.md` §7/§8.) Because both reviewer and author are LLMs,
high-stakes/irreversible changes additionally pass a non-LLM mechanical gate (WF gate,
branch protection, prod read-only).

## Identity & tokens

`--as <agent>` selects the gh token: `--token` → `RENQUANT_<AGENT>_GH_TOKEN`
→ `GH_TOKEN`/`GITHUB_TOKEN`. The safe operating procedure is:

1. store the Claude and Codex PATs in the local OS Keychain;
2. expose them to the orchestrator only through `RENQUANT_<AGENT>_GH_TOKEN`;
3. never paste token values into chat, PR bodies, comments, commits, config, or
   `.env` files; and
4. rotate any token that was exposed outside the secret store.

Give each agent its **own** token so:

- commits / reviews / merges are correctly attributed, and
- A PR branch has exactly one GitHub commit identity: the account that created
  the PR. A peer reviewer must never commit or push to that branch. Any
  additional GitHub commit attribution, including a `Co-Authored-By` trailer,
  is a merge blocker. The PR owner rebuilds the branch from the target base,
  applies the final diff as its own commit, force-pushes the clean history, and
  requests a new review. The reviewer supplies findings only; it never repairs
  the peer branch.

GitHub account attribution is not enough when both agents operate through an
operator account or co-authored commits. Every agent-written review/fix comment
must include visible text:

- `reviewed by <agent>` in review bodies;
- `fixed by <github-login> (agent: <agent>)` in fix comments;
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

Canonical storage/loading procedure lives in
[`RenQuant/doc/ops/agent-token-storage.md`](https://github.com/hallovorld/RenQuant/blob/main/doc/ops/agent-token-storage.md).
That SOP stores PATs with the Keychain hidden prompt and loads them without
printing or writing token values.

Before running the orchestrator:

```bash
source ../RenQuant/scripts/agent_gh_env.sh --orchestrator
renquant-orchestrator repos agent --as claude --workflow review
renquant-orchestrator repos agent --as codex --workflow review
```

Before any review or merge loop, verify that the accounts are different:

```bash
source ../RenQuant/scripts/agent_gh_env.sh claude
gh api user --jq .login

source ../RenQuant/scripts/agent_gh_env.sh codex
gh api user --jq .login
```

If both commands print the same login, stop. A single GitHub identity cannot
produce independent approvals, even if the token strings differ.

For one-agent manual work, verify the actor before any `gh pr review` or
`gh pr merge` command:

```bash
source ../RenQuant/scripts/agent_gh_env.sh codex
make agent-identity-codex
```

This must print `codex GitHub actor OK: haorensjtu-dev`. If it prints
`hallovorld` or any other login, stop and fix token loading before touching PRs.
Do not substitute `gh auth status` for this check. The active `gh` account is
allowed to differ from the agent token loaded into `GH_TOKEN`; Codex identity is
the login returned by `gh api user --jq .login` after sourcing
`agent_gh_env.sh codex`.

Automated merges enforce this fail-closed: `agent-workflow --workflow merge
--execute` and `repos agent --workflow merge --execute` require both
`RENQUANT_CLAUDE_GH_TOKEN` and `RENQUANT_CODEX_GH_TOKEN` to be configured and
resolvable to different GitHub logins before posting the `merged by <agent>`
audit comment. A one-off `--token` can select the gh token used for the action,
but it cannot bypass the two-actor preflight.

If a token is pasted into chat or appears in logs, immediately revoke it in
GitHub, create a replacement, update Keychain, and post a PR comment noting only
that the exposed token was rotated. Never quote the token value in the comment.

## Policy (encoded in `build_queue`, not in CI)

- an agent never reviews or approves a PR it authored **or contributed to**;
  reviewer fixes are prohibited. The reviewer submits findings, and the PR
  owner applies every change on its own branch. A branch with an additional
  GitHub commit identity, including a `Co-Authored-By` trailer, is not
  mergeable until the owner rebuilds it as a clean single-identity branch;
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
- `merge-audit --strict` audits recent merged PRs and treats post-merge
  `merged by` comments as non-compliant; the marker must exist before or at
  `mergedAt`;
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

# Audit manual merges for missing pre-merge `merged by` markers:
renquant-orchestrator merge-audit --repo hallovorld/renquant-orchestrator --strict
```

A hands-off loop is just the user (or `/loop`) periodically invoking these
three per agent. No webhooks, no Actions, no cloud model calls.

## HARD-gate design rule (GOAL-5 AC6)

Any PR that introduces or tightens a HARD gate on the capital-deployment
path (buy admission, order placement, artifact promotion feeding the live
scorer) MUST answer three questions in its progress doc, and reviewers
treat their absence as CHANGES_REQUESTED:

1. **Governed exception path** — the operator-authorized override
   mechanism (identity + hard expiry + scope binding to the specific
   artifact/config it covers), or an explicit statement that no override
   is possible and why that is acceptable. A gate with no governed
   exception becomes an ungoverned emergency later — the 2026-07-15
   diagnostic-only admission gate shipped without one and the book drained
   to 94% cash before a mechanism could be retrofitted under incident
   pressure (pipeline#203).
2. **Fail-closed shape** — what exactly happens when the gate fires
   (sell-only? full abort?), and confirmation that risk exits are never
   blocked by a buy-side gate.
3. **Detection surface** — which sentinel/alert observes the gate firing
   (a gate that fires silently for days is a slow-motion incident; see
   the degradation sentinel and dawn preflight). "None yet" requires a
   named follow-up task in the same PR.

This rule is review-enforced (checklist), not mechanically detected: the
reviewer decides whether a diff touches the capital path.

## What this is NOT

- Not a model runner — the orchestrator never calls an LLM. The agent does.
- Not a webhook server — it polls on demand via `gh`.
- Not a merge-policy bypass — `merge` only acts on genuinely approved+green
  PRs, and the human retains `gh pr merge --admin` for overrides.
