# rq105 SessionRunner CLI — `python -m renquant_orchestrator.intraday_session_runner`

STATUS: delivered (additive CLI + tests; SHADOW-by-default / never-submit posture unchanged)

WHAT:   adds the deferred "LiveSessionRunner + CLI" of RFC #208 — a `main(argv=None, *,
        tick_runner=None, live_state_provider=None, calendar=None) -> int` entry point on
        `intraday_session_runner.py` (+ `if __name__ == "__main__": raise SystemExit(main())`)
        so `python -m renquant_orchestrator.intraday_session_runner` drives the full
        `SessionRunner.run_session(...)`. The CLI mirrors the shadow scheduler's argument
        surface (`--strategy-config --data-root --db --out --manifest --order-state-file
        --data-manifest --artifact-manifest --env-file --mode --max-cycles --json
        --log-level`) and its fail-closed pipeline binding, then builds a `SessionRunnerConfig`
        + a lazy `port_factory` (real `AlpacaBrokerPort` for real mode, `PaperBrokerPort` for
        paper mode) and prints the `SessionResult`. The default `AlpacaLiveStateSource` read
        account is derived from the SAME §9.4 artifact the runner uses to select the port, so a
        paper-authorized session reads the paper book (no split-brain sizing).
        `SessionRunner.run_session` self-gates: §9.4 economic-authorization check → derive
        paper → §9.3a quintuple arm → shadow or live. With no authorization files present (the
        normal state) it falls through to the UNCHANGED Stage-1 `SessionScheduler` (shadow) and
        the `port_factory` is never invoked.

WHY/DIR: RFC #208 deferred the live SessionRunner + its CLI; the shadow scheduler already
        ships a launchd CLI (`intraday_session_scheduler:main`) but there was no module entry
        point that exercises the integrated `SessionRunner` (Stage-1 + Stage-2 arming + §9.4
        gate + software stops + entry-timing shadow observer) as one session lifecycle. This is
        the wiring that lets the operator run the full runner — still shadow until the §9.4 file
        and the quintuple gate both arm, neither of which this PR creates.

EVIDENCE:
  Claim 1 — the CLI is additive: `intraday_session_scheduler.py:main()` and the running
            shadow path are byte-for-byte unchanged (the runner-shadow setup is DUPLICATED,
            not refactored), so the shadow scheduler's tests stay green.
    artifact:   src/renquant_orchestrator/intraday_session_runner.py (new `main`),
                src/renquant_orchestrator/intraday_session_scheduler.py (unchanged)
    prod or exp:   production code (feature branch)
    existing data:   `git diff` touches only intraday_session_runner.py (new imports + new
                `main`) and the two test files; the scheduler module is untouched, and
                tests/test_intraday_session_scheduler.py all pass.
    best-known?: n/a
    scope:      one new module-level CLI; no change to SessionRunner/SessionScheduler class
                behavior
    [VERIFIED — code read + full `make test`; intraday suites green]

  Claim 2 — default is SHADOW and submits NOTHING: with no §9.4 file a full ticking session
            runs, records shadow ticks, arms nothing, and writes no live-order artifact; the
            broker port_factory is never constructed.
    artifact:   tests/test_intraday_session_runner_cli.py
                ::test_cli_full_shadow_session_no_auth_submits_nothing
    prod or exp:   experiment (regression test)
    existing data:   end-to-end run of `main([... --max-cycles 1 --json])` →
                `mode_effective=="shadow"`, `armed is False`, status in
                {completed, stopped_max_cycles}; ≥1 recorded shadow tick all `mode=="shadow"`;
                `section_9_4_economic_authorization.json` absent; `intraday_live_actions.jsonl`
                and `intraday_decisions_live.jsonl` never written. `--mode live` still shadow
                (gates 2-5 + §9.4 absent).
    best-known?: n/a
    scope:      CLI shadow path; broker never touched
    [VERIFIED — pytest, 7/7 in the new file]

  Claim 3 — the default live-state READ account matches the §9.4-selected execution backend
            (no split-brain sizing).
    artifact:   src/renquant_orchestrator/intraday_session_runner.py (main, live_state_provider
                construction) + tests/test_intraday_session_runner_cli.py
                ::test_cli_live_state_read_account_follows_section_94_gate
    prod or exp:   experiment (regression test) over production code
    existing data:   `main` calls `check_section_9_4_authorization(data_root)` before building
                the default `AlpacaLiveStateSource` and passes `paper=is_paper`. Test asserts:
                a §9.4-paper file (prereg_id==PAPER_PREREG_ID) → source built with `paper=True`;
                no §9.4 file (shadow default) → `paper=False`. The paper-file case never arms
                (stage2 authorization absent) so no live submit — the assertion is on the
                read-source construction only.
    best-known?: n/a
    scope:      default live-state read source; three §9.4 states (absent/paper/real)
    [VERIFIED — pytest]

  Claim 4 — fail-closed like the scheduler: no injected tick_runner and no
            `--data-manifest`/`--artifact-manifest` ⇒ refuse (rc 2), never invent a decision
            path (hard boundary: no decision/sizing internals here).
    artifact:   tests/test_intraday_session_runner_cli.py
                ::test_cli_fails_closed_without_pipeline_manifests
    prod or exp:   experiment (regression test)
    existing data:   `main(["--strategy-config", cfg, "--data-root", tmp])` → rc 2 before any
                session runs; mirrors the scheduler CLI's fail-closed test.
    best-known?: n/a
    scope:      CLI pipeline binding
    [VERIFIED — pytest]

SAFETY: no live arming. `SessionRunner`/`SessionScheduler` class behavior untouched; the §9.4
        economic-authorization gate and the §9.3a quintuple arm are the same code paths; no
        authorization file is created, placed, or templated; `AlpacaLiveStateSource` stays
        GET-only; the broker `port_factory` is lazy and only reachable from `_run_live` after
        BOTH gates arm. No live-tree / `renquant-orchestrator-run` / launchd / `ops/` / `data/`
        / `logs/` production writes; work is confined to a feature-branch worktree.

NEXT: (lead, NOT done here — merged != deployed) this CLI is inert until an operator records
      the §9.4 economic-authorization decision AND the §9.3a arming artifacts; do NOT wire it
      into launchd in this PR. When live intraday is authorized, a separate reviewed batch adds
      the ops wrapper/plist (mirroring `run_session_scheduler.sh`) and advances the
      `renquant-orchestrator-run` pin. Until then the runner CLI is a shadow-equivalent of the
      scheduler CLI.
