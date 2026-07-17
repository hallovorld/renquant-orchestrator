# Correction: retrain-panel104 ack diagnosis

STATUS: delivered
WHAT: corrects the sentinel_acks entry for com.renquant.retrain-panel104 —
the earlier "legacy tournament frozen since April" diagnosis was WRONG.
retrain_panel.sh is a compatibility wrapper delegating to
weekly_wf_promote (its header documents the legacy path's retirement);
the Sunday exit-1 mirrors the chronic WF-gate rejection, the same
already-acked root as weekly-wf-promote.
WHY/DIR: a reviewed ack ledger must be accurate; corrected the same
evening on reading the wrapper source. Net picture improves: the entire
loud launchd surface reduces to ONE chronic root (models failing the
quality gate — a model-research problem, G4's territory), plus one stale
07-01-era monthly row.
EVIDENCE: scripts/retrain_panel.sh header; sentinel tests 22/22.
NEXT: task #74 rescoped — no tournament repair needed for this job.
