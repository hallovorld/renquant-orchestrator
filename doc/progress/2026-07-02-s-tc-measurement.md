# S-TC transfer-coefficient measurement — research PR

STATUS:   research evidence (read-only; docs + one committed script + JSON evidence).
REVISION: r1.
WHAT:     task S-TC of the unified plan (#231 §1 Term TC): `scripts/poc_transfer_coefficient.py`
          + `doc/research/evidence/2026-07-02-roadmap-pocs/poc_stc_transfer_coefficient.json`
          + an addendum section in the merged POC verification memo. Measures the last
          reasoned-tier number in the #231 §0 state vector.
WHY/DIR:  IR = TC·IC·√BR — TC was asserted ≈0.4. Measured: full-book TC 0.438/0.481
          (Pearson/Spearman, today's broker positions vs the latest run's desired vector) and
          buy-side decision-TC ≈ 0.09 (desired kelly vs emitted order sizes among
          floor-clearing candidates, per run) — i.e. the current decision path transfers almost
          NONE of the model's relative-conviction ordering into new-money sizing; the 0.44
          full-book figure is inherited from historical accumulation. This is the strongest
          quantitative justification measured so far for lane A (de-throttle) + R4
          (selection-budget refactor), whose target is TC ≥ 0.6 on both readouts.
EVIDENCE: committed JSON (reproduce: one command in the script docstring); read-only inputs
          (runs.alpaca.db; Alpaca /v2/positions + /v2/account).
NEXT:     Codex review; the TC series becomes routine once S5 persists per-run position
          values; #231's state vector picks up the measured row at its next revision/addendum
          (that PR is frozen under review — not touched by this one).
