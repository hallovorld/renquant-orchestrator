# Manifest the two GOAL-5 sentinel launchd jobs

STATUS: delivered
WHAT: adds com.renquant.rq104-degradation-sentinel and
com.renquant.run-surface-drift to ops/launchd_manifest.json (regenerated
via the drift script's own --emit-manifest against the installed
reviewed-good plists; 35 → 37 jobs).
WHY/DIR: GOAL-5 AC2 — the live drill installed the two sentinels and the
drift scan alarmed on exactly them within minutes; this reviewed change is
the sanctioned remedy the alarm text prescribes. Post-merge re-scan must
be clean.
EVIDENCE: drill alarm output on the live machine; drift tests 13/13.
NEXT: none.
