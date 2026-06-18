# Agent Control Contract + AGENT-STATE + per-PR progress-doc rule   (PR #153)

STATUS:    in-progress (awaiting Codex review; not self-merged)

WHAT:      Rewrites `doc/AGENT-RETROSPECTIVE.md` into an **agent control contract**
           centred on systemic solutions. Controls C1 (mechanical sandbox/read-only
           prod), C2 (status+evidence templates), C3 (scoped tasks), C4 (constraint
           ledger in `doc/AGENT-STATE.md`), C5 (a committed progress doc in every PR).
           Enforcement model set to **Codex review = the merge gate** (operator does
           NOT read every PR); §7.1 is the checklist Codex applies per PR. Adds
           `doc/AGENT-STATE.md` (long-term agreements · mid-term plan · short-term
           state). Wired into `doc/INDEX.md` (banner + Active-docs table) and
           `CLAUDE.md`; `agent-pr-workflows.md` now names §7.1 as the review standard.

WHY/DIR:   The recurring ~100x failure is systemic; agent promises don't bind. Direction:
           move all reliance onto EXTERNAL enforcement — Codex review per PR against a
           documented standard, plus non-LLM mechanical gates for high-stakes/irreversible
           actions (since Codex is also an LLM = correlated blind spots).

EVIDENCE:  n/a (process/docs change — no model or data claim).

UPDATE:    Implemented the memory as a real **three-tier structure** under `doc/memory/`
           (`long-term-agreements.md` binding ledger · `mid-term-plan.md` direction ·
           `short-term-state.md` disposable state) + `memory/README.md` (protocol,
           precedence LONG>MID>SHORT, per-tier cadence & enforcement). `AGENT-STATE.md`
           is now the thin front-door pointer.

NEXT:      Codex review of this PR; operator decision on whether the agent builds the
           C1 prod-path write-guard hook (the one control that blocks a violation
           mechanically rather than at review time).

UPDATE2:   Refined shape per tier + wrote explicit update rules (who/when/how/enforcement)
           in memory/README.md. MID is now a **folder** (`memory/mid-term/`: _north-star +
           one file per workstream: model-edge, win-rate-payoff, intraday-governor,
           agent-control). LONG stays a single binding-ledger file (Codex loads it whole);
           SHORT stays a single snapshot file (a folder would make it a log).
