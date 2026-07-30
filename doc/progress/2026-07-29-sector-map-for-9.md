# Progress: proposed sector_map for the 9 new tickers (Phase 3, review required)

STATUS:   proposal UNDER DISCUSSION — **not merge-ready, DO NOT MERGE.**
          LONG ledger row 7 ("design docs are not merged while under
          discussion") applies: ARM/ENTG/SNDK are undecided. The review raising
          this is correct and ACCEPTED. No config changed. Part of the atomic
          batch — landing any piece alone hard-fails buys for all 154 names.

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
                    `main` (byte-identical to the PINNED mirror on `sector_map`
                    and `watchlist`; see §4(ii) in the design doc for where the
                    pinned config and the umbrella copy diverge)
                    (sector_map 485-645, sector_etf_map 646-664,
                    max_positions_per_sector 665 = 6, require flag 427)
                    `[VERIFIED-now — all 8 cited line numbers re-read and
                    reproduce exactly: 210, 427, 511, 513, 649-650, 665, 829,
                    1338-1341]`.
                    CORRECTION: a prior revision claimed
                    `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
                    "does not exist on this machine". That was WRONG and is
                    withdrawn — it exists at
                    `/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
                    (66K, 2026-07-28) `[VERIFIED-now — stat]`, and it is the
                    file RenQuant#544 names as the live runner's config. It was
                    only ever cited as a bare relative path, which does not
                    resolve from `renquant-orchestrator`.
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
                    runner loads (`daily_104.sh:113`), and 13 -> 15 (+15.4%)
                    under the umbrella copy the trainer loads
                    (`train_104.py:193`) `[VERIFIED-now — both files and both
                    loader lines read this session]`. The review reproduced 13,
                    I read 14, and BOTH are correct — this is the divergence
                    filed as RenQuant#544 (OPEN), not a counting error on either
                    side. Measured precisely, the drift is 3 tickers, all
                    present in the pinned config and absent from the umbrella
                    copy, 0 in the other direction: CRWV (datacenter_hw — the
                    entire 14-vs-13 gap), RKLB and SPCX (industrial, no effect
                    on these counts) `[VERIFIED-now — set difference on
                    sector_map and watchlist]`.
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

REVIEW DISPOSITION (2026-07-29):
          ACCEPTED — (a) LONG row 7: this doc is not merge-ready while ARM/ENTG/
          SNDK are open; DO-NOT-MERGE marker added to both docs. (b) The eventual
          `sector_map`/`sector_etf_map` EDIT belongs in renquant-strategy-104,
          reviewed atomically with the retrain and fingerprint — this note
          proposes no orchestrator config change and should be reduced to a
          pointer once the decision is made. (c) The "cannot bind today" and
          "#223/#608/#610 would widen admission" claims are removed and stay
          removed. (d) `datacenter_hw` = 13 on the surface the review read.
          PUSHED BACK — the claim that
          `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
          does not exist on this machine: it does (66K, 2026-07-28), and
          RenQuant#544 names it as the runner's config. A prior revision of this
          doc wrongly conceded that point; both the concession and the original
          objection are withdrawn, with the measurement in the design doc §7.

NEXT:     Operator decision on the three flagged buckets. ARM is laid out as
          options A/B/C in design-doc §8 rather than resolved, because nothing
          measurable separates A (`ai_chip`) from B (`chip_ip_licensing`) —
          both map to XLK, so they differ ONLY in whether ARM is subject to
          `ai_chip`'s 6-slot concentration cap. That is a risk-policy call, not
          a taxonomy one. Then Phase 4 (retrain + re-stamp) and Phase 5 (atomic
          landing) as a strategy-104 PR.
