# Universe-extension Stage 1 — the triage RUNNER (ships reviewed, runs later)

STATUS:    runner + tests ONLY, per the merged spec's §6 freeze-then-review-then-run
           sequencing (orch#995 / the #990 precedent). NOTHING is run in this PR:
           no scoring, no corpus build, no output artifact. The one authorized run
           is a later, separately-executed step after this PR is reviewed+merged.

WHAT:      Commit `doc/research/data/2026-08-18-universe-stage1-derivation.py` (the
           deterministic, read-only-inputs runner implementing spec §3-§6 verbatim)
           + `tests/test_universe_stage1_runner.py` (32 synthetic-data tests of the
           pure functions + run guards; zero market-data reads). Machinery ADAPTED
           from the reviewed #992 runner (G1 grid / G5 labels / G6-G7 paired
           placebo incl. the codex orch#990 shared-cross-section correction / G9
           blocks), extended from the IC estimand to the DGTW top-decile spread
           estimand. The sequencing promises are guards, not conventions: U10
           (one-shot marker — refuses when any output exists) and U11
           (byte-identity vs a freshly FETCHED origin/main before any work, the
           #996 T1/T2 shape WITH the orch#997 fetch-first correction; fetch
           failure fails closed) run first in main(), and the post-fetch
           origin/main sha + runner sha256 land in the output pins.

WHY/DIR:   Universe-extension workstream (spec orch#995, merged): decide with ONE
           frozen, reviewed triage run whether the served scorer's edge transfers
           beyond the 145-name watchlist — PASS (triage) authorizes only drafting
           the Stage-2 point-in-time program; DEPRIORITIZED parks the direction
           with evidence. This PR is the freeze-then-review-then-run middle step
           (the #990/#996 house pattern): ship the runner reviewed and un-run so
           the later single execution is mechanically bound to the reviewed bytes.

SCORING-PATH FEASIBILITY (checked FIRST, as directed):
           [VERIFIED — measured in-session 2026-08-18] the served panel pin scores
           arbitrary NON-watchlist tickers from on-disk OHLCV+fundamentals through
           the exact serve chain (renquant_base_data.alpha158_ops
           compute_alpha158_frame -> raw fund/PEAD/SUE/SENT -> renquant_pipeline
           feature_transform.transform_feature_frame(source_space="raw") ->
           booster from booster_raw_json): 3 sampled extension names + 2 watchlist
           names all produced finite, distinct scores. The pipeline is NOT
           architecturally tied to 145 (the artifact itself was trained on a
           292-ticker panel). No blocker.

KEY FACTS pinned while building (each verified in-session):
  1. SERVED PIN = the served blend's PANEL component (components[0] of
     ranking.panel_scoring in the strategy-104 golden config):
     artifacts/prod/panel-ltr.alpha158_fund.json, file sha256 6461b827ab2339a8...,
     config_fingerprint sha256:f8fb2259b2bf1537, trained 2026-08-02, 172 features.
     Byte identity asserted production's way (blend_scorer content_pin_matches on
     FILE bytes + verbatim config-fp compare). The blend's momentum leg is
     ledger-served with genesis 2026-08 — no historical coverage on this corpus —
     recorded as context, never scored (runner header U1 declares this reading).
  2. POSITIVE-CONTROL REFERENCE located in the committed evidence: renquant-model
     doc/research/evidence/2026-07-24-capacity-memo/
     structural_decomposition_result.json ["dgtw"]["dgtw"] = +0.24038304426130444
     (§7.1 table prints +0.243). UNITS CAVEAT DISCOVERED: the memo's f60 label is
     the panel's fwd_60d_excess, which is per-date CS z-scored (verified on the
     committed panel: per-date mean 0 / std 1) — the reference is in CS-sigma
     units, so the control replicates the instrument in THOSE units; the verdict
     estimand stays in raw return units (costs are bps). Frozen tolerance:
     sign-preserving lower bound REF/3 = +0.0801 sigma; no upper bound voids
     (served-pin scoring is in-sample on this corpus, inflation expected —
     telemetry above 3x REF). Control asserted BEFORE any Arm A cross-section.
  3. UNIVERSE CONVENTIONS reverse-derived from the 08-18 feasibility evidence
     (session universe_screen.py/csv): "OHLCV >= 5y" == first bar on/before the
     corpus start (the snapshot's ~5y fetch depth); fund-covered == present in
     sec_fundamentals_daily.parquet. Recomputed through the runner's own cascade:
     Arm A = 609 EXACT, Arm B = 1,955 EXACT, W = 145 EXACT. Runtime tolerance ±3%
     (stores drift daily; drift is what the guard must catch), exact counts
     recorded at every stage.

SPEC-INTERNAL DISCREPANCIES found and resolved FAIL-CLOSED (reported, not papered
over; both in the runner header U4/U6 and re-reported by the run's output):
  a. The corpus window holds 1,161 trading days (spec's "~1,155"), so the frozen
     every-5th-day RULE yields 233 cross-sections vs the spec's derived 231. The
     rule governs (the #992 G1 precedent); |n-231|<=2 asserted; block counts land
     EXACTLY on the spec's 19 (h=60) / 58 (h=20).
  b. The last grid date 2026-02-13 has its h=60 label endpoint on 2026-05-12 — 2
     trading days past the 2026-05-08 snapshot edge the spec asserts labels
     mature inside. The §6 snapshot-edge guard governs: that one obs is trimmed
     at h=60 (asserted <=1, and asserted to lie outside every complete block, so
     19/58 are untouched); h=20 loses nothing. [VERIFIED in-session: exactly
     {60: ['2026-02-13'], 20: []}].

EVIDENCE:
  artifact:      the runner (un-run) + its tests + this doc. No output artifact
                 exists yet BY DESIGN — the spec forbids running before review.
  prod or exp:   neither — the runner ships un-run; the run is a later,
                 separately-authorized execution per spec §6. No serving surface,
                 no data store, no live config is touched by this PR or by the
                 future run (zero-writes guard U7: outputs only to the isolated
                 worktree's doc/research/data/ + a scratch cache).
  existing data: [VERIFIED — in-session smoke, read-only] U1 byte-identity holds
                 against the live golden config; U4 grid n=233 with the single
                 known h=60 edge-trim; U2 cascade reproduces 609/1,955/145 exactly
                 on the feasibility inventory; the served pin scored 3 extension +
                 2 watchlist names finite/distinct end-to-end. No estimand was
                 computed for ANY arm (the one-shot corpus stays unexposed).
  best-known?:   yes — reuses the reviewed #992 paired/block machinery (incl. the
                 orch#990 composition correction) instead of a rewrite; scores
                 through the serve-verbatim transform chain and the committed
                 train recipe for the 14 extras (differences declared in-header:
                 sentiment runtime regime gate not simulated — 3/172 features,
                 0.6% extension coverage); all §6 guards are hard assertions, the
                 U8 minimum-blocks floor is frozen NOW as prereg content per the
                 runner-guards-are-prereg-content rule.
  scope:         adds the runner + tests + this doc. Merging AUTHORIZES only what
                 the spec's §6 already authorized: the one-time isolated corpus
                 build + the ONE scoring run, results as their own PR. A PASS
                 (triage) would authorize ONLY the Stage-2 PIT program proposal.
                 Nothing here kills, admits, retrains, or reallocates capital.

TESTS:     tests/test_universe_stage1_runner.py — 32 passed (DGTW 3-cell fixture,
           bucket boundaries + cost-drag formula, 4-condition verdict each-flips +
           U8 floor + control floor, paired-placebo shared-set identity, block
           segmentation 19/58 + block-t arithmetic, pin-compare semantics, U10
           one-shot pass/refuse + this-PR-ships-unrun, U11 fetch-failure/-not-
           merged/-byte-drift each fail closed + fetch-precedes-compare with
           lineage pinned). Full suite at the original head: 6,340 passed / 5
           skipped / 3 failed — the 3 are pre-existing LIVE-state probes
           (test_goal7_arm_b_accrual_probe, test_position_cap_conformance) that
           read this machine's live ledger/book and fail identically without
           this change.

NEXT:      codex review of THIS runner -> merge -> the ONE run (caffeinate, in an
           isolated worktree; ~1h corpus build + minutes of scoring) -> results PR
           (verdict table first, per-ADV-bucket net-of-cost table, Arm-W control
           outcome, every number provenance-tagged) -> on PASS (triage): Stage-2
           PIT proposal to the operator (own spend ask).
