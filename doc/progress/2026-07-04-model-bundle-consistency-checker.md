# Pre-deploy model bundle consistency checker — default-path cleanup

STATUS: ready
WHAT: follow-up hardcoded-path cleanup for the existing pre-deploy model bundle
consistency checker (`scripts/check_model_bundle_consistency.py`, already on
main via #172/#173 with its 11 existing tests across
`tests/test_check_model_bundle_consistency.py` (7) and
`tests/test_bundle_consistency_ci_gate.py` (4)). This PR does NOT add the
checker or its tests — it only replaces the checker's hardcoded
`DEFAULT_REPO = Path("/Users/renhao/git/github/RenQuant")` with
`default_data_root()`, matching the same campaign-D path cleanup already
applied to `attribution/ledger.py`, `decision_pnl_attribution.py`, and
`transfer_coefficient.py`.
WHY/DIR: same class of fix as campaign D / OR-9 (#307) — hardcoded
workstation-local absolute paths break portability. The checker itself
(config fingerprint, watchlist parity, calibrator/scorer fingerprint binding,
WF-gate metadata contracts; motivated by the 2026-06-23 XGB deploy hitting
all four one-by-one in production) already existed and is unchanged in
behavior here.
EVIDENCE: no new tests added — the existing 11 tests continue to pass
unmodified against the new `default_data_root()`-based default.
NEXT: merge.

Round 2 (this update): corrected the PR narrative. Codex correctly flagged
that the original wording claimed to "commit the untracked" checker + "7 unit
tests," but `git log` confirms both the script and its tests landed via #172
(`5e5fdbde`/`1b9f9729`) and #173 (`cf74d129`/`27892dd1`) well before this PR.
The only functional change here is the one-line `DEFAULT_REPO` path fix.
