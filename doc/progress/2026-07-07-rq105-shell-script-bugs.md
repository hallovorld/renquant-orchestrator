# 2026-07-07 — Fix rq105 session-scheduler shell script

**PR**: orchestrator bugfix

## Bug

`run_session_scheduler.sh` in the repo was missing a legitimate PYTHONPATH
fix that a live-tree operator hotfix had applied to the `-run` deployment
checkout on 2026-07-06:

**subrepo PYTHONPATH**: the scheduler imports from pipeline/model/execution
subrepos at runtime, but the repo script only had orchestrator+common on
PYTHONPATH. Without subrepo paths, the scheduler fails on import. Fixed by
adding the `.subrepo_runtime/repos/*` sibling paths to `PYTHONPATH`.

The `-run` checkout also had a stale `--mode paper` argument that the CLI
does not accept (mode is controlled via config, not CLI). This caused the
deployed scheduler to fail with `unrecognized arguments: --mode paper`.
The repo version correctly does NOT have `--mode paper`.

## Round 2 (codex review)

STATUS: fixed
WHAT: the previous round of this PR also hard-exported
`RENQUANT_INTRADAY_DECISIONING=1` in the committed wrapper, copying a
live-tree operator hotfix that had uncommented the flag on 2026-07-06.
That silently flipped the documented triple-gate contract's default from
operator-armed to code-armed in the committed repo default — a real
control-plane change, not a neutral drift-sync fix. The PR description also
carried a stale claim about a `run_shadow_serving.sh` change tied to PR
#416; the current diff never touches that file, and #416 was ultimately
fixed differently than described (kept `--feature-snapshot-json` required,
fixed the real gap in the calling script instead of relaxing the CLI).
WHY-DIR: `ops/renquant105/README.md`, `doc/progress/2026-07-03-stage1-session-scheduler.md`,
and `doc/design/renquant-105-as-built.md` all document Stage-1 as
shadow-only and default-OFF behind a triple gate, with activation an
explicit, recorded operator landing step (uncommenting the export line) —
never a committed default. Whatever happened on the live `-run` checkout is
a separate operator/deployment-state decision; it does not, on its own,
authorize changing the repo's committed default without those same docs
being coherently updated to reflect an intentional policy change. No such
doc update exists, so this PR reverts to the documented default-OFF
contract and keeps only the legitimate PYTHONPATH drift fix.
EVIDENCE: `export RENQUANT_INTRADAY_DECISIONING=1` reverted back to the
commented-out form matching the file's own documented triple-gate header.
Added `test_session_scheduler_wrapper_does_not_hard_export_activation_flag`
— a control-plane regression test asserting the wrapper never contains an
active (uncommented) hard-export of the activation flag; confirmed this
test fails against the pre-fix content (verified via the prior commit) and
passes after. Removed the stale `run_shadow_serving.sh`/#416 claim from
this doc; that file is untouched by this PR's diff.
NEXT: if activating Stage-1 intraday decisioning by default is genuinely an
intended, considered policy change, that requires its own explicit PR
updating `ops/renquant105/README.md`, the Stage-1 progress doc, and the
as-built design doc coherently — not a shell-script sync fix.

## Test

Added `test_session_scheduler_wrapper_cli_args_are_valid` — extracts CLI
args from the shell script and validates them against the real argparse
definition. Would have caught the `--mode paper` bug.

Added `test_session_scheduler_wrapper_does_not_hard_export_activation_flag`
— asserts the wrapper's default state never activates live intraday
decisioning; catches any future re-introduction of the control-plane
regression above.

## Root cause

Shell scripts fell behind a live-tree operator hotfix. This PR syncs only
the legitimate PYTHONPATH drift fix; the activation-gate change from that
hotfix is deliberately NOT synced into the committed repo default (see
Round 2 above).
