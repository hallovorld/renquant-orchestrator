# 2026-07-05 rq105 paper trading readiness checker + setup docs

## What

Added `ops/renquant105/check_paper_trading_readiness.py` -- a read-only
diagnostic that verifies all prerequisites for enabling rq105 paper trading.
Updated `ops/renquant105/README.md` with the paper trading setup process.

## Why

PR #365 merged the paper-mode authorization gate. The operator needs a
pre-flight checklist before Monday's paper trading enablement. Without it,
the operator would have to manually trace through intraday_session_runner.py
and intraday_live_executor.py to understand which files/flags/thresholds the
session runner will check at startup.

## What the checker verifies

1. `data/rq105/` directory exists
2. `section_9_4_economic_authorization.json` present with correct paper content
   (`authorized: true`, `prereg_id: rq105-paper-canary-prereg-v1`)
3. `PaperBrokerPort` importable from `renquant_execution`
4. Quintuple arming gate prerequisites:
   - G1: `intraday_decisioning.enabled=true` + `mode=live` in strategy config
   - G2: `stage2_authorization.json` present with required schema keys
   - G3: `RENQUANT_INTRADAY_LIVE` env flag set truthy
   - G4: `intraday_decisioning.KILL` file absent
   - G5: `stage2_canary_state.json` accessible (or absent = OK for first run)
5. Shadow session manifest count >= `MIN_SHADOW_SESSIONS_CLEAN_PAPER` (1)

Prints a clear pass/fail checklist with remediation instructions for failures.
Exit 0 = ready, exit 1 = blocked.

## Safety

The script is strictly read-only -- it checks files but never creates or
modifies any. Follows the same pattern as `check_activation_prereqs.py`.

## Round 2 (Codex review — duplicated gate logic + hard-coded path)

Codex blocked this for a design reason: the checker had reimplemented the
§9.4 authorization check and the G1-G5 arming gate logic as a separate,
parallel copy instead of calling the authoritative implementations, and
hard-coded a machine-specific fallback path
(`/Users/renhao/git/github/RenQuant`) instead of using `runtime_paths`'
real resolver. Both created drift risk: if the gate semantics moved, this
checker could silently go stale while still looking official.

Fixed by extracting the real logic into standalone, importable functions
and calling them directly — not by writing a second implementation:

- `intraday_session_runner.py`: extracted `SessionRunner._check_section_9_4`
  into a module-level `check_section_9_4_authorization(data_root)`, and
  `SessionRunner._build_kill_switch` into `build_kill_switch(intraday_config,
  data_root)`. Both the runner's own methods and the checker now call the
  same functions — no duplicate copy either way.
- The checker's G1-G5 checks (previously five separate hand-rolled
  functions re-deriving the same booleans the real gate computes) are
  replaced by ONE call to `intraday_live_executor.resolve_stage2_arming` —
  the exact function `SessionRunner._evaluate_arming` calls — built from the
  real `load_intraday_config`, `default_authorization_path`,
  `default_canary_state_path`, and a real `KillSwitch`. The checker no
  longer has its own opinion about gate semantics at all.
- `MIN_SHADOW_SESSIONS_CLEAN_PAPER`, `PAPER_PREREG_ID`, `SECTION_9_4_FILENAME`
  are now imported directly instead of re-declared as local constants.
- `_resolve_data_root()` removed; the checker now calls
  `runtime_paths.default_data_root()` (env-var-first, repo-relative fallback
  via `__file__` — no hard-coded absolute path anywhere in the module).

Verified the coupling is real, not just visually similar: temporarily
changed `MIN_SHADOW_SESSIONS_CLEAN_PAPER` from 1 to 5 in
`intraday_live_executor.py` and confirmed the checker's own threshold and
failure message changed to 5 with zero edits to the checker script, then
reverted the test change. Also ran the checker end-to-end against a
synthetic data root confirming (a) a genuinely empty root fails all 4
gated checks with correct remediation text, and (b) a partially-satisfied
root produces the exact real per-gate reason string from
`resolve_stage2_arming` (e.g. "gate 2 (authorization file): authorization
file absent... gate 5 (canary envelope): cannot evaluate... fails closed"),
proving the real function is genuinely being called, not a lookalike.

`[VERIFIED — coupling test (temp constant edit) + end-to-end synthetic-root
runs, this session]`

Full suite: 2886 passed, 3 skipped (2 pre-existing unrelated failures in
`test_bundle_consistency_ci_gate.py`, confirmed reproducing identically on
clean `origin/main` earlier this session — not caused by this change).
