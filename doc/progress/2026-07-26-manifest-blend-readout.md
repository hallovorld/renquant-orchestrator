# Manifest entry: com.renquant.rq104-blend-readout (activation batch)

**Date:** 2026-07-26 · **Refs:** orch#581 (job merged), strategy#65/#66
(shadow slot), umbrella#530 (pins + artifact), pipeline#213 (readout rules)

Adds the launchd manifest entry for the daily 15:21 blend-readout job in the
SAME batch as its `launchctl load` (manifest==live atomicity — the drift
scan must see both or neither). ProgramArguments digest computed with the
drift-scan's own `program_args_digest` recipe against the run-checkout path.

Executed under the 2026-07-26 operator activation delegation (trail:
strategy#65 progress doc). Revert: `launchctl unload` + remove the plist +
revert this commit.
