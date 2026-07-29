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

EVIDENCE: artifact: `renquant-strategy-104/configs/strategy_config.json` on
                    `main` (the PINNED config; see §4(ii) in the design doc
                    for where it and the umbrella copy diverge)
                    (sector_map 485-645, sector_etf_map 646-664,
                    max_positions_per_sector 665 = 6, require flag 427)
                    `[VERIFIED — git show origin/main:configs/strategy_config.json
                    in the renquant-strategy-104 clone, this session; prior
                    citation of `.subrepo_runtime/repos/...` was a nonexistent
                    path on this machine, corrected here]`,
                    enforcement at
                    `renquant-pipeline/.../preflight_pipeline/tasks/sector_map.py:49-82`,
                    `task_selection.py:39-40`, `portfolio_qp/tasks.py:1501-1536`.
                    All READ-ONLY.
  prod or exp:      PROPOSAL. Nothing written, no config changed.
  existing data:    Yes: `max_positions_per_sector = 6`
                    `[VERIFIED — strategy_config.json:665]`; the cap
                    groups on the RAW BUCKET not the ETF
                    `[VERIFIED — task_selection.py:39-40,
                    task_joint_actions.py:155/244,
                    portfolio_qp/tasks.py:1501-1536]`, so the
                    four buckets sharing XLK do not merge caps; the cap limits
                    HELD positions, not watchlist size `[DERIVED — same
                    enforcement path]`; NXPI is
                    already mapped `[VERIFIED — strategy_config.json:511]`;
                    WDC is already in
                    `datacenter_hw` `[VERIFIED — strategy_config.json:513]`.
                    Concentration: ai_chip, WATCHLIST-relative, 17 -> 23 (+35.3%)
                    `[VERIFIED — sector_map entries whose ticker is in watchlist,
                    this session]` — my first version used sector_map ENTRY count
                    (19), but a cap counts held positions among WATCHLIST names,
                    and only 17 of the 19 entries are on it.
                    datacenter_hw 14 -> 16 (+14.3%) under the PINNED config the
                    runner loads, and 13 -> 15 (+15.4%) under the umbrella copy
                    the trainer loads `[VERIFIED — both files read this session]`.
                    The difference is exactly CRWV; the review reproduced 13 and
                    I read 14 and BOTH are correct, which is the divergence filed
                    as RenQuant#544 rather than a counting error on either side.
                    No new sector_etf_map entry needed — both buckets map to XLK
                    `[VERIFIED — strategy_config.json:649-650]`.
  best-known?:      For the mechanics and counts, yes. Three bucket calls are
                    explicitly flagged as judgment: ARM (low — pure IP
                    licensing, no fab, unlike every ai_chip incumbent), ENTG
                    (medium — consumables vs capex equipment), SNDK (medium —
                    datacenter_hw on lineage vs ai_chip on the MU comp).
  scope:            Two docs. No pin advanced, no config edited, no live
                    surface touched.

CONCENTRATION COUNTS, AND AN OPEN MEASUREMENT QUESTION:
          23 ai_chip names competing for 6 held slots sounds alarming. #610
          (merged, `d69b7393`) reports the `mu >= 0.03` gate admitting 2-6
          names per session across the entire cross-section, but it is a
          pooled/read-only measurement, not a per-session strategy-side
          admission study, and it changed no config or admission rule — so it
          is NOT used here to conclude the cap "cannot bind today" or to
          predict what #223/#608/#610 "would cause." Whether the cap binds
          in practice is deferred to a canonical, reproducible per-session
          strategy-side admission-rate measurement, out of scope for this
          bucket-assignment proposal; re-run it whenever admission-affecting
          work lands.

SHARPEST POINT, called out rather than buried in a percentage:
          WDC + SNDK + STX would all sit in `datacenter_hw`. WDC and SNDK share
          DIRECT CORPORATE LINEAGE (SNDK is WDC's NAND spin-off), not just
          sector correlation, so they share cost structure and cyclicality. The
          correlation guard (threshold 0.70
          `[VERIFIED — strategy_config.json:210]`) would have to arbitrate, and a
          generic 0.70 threshold on same-lineage names is where it is least
          likely to behave as intended. I did NOT test it.

NEXT:     Operator/codex decision on the three flagged buckets, especially ARM.
          Then Phase 4 (retrain + re-stamp) and Phase 5 (atomic landing).
