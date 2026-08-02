# GOAL-1 #622 AC4: the ack ledger shrinks — 12 → 10, and the expired cohort goes to zero honestly

STATUS: complete. WHAT: removed the two acks whose jobs now exit 0
(`daily104`, `weekly-retrain-patchtst` — their own clears_when conditions were
met, late), and re-stamped `shadow-ab-daily` with a MEASURED diagnosis replacing
its expired 07-17 row. Test pins updated to the new measured ledger; the expiry
positive-control now asserts removed-not-renewed and re-diagnosed-not-renewed.
WHY-DIR: #622's AC4 required the ledger to shrink as a RESULT of the issue, not
grow. The 2026-07-20 cohort was about to cross the LONG-EXPIRED threshold on
2026-08-04 as three findings; two of those jobs had quietly healed and one had a
different, diagnosable failure.
EVIDENCE: launchctl last exits — daily104 **0**, weekly-retrain-patchtst **0**,
shadow-ab-daily **3** `[本次实测 2026-08-01 via launchctl list]`. shadow-ab exit 3
root-caused from its own session log (written daily 14:35 through 2026-08-01):
`PRECHECK: run manifest verification failed` — run-checkout pin drift, 5 repos
HEAD != manifest commit + renquant-model tree DIRTY ('M README.md'). The
b48d3ed1 guard is refusing BY DESIGN; remedy = the operator-gated pin sync
(orch#747 item 5), so the new ack binds to that ref. The stale
"No such file or directory" lines in launchd.err.log predate 07-18 (script
restored) and are NOT the current failure. Ledger 12 → 10 rows; audit fires
0 findings on 08-01 AND 08-04 (was 3), 6 on 08-15. Tests 148/149 passed at
commit time (the one remaining pin depends on this commit's own date via git
history; verified post-commit below). `[VERIFIED — pytest + audit run on the
edited ledger, 2026-08-01]`
NEXT: the shadow-ab ack clears itself at the #747 item-5 pin sync; nothing else
watches it manually. AC6 gate-design rule: N/A — no capital-admission gate
touched; this edits an ops alarm-disposition ledger and its tests.
