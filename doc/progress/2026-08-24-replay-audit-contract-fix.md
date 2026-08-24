# The replay audit compared what the recorder never persists — fixed, and GREEN

STATUS:   delivered. replay_audits_green — the §9.3a evidence item that was
          FALSE this morning — is now TRUE for all three audited sessions,
          with the reports committed as evidence.
WHAT:     first-ever runs of the RFC#208 §6 replay harness showed 31/32
          decision mismatches on 2026-08-19/20/21. Diagnosis chain, each step
          eliminating one hypothesis by measurement: correct-config rebind
          (still 31/32) → session-era code via scratch worktree at 3bc782ab
          (still 31/32) → per-key payload diff → ROOT CAUSE: the recorder
          strips the ~90KB decision_trace on no-intent ticks (stamping
          decision_trace_stripped) and every real shadow tick to date is a
          no-intent tick, while the audit compared the UNSTRIPPED replay
          canonically. A contract drift between recorder and verifier — with
          the recorder's own rule applied, 0/32 mismatches on all three
          sessions.
          FIX: the stripping rule is extracted as ONE named function
          (strip_noop_decision_trace) used by BOTH the recorder and the audit
          (the wf_promote_outcome lesson: two copies of a rule drift). PLUS a
          binding guard: the audit now REFUSES (fail closed) when the supplied
          --strategy-config does not hash to the manifest's
          strategy_config_fingerprint — I ran three misbound audits silently
          before this existed, against the pinned config while the scheduler
          had resolved the sibling checkout.
WHY/DIR:  replay_audits_green is a hard §9.3a authorization-evidence item for
          105 live (orch#1039). It also proves the shadow loop is genuinely
          deterministic — the strongest property the live flip rests on.
EVIDENCE:
  artifact:      shared stripper + audit fix + binding guard + 3 new tests
                 (13 total green) + the three green reports under
                 doc/research/data/2026-08-24-replay-audits/.
  prod or exp:   exp — audit is read-only; no live surface touched.
  existing data: replay OK 32/32 x3 with correct binding [VERIFIED — CLI runs];
                 misbinding refused with both hashes named [VERIFIED];
                 mutation: removing the audit-side stripping turns the
                 no-trade regression test red [VERIFIED]; the old suite never
                 caught this because its fixture session HAS intents — the
                 new fixture is intent-free like every real tick to date.
  best-known?:   yes — comparing what the recorder persists is the only
                 comparison that can ever be green across a stripping recorder.
  scope:        harness + recorder refactor (behaviour-identical write path)
                + tests + evidence reports. SEPARATELY FILED, not fixed here:
                the scheduler resolves the SIBLING checkout's strategy config
                in preference to the pinned copy (orch#1016-class).
REVIEW:    codex (haorensjtu-dev).
