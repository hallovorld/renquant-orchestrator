# Landing record — 2026-07-02 collector/PIT activation batch (operator-granted)

STATUS: ops record (durable log of MACHINE actions executed under the operator's temporary
grant of 2026-07-02, plus the governance decision that now applies to all future landings).
DATE: 2026-07-02

## 1. The governance decision (operator, 2026-07-02 — recorded per "所有决策要进pr进doc")

Delegation is TIERED from this date:

- **Research / analysis / PRs / delegated decisions** (the RS-x class, #230 §1 protocol):
  autonomous, notify-not-approve. Unchanged.
- **Machine-LANDING actions** (launchd installs, starting jobs, live-tree git sync,
  subscriptions/spend execution, anything that writes outside dedicated research paths):
  **ASK FIRST, every time.** One grant covers exactly one enumerated batch. The operator
  endorsed the ask-first habit explicitly ("这个习惯很好，先问了一下。以后要做还是要问的").
- Hard safety gates unchanged (no live-tree git without a per-instance grant; never during
  market hours; branch protection; canonical prod paths).

## 2. What the 2026-07-02 grant covered, and what was executed

| # | Action | Executed | Result |
|---|---|---|---|
| 1 | Pinned run checkouts (`renquant-orchestrator-run`, `renquant-base-data-run`) | ✅ 08:0x PT | ff-only clones of main |
| 2 | N1 collectors: 3 plists (quote-logger 06:25 / postclose 13:15 / liveness 14:00) | ✅ | see §2a for per-job evidence identifiers |
| 3 | N2 PIT: 2 plists (estimate-snapshot 14:30 / liveness 15:00) | ✅ | see §2a |
| 4 | Quote-logger smoke (`--once --force`) | ✅ | 97 tick rows written; Alpaca creds + output path verified |
| 5 | Manual session start for TODAY (plists installed after 06:25) | ✅ | session loop running; see §2b for reproducible row-count/hash evidence |
| 6 | **First real PIT snapshot** | ✅ | `data/estimate_snapshots/2026-07-02/`: analyst_estimates + grades_consensus + price_target_consensus + price_target_summary (parquet + manifest each). **The as-of clock started 2026-07-02**; C1's ≥6-month window counts from here |
| 7 | #236 follow-up: 4th-collector plists (batch-scores-export 06:15 / shadow-serving 13:45) | ✅ post-merge | see §2a; total 7 jobs |
| 8 | Manual batch-scores export for today | ⚠️ **fail-closed (by design)** | see §2c for exact run_id/error/owner |
| 9 | Live-tree sync (#242 runbook) | **DEFERRED to ≥15:30 PT same day** | the runbook's own market-hours rule blocked an 08:11 PT execution — recorded as the runbook working. **This item was already part of this same enumerated batch (row 9 above) — the operator grant covers its execution later the SAME calendar day (2026-07-02) once market hours end; it does NOT extend to any subsequent day. If not executed by end-of-day 2026-07-02, a fresh ask is required under the tiered-delegation rule in §1.** |
| 10 | backtesting #59 review nudge | ✅ | comment posted |

## 2a. Per-job launchd evidence (captured 2026-07-02T15:26:04Z, this fix pass)

All 7 jobs verified present, loaded (`launchctl list` returns a status dict, not "not found"), and `LastExitStatus=0` at capture time. `PID` shows `-` for all (expected — these are `OnDemand`/calendar-interval jobs, not continuously running processes; `-` means "not currently executing," not "not loaded").

| Label | Plist sha256 (first 12) | Plist mtime (install proxy) | `launchctl list` snapshot |
|---|---|---|---|
| `com.renquant.rq105-quote-logger` | `ff034a55fc15` | 2026-07-02T08:08:46 | loaded, `LastExitStatus=0`, `OnDemand=true`, Program=`/bin/zsh` |
| `com.renquant.rq105-postclose` | `7d36a3c69734` | 2026-07-02T08:08:46 | loaded, `LastExitStatus=0`, `OnDemand=true`, Program=`/bin/zsh` |
| `com.renquant.rq105-liveness` | `d912a43b4f80` | 2026-07-02T08:08:46 | loaded, `LastExitStatus=0`, `OnDemand=true`, Program=`.venv/bin/python` |
| `com.renquant.pit-estimate-snapshot` | `c6e8b506ac92` | 2026-07-02T08:08:46 | loaded, `LastExitStatus=0`, `OnDemand=true`, Program=`/bin/bash` |
| `com.renquant.pit-liveness` | `ea221bc22903` | 2026-07-02T08:08:46 | loaded, `LastExitStatus=0`, `OnDemand=true`, Program=`.venv/bin/python` |
| `com.renquant.rq105-batch-scores-export` | `4b32342f1797` | 2026-07-02T08:15:29 | loaded, `LastExitStatus=0`, `OnDemand=true`, Program=`.venv/bin/python` |
| `com.renquant.rq105-shadow-serving` | `1731522cd062` | 2026-07-02T08:15:29 | loaded, `LastExitStatus=0`, `OnDemand=true`, Program=`/bin/bash` |

Captured directly via `launchctl list com.renquant.<label>` + `shasum -a 256` + `stat -f %Sm` on each plist under `~/Library/LaunchAgents/`, this fix pass — not re-derived from the original operator's report. `LastExitStatus=0` reflects the last **completed** invocation (harmless for jobs that haven't fired yet today at capture time), not a guarantee of today's full-session outcome; §2c documents the one job (`rq105-batch-scores-export`) whose actual scheduled invocation is known to fail closed.

## 2b. Quote-logging evidence (captured 2026-07-02T15:26Z, this fix pass)

- **Output path:** `logs/renquant105_pilot/intraday_ticks.jsonl` (relative to `RQ_ROOT=/Users/renhao/git/github/RenQuant`), written by `renquant_orchestrator.intraday_quote_logger`.
- **Row count as of 2026-07-02T15:26Z:** 1,731 lines (supersedes the r1 "564+ and growing" figure, which was a mid-session snapshot, not a stable count).
- **Feed identity:** `"source": "alpaca-iex"` (stamped per-row; confirms the IEX-feed dependency documented in #245, not SIP).
- **Content hash (whole file, at capture time):** `656dfc95d29962273152bec5a3613e6e0875730298d3ce2eb223ae6d20a9c613`
- This is a growing, append-only file — the hash/count above are a point-in-time snapshot, not a final/frozen value; re-verify independently if used as evidence in a later document.

## 2c. Failed batch-scores exporter — full record

- **Command:** `PYTHONPATH=<renquant-orchestrator-run>/src <RenQuant>/.venv/bin/python <renquant-orchestrator-run>/ops/renquant105/export_batch_scores.py`
- **Exact error (reproduced this fix pass, 2026-07-02T15:26Z, byte-for-byte from stdout):**
  ```
  run 2026-07-01-live-01c54b39 missing required fingerprint field(s) in its run_bundle_json: artifact_hashes — refusing to export an unfingerprinted vector
  ```
- **Run ID:** `2026-07-01-live-01c54b39`
- **Fingerprint-gap field:** `artifact_hashes` (absent from this run's `run_bundle_json`)
- **Suspected cause:** the live checkout runs pre-fingerprint-hardening code (pins-behind state relative to `#236`'s merged fingerprint contract) — plausible given the run predates the same-day pin-align, but NOT independently confirmed in this fix pass (would require inspecting the live checkout's exact commit/pin state, out of scope here).
- **Follow-up owner:** the live-tree sync (§2, row 9) is the identified remediation step — once the live checkout is synced past `#236`'s merge, retry the export and confirm `artifact_hashes` is present on the next completed run. If the export still fails post-sync, escalate as a new issue (owner: whoever executes/verifies the live-tree sync per §2, row 9's same-day authorization).

## 3. Decisions cross-referenced (all in PRs per the operator's rule)

- **ATP deferral + full reasons**: PR #245 (RS-3 r2 addendum) — cost arithmetic (~11%/yr of
  book), daily-bar opening prints suffice, re-trigger = M2 go-live OR book ≥ $50k.
  **`#245` is still under CHANGES_REQUESTED review as of this record's last update — its
  "IEX bias is precision-not-safety" framing, its daily-bar provenance claim, and its
  $50k re-trigger threshold are all currently disputed by Codex's review and NOT yet
  settled.** Do not treat that framing as accepted fact until `#245` itself reaches
  APPROVED; this record only cites it as the place the underlying decision is being made,
  not as a closed conclusion.
- **FMP Starter confirmed active** (key-metrics + 10-year estimates verified): PR #245
  (same caveat — #245 is not yet approved).
- **λ-sweep correction** (round-1 harness never enabled the mechanism; A-1 confirmed a
  production no-op mechanically): merged #240 as revised in review.
- The FMP 5y C2-substrate harvest refresh: NOT executed today (no rushed rate-limit runs);
  a proper base-data fetcher PR is the next-tick task, C2's window is Q4.
