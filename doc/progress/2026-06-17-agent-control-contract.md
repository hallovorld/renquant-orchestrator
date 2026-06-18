# Agent Control Contract + per-PR progress-doc rule   (PR #153)

STATUS:    in-progress (awaiting operator review; not self-merged)

WHAT:      Rewrites `doc/AGENT-RETROSPECTIVE.md` from a self-criticism essay into an
           **agent control contract** — the external controls (C1 mechanical sandbox /
           read-only prod, C2 status+evidence templates the operator bounces, C3 scoped
           tasks, C4 constraint ledger, **C5 a committed progress doc in every PR**)
           that contain a *systemic* failure, because agent promises do not bind.
           Adds this `doc/progress/` convention, plus **`doc/AGENT-STATE.md`** — the
           externalised executive memory (long-term agreements · mid-term plan ·
           short-term state) the agent refers to every session. Links both from
           `doc/INDEX.md` (grep-first) and `CLAUDE.md` (loaded every session).

WHY/DIR:   The recurring ~100× failure is systemic, not task-level; it cannot be fixed
           by the agent promising to behave. Direction: shift all reliance from
           agent self-discipline to **external, mechanical or auto-detectable controls**,
           and make every action leave a durable, reviewable record (this doc rule).

EVIDENCE:  n/a (process/docs change — no model or data claim).

NEXT:      Operator decision: (1) merge or amend this contract; (2) whether the agent
           should build the C1 prod-path write-guard hook + C2 template linter (the only
           controls that block a violation mechanically rather than after the fact).
