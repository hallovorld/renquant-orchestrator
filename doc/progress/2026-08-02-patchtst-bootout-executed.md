# 2026-08-02 — Grant B executed: weekly-retrain-patchtst booted out; pending set emptied

STATUS: complete (machine action executed and verified; the designed red
cleared in the same change)

WHAT: Under the operator's verbal grant (2026-08-02 ~22:47Z,
「授权你做你申请的那几个任务」, which named Grant B), orch#755's checklist
item (c) executed: `launchctl bootout gui/502/com.renquant.weekly-retrain-patchtst`
+ plist removed from ~/Library/LaunchAgents; verified no longer loaded.
Items (a) manifest removal, (b) s104 pin past #75, and (d) run-checkout sync
had all landed earlier. This PR deletes the
`com.renquant.weekly-retrain-patchtst` entry from the drift test's
PENDING_UNINSTALL bounded set — the exact-equality test went red on the
machine the moment the plist left disk (measured: 1 failed → 18 passed after
the shrink), which is precisely the forcing function #755 designed.

WHY/DIR: GOAL-5 run-surface hygiene; the RETIRE decision is orch#741's
(artifact 625d past the 28d SLA, 22/22 chain FAILEDs, PERSISTENCE-DRIVEN
verdict under a passing positive control). Saturday 05:30 is now free; the
momentum weekly job (05:00) keeps its uncoupled slot.

EVIDENCE:
- artifact: scratchpad grants-20260802.log (timestamped bootout trail:
  pre loaded → bootout OK → plist removed → verified not loaded); this PR's
  diff; drift tests 18 passed against the real machine
- prod or exp: run-surface (launchd) under the operator grant; reviewed
  surface updated in the same batch per the containment protocol
- existing data: same grant batch also executed: sibling sync ×4 (all four
  dev checkouts now AT their lock pins; pipeline's untracked stray file left
  in place), #742's 791MB umbrella residue deleted + issue closed, and the
  #94 stage-2 sign-off posted (bt#100 un-drafted into codex review)
- best-known?: yes — every machine state read back post-action
- scope: one bounded-set entry + this record; the manifest itself was
  already correct (#755)

NEXT: the silent-refusal sentinel's patchtst log-reading lane retirement —
the one remaining #755-named follow-up — rides its own small PR (the lane is
manifest-independent and harmless meanwhile).
