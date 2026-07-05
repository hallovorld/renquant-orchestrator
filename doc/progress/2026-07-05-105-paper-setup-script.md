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

## Round 4 (Codex review — strategy-config input-source drift)

Codex confirmed round 3's logic-sharing fix was genuinely correct
("materially better... mostly fixed"), then found a deeper, distinct gap:
`check_quintuple_arming_gate()` unconditionally read
`data_root / "strategy_config.json"`, while a real session is launched
against an *explicit pinned* strategy config path. That meant the checker
could report a readiness verdict against a different intraday config than
the one production will actually use — an input-source drift problem, not
a logic-duplication problem this time.

Investigated how every real launch entrypoint in this repo resolves its
strategy-config path: `intraday_session_scheduler.py`, `intraday_quote_logger.py`,
and `train_gbdt.py` all follow the identical pattern — an explicit
`--strategy-config` CLI override takes precedence; absent that, fall back to
`runtime_paths.default_strategy_config_path()` (which itself checks the
strategy-104 subrepo path, then an umbrella fallback). No non-test code in
this repo constructs `SessionRunner` directly yet (no CLI wiring exists for
it), so there's no single existing call-site to point at — but this
repo-wide convention is exactly the "wrapper/artifact contract" codex
referenced.

Fixed by adopting the same convention in the checker itself:
- Added an explicit `--strategy-config` CLI argument to `main()` (via
  `argparse`), documented as "pass the exact path you intend to launch a
  real session with."
- `check_quintuple_arming_gate()` no longer resolves any path itself — it
  now takes `strategy_config_path` as an explicit parameter, so it
  structurally cannot guess wrong.
- `main()` resolves the path exactly like every other real entrypoint:
  `Path(args.strategy_config) if args.strategy_config else
  default_strategy_config_path()` — imported directly from `runtime_paths`,
  not re-derived.
- Module docstring updated to state the resolution contract explicitly.

Added `tests/test_check_paper_trading_readiness.py` (3 tests): (1) an
explicit `--strategy-config` path is genuinely read, proven against a decoy
file sitting at the old hardcoded `data_root / "strategy_config.json"`
location; (2) absent an override, the checker calls the same
`default_strategy_config_path()` real entrypoints use, again proven against
a decoy at the old hardcoded location; (3) `check_quintuple_arming_gate()`
fails closed with a `--strategy-config`-mentioning remediation when the
passed-in path doesn't exist — it no longer has any fallback path logic of
its own. Confirmed via `git stash` that all 3 tests genuinely fail against
the pre-fix code (`AttributeError`/`TypeError` — the pre-fix function
signature and module didn't even have the surface these tests exercise),
then pass after.

`[VERIFIED — stash-diff pre/post-fix test failure, this session]`

Full suite: 2978 passed, 3 skipped (same 2 pre-existing unrelated failures
in `test_bundle_consistency_ci_gate.py`, confirmed reproducing identically
on clean `origin/main`).
