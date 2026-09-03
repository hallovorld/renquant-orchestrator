# L2 MoE mixture book — the mixture-of-experts allocation marked daily in shadow   (PR #1114)

STATUS:    delivered — derived view, no live surface, no ntfy.
WHAT:      `l2_paper_bandit.py` gains `mixture_view()` + `write_mixture()`: on
           every run, after the verified Hedge-weight log is synced, the engine
           rewrites `logs/l2_paper_bandit/l2_moe_mixture.jsonl` — one row per
           calendar date with the weights EFFECTIVE that day (previous row's
           weights; the floor-applied equal start on day 1 — rule 2), each
           arm's realized paper return ACROSS A PRICED STEP ONLY (the arm must be
           marked on this date and the previous calendar date; otherwise it sits in
           cash, and its multi-day catch-up on re-mark is EXCLUDED — no synthetic
           P&L, rule 3), the mixture return Σ w·r over held arms, the compounded mixture value
           from 1.0, every arm's value, the champion's value, the best fixed
           arm in hindsight and `mixture_minus_champion`. The CLI's SYNCED
           payload carries `mixture_latest`. The verified log is untouched
           (schema, bytes, replay-verify all unchanged; tested).
WHY/DIR:   Operator 2026-09-03: "moe模型尽快进shadow". The MoE direction is the
           three-layer allocation machine (orch#918); L2 = online expert
           allocation over the four paper books the lanes already mark. The
           weights alone (installed today, first row 15:45 PT) are a state; the
           mixture book is the MoE's own P&L path — what the routing WOULD have
           earned — replayable over the whole marked history, and the object
           the §2 regret claim (vs the best fixed arm, never profitability) is
           measured on. This is G-M AC2.
EVIDENCE:  artifact:      `logs/l2_paper_bandit/l2_moe_mixture.jsonl` (written by the scheduled job once `-run` carries this merge)
           prod or exp:   experiment — read-only over the lane DBs; a derived file next to the verified log
           existing data: dry run over the real DBs 2026-09-03 07:10 PDT: 96 rows replayed, champion weight 0.504974 [VERIFIED — module stdout]; `tests/test_l2_paper_bandit.py` 11 passed (7 existing + 4 new: first-day/rule-2 weights, compounding + champion/best-arm tracking, missing intermediate mark ⇒ 0 contribution AND catch-up excluded, catch-up magnitude never enters the mixture, deterministic rewrite + CLI payload, verified log untouched) [VERIFIED — 2026-09-03 14:40 PDT]
           best-known?:   n/a — a marking, not a verdict; the regret bound is conditional on the §2 contract
           scope:         "this marks the mixture on paper books; it allocates nothing and claims nothing about profitability"
CORRECTIONS (review r1, codex HIGH): r0 applied the weight effective on the
           re-mark date to an arm's whole multi-day catch-up return (paper_returns
           books the gap return on the later mark) — synthetic P&L, path-dependent
           on gap timing. r1 valuation rule: the mixture holds an arm only across a
           calendar step it can price (marked on both ends); a gap ⇒ cash, and the
           catch-up is excluded (`gap_excluded`, `held` on every row). Regression:
           missing intermediate mark; catch-up magnitude (0% vs +50%) leaves the
           mixture identical on the re-mark date while per-arm book values differ.
NEXT:      merge → `-run` ff-only (the job's PYTHONPATH) → first mixture file at the next 15:45 PT run (backfilled over the full history); weights + mixture lines join the ops report; ≥2 weeks of history before any proposal (design). G-M AC3 (routed-scorer shadow profile) is the next line.
