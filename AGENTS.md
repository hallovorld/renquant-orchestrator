# AGENTS.md

Canonical operating model:
https://github.com/hallovorld/RenQuant/blob/main/doc/arch/subrepo-operating-model.md

Local repo map: `RENQUANT_REPOS.md`.

Branch policy: `main` is the stable interface consumed by the umbrella repo and
automation. Experiments, optimizations, and large upgrades happen on feature
branches, then merge back only after tests and integration checks pass.

## Repo Role

`renquant-orchestrator` owns pinned-subrepo daily orchestration. It stitches
strategy/data/model/pipeline/execution/backtesting repos into one auditable run.

## Hard Boundaries

- Use `renquant-common` pipeline primitives for orchestration.
- Do not implement model training internals here.
- Do not implement signal/decision tree internals here.
- Do not implement broker adapters here.
- Do not silently continue without strategy/data/artifact fingerprints.
- Persist a run bundle for every full run.
- Do not delete or empty the source umbrella repo at
  `/Users/renhao/git/github/RenQuant`.

## Workflow

```bash
make test
make doctor
```

## Agent PR Identity Gate

Before any agent-authored `gh pr review`, `gh pr merge`, or cross-repo
review/merge loop, load and verify the agent-specific GitHub token. For Codex:

```bash
source /Users/renhao/git/github/RenQuant/scripts/agent_gh_env.sh codex
make agent-identity-codex
```

The expected Codex actor is `haorensjtu-dev`. If the check prints any other
login, stop; do not review, approve, or merge from the ambient `gh` account.
