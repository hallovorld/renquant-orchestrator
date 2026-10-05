# Progress: GOAL-2v3 Stage I-0 gate run — PASS

Run from the frozen commit f3d5bf7b with --gate-run after the operator
acknowledged Amendment A1. BEAR n_eff_adj 191 vs bar 30; all regimes clear.
Stage I-1 proceeds per the merged preregistration (#1076).

## Packaging (review r1 of #1083)

- Gate-run bundle is immutable under its own identity:
  `doc/research/data/2026-08-29-g2v3-i0-gate-run/` (run ID
  `i0-gate-20260829-f3d5bf7b`): report (sha256 `da41a706…`), gz audit
  (`dd5127d7…`), and `provenance.json` (frozen commit + clean tree, exact
  invocation, UTC start/end derived from file timestamps, seed hash/count,
  full frozen parameter block, script + design-doc hashes at f3d5bf7b,
  input-manifest aggregate over the audit's per-file bar hashes, output
  hashes, verdict cross-check).
- The 2026-08-27 DEVELOPMENT_ONLY artifacts in
  `doc/research/data/2026-08-27-g2v3-i0/` are restored byte-for-byte to
  their main content — the before/after record is intact.
- `tests/test_g2v3_gate_run_bundle_provenance.py` (collected by `make test`)
  validates every GATE_RUN bundle against its provenance and proves the
  check bites on a tampered copy.
- The gate result itself was NOT rerun or altered.
