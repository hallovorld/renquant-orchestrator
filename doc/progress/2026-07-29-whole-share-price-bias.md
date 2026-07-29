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

EVIDENCE: artifact: canonical daily-prod logs only, `RenQuant/logs/daily_104/
                    2026-0[567]-[0-9][0-9].log` (64 files; excludes 65 ad hoc
                    `_shadow`/`_smoke`/`_manual`/`_readonly`/`_after_fix`/
                    `_multirepo`/etc. runs also present in that directory —
                    `scripts/daily_104.sh:40` pins the canonical name to
                    exactly `$LOG_DIR/$DATE.log` with no suffix), READ-ONLY;
                    the **pinned** `renquant-strategy-104/configs/
                    strategy_config.json` (not the umbrella fallback copy —
                    see correction below); `renquant-pipeline/kernel/
                    pipeline/task_selection.py:244-259`.
  prod or exp:      PROD observation. Logs and config read READ-ONLY; nothing
                    changed, no order placed.
  existing data:    Yes, measured this session:
                    BOUGHT  n=33, median $160.59, mean $227.23
                    SKIPPED n=11, median $764.28, mean $810.43
                    [VERIFIED — this session, `grep -h "NEW_BUY"` /
                    `grep -h "insufficient cash — skip"` across the 64
                    canonical files listed above]
                    ratio of medians 4.76x `[DERIVED — 764.28/160.59]`
                    one-sided Mann-Whitney U (skipped > bought): U=323,
                    p=6.6e-5 `[VERIFIED — this session,
                    scipy.stats.mannwhitneyu(skipped, bought,
                    alternative='greater') on the two samples above]`
                    skipped set: ASML $1,777 (x2), BLK $994.85, CAT $993.42,
                    EME $782.08/$764.28/$742.73, AVGO $360.34, TSLA $309.22,
                    SPG $236.69, BWXT $177.07 `[VERIFIED — same grep]`
                    **Correction (this revision):** the original evidence
                    block read the umbrella's stale fallback copy
                    (`RenQuant/backtesting/renquant_104/strategy_config.json`)
                    as the live surface and reported both switches as
                    absent/null. `scripts/daily_104.sh:113-119` resolves the
                    PINNED `renquant-strategy-104` subrepo config first;
                    read against that config
                    [VERIFIED — this session, read
                    `renquant-strategy-104/configs/strategy_config.json` on
                    `main`], both switches are declared and explicitly
                    `false` (not absent): `execution.fractional_shares.
                    enabled=false` (+ `min_notional=1.0`,
                    `min_fractional_trade_notional=25.0`),
                    `sizing.one_share_floor_enabled=false`. Only
                    `kelly_sizing.disable_extra_multipliers` is genuinely
                    unset. The umbrella fallback copy also carries a stale
                    `kelly_sizing.fractional=0.5` vs the pinned copy's `0.3`
                    — the same drift already documented in
                    `renquant-strategy-104#71`. The remedy conclusion is
                    unchanged (both switches are OFF in production); the
                    "absent from config" description was wrong and is
                    corrected here to "declared, and explicitly disabled."
  best-known?:      Yes for the price gap, now with a significance test
                    backing it (see above). Explicitly NOT estimated: whether
                    the excluded high-price names would have outperformed. Two
                    days of forward return on eleven names is noise, and
                    dressing it up would be worse than leaving the question
                    open.
  scope:            Two docs. No pin advanced, no config edited, no live
                    surface touched.

THE DISTINCTION THAT MATTERS:
          Lost deployment is opportunity cost. This is a **factor exposure
          nobody chose**. This is a mechanism claim, not an inference from
          the price-gap statistic: the sizing log lines record ASML, BLK,
          CAT and EME clearing every admission gate before integer share
          arithmetic zeroed them. So the live book is not testing the model
          the model was validated as, and any conclusion drawn about live
          performance inherits that.

          Not absolute — LLY at $1,142.81 was bought on 2026-06-09 — but a
          4.76x median gap at n=33 vs n=11 tests significant (one-sided
          Mann-Whitney p=6.6e-5), not noise.

NEXT:     The remedy is one of two switches already built and both dark:
          `sizing.one_share_floor_enabled` (A-3, rounds up to exactly one
          share) or `execution.fractional_shares.enabled` (S-FRAC v2, sizes
          fractionally). #607 proposes the second and is being re-homed to
          `renquant-strategy-104` per review. This measurement is the strongest
          argument for either, and should be cited there rather than restated.
