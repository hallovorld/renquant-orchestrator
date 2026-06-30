# agent-automation closed loop — design RFC

STATUS:   design for review (no implementation, no wiring). Per operator: describe → PR → Codex review → then build.
WHAT:     RFC for an event-driven closed loop that automates the 3 agent hops the operator runs by hand —
          (A) ntfy alert → Claude triages, (B) Claude opens PR → Codex reviews, (C) Codex comments → Claude fixes —
          fused into ONE state machine with explicit human gates. Recommends a HYBRID architecture.
WHY/DIR:  the operator drives this loop manually today; automate the trigger WITHOUT touching the merge authority.
          Key decision: GitHub-NATIVE for B+C (Codex GitHub app auto-review; @anthropics/claude-code-action) =
          vendor-maintained, event-driven, nothing to build; n8n ONLY for A (ntfy→triage), the cross-system glue
          n8n uniquely provides (ntfy is not a GitHub event). The existing agent_workflows.py + CODEOWNERS mutual
          review stay the source of truth for what may merge; this RFC changes only what triggers an agent.
EVIDENCE: all 5 safety requirements were hit MANUALLY this session (cited in §1 as motivation): RFC r1→r5 +
          a 4-round feature PR (non-termination); a real same-branch push-reject (concurrency); the monthly
          spend limit killed in-flight subagents (budget); the WF-gate reject mislabelled 🔴 ERROR (ntfy noise);
          real-money live system + the 2026-06-25 live-tree `git reset --hard` near-miss (merge/deploy gate).
          `[design only — no new measurement; grounds on existing agent_workflows.py + PR #197]`
SCOPE:    this PR = design doc (doc/design/2026-06-30-agent-automation-closed-loop.md) + this progress note. No code.
NEXT:     resolve the 8 open questions (esp. Q3: does n8n beat the existing local poll?), then Phase 1 =
          ntfy→triage bridge only, read-only/advisory; Phase 2 = native fix↔review loop behind the human merge
          gate; never a Phase 3 that hands merge/pin-bump/deploy to an agent.
