# Progress: design proposal to switch on fractional sizing (sign-off required)

STATUS:   proposal only. NO config changed. The change is a live capital gate.

WHAT:     `doc/design/2026-07-29-enable-fractional-sizing.md` — proposes adding
          `execution.fractional_shares` to strategy-104's config, with the
          measured case, an explicit list of what it does NOT fix, four named
          risks, a pre-flight checklist, and rollback.

WHY/DIR:  S-FRAC v2 is built, merged and pinned in the pipeline;
          `kernel/sizing.py:204` says there is no behaviour change unless
          strategy-104 opts in, and strategy-104's `execution` block does not
          contain `fractional_shares` at all. It has been dark since it landed
          — the "deployed-but-dark" pattern, where a default-OFF fix that never
          reaches daily-full is worth zero.

EVIDENCE: artifact: `RenQuant/logs/daily_104/2026-07-*.log`, live
                    `backtesting/renquant_104/strategy_config.json`,
                    `renquant-pipeline/kernel/sizing.py` — all READ-ONLY.
  prod or exp:      PROPOSAL. No production config, code, or artifact changed.
  existing data:    Yes, measured this session. Size-zero skips per session:
                    07-02 (2), 07-10 (1), 07-13 (2), 07-27 (2), 07-28 (1);
                    deployment 2.8% / 8.8% / 6.7% / 5.0% / 0% of available
                    cash. Names floored: TSLA $309.22, EME $742.73, SPG
                    $236.69.
  best-known?:      Yes for the defect and the config gap. The impact estimate
                    is [DERIVED] and deliberately conservative — see below.
  scope:            One design doc. No pin advanced, no config edited, no
                    live surface touched.

THE HONEST PART:
          Fractional would have taken 2026-07-27 from $463 to roughly $925 —
          still only ~10% of available cash. The larger constraint is the
          target itself: Kelly produced 6.1% average, the emitted orders
          carried 2.2% after conviction scaling. Fractional does not touch
          that. The doc says so in its own §3 rather than letting a signer
          infer a bigger win than the measurement supports.

          Also recorded unresolved: the config says
          `kelly_sizing.fractional = 0.5` while the runtime logged
          `fractional=0.30`. That scales every target and should be understood
          before or alongside this change.

NEXT:     Operator sign-off is the gate. Before that: choose `min_notional`
          deliberately, run a full-funnel sim with the flag on vs off (the
          live-tree preflight rule — "committed = safe" is false), and confirm
          exit/tax-lot paths accept fractional quantities.
