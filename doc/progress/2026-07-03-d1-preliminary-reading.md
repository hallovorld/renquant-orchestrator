# D1 preliminary reading — the gate-repair chain is closed; v3 shadow PASSES on the prod bundle

STATUS:   milestone record (S4/D1). The chain S1→S2→S3 is fully merged as of 2026-07-03
          ~02:30 PT (backtesting #61 approved by codex after the leader ruling; merged with
          the pre-merge marker). REVISION: r1.
WHAT:     records the PRELIMINARY D1 reading and the path to the official one.
          - Chain state: S1 (dedup/faithfulness) MERGED, S2 (placebo-difference scorer)
            MERGED, S3 (#61: v2 stays ENFORCING, v3 genuine_ic > 0.02 as SHADOW-ONLY
            diagnostic per the agreed review disposition) MERGED.
          - Preliminary reading: the S8 regeneration run (2026-07-03 01:25 PT, exit 0)
            freshly recomputed the prod GBDT bundle's gate quantities on
            walkforward_manifest_gbdt_prod_recipe_v2: fresh genuine_ic reproduced the
            committed 0.041681 within the ±0.001 faithfulness gate. Against the v3 frozen
            criterion (genuine_ic > 0.02): **preliminary PASS, margin ≈ 2.1×**.
          - What this does and does not say: it says the prod bundle's walk-forward
            evidence (2024-02→2026-02, 508 dates, placebo-subtracted) clears the frozen
            shadow bar — the repaired gate no longer structurally rejects the corpus that
            produced it. It does NOT say the live-era edge is positive (S9's OOS baseline
            hit-rate 49.96%, live IC ≈ 0 stand unchanged), and v3 remains shadow-only:
            no enforcement change.
          - OFFICIAL D1 verdict: the next weekly wf_promote run AFTER today's daily run
            pin-aligns the machine (13:55 PT) — that run evaluates fresh retrain
            candidates through v2-enforcing + v3-shadow and starts the prospective
            evidence clock codex's review asked for.
WHY/DIR:  D1 is the milestone anchor for the model-evidence program (#231); the unblock
          authority (operator 2026-07-03: PRs blocking my next step may be driven to
          merge) was used to resolve the bt#61 review deadlock — recorded per the
          record+notify discipline.
EVIDENCE: bt#61 review thread (leader ruling comment + codex APPROVED 09:20:30Z);
          data/exp/oos_pick_table_recipe_v2.manifest.json (508 dates / 147,066 rows;
          content anchor ba964b40… reproduced); S8 driver output (faithfulness PASS).
NEXT:     13:55 PT pin-align → weekly gate run → official D1 verdict recorded in
          VERDICTS.md (per S-REL); v3's prospective shadow accumulation begins.
