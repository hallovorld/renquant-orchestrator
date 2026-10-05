# Progress: GOAL-2v3 Stage I-2 provenance validates from ANY checkout — path identity is repo-relative (codex r1 on #1091)

STATUS:    delivered. Validator + harness fix; the committed I-2 and I-1 bundles
           are byte-identical (hashes below). No production path written.

WHAT:      Codex r1 on #1091 (MED): from the committed PR worktree,
           `validate_i2_provenance(report, audit, root)` returned one line —
           "DEV_RUN census audit is not the gate bundle's audit
           <review-checkout>/…/g2v3_stage_i0_audit.json.gz" — because the
           validator compared the recorded absolute `inputs.census_audit.path`
           (the run's scratchpad worktree) with the importing checkout's
           `GATE_AUDIT`. It measured the reviewer's disk, not the run. #1091 was
           merged with the CLAIM corrected (bd710130: "verifies from the run's
           own checkout"); this PR corrects the VALIDATOR so the claim is
           unconditional again. Full account (finding, rule, tests, the
           reproduction command) is the "Review r1" section of
           `doc/progress/2026-08-29-g2v3-stage-i2-dev-run.md` (updated here) and
           the Corrections entry of
           `doc/research/2026-08-29-g2v3-stage-i2-dev-run.md`.

           Rule (`scripts/experiments/g2v3_stage_i2_stack.py`): a recorded
           absolute path is resolved against the recorded
           `provenance.source.repo_root` (fallback `invocation.cwd`) to a
           repo-relative path; the file at `<repo_root>/<relative>` must hash to
           the recorded sha256; for DEV_RUN the census audit's relative path
           must be the gate bundle's `<dir>/<audit_file>` and its sha256 the
           bound `audit_sha256`; the consumed-bar cross-check reads that same
           file; `gate_bundle.dir` / `i1_bundle.dir` get the same rule. Inputs
           outside the repository (umbrella SPY parquet, pinned strategy config)
           keep the recorded-path check — they can only be verified where they
           were recorded. Future runs also record `inputs.<x>.path_relative`
           (None outside the repository), checked whenever present.

           `validate_i1_provenance` in `g2v3_stage_i1_bases.py` has the same
           defect and the merged I-1 bundle (#1088) fails identically from any
           other checkout. That file is FROZEN by the I-2 §1 binding
           (`I1_HARNESS_SHA256` — the imported module is the code the accepted
           I-1 bundle was fitted with; `test_i1_harness_changed_or_missing_is_refused`
           and the committed I-2 report's `i1_bundle.harness_sha256` both pin
           its bytes), so it is NOT edited: the correction is
           `g2v3_stage_i2_stack.validate_i1_provenance` — I-1's own checks with
           the absolute-path census-audit verdicts replaced by the repo-relative
           rule. A test pins the frozen validator's single environmental
           failure so the wrapper is retired the day the I-1 harness is
           re-bound with the rule inside.

WHY/DIR:   A validator that passes only from the worktree that produced the
           bundle is "tests that measure the operator's disk": a green that
           nobody else can reproduce. Hash identity is what binds a committed
           file; the absolute prefix is environment.

EVIDENCE:  §4(b) block — this PR makes no model/data claim; the evidence is
           reproducibility.
           artifact:      unchanged — `shasum -a 256 -c` before/after:
                          I-2 `report.json` `8a2804fd…`, `g2v3_stage_i2_audit.json.gz`
                          `6629d29a…`; I-1 `report.json` `666d9c6a…`,
                          `g2v3_stage_i1_audit.json.gz` `d124d8f2…`;
                          `g2v3_stage_i1_bases.py` `13c31d12…` — all OK
                          `[VERIFIED 2026-08-29]`.
           prod or exp:   experiment tooling only; no live path read or written.
           existing data: before the fix, from a fresh `git worktree add` of
                          ec9fe909: I-2 validator 1 problem (the path line), I-1
                          validator 1 problem (the same line) `[VERIFIED]`.
           checks:        after the fix, from a fresh `git worktree add` at
                          another absolute path (76dcb870): `validate_i2_provenance`
                          → `[]`, `validate_i1_provenance` (portable) → `[]`,
                          `I1.validate_i1_provenance` (frozen harness) → the one
                          path line, as pinned `[VERIFIED 2026-08-29]`.
                          `pytest tests/test_g2v3_stage_i2_binding.py
                          tests/test_g2v3_stage_i2_harness.py
                          tests/test_g2v3_stage_i1_provenance.py
                          tests/test_require_progress_doc.py` → 116 passed
                          (17 new: both committed bundles validate from a shared
                          clone at another path; tampered relative path / path
                          outside the recorded root / changed `source.repo_root` /
                          sha256 / `path_relative` / foreign `gate_bundle.dir`,
                          `i1_bundle.dir` / tampered or deleted gate audit in
                          that checkout each still fail) `[VERIFIED pytest, 2026-08-29]`.

Reproduction from any checkout (`<root>` = a fresh `git worktree add <root> <this branch>`):

    cd <root> && PYTHONPATH=src python - <<'PY'
    import gzip, json, pathlib, sys; sys.path.insert(0, "scripts/experiments")
    import g2v3_stage_i2_stack as I2
    root = pathlib.Path(".").resolve()
    b = root / "doc/research/data/2026-08-29-g2v3-i2/i2-dev-20260829T132528Z-5269e593"
    print(I2.validate_i2_provenance(json.load(open(b / "report.json")),
                                    json.load(gzip.open(b / "g2v3_stage_i2_audit.json.gz")), root))   # [] *
    b1 = root / I2.ACCEPTED_I1_BUNDLE["dir"]
    print(I2.validate_i1_provenance(json.load(open(b1 / "report.json")),
                                    json.load(gzip.open(b1 / "g2v3_stage_i1_audit.json.gz")), root))  # [] *
    PY

    * given the two umbrella inputs each bundle records (`data/ohlcv/SPY/1d.parquet`, the
      pinned `strategy_config.json`) on disk where recorded; without them, exactly their two
      `inputs.<x>.path missing on disk` lines and nothing else — see "CI at 9be7cdd4" below.

Review r2 (codex, MED): `repo_relative` used `PurePath.relative_to`, which keeps `..`,
so `<recorded repo_root>/../outside/x` became the relative path `../outside/x` and
`repo_root / rel` was read directly — a tampered `inputs.spy_daily` / `strategy_config`
pointing at an outside file with a matching sha validated `[]` `[VERIFIED — reproduced]`.
Fix: `_abs_segments` / `path_form_problems` — a recorded path (and `source.repo_root`)
must be absolute with no '', '.' or '..' segment, else a problem in its own right, never
"outside the repository"; `repo_relative` is a lexical strict-descendant test on those
segments (its result can never carry a dot segment); `confined()` requires
`(repo_root / rel).resolve()` inside `repo_root.resolve()` (symlinks resolved) before any
read; `path_relative` must itself be relative and dot-free. Tests: the exact r2 repro for
`spy_daily`, `strategy_config` and the census audit across six traversal forms, on both
validators; a malformed `source.repo_root`; a symlink inside the checkout to an
outside copy with the right bytes. Artifacts still byte-identical
`[VERIFIED shasum -a 256 -c]`.

Follow-up on r2 (same session, second Claude session verifying at 78735625):
a refused `inputs.strategy_config` record (symlink leaving the checkout) was
still opened by the sector-map rebuild after the "resolves outside repo_root"
line was recorded `[VERIFIED — read_text probe at 78735625: the refused
link path was read]`. `_input_file_problems` now returns no path for a refused
or malformed record and the rebuild is guarded on it, so nothing is read for a
refused record; pinned by
`test_refused_strategy_config_is_not_parsed_for_the_sector_map_rebuild`
(outside file with a DIFFERENT sector_map behind the link: refusal line
present, no sector_map / sha256 line). Four test files → 133 passed
`[VERIFIED pytest, 2026-08-29]`.

CI at 9be7cdd4 (both `test` jobs red — 5 failed / 7000 passed / 74 skipped
`[VERIFIED — gh run view 33257622787 / 33257625808 --log-failed]`): five of the new
tests measured the operator's disk — the very defect this PR names. The two
"committed bundle validates from a checkout at another path" tests asserted `== []`,
but each committed bundle records two inputs OUTSIDE this repository (the umbrella's
`data/ohlcv/SPY/1d.parquet`, the pinned `strategy_config.json`) that the validator can
only check where they were recorded, and the frozen I-1 harness also reads the census
audit at the run's scratchpad-worktree path; the r2-repro cases for `spy_daily` /
`strategy_config` and the sector-map guard test copied those umbrella files' bytes. The
runner clones no umbrella, so: `inputs.spy_daily.path missing on disk` +
`inputs.strategy_config.path missing on disk` from both portable validators, those plus
the census line from the frozen harness (4 lines, not 1), and `FileNotFoundError` in the
other three `[VERIFIED — the same two-line / four-line verdicts reproduced locally with
the recorded outside paths re-pointed at nonexistent ones]`.

Fix (tests only; validator and bundles untouched): `_recorded_inputs_absent_here(rep)`
derives the validators' exact verdict on THIS machine — one `missing on disk` line per
recorded input it does not hold (outside-the-repo inputs for the portable validators;
every input for the frozen harness) — and the two bundle tests assert equality with it:
`[]` where the umbrella inputs live, exactly those lines and nothing else elsewhere, so a
checkout at another path still pins that the repo-relative census / gate / I-1 identity
is clean (a skip would not). The r2 repro for the umbrella inputs writes synthetic bytes
and re-points the record's sha256 at them (the r2 move itself; the refusal is lexical,
before any byte is read) — the census case stays a byte copy of the checkout's audit. The
sector-map guard test uses a minimal config with a foreign `sector_map` and a positive
control (the same bytes at a confined path DO add the `inputs.sector_map_sha256` line),
so its "not parsed" assertion is not vacuous. The `-> []` claim here and in the #1091
record docs is stated with its condition (footnote above).

Four test files → 133 passed `[VERIFIED pytest, 2026-08-29]`. The binding file under a
CI-condition shim (a `pathlib.Path.is_file` override reporting every umbrella and
scratchpad-worktree path absent, as on the runner) → 88 passed; the same shim on the
pre-fix tests → 2 failed / 86 passed, the two verdict failures CI showed (the three
`FileNotFoundError` cases are the umbrella reads themselves, which the fix removes)
`[VERIFIED pytest -p ci_sim, 2026-08-29]`. The CI result itself is read off the PR checks
after the push, not asserted here.

Memory tier touched: none (no new agreement; the lesson "tests that measure the
operator's disk" already exists). Not self-merged; Codex approval is the gate.
