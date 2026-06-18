# CLAUDE.md

> ⚠️ **BEFORE WORKING, READ [`doc/AGENT-RETROSPECTIVE.md`](doc/AGENT-RETROSPECTIVE.md).**
> It defines the binding gates (A–F) that exist because the same class of error
> was made ~100×: report bottom-line-first; never state "X works/fails" without
> the 5-line scope check; check existing evidence before long executions; never
> write production paths; urgency never moves the safety line.

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
