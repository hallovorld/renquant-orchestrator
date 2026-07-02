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
| 2 | N1 collectors: 3 plists (quote-logger 06:25 / postclose 13:15 / liveness 14:00) | ✅ | `launchctl list` 3/3 loaded |
| 3 | N2 PIT: 2 plists (estimate-snapshot 14:30 / liveness 15:00) | ✅ | 2/2 loaded |
| 4 | Quote-logger smoke (`--once --force`) | ✅ | 97 tick rows written; Alpaca creds + output path verified |
| 5 | Manual session start for TODAY (plists installed after 06:25) | ✅ | session loop running; ticks 97 → 564+ and growing |
| 6 | **First real PIT snapshot** | ✅ | `data/estimate_snapshots/2026-07-02/`: analyst_estimates + grades_consensus + price_target_consensus + price_target_summary (parquet + manifest each). **The as-of clock started 2026-07-02**; C1's ≥6-month window counts from here |
| 7 | #236 follow-up: 4th-collector plists (batch-scores-export 06:15 / shadow-serving 13:45) | ✅ post-merge | 2/2 loaded; total 7 jobs |
| 8 | Manual batch-scores export for today | ⚠️ **fail-closed (by design)** | the exporter (as hardened in #236 review) requires `artifact_hashes` in the run bundle; run `2026-07-01-live-01c54b39`'s bundle lacks it → refused. Shadow serving will SKIP today with ntfy. Suspected cause: the live checkout runs pre-fingerprint code (the pins-behind state); re-check after the live-tree sync; open a follow-up if it persists |
| 9 | Live-tree sync (#242 runbook) | **DEFERRED to ≥15:30 PT same day** | the runbook's own market-hours rule blocked an 08:11 PT execution — recorded as the runbook working |
| 10 | backtesting #59 review nudge | ✅ | comment posted |

## 3. Decisions cross-referenced (all in PRs per the operator's rule)

- **ATP deferral + full reasons**: PR #245 (RS-3 r2 addendum) — cost arithmetic (~11%/yr of
  book), daily-bar opening prints suffice, observe-only ⇒ IEX bias precision-not-safety
  (accepted + documented per #223 A5.3 path 2), re-trigger = M2 go-live OR book ≥ $50k.
- **FMP Starter confirmed active** (key-metrics + 10-year estimates verified): PR #245.
- **λ-sweep correction** (round-1 harness never enabled the mechanism; A-1 confirmed a
  production no-op mechanically): merged #240 as revised in review.
- The FMP 5y C2-substrate harvest refresh: NOT executed today (no rushed rate-limit runs);
  a proper base-data fetcher PR is the next-tick task, C2's window is Q4.
