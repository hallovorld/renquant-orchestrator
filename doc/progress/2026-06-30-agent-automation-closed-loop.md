# agent-automation closed loop — design RFC

STATUS:   design for review (no implementation, no wiring). Per operator: describe → PR → Codex review → then build.
          r2 (2026-06-30): revised to address Codex (`haorensjtu-dev`) CHANGES_REQUESTED at head f11e20c1.
WHAT:     RFC for an event-driven closed loop that automates the 3 agent hops the operator runs by hand —
          (A) ntfy alert → Claude triages, (B) Claude opens PR → Codex reviews, (C) Codex comments → Claude fixes —
          fused into ONE state machine with explicit human gates.
WHY/DIR:  the operator drives this loop manually today; automate the TRIGGER without weakening the merge authority.
          r2 answers the architecture question directly: START by extending the EXISTING local queue/poller +
          deterministic control plane (agent_workflows.py); add n8n ONLY if a MEASURED cross-host fan-out need
          appears. n8n is demoted from r1's day-one HYBRID to a conditional, deferred option.
R2 FIXES (response to Codex, 5 points; full map in design §0.1):
          1. Merge agreement — no longer "permanently human-only". PRESERVE deterministic merge for ORDINARY
             approved PRs; MANDATORY human hold only for a named high-risk set (prod paths / generated PRs /
             pin-deploy / policy changes / escalations). Framed as an explicit AMENDMENT to doc/agent-pr-workflows.md
             with operational cost stated (design §2).
          2. Identities were ASSUMPTIONS — added a Phase-0 disposable-PR identity probe (App review = bot identity;
             GITHUB_TOKEN push = github-actions[bot], NOT hallovorld/haorensjtu-dev). Defines how agent_workflows.py
             maps VERIFIED trusted identities to logical agents WITHOUT weakening self-review (design §3).
          3. Added a real THREAT MODEL for a write-capable agent on untrusted PR content — pull_request (not
             pull_request_target), fork=no-secrets, actor/repo allowlists, immutable SHA pins, least-priv
             permissions:, secret gating, path/workflow-change blocks, narrow command allowlist (not Bash(git*)/
             gh*), default-deny egress; prompt delimiter is NOT a security boundary (design §7).
          4. Defined ONE ATOMIC state/lock SoT keyed by (repo,pr,head_sha,review_id): atomic acquire/lease/expiry,
             idempotency, stale-cancel, coalescing, crash recovery, single transition owner. Actions concurrency
             serializes Action JOBS only, not local/n8n workers (design §6).
          5. Rollout now tests the dangerous path FIRST: new Phase 0 (identity probe + shadow/replay + adversarial
             injection/workflow-mod + duplicate/out-of-order + crash recovery + sandbox repo), canary allowlist,
             pre-registered caps X/Y/Z/W + divergence metric as blocking Phase-2 gate criteria (design §9).
EVIDENCE: all 5 safety requirements were hit MANUALLY this session (design §1): RFC r1→r5 + 4-round feature PR
          (non-termination); a real same-branch push-reject (concurrency); the monthly spend cap killed in-flight
          subagents (budget); the WF-gate reject mislabelled 🔴 ERROR (ntfy noise); real-money live system + the
          2026-06-25 live-tree `git reset --hard` near-miss (merge/deploy gate).
          `[design only — no new measurement; grounds on existing agent_workflows.py + PR #197]`
SCOPE:    this PR = design doc (doc/design/2026-06-30-agent-automation-closed-loop.md) + this progress note. No code.
NEXT:     if Codex approves the r2 direction, follow-up patches a one-paragraph clause into doc/agent-pr-workflows.md
          (§2.2) recording the high-risk merge-freeze amendment; then Phase 0 = identity probe + shadow harness in
          a sandbox repo before any live wiring.
</content>
