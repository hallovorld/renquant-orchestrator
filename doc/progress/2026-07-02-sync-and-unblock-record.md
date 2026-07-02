# Sync + unblock-clause record — ops PR

STATUS:   ops record (docs only; records actions already executed under grants).
REVISION: r1.
WHAT:     `doc/ops/2026-07-02-sync-and-unblock-record.md` — (1) the executed #242 live-tree
          sync: classification (one class-1 code file, zero class-2, no HALT), ff-only +
          stash-apply with per-class conflict resolution, canary GREEN (runner.py:1785
          self._config), stash retained, doctor RED = expected pin-align remainder
          (mechanism-owned), one recorded timing deviation (mutations began 15:27 vs the
          15:30 runbook line); (2) FIRST use of the operator's unblock clause: common 0.9.0
          broke backtesting/base-data CI repo-wide (caps <0.9), blocking #61 → D1 — cap-bump
          fix PRs dispatched with zero-importer verification; (3) the same-day warn-source
          resolution map (shadow-serving SKIP self-heal chain, paired_is diagnosis agent,
          #248 deployed to run checkouts).
WHY/DIR:  the landing/unblock discipline requires record + notify for every grant use; two
          grant uses happened today (the authorized sync batch item #9; the unblock clause).
EVIDENCE: snapshot archives in scratchpad sync-snapshots/ (TS 20260702-1523); canary grep
          output; conflict list (2×DU live_state, DU dashboard, UU lock); make doctor RED
          fields; CI break evidence from the #59 fix agent's report.
NEXT:     tomorrow's daily run completes pin-align (doctor → green) and stamps
          artifact_hashes (exporter self-heal); pairing diagnosis + CI cap PRs land via
          normal review.
