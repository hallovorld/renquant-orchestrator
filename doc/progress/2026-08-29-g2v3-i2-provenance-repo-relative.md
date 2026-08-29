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
                                    json.load(gzip.open(b / "g2v3_stage_i2_audit.json.gz")), root))   # []
    b1 = root / I2.ACCEPTED_I1_BUNDLE["dir"]
    print(I2.validate_i1_provenance(json.load(open(b1 / "report.json")),
                                    json.load(gzip.open(b1 / "g2v3_stage_i1_audit.json.gz")), root))  # []
    PY

Memory tier touched: none (no new agreement; the lesson "tests that measure the
operator's disk" already exists). Not self-merged; Codex approval is the gate.
