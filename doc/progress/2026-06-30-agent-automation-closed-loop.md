# agent-automation closed loop — design RFC

STATUS:   design for review (no implementation, no wiring). Per operator: describe → PR → Codex review → then build.
          r2 (2026-06-30): revised to address Codex (`haorensjtu-dev`) CHANGES_REQUESTED at head f11e20c1.
          r3 (2026-06-30): revised to address Codex round-3 CHANGES_REQUESTED at head e1941719 (the concurrency
          claim was internally inconsistent). Full map in design §0.2.
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
R3 FIX (response to Codex round-3, 1 blocking point; full map in design §0.2):
          BLOCKING — the cloud fix runner never acquired the authoritative local lease, so the concurrency claim
          was internally inconsistent: r2 §5 had claude-code-action PUSH the fix while §6 made the local store the
          authoritative cross-runtime lock, but a GitHub-hosted Action can neither see nor acquire that lease →
          a local fix and a cloud fix could still race; stale-cancellation was only advisory.
          RESOLUTION — choose ONE executable architecture, specified end-to-end. r3 adopts OPTION (a): the LOCAL
          POLLER is the SOLE fix executor. GitHub supplies review EVENTS only; the lease-holding poller is the one
          component that authors + pushes a fix, with HEAD-SHA REVALIDATION immediately before push (design §5.2).
          claude-code-action is removed from the fix/push path entirely → "one fix per PR across all runtimes"
          holds BY CONSTRUCTION. §5/§6/§7/§8.2/§9 rewritten to be mutually consistent under option (a); new §6.5
          states the chosen option (a) + documents OPTION (b) (shared transactional lock/state service reachable by
          both runtimes, lease + head-SHA revalidation before push) as the alternative required ONLY if a cloud
          executor is ever truly needed, with its added infra cost — not adopted today.
          Phase-0 harness gains a REAL local-vs-cloud executor RACE test (two executors contend for the same
          (repo,pr,head_sha); pass = exactly one pushes, other coalesces/aborts-as-superseded, no double-push /
          divergent head) — added to Phase-0 exit gate + Phase-2 pass criteria (design §9).
CI DEP:   Codex flags CI red on the shared weekly-APY tests (553 pass, 2 fail). Those 2 failures are SHARED and
          PRE-EXISTING (not introduced by this PR — this PR is design-docs only, no code) and are being fixed on a
          SEPARATE branch. Required checks must be GREEN before this PR merges; tracking that as a merge dependency,
          not a change owned by this RFC.
EVIDENCE: all 5 safety requirements were hit MANUALLY this session (design §1): RFC r1→r5 + 4-round feature PR
          (non-termination); a real same-branch push-reject (concurrency); the monthly spend cap killed in-flight
          subagents (budget); the WF-gate reject mislabelled 🔴 ERROR (ntfy noise); real-money live system + the
          2026-06-25 live-tree `git reset --hard` near-miss (merge/deploy gate).
          `[design only — no new measurement; grounds on existing agent_workflows.py + PR #197]`
SCOPE:    this PR = design doc (doc/design/2026-06-30-agent-automation-closed-loop.md) + this progress note. No code.
NEXT:     if Codex approves the r3 direction, follow-up patches a one-paragraph clause into doc/agent-pr-workflows.md
          (§2.2) recording the high-risk merge-freeze amendment; then Phase 0 = identity probe + shadow harness +
          the local-vs-cloud race test in a sandbox repo before any live wiring. Separately: get the shared
          weekly-APY CI back to green (owned elsewhere) so required checks pass before merge.
</content>
