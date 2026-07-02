# 104 capability program — design PR

STATUS:   design for review (docs only — no code/config/broker/risk/sizing change in this PR).
          Describe → discuss → Codex + operator review → then per-item config/implementation PRs.
REVISION: r1.
WHAT:     one consolidated, prioritized program answering four operator directives (2026-07-02):
          (1) a three-lane cash-drag remediation design; (2) every open problem from this review
          cycle as a prioritized experiment/design backlog (P0–P3, each with owner repo +
          acceptance criterion); (3) 104 structural refactor candidates R1–R7; (4) an
          evidence-bounded alpha track (operator explicitly wants alpha and is dissatisfied with
          current model capability). Artifact:
          `doc/design/2026-07-02-104-capability-program.md`.
WHY/DIR:  cash is 75% idle ($8,140 / $10,806) with `cash_reserve_pct = 0` — the idleness is
          plumbing, not policy: `panel_buy_top_n = 3` + ~3% per-name targets throttle
          redeployment to ~$336/session (~24 sessions to redeploy); `qp_cash_drag_lambda = 0` in
          the pinned config while the solver default is 0.05 (the QP is told idle cash is free);
          whole-share sizing drops high-price names (BLK $1.1k > $324 target → selection drifts
          to cheap stocks — the OXY case); Kelly × conviction × σ-mult compound to ~3.1% vs the
          12% cap. Lane A de-throttles existing knobs (λ, top_n, 1-share floor) via
          ledger/shadow-validated config experiments; lane B parks idle cash in a benchmark
          sleeve (SPY or T-bill ETF — a recorded operator RISK decision) so stock-picking is the
          only live bet; lane C (more per-name deployment) stays evidence-gated on the P0 items
          because the model has no standing WF validation. The alpha budget goes to changing the
          INFORMATION SET (PIT revisions #205, FMP full fundamentals, down-cap MVP screen,
          cluster-wave breadth per E34's resume condition) — not to architecture swaps
          (E27/E33: linear ≥ transformer at this scale) and not to re-scanning the mined-out
          current panel (four honest NULLs this cycle).
EVIDENCE: 2026-07-01 run `01c54b39` (PV/cash/funnel/OXY trade row: 7 sh @ $47.94, target 3.1%,
          kelly 7.3% × conviction 0.504 × σ-mult 0.875); pinned
          `strategy_config.json` (`qp_cash_drag_lambda = 0`, `panel_buy_top_n = 3`,
          `cash_reserve_pct = 0`, BULL_CALM `max_position_pct = 0.12`);
          `portfolio_qp/tasks.py:2042` (solver default 0.05); failed-experiments-log E27/E33/E34
          (linear beats transformers; iTransformer overfit train 0.135/val 0.018; 103→816
          expansion dropped IC +0.032→+0.016, transfer-coefficient collapse);
          `transformer_v4_wl200_clean.parquet` measured 346,022 rows / 2,541 dates / 142
          tickers (→ ~42 non-overlapping fwd_60d windows per ticker); A1/A2 audits (genuine IC
          CI ∋ 0; BULL_CALM ≈ −0.003; combos dominated by regime-artifact momentum); #256 (GBDT
          IC ~61% persistence); OXY forensics (thin conviction margin, top-3 elimination win,
          sign_laundered 44/90).
NEXT:     Codex + operator review of the priority table and the six open questions (lane-B risk
          choice; FMP/SIP spend; lane-A timing vs first gate verdict; R1 tournament-retirement
          appetite; down-cap screen authorization; P0–P3 ordering). On agreement: per-item PRs —
          P0-1/P0-2 first (time-irreversible data substrate), then P0-3/P0-4 (gate repair +
          ledger wiring, the critical path), then lane A/B config PRs. No implementation in this
          PR.
