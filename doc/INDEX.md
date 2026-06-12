# Agent Index — design/decision/research docs (grep me first)

| Doc | Status | One-line hook |
|---|---|---|
| `research/2026-06-12-engineering-architecture-deep-plan.md` | **AUTHORITY (with errata)** | five-plane engineering program; DRPH; contracts; disaster guards; execution PR backlog |
- `doc/research/2026-06-12-intraday-trading-roadmap.md` — after-close → intraday roadmap (4 layers; P0 risk-reaction NOW, P1 execution, P2 gated experiment, P3 SHELVED w/ triggers); consumes #108 infra, never reorders #110.
| `research/2026-06-12-model-capability-roadmap.md` | blocked by decision below | PatchTST improvement candidates (read errata first: cross-stock is high-variance, breadth claim retracted) |
| `decisions/2026-06-12-engineering-before-model-research.md` | ACTIVE decision | #108 before #106; four unblocking milestones |
| `decisions/2026-06-12-scorer-lineup-decision.md` | ACTIVE decision | PatchTST primary, XGB shadow, ensemble SHELVED + reopening triggers |
| `design/2026-06-12-short-selling-design.md` (+spec, +lit review) | merged design; impl gated | shorts: P0 hedge > P2 efficiency > P1 shelved; G-E6/G-EXEC gates; max 2; no regime precondition |
| `audit/2026-06-11-false-bear-buy-suppression-cascade.md` | resolved (fixes shipped) | the false-BEAR cascade; P0–P4 fix map |
| `research/2026-06-12-patchtst-capability-boundary.md` | merged research | measured IC, freshness-vs-regime confound, info-expansion evidence |
| `research/2026-06-12-model-edge-recovery-plan.md` | WS-1/2/3 approved | data hygiene / PIT retrains / regime-conditional allocation |
| `research/2026-06-11-regime-detection-hmm-markov-switching-rfc.md` | approved RFC | HMM regime engine, shadow-first |
| `research/2026-06-11-max-hold-time-exit-rfc.md` | implemented (#27) | max_hold = far backstop only; never sub-horizon per-regime |

**Rules for agents:** errata > body where they conflict · decisions block
roadmaps · experiments live on `epic/model-edge-experiments`, never main ·
PRs under operator review are FROZEN · all merges by humans.
