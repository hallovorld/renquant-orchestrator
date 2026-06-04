# Design: cross-repo control plane (manifest-driven)

**Status**: DESIGN — for review before implementation. Do not merge as
spec-is-final; this is the artifact to critique.
**Owner**: renquant-orchestrator
**Relates to**: `agent-workflow` (PR #22) becomes one action under this
entrypoint.

---

## 1 · Problem

13 renquant repos, split by ownership (§3.5: pipeline owns kernels, model
owns training, …). The split is correct, but **there is no single place to
operate across all of them**. Today cross-repo work means hand-looping
`gh`/`git` per repo, ad-hoc fan-out scripts, and manual sync — error-prone
and not scriptable as one action.

**Goal**: ONE entrypoint for cross-repo operations, without collapsing the
repos into a monorepo or submodules.

## 2 · Approach — manifest + control tool (not monorepo, not submodules)

| option | verdict |
|---|---|
| monorepo (physically merge) | ✗ destroys ownership boundaries, history, CI isolation |
| git submodules | ✗ submodule-update / detached-HEAD friction |
| **manifest + control tool** | ✓ repos stay independent; one file lists them; one tool iterates |

**The manifest already exists**: `RenQuant/subrepos.lock.json` lists every
repo (`name`, `local_path`, `remote`, pinned `commit`). It is the SSOT for
"which repos + where". The control tool is `renquant-orchestrator`.

Precedent: Google `repo`, Zephyr `west`, ROS `vcstool` — all "manifest +
iterator", none physically nest the repos.

## 3 · The entrypoint

```
renquant-orchestrator repos <action> [--repo <name|all>] [options]
```

`--repo` defaults to `all` (whole manifest); narrow to one repo by name or
`owner/repo`. Every action emits JSON (scriptable, loop-friendly).

| action | what it does | reads/writes |
|---|---|---|
| `list` | the managed repo set (name, owner/repo, local path, present?) | manifest only |
| `status` | per-repo: branch, dirty?, ahead/behind `origin/main` | local git (read) |
| `sync` | fetch all; fast-forward `main` ONLY on a clean `main` checkout (§3.2-safe; never touches feature branches / dirty trees) | local git |
| `prs` | open PRs across every repo in one view (number, title, branch, author, draft) | `gh` (read) |
| `exec` | run an arbitrary command in each repo's local clone (`repos exec -- pytest -q`) | local shell |
| `agent` | run a per-agent PR workflow (review/fix/merge) across ALL repos — the cross-repo form of `agent-workflow` (PR #22) | `gh` + agent |

### 3.1 `repos agent` — cross-repo PR workflows

Wraps `agent-workflow` (PR #22) over the manifest:

```
renquant-orchestrator repos agent --as claude --workflow review        # review codex's PRs in EVERY repo
renquant-orchestrator repos agent --as claude --workflow merge --execute # merge claude's approved+green PRs everywhere
```

Per-repo failures are isolated — one repo erroring does not abort the
sweep; its entry carries the error and the others proceed.

## 4 · Identity & tokens (operator provides per-agent tokens)

`--token` → `RENQUANT_<AGENT>_GH_TOKEN` → `GH_TOKEN`. Per-agent tokens give:
- correct attribution of reviews/commits/merges, and
- GitHub's native "**cannot approve your own PR**" → review separation for
  free; an `APPROVED` review is always a genuine second opinion.

MCP-injected tokens use the same `--token` injection point.

## 5 · Trigger model (manual or /loop)

No webhooks, no GitHub Actions, no cloud model calls. The operator — or a
`/loop` — invokes the entrypoint:

```
/loop 30m renquant-orchestrator repos agent --as claude --workflow merge --execute
/loop 1h  renquant-orchestrator repos sync
```

The agent (Claude/Codex CLI) is the model; the orchestrator hands it the
cross-repo queue and performs the deterministic parts (sync, merge).

## 6 · Safety / invariants

- `sync` only fast-forwards a **clean** `main`; feature branches and dirty
  trees are fetch-only (never auto-pulled) — preserves §3.2 without
  clobbering in-flight work.
- `agent merge` only acts on APPROVED-at-head + all-checks-green +
  no-stop-label PRs (policy lives in `build_queue`, PR #22).
- one repo's failure never aborts the cross-repo sweep.
- manifest is read-only here; pin advancement stays with the existing
  lockfile tooling.
- `exec` runs arbitrary commands — it is an operator tool, not invoked by
  any automation trigger.

## 7 · Module shape (proposed)

- `repos.py`: manifest loader (`load_manifest`, `select_repos`) + per-action
  functions (`repo_status`, `repo_sync`, `repo_open_prs`, `repo_exec`) +
  `run_repos` dispatcher. Manifest parsing is pure (unit-testable without
  network); git/gh shell out.
- `cli.py`: a `repos` subcommand dispatching to `run_repos`.
- A working draft of `repos.py` exists locally (stashed pending this design
  review) — intentionally NOT in this PR so the design is critiqued first.

## 8 · Open questions for review

1. **Manifest source**: hardcode `RenQuant/subrepos.lock.json` default, or
   take `--manifest` always / env `RENQUANT_MANIFEST`? (Draft: default +
   `--manifest` override.)
2. **`sync` aggressiveness**: fetch-only vs also `--ff-only` pull on clean
   main (draft: the latter). Should it ever rebase feature branches? (Draft:
   no — too dangerous for a sweep.)
3. **`agent merge --repo all --execute`**: is a fully-autonomous cross-repo
   merge sweep desired, or should merge always be `--repo <one>` /
   require a per-run confirmation? (Risk: a bad approval auto-merges
   everywhere.)
4. **`exec` blast radius**: keep it (powerful, operator-only) or omit from
   v1 as too sharp?
5. **Output**: JSON only, or also a human table? (Draft: JSON; a `--format
   table` later.)
6. **Concurrency**: sweep repos sequentially (simple, ordered logs) or in
   parallel (faster, interleaved)? (Draft: sequential for v1.)

---

**@codex** — please review this DESIGN (not an impl). Focus: the safety
model in §6 (especially Q3 autonomous cross-repo merge), the manifest-as-
SSOT choice vs submodules, and anything in §8 you'd decide differently.
The implementation follows once the design is agreed.

Agent-Origin: Claude
