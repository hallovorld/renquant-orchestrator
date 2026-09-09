# CI went red on every orchestrator PR when the A4-T1 window closed   (PR #TBD)

STATUS:    delivered — repo-wide unblock: `test` fails on EVERY orchestrator
           PR from 2026-09-08, including doc-only ones.
WHAT:      `ops/renquant104/a4t1_promote_staged.sh` gains one documented TEST
           seam: `RQ_A4T1_AS_OF` (shape-checked `YYYY-MM-DD` before python
           runs, exit 2 on anything else) forwarded as `--as-of`. Unset — the
           production case — the command is byte-identical to before and the
           CLI resolves the wall clock exactly as it does today.
           `tests/test_a4t1_governance.py::_sub_env` sets it to the frozen
           `A4T1_AS_OF` (2026-09-01) already used by every in-process test,
           plus one new test pinning the seam itself: a malformed value is
           refused before python and writes no verdict file, and with the
           variable UNSET the wrapper forwards no `--as-of`, so today's real
           date decides (inside the window PROMOTED, outside
           `refused_on = temporal_bounds`) — the production contract, asserted
           either way rather than assumed.
WHY/DIR:   The A4-T1 authorization record carries `temporal_bounds
           [2026-08-31, 2026-09-07]`, and `a4t1-promote` defaults `as_of` to
           `dt.date.today()`. Every in-process test passes a frozen date; the
           end-to-end test drives the bash wrapper, which had no way to, so it
           read the wall clock. It passed for eight days and then failed on
           2026-09-09 UTC — one day past the bound — and will fail every day
           after: `AssertionError: a4t1-promote: exit 1 … assert 1 == 0`. A
           wall-clock exception window plus a subprocess test is a dated
           bomb, and it went off on a doc-only PR, which is how it was found.
           Direction: G-D — the merge gate must fail for a real defect, not
           for the calendar; with codex quota already out to 2026-10-03 a red
           `test` on every PR would have hidden any genuine regression behind
           a permanent red.
EVIDENCE:  artifact:      `renquant-orchestrator#1118` (ledger + progress doc ONLY) run 34315987882 → `FAILED tests/test_a4t1_governance.py::test_bash_wrapper_end_to_end_records_the_verdict — AssertionError: a4t1-promote: exit 1 (verdict recorded at …/20260831T141820Z.a4t1_promote.json); assert 1 == 0`, `1 failed, 7176 passed, 78 skipped`; the same failure on #1117 (run 34315626130) [VERIFIED — `gh run view --log-failed`, 2026-09-08 ~23:5x PDT]
           prod or exp:   no production behaviour change — the seam is inert unless the variable is set, and the promote path, the authorization record, the ledger and the temporal bound are untouched
           existing data: `tests/test_a4t1_governance.py` 23 passed with the fix (22 existing + 1 new seam test); with the change stashed, the SAME test file on `origin/main` reproduces `FAILED … test_bash_wrapper_end_to_end_records_the_verdict` on today's date [VERIFIED — 2026-09-09 between 00:05 and 00:15 PDT, both runs in one scratch worktree]
           best-known?:   n/a — test-infrastructure repair; no model or governance claim. It does NOT extend the window: outside `[2026-08-31, 2026-09-07]` the production wrapper still refuses on `temporal_bounds`, and the new test asserts that
           scope:         "this adds one env-gated `--as-of` passthrough used by the test suite; it does not change what the promote path decides, when the exception is valid, or any artifact"
NEXT:      the two red PRs (#1117, #1118) go green once this merges and they
           rebase. Same class, not fixed here and worth a sweep when codex is
           back: any other subprocess test that reads the wall clock against a
           dated bound — `renquant-backtesting`'s A4-T1 suite is the first
           place to look, since `freshness_fallback` carries the same window.
