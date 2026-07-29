# Progress: the buy gate sits above the model's own 90th percentile

STATUS:   measurement. No fix applied — lowering a live capital gate on a
          distributional observation is precisely the error this programme has
          been burned by before.

WHAT:     `doc/research/2026-07-29-mu-floor-sits-above-the-model-p90.md`.
          Measured the `mu` distribution the `mu_floor = 0.03` gate is applied
          to, and applied both buy gates to the same rows to see which binds.

WHY/DIR:  Chasing why 104 placed 0 orders on 2026-07-29 (`no trade
          (risk_gate_vol_dropped(29))`) while sitting at 50% cash. The three
          constraints already filed (#223 wash-sale, #224 message, #608
          whole-share) all act on the 2-6 names that reach sizing. This one
          decides how many reach it at all.

EVIDENCE: artifact: `RenQuant/data/runs.alpaca.db` (opened
                    `mode=ro&immutable=1`), live config
                    `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`.
  prod or exp:      PROD observation, READ-ONLY. Nothing written, no order
                    placed, no config changed.
  existing data:    Yes, measured this session over 1,010 scored rows,
                    2026-07-08..07-29:
                      pooled median mu = -0.0005 `[VERIFIED]`
                      pooled p90       = +0.0278 `[VERIFIED]`
                      pooled max       = +0.0484 `[VERIFIED]`
                      clearing mu>=0.03 = 80/1010 = 7.9% `[VERIFIED]`
                    Both gates on the same rows, 07-20..07-29:
                      pass rank floor  18-23% `[VERIFIED]`
                      pass mu>=0.03     3-8%  `[VERIFIED]`
                      pass BOTH        == pass mu, every session `[VERIFIED]`
                      compound 48/810 = 5.93% `[DERIVED]`
  best-known?:      Yes for the distribution and for which gate binds. NOT
                    claimed: that mu_floor should be lowered, that the
                    calibrator is wrong, or what a different floor would have
                    earned. I measured the calibrator's output distribution,
                    not its accuracy.
  scope:            Two docs. No pin advanced, no config edited, no live
                    surface touched.

THE TWO FINDINGS:
          (1) `mu_floor = 0.03` sits ABOVE the p90 (+0.0278) of the expected
              returns the model produces, so admission is ~8% by construction,
              independent of edge.
          (2) The adaptive rank floor is REDUNDANT: `pass BOTH` equals `pass
              mu` in every session, so it never removes a name that `mu` would
              have kept. It is what the logs BLAME
              (`veto:rank_score_below_floor`) and not what decides — which
              matches the AAPL forensics from the other direction.

NEXT:     Establish from the config's own provenance whether `mu_floor` is an
          ECONOMIC hurdle (costs/capital cost) or a STATISTICAL one (a
          percentile of model output). If economic, the honest conclusion is
          that the model rarely clears it. If statistical, it is mis-set by
          construction and should be expressed as a percentile. That is
          answerable and cheap; guessing is not.
