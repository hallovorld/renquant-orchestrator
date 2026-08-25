# The twin-surface parity detector finally RUNS — watchlist drift joins it (orch#1020)

STATUS: closes orch#1020's reporting half. The reconciliation half (which
list is right for CRWV/RKLB/SPCX) stays open on the issue — a reviewed
config decision, not a detector's call.

## The gap, restated

`ops/strategy_config_primary_parity.py` existed, KNEW the R5 twin condition,
and was excluded from the scheduled audit ("requires --config <path> — baking
machine paths into the reviewed tuple is the tests-that-measure-the-
operator's-disk failure"). Meanwhile the two watchlists drifted 145 vs 142
(CRWV/RKLB/SPCX) and nothing reported it — the detector didn't LOOK at
watchlists, and nothing RAN the detector. Deployed-but-dark, twice over.

## Changes

1. **Watchlist parity** (`read_surface`/`compare`): the declared universe is
   part of a surface's identity. Malformed members fail closed (the #694
   lesson); ABSENT-vs-declared is a disagreement; drift is named ticker by
   ticker.
2. **$RQ_ROOT defaults**: with `--config` omitted, the subjects are the two
   surfaces the daily run actually stitches (pinned subrepo config + umbrella
   tournament config), the same env convention every scheduled probe uses —
   which dissolves the machine-path objection.
3. **The first stdout line now encodes the disagreement STRUCTURE**
   (`PARITY: 4 disagreement(s) [… watchlist(CRWV,RKLB,SPCX) …]`) because
   `ops_audit.run_member` fingerprints `out[0]`: an ack binds to THIS drift
   and any new drifted ticker re-fingerprints as NEW. Fingerprinting the old
   first line (the surface listing) would have let one ack silently cover
   every future divergence — the wrong object, at the disposition layer.
4. **Audit membership**: `("strategy-config-parity", …, (1,))` joins MEMBERS;
   `UNSCHEDULABLE_YET` shrinks to one; both meta-tests updated (they pin the
   contract map and the exclusion list by design).
5. **Ack entry** for the STANDING findings (fingerprint `a31becc0dc3fb5bb`),
   so the new member alarms on NEW drift instead of being red forever and
   learned-ignored: the R5 identity divergence is registry-recorded; the
   3-ticker watchlist drift is what #1020 tracks. `clears_when`: any change
   in the disagreement set re-fingerprints; expires 2026-09-24 regardless.
   The audit still prints the ACKED line as INFO — nothing is silent.

## Evidence (§4b)

- Against the REAL surfaces [VERIFIED 2026-08-24, read-only]: exit 1;
  summary `PARITY: 4 disagreement(s) [ranking.panel_scoring.kind;
  ranking.panel_scoring.artifact_path; watchlist(CRWV,RKLB,SPCX);
  shadow_models]` — the exact #1020 drift plus the known R5 condition.
- After the ack: `ops_audit` reports the member `exit=1 ACKED` as INFO
  [VERIFIED — worktree run].
- Suites: parity + ops_audit + disposition = **95 passed** (py3.10);
  new tests include the ack-safety property (two different drift sets must
  produce different fingerprint subjects) and the $RQ_ROOT default mode.
