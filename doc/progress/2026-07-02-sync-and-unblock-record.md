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

REVISION: r2 (Codex review — the record was materially ahead of reality).
WHAT:     tightened §1/§2/§3 of the ops doc into evidence-only reporting: every
          "expected"/"self-heal"/"next daily run" claim is now labeled a PREDICTION,
          separated from what was actually OBSERVED. §2's "zero-importer verification"
          premise was corrected — it was WRONG (renquant-pipeline's main branch imports the
          exact names removed by common#19/#20; verified live and found the cap-bump-alone
          fix would have reproduced the calibrator/scorer fingerprint-mismatch incident
          class, not just an ImportError). Replaced the vague "cap-bump fix PRs dispatched"
          claim with a per-repo chain-status table checked against each repo's actual
          `origin/main` at edit time (base-data#29 + artifacts#12 MERGED;
          backtesting#62/model#41/pipeline#159 still OPEN; renquant-strategy-104 has NO
          pin-fix PR filed, contra the original "chain effectively contained" framing).
          §3's warn-source table now separates observed resolution from expected-but-
          unconfirmed mechanism per row, and corrects two rows the original text hadn't
          caught up to (pairing-logger fix merged as #253; #248 already merged).
EVIDENCE: re-ran `gh pr view`/`gh pr list` against every referenced repo/PR live at edit
          time, and `git show origin/main:pyproject.toml` for base-data and backtesting
          directly, rather than trusting the r1 doc's claims.
NEXT:     re-check `renquant-backtesting#61`'s CI after `#62`/`#41`/`#159` merge; file the
          `<1.0` pin-fix PR for renquant-strategy-104 — confirmed still on
          `renquant-common>=0.7,<0.9` on `origin/main`, no fix in flight.
