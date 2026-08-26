# Legitimize the RENQUANT_INTRADAY_DECISIONING activation into the reviewed surface

Date: 2026-08-26
Branch: `ops/legitimize-intraday-decisioning`

## What

Commit, byte-for-byte, the activation edit that has been living as an
UNCOMMITTED modification in the `renquant-orchestrator-run` checkout since
2026-08-12: `ops/renquant105/run_session_scheduler.sh` exports
`RENQUANT_INTRADAY_DECISIONING=1` (G-H task#28, operator-authorized
2026-08-12; shadow/never-submit is runtime-asserted; revert = re-comment the
line).

## Why now

- CONTAINMENT PROTOCOL (c): a change meant to persist must land on the
  reviewed surface. This one has persisted 14 days as a dirty working-tree
  edit. The run-surface drift scan alarming on the dirty `-run` tree is the
  designed reminder — this PR is the "legitimize" arm of that alarm.
- The edit has ALREADY been lost-and-reapplied once: the 2026-08-24 #1044
  ff-merge conflicted with the stashed copy (UU), and the resolution had to
  re-apply the export by hand. [VERIFIED: the comment block in the live diff
  records this.] A recovery checkout or clean-sync at any point would
  silently DEACTIVATE the operator's authorized decision loop — the
  `recovery-checkout-clobbers-code-hotfixes` failure shape, aimed at a live
  activation.
- Behavior change of this PR: NONE at merge time. The running launchd job
  already executes with the flag active (the -run tree carries the identical
  bytes); this moves the authority for those bytes from an uncommitted edit
  to a reviewed commit.

## Deploy note (the step that ENDS the alarm)

After merge, the `-run` sync must reconcile the now-redundant local edit:
`git -C renquant-orchestrator-run checkout -- ops/renquant105/run_session_scheduler.sh`
(content becomes identical to the incoming commit) then the usual ff-only
advance. File content before and after is byte-identical — the flag never
blinks. This is a landing action; it rides the next authorized -run sync.

## Revert

Re-comment the `export RENQUANT_INTRADAY_DECISIONING=1` line in a reviewed
commit (or, in an emergency, in the -run tree WITH a containment record per
CLAUDE.md).
