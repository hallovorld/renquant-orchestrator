# Agent Index — docs (grep me first)

**Start here:** [`renquant-system-feature-map.md`](renquant-system-feature-map.md)
— the canonical living inventory of the whole system (features by category +
status, roadmap, pending discussion). It supersedes the old per-topic roadmap /
plan / audit docs (now in git history).

## Active docs

| Doc | Status | One-line hook |
|---|---|---|
| `renquant-system-feature-map.md` | **AUTHORITY** | all features by category + status; roadmap; pending discussion |
| `decisions/2026-06-12-engineering-before-model-research.md` | ACTIVE decision | #108 before #106; model evidence untrustworthy until rails green |
| `decisions/2026-06-12-scorer-lineup-decision.md` | ACTIVE decision | PatchTST primary, XGB shadow, ensemble SHELVED + reopening triggers |
| `research/2026-06-11-regime-detection-hmm-markov-switching-rfc.md` | approved RFC, not built | HMM regime engine upgrade, shadow-first (feature-map §3) |
| `research/2026-06-12-ensemble-primary-proposal.md` | SHELVED (code-referenced) | ensemble backfill rationale; kept for `scripts/experiments/ensemble_backfill_v0.py` |
| `research/2026-06-10-ic-to-pnl-architecture.md` (+ `research/evidence/*`) | reference data | IC→PnL experiment verdicts (referenced by evidence manifests) |
| `cross-repo-control-plane-design.md` | reference (code-referenced) | control-plane design for `src/renquant_orchestrator/repos.py` |
| `agent-pr-workflows.md` | operational | the autonomous review→fix→merge loop |

## Rules for agents

- The **feature map** is the source of truth for *what exists / what's next*;
  **decisions** block roadmaps where they conflict.
- Experiments live on `epic/model-edge-experiments`, never `main`.
- PRs under operator review are FROZEN — revisions = new branch + new PR.
- All merges are by humans (or the authorized agent-pr-loop), never self-merge.
