# CLAUDE.md

## ⚠️ Agent operating rules — read before acting

> This block is a **prompt that raises compliance — NOT enforcement.** Enforcement is
> Codex review ([`doc/AGENT-RETROSPECTIVE.md`](doc/AGENT-RETROSPECTIVE.md) §7.1) + mechanical
> hooks (C1). Do not mistake "it's in CLAUDE.md" for "it's enforced."

**Before acting**, read the externalised memory in order **LONG → MID → SHORT**:
[`doc/memory/`](doc/memory/README.md) (SPEC: 机制 · SOP · 文档). The binding constraints are
the **single source of truth** in [`doc/memory/long-term-agreements.md`](doc/memory/long-term-agreements.md)
— not duplicated here. Full design + SOP: [`doc/AGENT-RETROSPECTIVE.md`](doc/AGENT-RETROSPECTIVE.md).

**Non-negotiable operating behaviours (stable meta-rules; specifics live in the LONG ledger):**
1. **Report bottom-line-first** — conclusion + the decision needed; the one number;
   tag `[VERIFIED]`/`[GUESS]`. No "X works/fails" without the §4(b) evidence block.
2. **Never write production paths** (`data/*.parquet`, `strategy_config.json`, live
   artifacts/state, committed WF corpora). Experiments in isolated worktrees only.
3. **Every PR carries `doc/progress/<date>-<slug>.md`** and updates the touched memory tier;
   **never self-merge.** Codex approval is the **mechanical** gate (CODEOWNERS +
   `require_code_owner_reviews` + `enforce_admins`, 2026-06-19 — each agent's PR needs the
   other's approval; admins can't override).
4. **Never bypass the WF gate / branch protection;** honour every item in the LONG ledger.
5. **CONTAINMENT PROTOCOL** (GOAL-5 AC3; born from the 2026-07-15 silent
   sell-only containment that starved the live book for a day). Any emergency
   mutation of a live run surface — a launchd job swap/disable, a hand-edit of
   a deployed config/artifact/state file, disabling a scheduled job — REQUIRES,
   in the SAME action batch:
   (a) a tracked task/issue naming the owner and an explicit expiry or restore
       condition ("until X is deployed" is a condition; "temporary" is not);
   (b) a durable record (doc/progress or memory) stating exactly what was
       changed and the literal revert steps;
   (c) if the change is meant to persist, the reviewed surface updated in the
       same batch (`ops/launchd_manifest.json` for launchd jobs, the pin/ref
       for checkouts) — otherwise the daily run-surface drift scan alarming on
       it is the DESIGNED reminder to lift or legitimize it. Never silence
       that alarm by editing the manifest outside review.
   A containment with no record is treated as an incident, not a fix.

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
