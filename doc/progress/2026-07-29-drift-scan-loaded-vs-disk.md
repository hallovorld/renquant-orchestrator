# Progress: the drift scan now checks whether a reviewed launchd change is in FORCE

STATUS:   delivered (check + 13 tests, live-validated clean on this machine).

WHAT:     `ops/run_surface_drift_check.py` gains `read_loaded_program_args()`
          and `check_launchd_loaded()`, wired into `main()` as surface (c).
          For every manifested job it compares what launchd has ACTUALLY
          LOADED against the plist on disk, and alarms when they differ.
          A job that is not loaded at all is deliberately NOT reported — that
          is a liveness question, and alarming on it would fire on every job
          the operator has intentionally stopped.

WHY/DIR:  Editing a plist does not reload it. launchd keeps serving the
          definition it loaded until something re-bootstraps the job, so a
          reviewed change can land in the manifest, land on disk, and never
          take effect — while the existing manifest-vs-disk check reports
          clean the entire time. That is the silent half of a run-surface
          change and it was previously unmonitored.

          Found by walking into it. Verifying the rq105 export fix
          (orch#599), the 2026-07-29 06:15:04 run had produced
          `score_source=prod` while the plist on disk said wrapper. The plist
          had been switched at 06:29:53 — fourteen minutes AFTER that run —
          so the output was from the old definition and the fix was fine. But
          establishing that took hand-comparing three timestamps (plist mtime,
          output mtime, `launchctl print … runs =`). Nothing in the scan could
          distinguish "deployed, not yet run" from "not working", which is
          exactly the distinction an operator needs at 06:20.

EVIDENCE: artifact: `ops/run_surface_drift_check.py` +
                    `tests/test_drift_scan_loaded_vs_disk.py`, this branch on
                    `renquant-orchestrator` @ origin/main 51bc7e1e.
  prod or exp:      PROD ops tooling, READ-ONLY. The check shells `launchctl
                    print` and reads plists; it mutates nothing, reloads
                    nothing, and writes nothing.
  existing data:    Yes — measured on this machine this session, not recalled.
                    rq105 plist mtime `Jul 29 06:29:53`; that day's export meta
                    written `Jul 29 06:15:04`; `launchctl print` reports the
                    loaded arguments ARE the wrapper and `runs = 0` since the
                    re-bootstrap. Live run of the new check across all 30
                    manifested jobs: **clean**, with 3 jobs (`daily103`,
                    `open103`, `preclose103`) correctly reported as not loaded
                    rather than as drift.
  best-known?:      Yes for the gap. NOT claimed: that the rq105 blend fix
                    works — its first scheduled run under the new definition
                    is 2026-07-30 06:15 and remains UNVERIFIED until then.
  scope:            `renquant-orchestrator` ops + tests. No pin advanced, no
                    umbrella change, no live surface mutated, no job reloaded.

VERIFICATION (identical PYTHONPATH on both sides):
  baseline `origin/main` : 7 failures
  this branch            : 7 failures
  The one differing entry (`test_cli.py::test_parking_sleeve_cli_computes_
  allocation`) is a worktree-environment artefact: it resolves
  `<checkout_parent>/renquant-strategy-104/configs/strategy_config.json`,
  which does not exist beside a scratch worktree. That test does not reference
  the changed module (`grep -c run_surface_drift tests/test_cli.py` = 0).
  New tests: 13 passed.

NEXT:     Check the 2026-07-30 06:15 run for `score_source: blend` with a
          populated `blend_component_sha256s`. From tomorrow the scan answers
          the "is it in force" half automatically; the "did it produce blend"
          half still needs the output read.
