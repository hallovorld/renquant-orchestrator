# Progress: sector_map for the 9 new tickers (Phase 3) — ARM decided, counts corrected

STATUS:   **post-decision analysis record.** ARM's bucket — the one call that
          needed a ruling — is **DECIDED: `ai_chip`**, sharing `ai_chip`'s 6-slot
          concentration cap. Nothing in these docs awaits a decision *in this
          repo*, so LONG row 7 ("design docs are not merged while under
          discussion") is satisfied. No config changed, and none may be here: the
          `sector_map`/`sector_etf_map` EDIT is strategy-owned and lands in
          `renquant-strategy-104` atomically with the retrain and fingerprint.
          Part of the atomic batch — landing any piece alone hard-fails buys for
          all 154 names.

WHAT:     `doc/design/2026-07-29-sector-map-for-9-chip-tickers.md`. Bucket
          assignments for all 9, the enforcement mechanics established first, the
          concentration measurement, and the ARM decision record.

WHY/DIR:  `sector_map` and `sector_etf_map` are both config_fingerprint fields
          and P-SECTOR-MAP hard-fails buy mode on a missing entry
          (`require_sector_map_for_buys = true`). The taxonomy is hand-curated
          and finer than GICS; no script produces it, so this is the one part of
          the batch that needs human judgment. DIR: record the mechanics and the
          measured concentration in the orchestrator (cross-repo sequencing),
          land the config edit in strategy-104.

CORRECTIONS IN THIS REVISION (visible, per LONG #10 — not silent overwrites):
          **(A) The concentration figure was understated, and I found it, not the
          review.** A prior revision reported `ai_chip` **17 -> 23 (+35.3%)**. It
          applied the watchlist-relative correction to the BEFORE count but not
          the AFTER count: it excluded NXPI from `net new` as "already mapped".
          NXPI does already have a `sector_map` entry, but it is **NOT on the
          watchlist** `[VERIFIED — repro block in design-doc §7, membership
          test]`, and the batch adds all 9 to the watchlist. On the only axis a
          cap can see, NXPI is a NEW member. Seven of the nine land in `ai_chip`,
          so the corrected figure is **17 -> 24 (+41.2%)**
          `[DERIVED — 7/17]`.
          **(B) The "largest bucket" claim mixed two axes.** It compared
          `ai_chip` watchlist-relative (23) against `software` ENTRY count (26).
          On one consistent watchlist-relative axis, `ai_chip` is currently
          **4th** (17; behind industrial 21, software 19, finance 18) and after
          the batch it is **24 — the largest bucket outright**, ahead of
          industrial's 21 `[VERIFIED — repro block in design-doc §7,
          per-bucket counts restricted to watchlist members]`. Both corrections
          make the concentration case STRONGER than the prior revision stated.

EVIDENCE: artifact: `renquant-strategy-104/configs/strategy_config.json` on
                    `main`, byte-identical to the PINNED mirror on `sector_map`
                    and `watchlist` `[VERIFIED — repro block in design-doc §7,
                    dict equality on both fields]`. All 8 cited line numbers
                    re-read and reproduce exactly — 210, 427, 511, 513, 649-650,
                    665, 829, 1338-1341 `[VERIFIED — each line printed from the
                    PINNED config, this session]`.
                    enforcement at
                    `renquant-pipeline/.../preflight_pipeline/tasks/sector_map.py:49-82`,
                    `task_selection.py:39-40`, `portfolio_qp/tasks.py:1501-1536`.
                    All reads READ-ONLY; nothing written under `RenQuant/`.
  prod or exp:      Neither. Docs only. Nothing written, no config changed.
  existing data:    `max_positions_per_sector = 6`
                    `[VERIFIED — strategy_config.json:665]`; the cap groups on
                    the RAW BUCKET not the ETF `[VERIFIED — task_selection.py:39-40,
                    task_joint_actions.py:155/244,
                    portfolio_qp/tasks.py:1501-1536]`, so the four buckets
                    sharing XLK do not merge caps; the cap limits HELD positions,
                    not watchlist size `[DERIVED — same enforcement path]`;
                    NXPI already mapped `[VERIFIED — strategy_config.json:511]`;
                    WDC already in `datacenter_hw`
                    `[VERIFIED — strategy_config.json:513]`.
                    Concentration, watchlist-relative:
                    `ai_chip` **17 -> 24 (+41.2%)**; `datacenter_hw`
                    **14 -> 16 (+14.3%)** under the PINNED config the runner
                    loads (`daily_104.sh:113`), **13 -> 15 (+15.4%)** under the
                    umbrella copy the trainer loads (`train_104.py:193`)
                    `[VERIFIED — repro block in design-doc §7, both surfaces;
                    both loader lines read this session]`.
                    The review reproduced 13 and I read 14, and BOTH are
                    correct — the two files have diverged. The drift is exactly
                    3 tickers, all present in the pinned config and absent from
                    the umbrella copy, 0 in the reverse direction: CRWV
                    (`datacenter_hw` — the entire 14-vs-13 gap), RKLB and SPCX
                    (`industrial`, no effect on these counts)
                    `[VERIFIED — repro block in design-doc §7, set difference]`.
                    Filed as `hallovorld/RenQuant#544`, OPEN, citing the same two
                    loader lines `[VERIFIED — gh issue view hallovorld/RenQuant#544]`.
                    No new `sector_etf_map` entry needed — both buckets map to
                    XLK `[VERIFIED — strategy_config.json:649-650]`.
  best-known?:      Mechanics and counts: yes, re-measured this session. ARM's
                    bucket is DECIDED but by policy, not measurement — the
                    taxonomic stretch in design §3 is unchanged by the decision
                    and no confidence was added to it. ENTG (consumables vs capex
                    equipment) and SNDK (`datacenter_hw` on lineage vs `ai_chip`
                    on the MU comp) remain medium-confidence recommendations,
                    ratified on the strategy-104 PR that makes the edit.
  scope:            Two docs. No pin advanced, no config edited, no live surface
                    touched, nothing written under `RenQuant/`.

SHARPEST POINT, called out rather than buried in a percentage:
          WDC + SNDK + STX would all sit in `datacenter_hw`. WDC and SNDK share
          DIRECT CORPORATE LINEAGE (SNDK is WDC's NAND spin-off), not just sector
          correlation, so they share cost structure and cyclicality. The
          correlation guard (threshold 0.70
          `[VERIFIED — strategy_config.json:210]`) would have to arbitrate, and a
          generic 0.70 threshold on same-lineage names is where it is least
          likely to behave as intended. I did **NOT** test it.

WHETHER THE CAP BINDS — still open, still not claimed:
          24 `ai_chip` names competing for 6 held slots is the corrected figure.
          #610 (merged, `d69b7393`) reports the `mu >= 0.03` gate admitting 2-6
          names per session across the whole cross-section, but it is a
          pooled/read-only measurement, not a per-session strategy-side admission
          study, and it changed no config or admission rule — so it is NOT used
          here to conclude the cap "cannot bind today", and no claim is made that
          #223/#608/#610 "would cause" higher admission. Deferred to a canonical,
          reproducible per-session strategy-side admission-rate measurement.

REVIEW DISPOSITION:
          ACCEPTED — (a) The "cannot bind today" and "#223/#608/#610 would widen
          admission" claims are removed and stay removed. (b) `datacenter_hw` =
          13 on the surface the review read; both readings are now stated with
          the divergence pinned to 3 named tickers. (c) The config EDIT is
          strategy-owned and lands in strategy-104 atomically with the retrain
          and fingerprint — accepted without reservation; nothing here edits
          config. (d) LONG row 7 — resolved by the ARM decision rather than by
          argument.
          PUSHED BACK, with measurements — (e) The claim that
          `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
          "does not exist on this machine": it does, 66K, dated 2026-07-28
          `[VERIFIED — ls -la on the absolute path, this session]`, and
          RenQuant#544 names it as the runner's config. A prior revision of this
          doc wrongly CONCEDED that; both the concession and the original
          objection are withdrawn. It was only ever cited as a bare relative
          path, which does not resolve from `renquant-orchestrator`.
          (f) That this record should not exist in the orchestrator at all: the
          §1/§4 measurements are pipeline-enforcement and pinned-vs-umbrella
          divergence facts (RenQuant#544) that no single strategy PR owns and
          that the strategy PR will cite rather than reproduce. Deleting this
          record would lose them, not relocate them. The bucket TABLE should be
          reduced to a pointer once the strategy-104 PR exists, so the assignments
          live in exactly one place.

NEXT:     Phase 4 (retrain + re-stamp) and Phase 5 (atomic landing) as a
          strategy-104 PR carrying the config diff, the fingerprint and the
          retrain evidence; ENTG and SNDK are ratified on that review. The
          untested WDC/SNDK correlation-guard behaviour should be exercised
          before the batch lands, not after.
