# Relocate the fractional-sizing enablement proposal to renquant-strategy-104

STATUS:    delivered (relocation). Removes
           `doc/design/2026-07-29-enable-fractional-sizing.md` from this
           repo. The proposal now lives, substantially revised, in
           `hallovorld/renquant-strategy-104#70`. This PR is reduced to
           this progress doc documenting the relocation.

WHAT:      Codex BLOCKER found the canonical config this PR proposes to
           change (`kelly_sizing`, `execution.fractional_shares`) is owned
           by `renquant-strategy-104`, not orchestration — this repo may
           later record an approved rollout and its run bundle, but should
           not host the decision or the proposed policy patch itself. Per
           the umbrella multi-repo code-placement rule, this PR completes
           that move.

           While relocating, three substantive fixes landed (full detail in
           `renquant-strategy-104#70`'s own progress doc): (1) resolved the
           config/runtime discrepancy the original flagged as unresolved —
           it was a stale umbrella-tree snapshot copy, not a live baseline
           problem; (2) found an already-reviewed, more rigorous enablement
           contract for this exact change exists from 2026-07-12, staged
           but never merged to `renquant-strategy-104` `main` — this
           proposal's own checklist is not a substitute for it; (3) fixed
           an invalid full-funnel comparison criterion ("no existing order
           changes" is not achievable even in a correct implementation,
           since fractional fills consume cash that can legitimately shift
           later whole-share orders in the same session).

WHY/DIR:   Per the umbrella multi-repo code-placement rule (strategy policy
           -> the owning strategy repo, never the orchestrator), this repo
           does not own live capital-gate proposals for strategy-104.

EVIDENCE:  n/a

NEXT:      This PR now carries no config-change proposal of its own — the
           relocated proposal and its full evidence are in
           `renquant-strategy-104#70`. Review continues there. If GOAL-6 or
           any orchestrator-side sequencing needs this decision, cite
           `renquant-strategy-104#70` directly; nothing further pending in
           this repo for this proposal.
