# 2026-07-02 landing record + tiered-delegation governance — ops PR

STATUS:   ops record (docs only — records actions ALREADY executed under the operator's
          explicit temporary grant, and the standing governance decision).
REVISION: r1.
WHAT:     `doc/ops/2026-07-02-landing-record.md` — (1) the tiered-delegation governance
          decision (research = notify-not-approve; machine-landing = ask-first per batch;
          hard gates unchanged); (2) the executed batch: 7 launchd jobs live (N1 ×3, N2 ×2,
          4th-collector ×2), quote-logger smoked (97 rows) + today's session manually
          started (564+ ticks), FIRST real PIT snapshot landed (4 endpoints,
          2026-07-02 — C1's accrual clock starts); (3) the batch-scores exporter
          fail-closed finding (missing artifact_hashes in the 07-01 run bundle — suspected
          pins-behind; re-check post-sync); (4) live-tree sync deferred to ≥15:30 PT by the
          #242 runbook's own market-hours rule; (5) cross-references putting every decision
          in a PR (ATP deferral = #245; λ correction = #240-as-revised).
WHY/DIR:  operator rule (2026-07-02): 所有决策要进pr进doc — two items lived only in chat
          (the governance decision and the landing record itself); this PR closes that gap.
EVIDENCE: launchctl list output, tick-file row counts, the snapshot directory listing, the
          exporter's refusal message — all quoted in the record.
NEXT:     ≥15:30 PT: execute the live-tree sync under the same grant; verify the exporter
          self-heals; then all seven collectors run unattended from 2026-07-03.
