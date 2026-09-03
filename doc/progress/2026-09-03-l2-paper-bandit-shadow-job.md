# L2 paper-bandit shadow job — manifest legitimisation (operator grant 2026-09-03)

STATUS:    the job is INSTALLED and LOADED (com.renquant.l2-paper-bandit,
           weekdays 15:45 local, production venv, PYTHONPATH = the
           operator-synced `renquant-orchestrator-run/src`, RunAtLoad=false);
           this PR is the same-batch reviewed-surface update the containment
           protocol requires. Until it merges AND `-run` is synced, the
           run-surface drift scan correctly alarms "unmanifested job" — that
           alarm is the DESIGNED reminder and is being closed by review, not
           silenced. Tracker issue: see PR body (owner, grant, expiry, literal
           revert steps).

WHAT:      ops/launchd_manifest.json += com.renquant.l2-paper-bandit with
           program_args and program_args_sha256 computed by the drift check's
           own recipe (`sha256(json.dumps(program_args))`,
           ops/run_surface_drift_check.py:185-186) and an evidence_glob on the
           engine's append-only log
           (`logs/l2_paper_bandit/l2_paper_bandit.jsonl`).

WHY/DIR:   Operator 2026-09-03: "make moe run in daily shadow asap!". The MoE
           direction is the three-layer allocation machine (orch#918); L2 =
           "to whom" — Hedge/EG weights over the expert paper books the shadow
           lanes already mark daily (engine orch#923, merged 2026-08-09; the
           progress doc for that PR named the job install as its own granted
           batch, exactly like L1's orch#921). Shadow phase: publishes weights
           and logs; allocates nothing; no orders, no config, no live surface.

SCHEDULE:  15:45 weekdays. The engine replays the FULL weight history from the
           arm DBs on every run and REFUSES (exit 1, never appends) if any
           existing log row diverges from the replay. A day's row may therefore
           be written only once that day's marks are FINAL:
           - champion (`data/runs.alpaca.db`): post-close snapshot from daily104
             (13:55 + runtime);
           - three profile books (`runs.alpaca_shadow_blend*.db`): marked by
             shadow-ab-daily, observed 14:14-14:20 on 2026-09-02
             [VERIFIED — DB mtimes];
           - l1-exposure-shadow fires 15:30; 15:45 keeps the two shadow
             writers ordered.
           RunAtLoad=false for the same reason: an install-time run at 07:15
           would freeze the 07:00 dawn-preflight champion mark into the log
           and poison it permanently.

EVIDENCE:  artifact:      installed plist (plutil-linted, bootstrapped,
                          launchctl-listed, state "not running", RunAtLoad
                          false) [VERIFIED — install session 07:15 PDT];
                          module import + data-root resolution verified under
                          the PRODUCTION venv with the -run PYTHONPATH from
                          both the orchestrator and umbrella cwd → data root
                          `/Users/renhao/git/github/RenQuant` [VERIFIED]
           dry run:       read-only over the real arm DBs, log to session
                          scratch: SYNCED, 96 rows replayed, latest weights
                          champion 0.504974 / profile_blend 0.166017 /
                          profile_blend_mom 0.164518 / profile_blend_rb_mom
                          0.164491, zero clips [VERIFIED — module stdout,
                          2026-09-03 07:10 PDT]. That run's 09-03 row shows
                          all three profiles EXCLUDED (no mark yet pre-close)
                          — expected, and the production job never runs in
                          that state.
           prod or exp:   prod run surface — under the standing operator grant
           existing data: manifest jobs count +1; the L1 sibling
                          (com.renquant.l1-exposure-shadow) has written a row
                          every trading day since 2026-08-10 through
                          2026-09-02 [VERIFIED — jsonl tail]
           best-known?:   n/a — ops change
           scope:         one manifest entry + this record + tracker issue.
                          Departure from L1: PYTHONPATH points at the
                          `-run` checkout (main, ff-only), not the dev checkout
                          L1 uses, so the job runs what review merged, never
                          whatever branch the dev tree happens to be on.

TESTS:     drift check run on this branch's manifest and on the production
           (`-run`) manifest; see PR body for the two outputs — the branch
           reports no l2 finding, the production one alarms on the
           unmanifested job (the expected window). Engine behaviour itself: 7
           tests, orch#923.

NEXT:      first scheduled row today 15:45; confirm the row lands, the exit
           code is 0 and launchd_stderr stays empty; drift finding closes
           post-merge + `-run` sync; weights line joins the ops report; two
           weeks of live weight history before any proposal, per the design.
