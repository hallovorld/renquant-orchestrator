# Progress — META no-buy forensics (2026-07-11)

**What:** Operator-escalated forensic (production-incident treatment): why did the live
system not buy META in any session 2026-07-06 → 2026-07-10. Read-only throughout (immutable
DB open, log/state reads, read-only Alpaca GETs); no state mutated, no orders, no git in the
live umbrella tree or primary checkouts (work done in an isolated orchestrator worktree).

**Verdict (bottom line):** Model view, not engineering, and NOT the wash-sale recurrence.
On every session the funnel ran (07-06/07/10) META was double-killed by two independent
correctly-scaled gates: rank_score below the VetoWeakBuys `mean+1σ` floor (0.5413 vs 0.565;
0.5375 vs 0.554; 0.5053 vs 0.544) AND 60d mu below the ConvictionGate 0.03 floor
(0.0192/0.0179/0.0064). The funnel was alive — it submitted AVGO+MCHP (07-06), ZM (07-07),
FTNT/APH/ZM/NFLX (07-10), all outranking META. Wash-sale cleared three ways: no META key in
`last_sell_dates`; broker-truth last sell fill 2026-06-02 (30d window expired 07-02);
`blocked_wash=0` all week. Permanent fix (umbrella #428) merged 2026-07-02 AND deployed
(`adapters/runner_ext_sell.py`, wired at `adapters/runner.py:995-1011`).

**Separate finding:** 07-08/09 buy scan ran with 0 tickers — 133/145 per-ticker admission
models failed the `live_train_end` 60d freshness gate (metadata vintage regressed to
2026-04-23 in the 07-07→07-08 window; recovered by the 07-09 retrain → 125/145 on 07-10).
Universe-wide availability incident, not META-specific (META's bracketing-day scores were
nowhere near admission); both days were mis-reported as normal `no trade (no_candidates)`.

**Context:** META rallied +11.5% on the week ($600.42→$669.25) and street consensus is Buy
(~$834 target). Model-vs-street divergence flagged for the operator; model is primary.

**Deliverable:** `doc/research/2026-07-11-meta-no-buy-forensics.md` (verdict, per-session
funnel table, wash-sale evidence block, outage analysis, recommendations with ownership).

**Follow-ups recommended (not implemented here):**
1. Page on buy-scan universe collapse (`0 candidates from 0 tickers`) as an outage, not a
   no-trade decision (umbrella runner / orchestrator monitor).
2. Root-cause the 07-08 per-ticker policy-metadata `live_train_end` regression
   (2026-06-23 → 2026-04-23), window coinciding with the 07-08 live-tree mutation incident.
3. No META-specific gate change; validate the fade-the-spike view via decision-ledger
   forward returns before touching floors.
