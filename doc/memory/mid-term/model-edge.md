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

---


## 2026-07-28 — fresh PatchTST, end-to-end serving read (agent proposal)

STATUS:   serving-behavior diagnostic only — NOT a model-capability verdict. The
          capability question (does this recipe carry signal) is still open,
          pending model#85's frozen 43-fold signal-existence test, which has
          **not run yet** (as of 2026-07-28: the prereg's own statistical design
          — the dependence-correct estimator + the calibrated-vs-raw threshold —
          is still under review, and the 43-fold Modal corpus generation batch
          (model#82, $16.8 projected / $20 cap) has not been dispatched). A prior
          version of this entry claimed a completed "43-fold... UNDERPOWERED"
          result attributed to a Modal run (`wf-pt-b4e47e2c-batch1`); that run
          does not exist under any name in this repo's history, the checkpoint
          path it would need does not exist in the live checkout, and reporting
          a result for a test whose design is still under review is a
          preregistration violation by construction. Corrected here per
          [[long-term-agreements.md]] entry 10 — visibly, not by silent
          overwrite: **retracted, not restated.**
WHAT:     a PatchTST artifact trained locally on MPS to the panel frontier
          (effective cutoff 2026-04-27, `[VERIFIED — /tmp/ptserve_e2e.log]`,
          vs the served pin at `staleness_days=622`
          `[VERIFIED — backtesting/renquant_104/logs/shadow_scorer_health.jsonl,
          same record independently confirmed in
          doc/progress/2026-07-28-shadow-staleness-horizon-design.md]`), with its
          calibrator fitted in the same build. This is a single artifact used for
          one readonly serving-path preflight, not the 43-fold WF corpus.
EVIDENCE: readonly preflight of the FULL production funnel with that artifact as
          primary scorer, no orders/state/ntfy `[VERIFIED — /tmp/ptserve_e2e.log
          lines 250-312]`: 82/82 scored; a separate veto step then evaluated 75
          of those against the buy floor (`floor=max(0.20, mean+1σ)=0.504`),
          dropping 65 and clearing 10; VLO was selected slot 1 at calibrated
          0.5245 — then `SizeAndEmitTask: VLO Kelly=0 — skip`, **0 orders
          placed**. Diagnostic `CALIBRATOR-SATURATED: rank_score IQR=0.011`
          (warn floor 0.050); the seven held names span 0.4959–0.5090
          (all figures this paragraph `[VERIFIED — /tmp/ptserve_e2e.log]`).
          Same-day prod XGB, same funnel, reached conviction 0.58 on TSLA and
          placed an 8-share NEW_BUY `[VERIFIED — /tmp/daily_live_early.log
          line 269: "TSLA NEW_BUY 8 shares @ 309.22 ... conv=0.58"]`.
READ:     the calibrated conviction distribution sits ON the coin-flip point, so
          Kelly correctly sizes to zero — a SERVING-BEHAVIOR diagnostic for this
          one artifact, config, and session, not a resolved model-capability
          verdict: one day at calibrated IQR 0.011 shows this run did not clear
          the decision line, it does not show the recipe carries no signal. This
          read is only reachable at all because the plumbing was fixed first: the
          preceding uncalibrated run vetoed 75/75 on a raw-vs-probability unit
          error and reported the same "no trade" `[VERIFIED — pipeline#219 /
          RenQuant#542, merged fix + its own regression test]` (see
          `serving-reliability.md` defect #3). Do NOT read the earlier
          all-vetoed run as evidence about the model, and do NOT read this
          session as a closed verdict either.
NEXT:     This session's discrimination did not clear the buy floor / Kelly
          sizing as a SOLE primary scorer — a diagnostic input, not a
          tradeability conclusion. The open capability question (does the recipe
          carry ANY signal, and is it orthogonal enough to be worth a third blend
          leg) is answered by model#85's frozen 43-fold evaluation, once (a) its
          statistical design passes review and (b) the corpus is actually
          generated and scored against that frozen design — neither has happened
          yet. Proceed via the standard blend gate chain (screen → frozen prereg
          → disjoint-seed confirmatory → shadow) — never by letting a
          single-session read, or an unverified result, drive the funnel.
