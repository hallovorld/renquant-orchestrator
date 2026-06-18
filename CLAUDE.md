# CLAUDE.md

> ⚠️ **BEFORE WORKING, READ TWO DOCS:**
> 1. [`doc/AGENT-RETROSPECTIVE.md`](doc/AGENT-RETROSPECTIVE.md) — the control
>    contract: the systemic failure mode and the external controls (C1–C5) that
>    contain it. Report bottom-line-first; no "X works/fails" without the evidence
>    block; never write production paths; every PR carries a progress doc.
> 2. [`doc/AGENT-STATE.md`](doc/AGENT-STATE.md) — the externalised executive memory:
>    **long-term agreements (binding) · mid-term plan · short-term state.** Refer
>    every session; never violate §A; update §C as work proceeds.

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
