# Progress — META no-buy forensics (2026-07-11)

**What:** Operator-escalated forensic (production-incident treatment): why did the live
system not buy META in any session 2026-07-06 → 2026-07-10. Read-only throughout (immutable
DB open, log/state reads, read-only Alpaca GETs); no state mutated, no orders, no git in the
live umbrella tree or primary checkouts (work done in an isolated orchestrator worktree).

**r2 (Codex review, 2026-07-11):** three corrections — (1) the verdict is a MIXED result, not
a clean "model view": META was genuinely rejected on the 3 sessions it was scored (07-06/07/10),
but on the 2 outage sessions (07-08/09) it was never scored at all, so its counterfactual there
is UNKNOWN, not inferable from the bracketing days; (2) repository ownership corrected — the
universe-collapse alert belongs to `renquant-orchestrator`'s own `model_freshness_monitor.py`,
and the `live_train_end` producer/consumer logic belongs to `renquant-pipeline`
(`job_universe.py`, `pp_training.py`), not the deprecated umbrella; (3) the outage is described
as SYMPTOM RECOVERY, not "resolved" — the producer mutation that caused the metadata regression
is not causally identified. Evidence sealed to
[`renquant-artifacts#16`](https://github.com/hallovorld/renquant-artifacts/pull/16) (5
canonical run rows, META's candidate_scores on the 3 scored sessions, explicit confirmed
absence on the 2 outage sessions, raw log excerpts, current metadata snapshot) — mutable live
DB/log/state paths were r1's citation, now replaced with this sealed, content-addressed record.

**Verdict (bottom line, r2):** MIXED. On 07-06/07/10 META was double-killed by two independent
correctly-scaled gates: rank_score below the VetoWeakBuys `mean+1σ` floor (0.5413 vs 0.565;
0.5375 vs 0.554; 0.5053 vs 0.544) AND 60d mu below the ConvictionGate 0.03 floor
(0.0192/0.0179/0.0064). The funnel was alive — it submitted AVGO+MCHP (07-06), ZM (07-07),
FTNT/APH/ZM/NFLX (07-10), all outranking META. On 07-08/09 the entire buy universe collapsed
(0 candidates from 0 tickers) and META was never evaluated — its counterfactual on those two
days is unknown. Wash-sale cleared three ways on all 5 sessions: no META key in
`last_sell_dates`; broker-truth last sell fill 2026-06-02 (30d window expired 07-02);
`blocked_wash=0` all week. Permanent fix (umbrella #428) merged 2026-07-02 AND deployed
(`adapters/runner_ext_sell.py`, wired at `adapters/runner.py:995-1011`).

**Separate finding (symptom recovered, root cause NOT identified):** 07-08/09 buy scan ran
with 0 tickers — 133/145 per-ticker admission models failed the `live_train_end` 60d freshness
gate. The exact regression-window metadata value is not independently reconstructable (no
commit history in that window); the previously-stated "~2026-04-23" figure is an inference
from the log's staleness distance, not an observed value. Recovered by the 07-09 retrain →
125/145 on 07-10 — this is symptom recovery, not confirmed root-cause resolution. Universe-wide
availability incident, not established as META-specific either way; both days were mis-reported
as normal `no trade (no_candidates)`.

**Context:** META rallied +11.5% on the week ($600.42→$669.25) and street consensus is Buy
(~$834 target). Model-vs-street divergence flagged for the operator; model is primary.

**Deliverable:** `doc/research/2026-07-11-meta-no-buy-forensics.md` (mixed-result verdict,
per-session funnel table, wash-sale evidence block, outage analysis with corrected ownership,
recommendations) + sealed evidence at `renquant-artifacts#16`.

**Follow-ups recommended (not implemented here):**
1. Page on buy-scan universe collapse (`0 candidates from 0 tickers`) as an outage, not a
   no-trade decision (owner: `renquant-orchestrator`'s `model_freshness_monitor.py`).
2. Root-cause the 07-08 per-ticker policy-metadata `live_train_end` regression (owner:
   `renquant-pipeline`), window coinciding with — not established as caused by — the 07-08
   live-tree mutation incident.
3. No META-specific gate change; validate the fade-the-spike view via decision-ledger
   forward returns before touching floors.
