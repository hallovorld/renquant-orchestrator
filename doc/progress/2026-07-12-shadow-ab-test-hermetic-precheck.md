# fix: make shadow-ab tests hermetic against dirty sibling repos

**Date**: 2026-07-12 (updated 2026-07-11 — see "Final fix" below)
**PR**: #489, `fix/shadow-ab-test-hermetic-precheck`

## Problem

6 of 15 `test_shadow_ab_daily_script.py` tests failed locally when sibling
repos (renquant-artifacts, renquant-pipeline) had untracked files. The
tests used REAL sibling checkouts in the manifest for their import closure,
and `verify_run_manifest` (the precheck) rejected them as DIRTY before the
actual test logic ran. CI passed because CI checkouts are always clean.

## History (3 review rounds)

1. **Commit `66a494fd`** — first attempt. Added
   `RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY=1`, an env var baked directly
   into the PRODUCTION `scripts/shadow_ab_daily.sh` that skipped the entire
   manifest-verification precheck when set, and set it in the tests that
   don't exercise the precheck itself.
2. **Codex round-2 review (BLOCKING)**: the env var is a production
   bypass of the verify-before-import boundary — a plist that never sets
   it "is not a security control." Ordered: make tests hermetic via clean
   temporary detached worktrees or test-only dependency injection, never a
   production bypass. Also flagged the twin-parity re-pin (P1, see below)
   as unrelated/undocumented.
3. **Commit `be10379b`** responded to the P1 only (twin-parity
   documentation, still thin — see "Twin-parity re-pin" below).
   **Commit `bdfcc45b`** responded to the P0 with a *different* partial
   fix: added `ignore_untracked: bool = False` to
   `deployment_manifest.check_checkout_state` and set
   `ignore_untracked=True` at the `shadow_ab_runner.verify_run_manifest`
   call site — filtering untracked (`?? `) lines out of the dirty check.
   **The `RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY` bypass in
   `shadow_ab_daily.sh` was never removed.**
4. **Codex round-3 review (BLOCKING, on CI)**: CI itself proved the bypass
   was live — `test_dirty_repo_fails_closed_before_either_arm` and
   `test_dirty_manifest_on_non_session_date_fails_closed_not_skip` were
   BOTH failing on CI, because `ignore_untracked=True` made the tests' own
   dirty-simulation (an untracked marker file) silently pass. Ordered:
   remove `RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY` entirely, do not merge
   `ignore_untracked=True`, make test imports hermetic with clean temporary
   worktrees or clones, and preserve the dirty-fails-first regression tests
   on both session and non-session dates.

## Concurrent push during this fix (`5d5d09e1`)

While this fix was in progress, another session pushed
`5d5d09e1` ("fix(test): use git-rm for dirty fixture to fix CI
detection") directly to this branch. That commit is preserved in the
git history (rebased onto, never force-overwritten) but its *content*
went the opposite direction from Codex's round-3 ask, so it was
substantively superseded rather than kept:

- It diagnosed the CI failures Codex reported as a filesystem
  stat-cache timing bug and "fixed" the dirty-repo fixture by using
  `git rm -f README.md` (a tracked-file deletion) instead of writing an
  untracked marker file. Codex's own review already identified the real
  cause precisely: `ignore_untracked=True` filtering out `"?? "` lines,
  not a timing race. Keeping the tracked-deletion fixture would have
  silently dropped the ONE regression case that specifically exercises
  "untracked content must still fail closed" — exactly what round-3 was
  about — so this fix reverts that hunk back to the untracked-marker-file
  fixture (`tests/test_shadow_ab_daily_script.py::_build_manifest`).
- It added `env.pop("RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY", None)` to
  `_env_for` — moot once the whole `skip_manifest_verify` parameter/env
  var is removed (this fix removes it entirely; see below).
- It added a NEW test,
  `test_untracked_files_do_not_trigger_precheck_abort`, asserting
  `returncode == 0` for a manifest with untracked stray files — i.e.
  explicitly codifying the exact behavior Codex's round-3 review says
  must NOT exist ("do not merge ignore_untracked=True... A blanket
  ignore can hide untracked Python, package metadata, or other
  import-affecting content"). This fix removes that test; the correct
  contract (untracked content DOES fail closed) is already covered by
  `test_dirty_repo_fails_closed_before_either_arm` /
  `test_dirty_manifest_on_non_session_date_fails_closed_not_skip`.

Resolved via `git rebase origin/fix/shadow-ab-test-hermetic-precheck`
(never `--force-overwrite`/`push --force` without `--force-with-lease`,
never a bare `reset`) — `5d5d09e1` remains a real ancestor commit in this
branch's history; this fix's commit sits on top of it with the tree
content corrected back onto Codex's round-3 requirements.

## Final fix (this pass)

Implements Codex's round-3 ask completely — no partial pass:

1. **`scripts/shadow_ab_daily.sh`**: removed the
   `RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY` conditional wrapper entirely.
   The run-manifest / pin-identity precheck (`verify_run_manifest`) is
   unconditional again — it always runs first, exactly as it did before
   this PR's first commit. No reference to the env var remains anywhere in
   the file (code, comments, or docstring).
2. **`src/renquant_orchestrator/shadow_ab_runner.py`**: reverted
   `verify_run_manifest`'s call to `check_checkout_state` back to the
   implicit strict default — any untracked file, tracked modification, or
   wrong commit fails closed again. **Round 4 (Codex final cleanup ask):**
   the `ignore_untracked` parameter itself is REMOVED from
   `deployment_manifest.check_checkout_state` entirely, not merely left
   unused — Codex correctly held that leaving dormant bypass machinery on
   the shared verification core (even opt-in, even default-`False`) is a
   latent future-integrity-escape-hatch that contradicts the strict
   multi-repo import-closure rule this whole round exists to enforce; if a
   genuinely narrower exception is ever justified, it needs its own
   reviewed design (an explicit path allowlist plus negative tests), built
   fresh, not resurrected from this PR's unused scaffolding. `deploy_pin.py`
   and `model_identity_tripwire.py`'s evidence checkout verification never
   passed this argument, so removing it is a pure deletion with zero
   behavior change for them.
3. **`tests/test_shadow_ab_daily_script.py`** — root-cause fix, not a
   workaround: `_build_manifest`'s real-import-repo resolution
   (`renquant-common`, `renquant-base-data`, `renquant-artifacts`,
   `renquant-pipeline` — the repos the wrapper script's market-snapshot
   path genuinely imports code from) now points at a **clean, detached
   temporary `git worktree`** of each real sibling checkout's current HEAD
   commit (`git worktree add --detach <tmp_dir> <head-sha>`,
   `_add_detached_worktree`), created under the test's own `tmp_path`
   rather than the real checkout's working directory. A detached worktree
   only ever contains the tracked files at that exact commit, so it is
   clean by construction regardless of what untracked cruft sits in the
   developer's actual local sibling checkout. This makes the manifest
   hermetic WITHOUT weakening `verify_run_manifest`'s clean-tree check at
   all — the opposite direction from the rejected `ignore_untracked`
   approach.
   - New `build_manifest` pytest fixture wraps `_build_manifest` and tears
     down every worktree it creates (`git worktree remove --force`) after
     each test, success or failure, so no `git worktree` registration
     leaks into the real sibling checkouts' `.git/worktrees/` across test
     runs. Verified empirically: `git -C <sibling> worktree list` before
     and after a full local test run shows zero new/leaked entries.
   - All 13 call sites updated from `_build_manifest(tmp_path, ...)` to
     the `build_manifest(...)` fixture factory; `RENQUANT_SHADOW_AB_SKIP_MANIFEST_VERIFY`
     and the `skip_manifest_verify` test helper parameter (on `_env_for`
     and `_env_for_date`) are removed entirely — no test needs it anymore,
     since real-import repos are hermetic by construction and the
     production script no longer honors it.
   - `TestRunManifestVerification::test_dirty_repo_fails_closed_before_either_arm`
     and `TestSessionCalendarGate::test_dirty_manifest_on_non_session_date_fails_closed_not_skip`
     are unchanged in what they assert; their dirty-simulation fixture
     writes an untracked marker file into a FAKE repo (`_init_fake_repo`
     via `dirty="renquant-execution"`), not one of the real-import repos
     going through the new worktree path — so they are unaffected by the
     worktree change and now pass again cleanly with strict verification
     restored.

### Root cause of the untracked content (Codex: "move that writer to a
neutral runtime state root")

Investigated both real sibling checkouts directly (read-only):

- `renquant-artifacts`: `src/renquant_artifacts.egg-info/` — standard
  Python packaging metadata from an editable (`pip install -e`) install.
  Regenerated automatically by `setuptools`/`pip` on every editable
  install/build; not runtime state, not written by any orchestrator or
  pipeline code path, harmless.
- `renquant-pipeline`: an untracked `persistence_backup_check.py` at the
  repo root. Diffed it against the tracked
  `src/renquant_pipeline/kernel/persistence.py`: byte-identical except for
  missing the newest ~63-line "Fill-truth vocabulary" section (dated
  2026-07-11 per its own header comment, referencing orchestrator #484
  §8 item 8). This is a one-off manual backup/diff snapshot an earlier,
  unrelated session made of `persistence.py` before/while editing it —
  not a systematic production code path that writes logs or state into a
  pinned checkout's working tree. No production writer was found.

Conclusion: neither piece of untracked content is a "runtime state being
written into a pinned code checkout" in the sense Codex was concerned
about (an ongoing production code path). No follow-up PR is filed for a
writer, because none was found — and regardless, this PR's fix (hermetic
worktrees, step 3 above) already fully closes the coverage gap independent
of what generates untracked content in either real sibling checkout, so
the test suite's correctness does not depend on that content ever being
cleaned up or explained.

### Twin-parity re-pin (P1)

`be10379b` re-pinned `data/twin_parity_manifest.json`'s `broker` and
`alpaca_broker` diverged-twin hashes. Verified against ground truth for
this doc:

- **Source commit**: `renquant-execution` commit
  `cba1dd90bcd74bfeed43c0e20ca6b45094adb362` ("fix(ledger): shared-wiring
  contract derives account id from the broker", 2026-07-10) is the commit
  that touched exactly `src/renquant_execution/broker.py` and
  `src/renquant_execution/alpaca_broker.py` (`git show --stat cba1dd9`
  confirms both files, and only those two source files, changed).
  `git log cba1dd9..HEAD -- src/renquant_execution/broker.py
  src/renquant_execution/alpaca_broker.py` on the real sibling checkout is
  empty — no further commits touched either file since, so HEAD's content
  is exactly cba1dd9's.
- **Hash match**: `shasum -a 256` on the real sibling checkout's current
  `broker.py`/`alpaca_broker.py` gives
  `9d352f00a996ec3278e9c1e6f14a04590fcd007cd02e8d0ad304a2f9de34eca2` and
  `63bb9caa1751b70b241e74cecb6f4c62daace311660154f2e1fc619b9d07861f`
  respectively — exactly the two `execution_sha256` values `be10379b`
  wrote into `data/twin_parity_manifest.json`.
- **Checker output** (`python3 scripts/check_twin_parity.py
  --siblings-root /Users/renhao/git/github`, run read-only against the
  real sibling checkouts on this machine):

  ```
  [PASS] byte_identical:alerts.py               live/alerts.py == src/renquant_execution/alerts.py (byte-identical)
  [PASS] byte_identical:ibkr_broker.py          live/ibkr_broker.py == src/renquant_execution/ibkr_broker.py (byte-identical)
  [PASS] diverged_pin:broker                    live/broker.py / src/renquant_execution/broker.py match their pinned divergence
  [PASS] diverged_pin:alpaca_broker             live/alpaca_broker.py / src/renquant_execution/alpaca_broker.py match their pinned divergence
  [PASS] diverged_pin:paper_broker              live/paper_broker.py / src/renquant_execution/paper_broker.py match their pinned divergence
  [PASS] diverged_pin:readonly_broker           live/broker_readonly.py / src/renquant_execution/readonly_broker.py match their pinned divergence
  [PASS] constant:MIN_FRACTIONAL_NOTIONAL_USD   execution == pipeline == 1.0
  [PASS] function_pin:compute_parent_intent_id  both function sources match their pins
  [PASS] function_pin:_FIELD_SEP                _FIELD_SEP identical on both sides ('\x1f')
  [PASS] tax_pin:rotation_short_term_rate       rotation_short_term_rate: values [0.5] (x3)
  [PASS] tax_pin:rotation_long_term_rate        rotation_long_term_rate: values [0.32] (x3)
  [PASS] tax_pin:qp_tax_rate_st                 qp_tax_rate_st: values [0.3] (x1)
  [PASS] tax_pin:qp_tax_rate_lt                 qp_tax_rate_lt: values [0.15] (x1)
  [PASS] tax_pin:selection_tax_rate             selection_tax_rate: values [0.3] (x2)

  twin-parity: 14 pass, 0 fail, 0 skip
  ```

  14/14 pass with the currently-pinned manifest — the re-pin is correct
  and current. Documented here rather than split into a separate PR: the
  change is a single 2-field data re-pin (not code), with immutable
  provenance (source commit + hash match + checker output) now recorded
  directly in this progress doc, satisfying Codex's "document execution
  commit and checker output" alternative to splitting.

## Verification

- `tests/test_shadow_ab_daily_script.py`: 15/15 pass locally (isolated
  worktree, never the shared checkout), including both tests Codex cited
  as CI-failing:
  `TestRunManifestVerification::test_dirty_repo_fails_closed_before_either_arm`
  and
  `TestSessionCalendarGate::test_dirty_manifest_on_non_session_date_fails_closed_not_skip`
  — confirmed stable across 3 repeated runs.
- One test, `TestPortableTimeout::test_hung_session_is_killed_and_marked_pair_invalidated`,
  intermittently exceeds the test harness's 30s subprocess wall-clock on
  this machine's slow `python3.9` (CommandLineTools) interpreter — the
  script's own internal watchdog still correctly kills the hung session
  and exits 4 (visible in the captured stderr even on "failure"), it's
  just slower than 30s wall-clock end-to-end. Reproduced identically on an
  UNMODIFIED worktree of the same branch tip (`bdfcc45b`) — pre-existing,
  environment-only, not introduced or worsened by this fix.
- Full repo suite (`python3 -m pytest tests/ -q`): 3685 passed / 8 failed
  (7 pre-existing `cvxpy`-missing environment failures, reproduced
  identically on an unmodified `bdfcc45b` worktree, + the one timing flake
  above) / 4 skipped. Zero new failures introduced by this fix.
- `shellcheck scripts/shadow_ab_daily.sh`: clean.
- No `git worktree` leakage into any of the four real sibling checkouts
  (`renquant-common`, `renquant-base-data`, `renquant-artifacts`,
  `renquant-pipeline`) after the full local test run — confirmed via
  `git -C <repo> worktree list` before/after.
- All work done in an isolated `git worktree` under scratchpad
  (`git worktree add --detach <path> origin/fix/shadow-ab-test-hermetic-precheck`)
  — the shared `renquant-orchestrator` checkout and the shared
  `renquant-artifacts`/`renquant-pipeline` sibling checkouts were never
  written to, only read from (`git worktree add`/`remove` against them,
  never a write inside their own working trees).
