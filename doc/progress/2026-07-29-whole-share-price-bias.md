# Progress: whole-share rounding gives the book an unchosen anti-high-price tilt

STATUS:   measurement. Follow-up to #606, which framed the idle half of the
          book as under-deployment — that framing was incomplete. No fix
          applied; both remedies are dark config switches needing sign-off.

WHAT:     `doc/research/2026-07-29-whole-share-price-bias.md`. Measured the
          price distribution of names that received orders against names that
          were sized to zero, across the live May-July run logs.

WHY/DIR:  Chasing the 2.2%-vs-6.1% target gap from #606 led to a code comment
          that had already diagnosed this on 2026-07-01, and to a consequence
          nobody had measured.

EVIDENCE: artifact: `RenQuant/logs/daily_104/2026-0[567]*.log` (READ-ONLY),
                    live `backtesting/renquant_104/strategy_config.json`,
                    `renquant-pipeline/kernel/pipeline/task_selection.py:244-259`.
  prod or exp:      PROD observation. Logs and config read READ-ONLY; nothing
                    changed, no order placed.
  existing data:    Yes, measured this session:
                    BOUGHT  n=33, median $160.59 `[VERIFIED]`, mean $227.23
                    SKIPPED n=11, median $764.28 `[VERIFIED]`, mean $810.43
                    ratio of medians 4.76x `[DERIVED — 764.28/160.59]`
                    skipped set: ASML $1,777 (x2), BLK $994.85, CAT $993.42,
                    EME $782.08/$764.28/$742.73, AVGO $360.34, TSLA $309.22,
                    SPG $236.69, BWXT $177.07 `[VERIFIED]`
                    Live config: `sizing` = null, `execution.fractional_shares`
                    = null, `kelly_sizing.disable_extra_multipliers` unset
                    `[VERIFIED]` — TWO dark switches for the same defect.
  best-known?:      Yes for the price gap. Explicitly NOT estimated: whether
                    the excluded high-price names would have outperformed. Two
                    days of forward return on eleven names is noise, and
                    dressing it up would be worse than leaving the question
                    open.
  scope:            Two docs. No pin advanced, no config edited, no live
                    surface touched.

THE DISTINCTION THAT MATTERS:
          Lost deployment is opportunity cost. This is a **factor exposure
          nobody chose**. The model ranked ASML, BLK, CAT and EME highly enough
          to clear every admission gate, and integer share arithmetic silently
          removed them. So the live book is not testing the model the model was
          validated as, and any conclusion drawn about live performance
          inherits that.

          Not absolute — LLY at $1,142.81 was bought on 2026-06-09 — but a
          4.76x median gap at n=33 vs n=11 is not noise.

NEXT:     The remedy is one of two switches already built and both dark:
          `sizing.one_share_floor_enabled` (A-3, rounds up to exactly one
          share) or `execution.fractional_shares.enabled` (S-FRAC v2, sizes
          fractionally). #607 proposes the second and is being re-homed to
          `renquant-strategy-104` per review. This measurement is the strongest
          argument for either, and should be cited there rather than restated.
