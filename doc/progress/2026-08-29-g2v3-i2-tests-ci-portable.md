# Progress: GOAL-2v3 Stage I-2 — the bundle tests no longer measure the operator's disk (main red after #1092)

STATUS:    delivered. Tests + record docs only; the validator
           (`scripts/experiments/g2v3_stage_i2_stack.py`) and the committed I-2 /
           I-1 bundles are untouched. No production path written.

WHAT:      #1092 was squash-merged as 56c07cba with both `test` CI jobs red —
           5 failed / 7000 passed / 74 skipped `[VERIFIED — gh run view
           33257622787 / 33257625808 --log-failed]` — so main's own CI at
           56c07cba is red for the same five tests `[VERIFIED — gh run list
           --branch main: 56c07cba CI failure]`. All five are in
           `tests/test_g2v3_stage_i2_binding.py` and all five measured the
           operator's disk — the very defect #1092 named in the validator:
           - the two "committed bundle validates from a checkout at another
             path" tests asserted `== []`, but each bundle records two inputs
             OUTSIDE this repository (the umbrella's `data/ohlcv/SPY/1d.parquet`,
             the pinned `strategy_config.json`) that the validator can only
             check where they were recorded, and the frozen I-1 harness also
             reads the census audit at the run's scratchpad-worktree path;
           - the r2-repro cases for `spy_daily` / `strategy_config` and the
             sector-map guard test read those umbrella files' bytes.
           The runner clones no umbrella: two `inputs.<x>.path missing on disk`
           lines from both portable validators, those plus the census line from
           the frozen harness, `FileNotFoundError` in the other three.

           Fix (tests only): `_recorded_inputs_absent_here(rep)` derives the
           validators' exact verdict on THIS machine — one `missing on disk`
           line per recorded input it does not hold — and the two bundle tests
           assert equality with it: `[]` where the umbrella inputs live, exactly
           those lines and nothing else elsewhere, so a checkout at another path
           still pins that the repo-relative census / gate / I-1 identity is
           clean (a skip would not). The r2 repro for the umbrella inputs writes
           synthetic outside bytes and re-points the record's sha256 at them
           (the r2 move itself; the refusal is lexical, before any read). The
           sector-map guard test uses a minimal config with a foreign
           `sector_map` plus a positive control (the same bytes at a confined
           path DO add the `inputs.sector_map_sha256` line). The `-> []` claim
           is stated with its condition in the #1092 progress doc, the I-2
           dev-run progress doc and the I-2 research record (Corrections).
           Full account: "CI at 9be7cdd4" in
           `doc/progress/2026-08-29-g2v3-i2-provenance-repo-relative.md`.

WHY/DIR:   A test that is green only where the umbrella lives is the same
           "green nobody else can reproduce" #1092 set out to remove. The exact
           machine-derived verdict keeps CI asserting the repo-relative identity
           instead of skipping it.

EVIDENCE:  §4(b) block — no model/data claim; the evidence is reproducibility.
           artifact:      unchanged — `git diff --name-only origin/main`: the test
                          file + four record docs only; nothing under
                          `doc/research/data/` `[VERIFIED 2026-08-29]`.
           prod or exp:   test tooling only; no live path read or written.
           existing data: the CI failure logs above; reproduced locally by
                          re-pointing the recorded outside paths at nonexistent
                          ones — the same two-line / four-line verdicts, nothing
                          else `[VERIFIED 2026-08-29]`.
           checks:        `pytest tests/test_g2v3_stage_i2_binding.py
                          tests/test_g2v3_stage_i2_harness.py
                          tests/test_g2v3_stage_i1_provenance.py
                          tests/test_require_progress_doc.py` → 133 passed at this
                          commit `[VERIFIED pytest, 2026-08-29]`. The binding file
                          under a CI-condition shim (a `pathlib.Path.is_file`
                          override reporting every umbrella and scratchpad-worktree
                          path absent, as on the runner) → 88 passed; the pre-fix
                          tests under the same shim → 2 failed / 86 passed (the two
                          verdict failures CI showed; the three `FileNotFoundError`
                          cases are the removed umbrella reads)
                          `[VERIFIED pytest -p ci_sim, 2026-08-29]`. The CI result
                          is read off this PR's checks, not asserted here.

Memory tier touched: none (no new agreement). Not self-merged; Codex approval
is the gate.
