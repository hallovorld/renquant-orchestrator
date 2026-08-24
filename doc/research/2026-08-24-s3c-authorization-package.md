# S3-c authorization package: everything up to the operator's signature

STATUS: evidence assembled; both authorization DRAFTS prepared. **Nothing is
armed and nothing here arms anything** — both files take effect only when the
operator copies them into `data/rq105/`, which is the designed authorization
act. The runner falls through to shadow without them, and the readiness
checker confirms exactly that today.

## The §9.3a evidence, final state [all VERIFIED 2026-08-24]

| item | value | artifact |
|---|---|---|
| `shadow_sessions_clean` | **13** (07-06..08-24, 31–32 ticks each, zero flagged errors; 37 session manifests on disk) | intraday_decisions_shadow.jsonl |
| `replay_audits_green` | **TRUE** — 0/32 mismatches × 3 sessions, reports carry their config+manifest binding | doc/research/data/2026-08-24-replay-audits/ (PR #1040) |
| `entry_timing_report` | generated from 10 sessions / 30 names / 90 rows: `delay_fixed` mean **+46.8 bps** saved vs baseline (median 0 — tail-carried), 0 degradations; `gap_reversion_trigger` 30 degradations (reject) | `data/2026-08-24-s3c-package/entry_timing_report.{txt,json}` |

Authoritative readiness check (`check_paper_trading_readiness.py`) output is
committed alongside: 3 PASS, 2 FAIL, and both FAILs are precisely the two
operator-act files this package drafts.

## The ladder the code already implements

1. **PAPER (available immediately, K=1 floor):** copy
   `DRAFT_section_9_4_paper.json` → `data/rq105/section_9_4_economic_authorization.json`.
   The runner derives paper mode from `prereg_id = rq105-paper-canary-prereg-v1`
   and fail-closes unless the constructed port is a `PaperBrokerPort`.
2. **LIVE canary (K=5 floor — evidence already exceeds it):** additionally
   copy `DRAFT_stage2_authorization.json` → `data/rq105/stage2_authorization.json`
   (real dates, 1–2 canary names), set `intraday_decisioning.mode="live"` in
   the PINNED config (a reviewed strategy-104 PR), export
   `RENQUANT_INTRADAY_LIVE=1` in the scheduler wrapper (a reviewed ops PR).
   Any missing gate ⇒ shadow, counted, never partial.

## LIVE is gated on a HARD prerequisite, not a recommendation [codex]

The Stage-2 draft is marked **NOT READY TO SIGN** and encodes it in the file
itself: orch#1041 (pinned-config resolution) must be merged AND deployed, and
≥1 shadow session recorded under the PINNED config fingerprint, before
`live_config_fingerprint` can be filled and the draft becomes signable. Both
drafts carry `evidence_bindings` — immutable sha256 identifiers of the exact
replay reports, the timing report, and the config fingerprint the evidence
attaches to — and state that any binding change voids the draft. Neither
prefills the operator's identity.

The timing study's caveat stays attached wherever the number travels: the
+46.8 bps mean is TAIL-CARRIED (median 0.0, p25 −15.7, 3 censored); adequate
for choosing a paper canary, not by itself evidence for unrestricted live
rollout.

## Known caveat attached to the evidence

The 13 shadow sessions ran under the SIBLING checkout's strategy config, not
the pinned one (orch#1041, orch#1016-class). The sessions are attributable —
every manifest fingerprints the config, and the replay audit binds to that
fingerprint fail-closed — but the §9.4 signer should know the evidence
attaches to config `sha256:c6d1abe2…`, and the resolution fix (#1041) will
change the fingerprint on its flip day. This is encoded as a HARD prerequisite inside the Stage-2 draft itself
(see above); paper mode need not wait for it.

## Explicitly not done here

No file under `data/rq105/` was created or modified. No config was changed.
No env flag was set. The drafts live in `doc/` and are inert by construction.
