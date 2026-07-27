# Wire the shadow-scorer sentinel (GOAL-1 AC3 was deployed-but-dark)

## STATUS
delivered

## WHAT
launchd plist (14:45 daily, after the daily-full writes health records) +
manifest entry (same batch, drift-scan atomicity) for
`ops/renquant104/rq104_shadow_scorer_sentinel.py` — the component that
turns shadow health records into ntfy alerts (degraded/not-actionable
states, silent non-loads). Load executed in the same batch under the
operator's 2026-07-27 "fix and rerun until clean" directive.

## WHY/DIR
Today's first shadow session proved the gap: the new shadow's
`missing_train_cutoff` degraded state was written to the health record but
NOTHING converted it to a notification — the sentinel existed (tests and
all) but was wired to no scheduler. "Deployed-but-dark is not done."

## EVIDENCE
Manifest digest computed with the drift-scan's own recipe; sentinel dry-run
against today's records alarms as expected (missing_train_cutoff +
patchtst staleness) — first-day noise that the in-flight train-cutoff fix
retires.

## NEXT
Load + drift-scan verify; artifact re-stamp deploy clears the
missing_train_cutoff alarm; PatchTST staleness remains the known chronic
WARN until its rescore lane lands.
