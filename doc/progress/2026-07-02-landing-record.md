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

ROUND 2 (Codex review — evidence identifiers, not prose): the r1 record's "7/7 live" /
"564+ and growing" / exporter-failure claims were prose summaries with no captured
identifiers a reviewer could independently check. Fixed: §2a adds per-job launchd
evidence (exact label, plist sha256, install-timestamp proxy via mtime, and a live
`launchctl list` snapshot captured fresh this round — not re-derived from the original
operator's report); §2b replaces "564+ and growing" with a fixed-timestamp row count
(1,731 as of 2026-07-02T15:26Z), feed identity (`alpaca-iex`), and a whole-file content
hash; §2c reproduces the exporter's exact error byte-for-byte, names the run_id and the
missing fingerprint field, and assigns a concrete follow-up owner (the live-tree sync
item already enumerated in the same grant). Also fixed: the live-tree-sync authorization
gap — row 9 of the batch table already explicitly included the sync in this SAME
enumerated grant, so the ambiguity was resolvable by cross-reference rather than
requiring a fresh ask; the record now states that authorization expires end-of-day
2026-07-02, not indefinitely. Also fixed: §3 no longer cites #245's disputed IEX-bias/
daily-bar/re-trigger claims as settled — #245 is still CHANGES_REQUESTED as of this
round, and the record now says so explicitly rather than treating it as closed.
