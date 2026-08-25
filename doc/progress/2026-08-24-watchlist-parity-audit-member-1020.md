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

## r2 (codex round 1): the preview was lossy and the ack lied about its expiry

Both accepted. (1) The bounded ticker preview stays for humans, but the
fingerprinted line now ALSO carries a digest of the complete canonical
state — all disagreement strings verbatim (identity VALUES included), every
read surface's full watchlist (duplicates preserved, ABSENT explicit) —
**letter-encoded**, because the disposition fingerprint substitutes digits
with `<N>` and a raw hex digest would collide after substitution, silently
re-opening the exact hole the digest closes. Four escape-regressions added:
11th-ticker change, ABSENT↔list flip, duplicate-only change, identity
VALUE change — each must change the fingerprinted line — plus a digit-free
property test. (2) The ack's `expires_at` is now **2026-09-07** — equal to
`acked_at + ACK_MAX_AGE_DAYS`, the effective bound `ack_expiry` computes —
with the equality stated in `reason` instead of a later date that the age
cap would silently override. 43 parity tests pass; audit shows the member
`exit=1 ACKED` (INFO) under the recomputed fingerprint.

## r3 (codex round 2): the canonical map lost one LIVE surface

Accepted: both production subjects are named `strategy_config.json`, and the
canonical watchlist map keyed by basename silently overwrote one — reopening
duplicate/absence/full-list collisions on the overwritten side. Keying is now
**index + the last three path parts** (subject order preserved; portable
across RQ_ROOTs; distinguishes `…/renquant-strategy-104/configs/…` from
`…/renquant_104/…`). New regression with two same-basename surfaces asserts
a past-the-preview change and a duplicate-only change on EITHER side alter
the fingerprinted line. The CI red was `test_ops_audit_acks_ledger`'s pin
that exactly one detector is ever acked — updated to enumerate two, with the
rationale in place (widening that set stays a reviewed edit of the test).
Ack re-keyed to the final fingerprint `1af4f5ed284b8ea0`. 104 passed across
the parity/audit/ledger suites.
