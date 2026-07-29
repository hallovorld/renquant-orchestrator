# Progress: CORRECTION — the fractional switches are deliberately off, not forgotten

STATUS:   this PR is reduced to a CORRECTION record. Its first revision was
          wrong on its central factual claim, and the enablement proposal is
          re-homed to `renquant-strategy-104` per review.

WHAT:     `doc/design/2026-07-29-enable-fractional-sizing.md` rewritten as a
          visible correction. The first revision claimed
          `execution.fractional_shares` was "absent entirely" from the live
          config and framed the state as deployed-but-dark by omission.

WHY/DIR:  I read the WRONG FILE. `scripts/daily_104.sh:113` resolves the
          production config from the PINNED subrepo and only falls back to
          `backtesting/renquant_104/strategy_config.json`. I read the fallback.

EVIDENCE: artifact: `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
                    (pinned HEAD `8402a62`) vs
                    `backtesting/renquant_104/strategy_config.json`;
                    `scripts/daily_104.sh:113-119`. All READ-ONLY.
  prod or exp:      PROD observation. Nothing changed.
  existing data:    Yes, both files read this session:
                    `execution.fractional_shares` PINNED = present with
                    `enabled: false` `[VERIFIED]`, `min_notional: 1.0`
                    `[VERIFIED]`, `min_fractional_trade_notional: 25.0`
                    `[VERIFIED]`; fallback = `null` `[VERIFIED]`.
                    `sizing.one_share_floor_enabled` PINNED = `false`
                    `[VERIFIED]`; fallback = `null` `[VERIFIED]`.
                    `kelly_sizing.fractional` PINNED = `0.3` `[VERIFIED]`,
                    fallback = `0.5` `[VERIFIED]`, runtime logged `0.30`
                    `[VERIFIED — logs/daily_104/2026-07-27.log]`.
  best-known?:      Yes. The three corrections below are direct file reads.
  scope:            Two docs in this repo. No config, pin, or live surface
                    touched.

THE THREE CORRECTIONS:
          (a) The `fractional=0.30` vs `0.5` discrepancy DOES NOT EXIST. Pinned
              says 0.3, runtime logged 0.30. The review asked for this baseline
              to be pinned before proceeding; it dissolves — I was comparing
              the log against a file the live run does not load.
          (b) `min_notional` is NOT TBD. The pinned config already declares
              1.0, and `min_fractional_trade_notional` 25.0.
          (c) The framing was wrong and the real state is more defensible: a
              documented DEFAULT-OFF with three named preconditions (active-path
              capability gate, broker guard, sizing-fidelity evidence), an
              ownership split in `_provenance`, and an existing enablement
              contract at strategy-104
              `doc/progress/2026-07-12-one-share-floor-enablement.md`.

WHAT SURVIVES:
          The measurement, which is independent of which file declares what
          because it reads what the live run DID: 2026-07-27 placed 2 orders
          for $463 of $9,301 `[VERIFIED]`; bought median $160.59 (n=33) vs
          skipped median $764.28 (n=11), a 4.76x gap `[VERIFIED / DERIVED]` —
          orchestrator#608.

NEXT:     The enablement proposal goes to `renquant-strategy-104`, measured
          against its own enablement contract, citing #608 for evidence. The
          question is no longer "why was this never turned on" but "have the
          three preconditions been met".
