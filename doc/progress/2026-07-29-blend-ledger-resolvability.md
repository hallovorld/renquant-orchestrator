# Progress: blend ledger records WHY a session did not realize

STATUS:   delivered (telemetry + 2 tests). The frozen readout statistic and the
          all-or-nothing realization criterion are UNCHANGED.

WHAT:     `mature_fill` now records `n_resolvable_prod` / `n_resolvable_blend` /
          `n_picks_*` on every pass for every unrealized row, and persists the ledger
          even when nothing newly realizes, so a stuck session shows its shortfall
          instead of looking untouched.

WHY/DIR:  The ledger is the 120-session forward evidence — the one result in this
          programme that cannot be re-derived after the fact. Realization is
          all-or-nothing by design (a spread over a partial pick set is a different
          statistic, and the readout rule is frozen under pipeline#213), which means
          ONE unresolvable ticker drops that session from the evidence permanently
          and silently. Making the shortfall visible is additive; changing the
          criterion would be moving a frozen goalpost.

EVIDENCE: ledger state `[VERIFIED — data/rq104_blend_readout/ledger.jsonl, read
          2026-07-29]`: 2 sessions (2026-07-27, 2026-07-28), one row per date, no
          duplicates, prod∩blend overlap 6/10 on both, `realized: false` on both —
          correct, their forward windows have not closed. Coverage risk quantified
          `[VERIFIED — runs.alpaca.db::ticker_forward_returns]`: every date that has
          any realized forward return is at **100%** completeness (8 of 8 sampled),
          so the criterion is not currently dropping sessions — but the same table
          holds dates carrying only 2-3 tickers (2026-06-17, 2026-06-18), where a
          session would vanish without a trace. Latent, not active. Suite 7/7
          `[VERIFIED — pytest tests/test_rq104_blend_readout.py]`. No IC/Sharpe claim
          is made, so the §4(b) triad does not apply.

NEXT:     A separate decision, NOT taken here: the ledger backfills **fwd_20d** while
          the certified effect (+0.0687, CI lower +0.0156) and both models are
          **fwd_60d**. GOAL-6 Stage 0 additionally measured that a 20d horizon buys no
          net power (H2 NOT SUPPORTED — ~3x the blocks, proportionately smaller
          effect). Judging a 60d-certified model by a 20d spread may be measuring a
          different quantity. The readout rule is frozen, so this is written up for
          an operator/design decision rather than changed unilaterally.
