# agent-automation closed loop — design RFC

STATUS:   design for review (no implementation, no wiring). Per operator: describe → PR → Codex review → then build.
          r2 (2026-06-30): revised to address Codex (`haorensjtu-dev`) CHANGES_REQUESTED at head f11e20c1.
          r3 (2026-06-30): revised to address Codex round-3 CHANGES_REQUESTED at head e1941719 (the concurrency
          claim was internally inconsistent). Full map in design §0.2.
          r4 (2026-06-30): revised to address Codex round-4 CHANGES_REQUESTED at head 1c2e8725 (1 blocking SECURITY
          point — a /tmp clone is NOT a sandbox). Full map in design §0.3.
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
R4 FIX (response to Codex round-4, 1 blocking SECURITY point; full map in design §0.3):
          BLOCKING — a /tmp clone is NOT a sandbox. The r3-chosen option (a) still ran `claude -p` + PR-controlled
          tests on the PERSISTENT operator host beside the live tree; untrusted repo code executes during
          tests/import/build hooks and can read the user's home, Keychain sockets, git credential helpers, other
          repos, SSH config, local DBs, ambient network. Keeping the PAT out of the agent env + telling the model
          not to touch the live tree does NOT contain arbitrary code execution — and it contradicted §7.5's own
          "no untrusted PR code on a persistent self-hosted runner" rule.
          RESOLUTION — specify an ENFORCEABLE two-process sandbox boundary (design §5.2/§7.5/§7.3):
          * agent + PR-controlled tests run INSIDE an ephemeral OS/container/VM sandbox with ONLY the disposable
            checkout mounted — NO host home / Keychain / docker socket / other repos / SSH config / live tree;
            NO push credential inside; resource limits (cpu/mem/pids/wall-time); default-deny egress + narrow allowlist.
          * the sandbox exports ONLY a bounded patch + test evidence (no arbitrary host access, no credential, no push).
          * OUTSIDE the sandbox the POLLER validates the changed paths/content (§7.4), re-checks the leased head SHA
            (§5.2), then applies/commits and pushes with the scoped token (§7.3) — poller-only push authority.
          * the fix AGENT tool allowlist now contains NO commit/push/merge/force-push — removed §7.5's self-contradiction
            that still granted the agent "scoped commit/push"; only the poller (outside the sandbox) holds push authority.
          * §7.5's "no untrusted code on a persistent host" rule reconciled: untrusted code runs in a disposable
            per-run sandbox, never on the bare host. §5/§6/§7 made mutually consistent under this sandbox model.
          Phase-0 gains a REAL sandbox ESCAPE/EXFILTRATION suite (attempt to read ~, ~/.ssh, ~/.aws, ~/.config/gh,
          credential-helper output, Keychain/docker sockets, sibling repos, live tree; attempt non-allowlisted egress;
          pass = all unreachable / blocked, no push token present, only patch+evidence emitted) — added to the Phase-0
          exit gate AND the Phase-2 pass criteria; distinct from the prompt-injection fixtures (which test the model,
          not the environment) (design §9).
CI DEP:   Codex flagged CI red on the shared weekly-APY tests (553 pass, 2 fail). Those 2 failures are SHARED and
          PRE-EXISTING (not introduced by this PR — this PR is design-docs only, no code). r4 MERGES origin/main
          (weekly-APY CI fix #211, now on main) into this branch so the shared required `test` check runs against the
          fixed tree. Required checks must be GREEN before this PR merges.
EVIDENCE: all 5 safety requirements were hit MANUALLY this session (design §1): RFC r1→r5 + 4-round feature PR
          (non-termination); a real same-branch push-reject (concurrency); the monthly spend cap killed in-flight
          subagents (budget); the WF-gate reject mislabelled 🔴 ERROR (ntfy noise); real-money live system + the
          2026-06-25 live-tree `git reset --hard` near-miss (merge/deploy gate).
          `[design only — no new measurement; grounds on existing agent_workflows.py + PR #197]`
SCOPE:    this PR = design doc (doc/design/2026-06-30-agent-automation-closed-loop.md) + this progress note. No code.
NEXT:     if Codex approves the r4 direction, follow-up patches a one-paragraph clause into doc/agent-pr-workflows.md
          (§2.2) recording the high-risk merge-freeze amendment; then Phase 0 = identity probe + shadow harness +
          the local-vs-cloud race test + the sandbox escape/exfiltration suite in a sandbox repo before any live
          wiring. CI: origin/main (weekly-APY fix #211) is now merged into this branch, so the shared required
          `test` check should go green.
</content>
