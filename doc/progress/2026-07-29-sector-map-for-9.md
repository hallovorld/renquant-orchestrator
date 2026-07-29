# Progress: proposed sector_map for the 9 new tickers (Phase 3, review required)

STATUS:   proposal. No config changed. Part of the atomic batch — landing any
          piece alone hard-fails buys for all 154 names.

WHAT:     `doc/design/2026-07-29-sector-map-for-9-chip-tickers.md`. Bucket
          assignments for all 9, three of them flagged as low/medium
          confidence, plus the concentration analysis and the enforcement
          mechanics established first.

WHY/DIR:  `sector_map` and `sector_etf_map` are both config_fingerprint fields
          and P-SECTOR-MAP hard-fails buy mode on a missing entry
          (`require_sector_map_for_buys = true`). The taxonomy is hand-curated
          and finer than GICS; no script produces it, so this is the one part of
          the batch that needs human judgment.

EVIDENCE: artifact: `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
                    (sector_map 485-645, sector_etf_map 646-664,
                    max_positions_per_sector 665 = 6, require flag 427),
                    enforcement at
                    `renquant-pipeline/.../preflight_pipeline/tasks/sector_map.py:49-82`,
                    `task_selection.py:39-40`, `portfolio_qp/tasks.py:1501-1536`.
                    All READ-ONLY.
  prod or exp:      PROPOSAL. Nothing written, no config changed.
  existing data:    Yes: `max_positions_per_sector = 6` `[VERIFIED]`; the cap
                    groups on the RAW BUCKET not the ETF `[VERIFIED]`, so the
                    four buckets sharing XLK do not merge caps; the cap limits
                    HELD positions, not watchlist size `[VERIFIED]`; NXPI is
                    already mapped at line 511 `[VERIFIED]`; WDC is already in
                    `datacenter_hw` at line 513 `[VERIFIED]`.
                    Concentration: ai_chip 19 -> 25 (+31.6%), datacenter_hw
                    14 -> 16 (+14.3%) `[DERIVED]`. No new sector_etf_map entry
                    needed — both buckets map to XLK `[VERIFIED]`.
  best-known?:      For the mechanics and counts, yes. Three bucket calls are
                    explicitly flagged as judgment: ARM (low — pure IP
                    licensing, no fab, unlike every ai_chip incumbent), ENTG
                    (medium — consumables vs capex equipment), SNDK (medium —
                    datacenter_hw on lineage vs ai_chip on the MU comp).
  scope:            Two docs. No pin advanced, no config edited, no live
                    surface touched.

THE NUMBER THAT DEFUSES THE CONCENTRATION WORRY, AND ITS CONDITION:
          25 ai_chip names competing for 6 held slots sounds alarming, but the
          6-slot cap cannot bind today: the `mu >= 0.03` gate admits 2-6 names
          per session across the ENTIRE cross-section (7.9% of 1,010 rows;
          2 of 76 on 07-24) `[VERIFIED — orchestrator#610]`. The risk is
          CONDITIONAL on admission rising — which is exactly what the
          deployment work (#223, #608, #610) would cause. So: not a reason to
          withhold now, and a reason to re-check sector caps in the same change
          that widens admission.

SHARPEST POINT, called out rather than buried in a percentage:
          WDC + SNDK + STX would all sit in `datacenter_hw`. WDC and SNDK share
          DIRECT CORPORATE LINEAGE (SNDK is WDC's NAND spin-off), not just
          sector correlation, so they share cost structure and cyclicality. The
          correlation guard (threshold 0.70) would have to arbitrate, and a
          generic 0.70 threshold on same-lineage names is where it is least
          likely to behave as intended. I did NOT test it.

NEXT:     Operator/codex decision on the three flagged buckets, especially ARM.
          Then Phase 4 (retrain + re-stamp) and Phase 5 (atomic landing).
