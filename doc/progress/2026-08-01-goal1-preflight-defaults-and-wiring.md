# shadow_lane_preflight: resolved defaults, the SKIP fix, and a caller at last (GOAL-1)

## What landed (#723's two findings, closed)

1. **Zero declared bases → SKIP, not FAIL.** `ok=False` asserted "does not resolve" on
   the strength of never having been told where to look — the same epistemic state as
   multi-base ambiguity, which the module already graded `ok=None`. Now consistent.
2. **Resolved defaults, so an argless run means something:** lanes = whatever
   `shadow_models` the pinned config declares (read, never hardcoded); the watched set
   defaults from the CONFIG's declared lanes (deliberately not from `--lane`, so an
   explicit lane against an empty config still hits the pre-existing empty-watched
   refusal); bases default to the deployment's own split — `backtesting/renquant_104`
   AND the umbrella root, because that is literally where the two live lanes' artifacts
   are (clf under the former, PatchTST under the latter — measured when the single-base
   first draft FAILED the PatchTST lane on first contact).
3. **Wired into `ops_audit` MEMBERS** — the merged-with-no-caller state #723 named is
   over; the contract-pin test carries the new member with its exit-code citation, and a
   config declaring no shadow_models is a FINDING (exit 1), not a silent pass.

## Live argless run `[本次实测 2026-08-01]`

`0 failed, 1 skipped` (rc=3): both declared lanes' artifacts resolve uniquely under the
dual bases and the clf artifact loads; the PatchTST `.pt` lands `artifact_loads: SKIP`
because the loader knows xgboost only — an honest UNESTABLISHED kept visible by rc=3.

## Review notes

* The watched-default direction was corrected against an existing test mid-development:
  defaulting watched from `--lane` would have silently retired the empty-watched refusal
  contract. The config is the source; the CLI lane never is.
* Multi-lane argless output aggregates per-lane reports with lane-prefixed failure names.

Tests: 4 added + the ops_audit contract pin. Suite: 5390 passed, 2 skipped — green
before this push.
