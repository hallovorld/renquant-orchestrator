# Workstream: model edge (the binding problem)

STATUS:   active. 2026-06-21: XGB gated — POSITIVE aggregate real IC +0.054, PASSES the overall
          placebo + WF-floor, beats SPY 1/3; FAILs regime-sanity (BULL_CALM/CHOPPY) + BULL_CALM
          monotonicity. NOT promoted (gate FAIL, never bypass). The regime failure is substantive,
          not a formality: the dominant regime (BULL_CALM) is reliably weak and the aggregate is
          BEAR-inflated (see #167); not characterised as "the only wall left".
GOAL:     a PatchTST model with **positive real cross-sectional IC** that passes the WF gate.
NEXT:     pruning NOT closed (prereg ≥2-seeds/arm NOT fully run — Exp A single-seed). Defensible:
          Exp B recipe shows no stable edge across 2 seeds; no promotable model. Before closing or
          switching architecture → run a PROPERLY-POWERED signal-existence diagnostic (≥5 seeds,
          dense corpus, audit placebo matched to gate's 120d shift) + diagnose BULL_CALM
          monotonicity (real vs low-n artifact). Promotion needs operator sign-off; never bypass.
EVIDENCE: partial (final doc 2026-06-21): all completed runs FAIL. Exp B aligned_real_ic sign-
          unstable across seeds (+0.0079 / −0.0085); all ICs in noise band (<0.01) so the gate's
          floored placebo threshold is ill-conditioned here; corpus was sparse (4-cutoff, speed);
          audit placebo (shift-60-rows) mismatched the gate's 120d shift; BULL_CALM monotonicity
          undiagnosed. `[VERIFIED — /tmp/exp_{A,B,B45}_gate.log + self-audit, ephemeral]`
CONSTRAINT: 2026-06-21 operator lifted the XGB pitch-veto (LONG #3) and directed PatchTST → shadow.
          The XGB training method is rigor-audited (purged-WF-CV +60d embargo, honest +0.04 OOS IC),
          but the fresh XGB FAILED the WF gate (#166/#167) — so "XGB → prod" is operator-discretion
          behind the mu_floor conviction gate (#140), NOT a gate pass. Neither model passes the gate yet.

## PatchTST queue position (2026-07-26, operator-agreed)

Next role: **third blend leg** — a sequence-pattern tail classifier ("will
this name enter the top decile", trained on 60d patches) added to the
certified XGB blend (z(rank) + z(top-decile clf), model#74/#75/#76 chain,
CONFIRMED on two disjoint seed draws +0.055/+0.069). Rationale: the book's
certified skill is picking which high-vol name runs (DGTW block-t=+2.92);
pre-run sequence shape is plausibly visible to a patch model and invisible
to the cross-sectional trees — genuine architectural orthogonality, unlike
the killed G4 same-signal ensemble.

HARD prerequisites, in order — none may be skipped:
1. **Certified clean baseline first.** The repo's PatchTST has never passed
   a clean gate (all-negative-scores history; G4 killed; the prune line
   failed its placebo gates). No objective surgery on an uncertified base.
2. **Cost reality.** The placebo-armed verification machinery (tens of
   seeded runs, per-arm placebos) is 10-50× costlier than XGB's 15 s/fold;
   Modal remains gated by the standing no-Modal rule until its plan clears.
3. **Sequencing.** Not before the XGB-blend shadow (pipeline#213) is
   ACTIVE and stable — one certified change walks to production at a time.

Entry door is unchanged: screen with committed evidence → frozen prereg →
disjoint-seed confirmatory → shadow. Same machinery, no exceptions.

## rq105 consumer of the blend shadow (2026-07-28, operator directive)

rq105's frozen batch score vector switches source to the Step-5
shadow-blend lane DB (`RQ105_SCORE_SOURCE=blend`, orch PR #585): the
composite score the pinned `strategy_config.shadow_blend.json` profile
computes now feeds the shadow-realtime replay collector, with a
`scorer_identity` stamp per export and a one-line revert to prod.
Shadow/pilot surface only — no order path consumes the vector.
`[VERIFIED — STEP-0 trace in PR #585 + doc/progress/2026-07-28-rq105-batch-scores-blend-source.md]`
