# LONG-ledger row 2d — one-time authority for the correlation-artifact PATH fix (orch#1065)

STATUS: ledger-only PR, row-2a/2b/2c precedent: the authority row lands on
orchestrator `main` BEFORE the config PR merges. **Confirmation slot FILLED
2026-09-03** with the operator's first-hand reply 「授权，加速」("authorized,
speed up"), given between 18:01 and 18:10 PDT in the Claude operator session
428feb92 in direct reply to the agent message that enumerated the pending
operator decisions — "codex plan/credits; second A4-T1 license before 09-07;
untrack artifacts/prod/*; CRWV/RKLB/SPCX; row 2d (orch#1081, correlation
artifact path)". Recorded exactly as that: a reply to an enumerated list that
named this row and this change, not a message that restates the change
itself. Whether that meets the row-2b bar ("first-hand, change-specific") is
for the reviewer; the slot quotes what was said and nothing more. Posted with
timestamp on this PR and on renquant-strategy-104#104.

## The decision this row records (once confirmed)

Exactly one renquant-strategy-104 PR (branch `fix/corr-artifact-maintained-path`,
commit befb03d at preparation) moves `regime.correlation_artifact` from
`prod/watchlist-correlation.json` to `watchlist-correlation.json` in the
eight carriers rows 2a/2b move (active, golden, six prod-mirror lanes) plus
`regime._correlation_artifact_reason` on active + golden. No other key, file
or PR; frozen arms untouched; no artifact file written or promoted.

## Why a row is required

Row 2 makes `strategy_config.json` read-only with no exception. This is a
production-config write, so it needs its own single-use, PR-named row with
first-hand operator authority — the blanket directive of 2026-08-28
(「全面推进,不要停,别等我」) names no change and is therefore recorded as the
reason the package was prepared without waiting, NOT as authority.

## Evidence (file:line citations are in the row itself)

- Served copy: mtime 2026-05-23, `as_of_date` 2026-05-22, 60-day build, no
  regeneration job [VERIFIED — read-only json load, live umbrella].
- Maintained copy: mtime 2026-08-23, `as_of_date` 2026-08-21, written by
  pipeline `CorrelationJob` on every weekly retrain (rolling 120 bars)
  [VERIFIED — same read; `pp_training.py:653-701`].
- Cost: 80 dead blocks + 108 invisible conflicts at 0.70 [VERIFIED — prior
  work, orch#1065].
- Rail: P-CORR-FRESHNESS (pipeline#299, pinned at 76ab129) soft FAIL at 67
  NYSE sessions on the prod copy, soft ok at 5 on the maintained copy;
  P-CORR-METADATA hard ok on both; leakage assert behaves as designed
  [VERIFIED — read-only run against both files, 2026-08-29].
- Resolution parity across all consumers → bare filename [VERIFIED —
  preflight.py:1131-1137, portfolio_qp/tasks.py:314-319,
  runner_artifacts.py:36, LEAN main.py:257-259 + kernel/config.py:24-35].
- WF gate inert: `wf_config_builder.py:456-466` preserves the sim base's key.
- Estimand differs (120-bar vs 60-day): pairs ≥ 0.70 are 128 vs 171
  [VERIFIED — offline count]; flagged in the row, not hidden.

## What confirms this row

Operator states, first-hand, in any operator channel, that the narrowed
package above is approved (e.g. 「确认 correlation_artifact → maintained
file」). The verbatim text, date and channel go into the row's slot; the same
confirmation is posted with timestamp on this PR and on the strategy-104 PR.
Until then both PRs stay open and unmerged.

## Memory tier touched

LONG (`doc/memory/long-term-agreements.md`, row 2d appended after 2c; no
existing row's meaning edited).
