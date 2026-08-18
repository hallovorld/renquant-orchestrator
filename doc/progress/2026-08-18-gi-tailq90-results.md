# G-I `tail_q90_60d` — the authorized one-shot screen run: FLAGGED

STATUS:    delivered. The ONE authorized execution of the frozen, reviewed
           runner (spec orch#994, runner orch#996) has happened; the
           `tail_q90` family's one-shot budget is SPENT. Verdict at the
           trained horizon (h=60 PRIMARY): **FLAGGED**. Results, memo, and a
           TEST AMENDMENT forced by this PR's own arrival (see TESTS) — no
           src change, no config, no live surface.

WHAT:      Executed `doc/research/data/2026-08-18-gi-tailq90-derivation.py`
           VERBATIM from orchestrator main `9d73d546` (byte-identity asserted
           by the runner's own T2 guard; file sha256 `df5c1d66…ae9edc`),
           once, under caffeinate, in an isolated worktree, against read-only
           local stores. Commits the runner's three outputs (results JSON +
           IC-series CSV + refit-ledger JSON, all new files) and the results
           memo `doc/research/2026-08-18-gi-tailq90-results.md`.

           Verdict (h=60 PRIMARY, frozen §4 triage rule): FLAGGED —
           Δ=−0.00801 (mean genuine IC +0.06349 vs placebo +0.07150),
           block-t=−0.717 over 29/29 blocks, pos-blocks 55.2% (16/29; the
           only criterion met). h=20 informational: Δ=+0.01154, t=+1.586,
           pos 55.1% — would have met all three criteria but carries NO
           verdict by the merged spec's §4 REVISION (no horizon rescue).
           ρ (informational): vs the declared same-cutoffs rank-reference
           +0.696 (sd 0.072) — the spec §5 declared near-collision risk
           realised, 0.004 inside the 0.7 bar; vs mom_slow_12m −0.029, vs
           mom_fast +0.045. Runtime 221.4 s; all T1–T15 guards passed, exit
           0, zero deviations, no fix-and-rerun.

WHY/DIR:   Spec §6 sequencing (spec merged #994 → runner committed AND
           reviewed #996 → ONE run on the merged copy) held end to end —
           second consecutive family run under the
           freeze-then-review-then-run contract. G-I screen record on this
           corpus: 0 of 4 not flagged across both families (three #987
           emitters + this candidate). FLAGGED = deprioritised in the #984
           §5b queue + PIT-universe rerun required before any kill; nothing
           is killed and nothing is admitted.

EVIDENCE:
  artifact:      doc/research/data/2026-08-18-gi-tailq90-screen-results.json
                 + …-ic-series.csv + …-refit-ledger.json (written by the
                 run); doc/research/2026-08-18-gi-tailq90-results.md
  prod or exp:   exp — the authorized one-shot triage screen; isolated
                 worktree of main `9d73d546`; read-only inputs (panel
                 parquet, served artifact, OHLCV, watchlist config,
                 production-trainer helpers imported read-only); wrote only
                 doc/research/data/ inside the worktree; no production path
                 touched.
  existing data: the merged spec's priors: n_eff≈16 at h=60
                 (annotation-grade, #987 §4) and the declared HIGH-ρ risk vs
                 core (spec §5) — both materialised as recorded; the #992 moe
                 run (0/3 FLAGGED) on identical OHLCV/SPY digests
                 (`96a1050d…e746` / `68665523…b0ee`), making the two
                 families' screens same-store comparable.
  best-known?:   yes — the only measurement of this candidate on this
                 corpus, produced by the reviewed frozen runner with every
                 guard green, and per the one-shot rule it is FINAL for this
                 corpus; the failure is Δ<0 at the trained horizon, not a
                 power shortfall (the point estimate is on the wrong side of
                 zero).
  scope:         "this is the authorized G-I tail_q90 triage screen, exp, on
                 the survivorship-tilted current-watchlist corpus; the
                 verdict is FLAGGED triage only — deprioritised, PIT rerun
                 required before any kill, no admission, no roster change,
                 no serving change, no deploy."

TESTS:     `tests/test_tailq90_runner.py` AMENDED on this head (34 tests).
           An earlier revision of this doc said "none added/changed"; that was
           accurate when the PR carried results only and went stale the moment
           the amendment landed — codex MED, 2026-08-18.

           Why the amendment was unavoidable: the suite merged with #996
           contained `test_this_pr_ships_unrun_no_outputs_committed`, which
           called the RUNTIME guard `rn.assert_one_shot()` against the real
           `OUTPUTS`. That was true of the RUNNER PR (#996 shipped un-run,
           spec §6) but is not an invariant — THIS PR is the authorized run
           and legitimately commits those outputs, so the test could only ever
           fail from here on. A one-shot property asserted as a permanent test
           necessarily breaks at the one shot; CI failed on exactly that.

           The runtime guard is UNCHANGED and still refuses a second
           execution. Only the test's subject moved, from repository state to
           behaviour:
           * `test_one_shot_guard_fires_when_an_output_already_exists` drives
             `assert_one_shot()` on tmp_path outputs — passes when absent,
             raises when present, raises when ANY of several outputs exists.
           * `test_the_authorized_run_outputs_are_present_on_this_branch` —
             the complement: this branch IS the run, so the declared `OUTPUTS`
             must be committed here.
           Load-bearing, verified by neutering the guard's existence check:
           2 failed neutered, 34 passed restored.

           The run itself passed all 15 runtime guards (T1–T15) and exited 0.

NEXT:      per the merged spec, `tail_q90_60d` sits deprioritised in the
           #984 §5b queue; its only path forward is the point-in-time
           universe rerun (kill-side) or the full confirmatory path
           (admit-side) — and the ρ=0.696 near-collision with the core
           recipe caps its roster value even if a PIT rerun cleared it. The
           one-shot marker (T1) forbids re-execution against the committed
           output paths.
