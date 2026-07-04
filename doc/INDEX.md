# Doc Index

## System Architecture (as-built, 2026-07-04)

| Doc | System | One-line hook |
|---|---|---|
| [`design/renquant-104-as-built.md`](design/renquant-104-as-built.md) | **104** | Daily batch decisioning: panel scoring → gates → sizing → execution |
| [`design/renquant-105-as-built.md`](design/renquant-105-as-built.md) | **105** | Intraday session decisioning: Stage-1/2 + canary envelope (shadow-only) |
| [`design/renquant-106-as-built.md`](design/renquant-106-as-built.md) | **106** | Signal evolution: expkit + M-SIG stack (G106 not clearable today) |
| [`design/renquant-107-as-built.md`](design/renquant-107-as-built.md) | **107** | Governance: attribution + risk budgets + S-REL + scorer identity (observe-only) |

## Active Governance

| Doc | Status | One-line hook |
|---|---|---|
| `research/VERDICTS.md` | **AUTHORITY** | Standing verdict ledger — 14 rows, S-REL governed |
| `design/2026-07-04-compliance-fix-campaign.md` | ACTIVE | Consolidated 4-audit fix plan (groups A–D) |
| `design/2026-07-03-s-rel-experiment-reliability.md` | ACTIVE | S-REL program design |
| `design/2026-07-02-unified-107-master-plan.md` | ACTIVE | 107 master plan — risk/attribution/governance roadmap |
| `design/2026-07-02-m-sig-signal-stack-spec.md` | ACTIVE | M-SIG C1–C4 frozen prereg spec |
| `design/2026-07-02-104-capability-program.md` | ACTIVE | 104 capability upgrades (S-FRAC, S6–S12) |
| `design/2026-07-02-h2-execution-roadmap.md` | ACTIVE | Execution quality roadmap |
| `decisions/2026-06-12-scorer-lineup-decision.md` | ACTIVE decision | XGB primary (re-promoted 06-23), PatchTST shadow, ensemble SHELVED |
| `decisions/2026-06-12-engineering-before-model-research.md` | ACTIVE decision | Engineering before model research |
| `progress/` | per-PR records | every PR commits `progress/<date>-<slug>.md` |

## Active Design Notes

| Doc | Topic |
|---|---|
| `design/2026-06-30-renquant105-intraday-decisioning-architecture.md` | 105 RFC #208 — the governing architecture |
| `design/2026-07-03-stage2-live-executor.md` | Stage-2 gate design (companion to RFC #208) |
| `design/2026-07-03-entry-timing-policy.md` | Entry-timing policy design |
| `design/2026-07-03-attribution-engine.md` | Attribution decomposition design |
| `design/2026-07-03-risk-budget-ledger.md` | Risk budget design |
| `design/2026-07-03-expkit.md` | Experiment framework design |
| `design/2026-07-02-m6-fingerprint-unification.md` | M6 fingerprint governance |
| `design/2026-07-03-m6-stage2-fingerprint-migration.md` | M6 stage-2 migration |
| `design/2026-07-02-s-frac-fractional-v2.md` | S-FRAC fractional shares design |
| `design/2026-06-30-model-freshness-governance.md` | Model freshness RFC #210 |
| `design/2026-07-03-m4b-relative-conviction-floor.md` | M4-b matched-breadth protocol |
| `design/2026-07-03-d3-term-br-decision.md` | D3 term BR decision |

## Superseded / Historical

These docs are preserved for context but superseded by the as-built docs above:

| Doc | Superseded by |
|---|---|
| `design/2026-06-28-renquant105-alpha-discovery.md` | 105 as-built + Phase −1 NO-GO verdict |
| `design/2026-06-28-renquant105-direction-decision.md` | 105 as-built (direction decided: execution quality, not alpha) |
| `design/2026-06-27-autonomous-ops-loops.md` | Implemented; see collector modules |
| `design/2026-06-30-shadow-scorer-freshness.md` | Implemented; see scorer identity monitor |
| `design/2026-06-24-model-fixes-cant-reach-production-postmortem.md` | Historical postmortem |
| `design/2026-07-01-104-105-design-review-amendments.md` | Amendments incorporated into as-built docs |
| `renquant-system-feature-map.md` | Superseded by the four as-built docs for system inventory |
| `cross-repo-control-plane-design.md` | Reference (code-referenced by `repos.py`) |
| `agent-pr-workflows.md` | Operational (the autonomous review→fix→merge loop) |
| `research/2026-06-12-ensemble-primary-proposal.md` | SHELVED (scorer lineup decision) |
| `research/2026-06-10-ic-to-pnl-architecture.md` | Reference data for evidence manifests |

## Rules for agents

- The **as-built docs** are the source of truth for *what is deployed*.
- The **VERDICTS ledger** is the source of truth for *what experiments concluded*.
- Experiments live on `epic/model-edge-experiments`, never `main`.
- PRs under operator review are FROZEN — revisions = new branch + new PR.
