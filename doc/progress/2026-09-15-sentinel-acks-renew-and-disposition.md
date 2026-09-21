# 2026-09-15 — ack ledger: renew the two expired rows, disposition three undocumented exits, retire three dead rows; document weekly-apy104's exit codes

STATUS:   delivered, awaiting review — zero reviews at head.
WHAT:     renews the two expired ack rows (rq104-degradation-sentinel,
          shadow-ab-daily) with re-diagnosed clearing conditions, dispositions
          three previously-undocumented-meaning exits (agent-pr-loop,
          monthly-calibrator-refresh, rq104-risk-budget), documents
          weekly-apy104's exit codes 2/3, and retires three dead rows whose
          own retirement conditions were already met.
WHY/DIR:  every `rq104 DEGRADED` page since 2026-08-17 carried the same five
          undispositioned lines; nothing here silences a genuine alarm —
          model freshness, the shadow-scorer sentinel, silent refusal and
          run-surface drift all stay loud with their documented meanings.
EVIDENCE: see §4(b) below.
  artifact:      ops/renquant104/sentinel_acks.json + tests/test_ack_expiry.py + tests/test_ack_ledger_audit.py (208 passed across seven ack/sentinel/inbox files).
  prod or exp:   prod ledger edit (ops/renquant104/sentinel_acks.json) — a production-touching ack-ledger row change, not a data/model artifact.
  existing data: ledger audit on the committed ledger at 2026-09-15 — before: 4 findings (three 30-day-expired rows + an expiry cliff); after: expired 0/5, no findings, rc 0.
  best-known?:   yes — expiries staggered 09-25..09-29, all inside the 14-day backstop; the live-ledger census tests were moved to measured values with dated notes rather than re-asserted against stale exemplar rows.
  scope:         ops/renquant104/sentinel_acks.json, ops/agent_inbox.py (weekly-apy104 exit-code documentation) and the two ack test files only.
NEXT:     merge after review; the five rows expire 09-25..09-29 — if the underlying fixes (RenQuant#645, the renquant-model calibrator fix, the 10-01 risk statement) have not landed by then the page goes loud again by design.

## Conclusion

Every `rq104 DEGRADED` page since 2026-08-17 has carried the same five
undispositioned lines. Each is now either re-diagnosed today from its own
log and acked with a literal clearing condition, retired because its own
condition was met weeks ago, or (weekly-apy104) documented against the
monitor's exit-code lines so the page names the contract instead of
"NO DOCUMENTED MEANING". Nothing here silences a genuine alarm: model
freshness (exit 3), the shadow-scorer sentinel (8), silent refusal (1) and
run-surface drift (1) stay loud with their documented meanings.

| job (exit) | page text before | disposition today | clears when |
|---|---|---|---|
| rq104-degradation-sentinel (1) | ACK EXPIRED 29d | renewed; still "covers ONLY exit 1" | any firing with zero alarms (manual, self-referential) |
| shadow-ab-daily (3) | ACK EXPIRED 31d | RE-DIAGNOSED: PRECHECK refuses because all 8 run checkouts differ from `~/renquant-shadow-ab/run_manifest.json` (mtime 2026-07-17) `[VERIFIED: logs/2026-09-15_session.log; launchctl runs=19 last exit 3]` | manifest refreshed under §5 or job retired — operator decision |
| agent-pr-loop (1) | NO DOCUMENTED MEANING | codex usage limit until Oct 3 (verbatim stderr); loop mis-reported the cause for 12 days — fixed in RenQuant#645 `[VERIFIED: status.json 2026-09-15T22:05:46Z]` | quota reset + exit 0, or #645 deployed |
| monthly-calibrator-refresh (1) | NO DOCUMENTED MEANING | 09-01 BINDING MISMATCH quarantine; root cause reproduced (fit script stamps the v1 hash, runtime identifies legacy scorers by the 0.8.1 hash); 10-01 will repeat until the renquant-model fix is pinned `[VERIFIED: verify_calibrator_scorer_binding.py pass/fail/pass on live / simulated-fit / simulated-fixed]` | next monthly run logs `Binding gate: OK` |
| rq104-risk-budget (1) | CRITICAL (documented) | STALE: the 09-01 statement's book_beta 231.8%; recomputed 09-15 read-only into a scratch dir: WARN, beta 86.1% | the 10-01 statement exits 0 or 2 |
| weekly-apy104 (2) | NO DOCUMENTED MEANING | `DESIGNED_EXIT_CODES["weekly-apy104"]`: 2 = APY below the rolling-30d floor, 3 = drawdown streak — the monitor's own verdicts, `actionable=True` (stays loud, now explained) | n/a — a documented meaning, not an ack |

Retired (condition met, expired 30+ days, job absent from today's nonzero
list): `conditional-retrain104` (EXPIRED_CONDITION_MET), `monthly-meta-
label-retrain` (MANUAL_EXPIRED), `rq105-batch-scores-export`
(EXPIRED_CLAUSE_MET) — the same rule #622 AC4 applied to daily104.

## Evidence (§4(b))

- Ledger audit on the committed ledger at 2026-09-15: `expired 0/5`,
  `no findings`, rc 0 (was 4 findings: three 30-day-expired rows + an
  expiry cliff on 08-16). `[VERIFIED: ops/renquant104/ack_ledger_audit.py --today 2026-09-15]`
- Expiries staggered 09-25..09-29, all inside the 14-day backstop
  (`acked_at + 14 = 09-29`); the earliest-date rule was checked so no
  clause carries an ISO date that would expire a row early.
- Tests: 208 passed across the seven ack/sentinel/inbox files. The
  live-ledger census tests (`test_ack_ledger_audit.py`,
  `test_ack_expiry.py`) are "measured, not asserted" pins and were moved
  to the measured values with dated notes; the exemplar rows they quote
  (`rq105-batch-scores-export`, the `orch#747` clause) no longer exist and
  were re-pointed at rows that demonstrate the same property.
- `test_cli_reports_a_harness_failure_distinctly` had passed only because
  the committed ledger happened to carry findings at 2026-07-25; the first
  clean ledger exposed that (EXIT_OK is not in its accepted set). It now
  points the CLI at a history-less ledger, a harness failure by
  construction on any host.

## What this does NOT do

- Does not refresh or retire `shadow-ab-daily` (a run-surface change —
  operator decision under §5), does not touch codex, and does not fix the
  calibrator fit script (renquant-model PR, separate).
- The five rows expire 09-25..09-29 by design: if the underlying fixes have
  not landed by then the page goes loud again, which is the ledger's
  purpose.
