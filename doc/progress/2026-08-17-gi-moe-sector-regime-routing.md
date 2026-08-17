# G-I MoE (sector × regime routing) — design (doc only)

STATUS:    design for review. Docs only — NO code / config / behavior change.
           Per operator (2026-08-17): design PR must be APPROVED before any
           implementation starts; G-I is then self-driven through the loop.

WHAT:      Commit `doc/design/2026-08-17-gi-moe-sector-regime-routing.md`: the full
           MoE v1 design — the 11×4 power-gated routing table (33/44 cells hard-wired
           to the champion), the expert roster (existing 6 + 4 momentum-grade
           candidates at zero new data/architecture cost), the strategy-facing alias
           registry, the momentum-path qualification pipeline with an
           incremental-information gate, the frozen §5b cell-assignment decision rule
           (candidate-manifest freeze BEFORE any corpus scoring; estimand + pinned
           champion comparator; coverage minima; Holm FWER ≤ 5% over the FULL
           frozen-manifest × cell family, screen failures included — codex review
           2026-08-17 round 3; ΔIC ≥ +0.02 minimum effect; no-decision ⇒ champion;
           Stage-A assignment + Stage-B operational fail-safe (NOT statistical
           confirmation); demotion ratchet; honest downside guarantee), serving via
           the existing blend/regime_router composition machinery, measurable
           AC1–AC6 with an explicit AC-GATE go/no-go (codex rounds 7–8: on the
           expected NO-GO — all-champion on current geometry — the impl phase
           stops at the auditable Stage-A verdict; the live MoE shadow lane +
           AC4 replay attribution are GO-branch-only, and AC1's fallback proof
           is an offline schema/composition contract test, not a live lane),
           an explicit honesty ledger, and a visible §10 Corrections
           section (LONG row 10): the sample-geometry episode counts were
           re-measured in-session and the earlier 17/8/5/3 estimate did not
           reproduce — realistic v1 Stage-A outcome corrected to all-champion
           (m = 2 blocks at the fwd-60d horizon under the frozen gap-merge rule,
           below the frozen m ≥ 10 floor; rule-and-occupancy joint, per §3's
           Sensitivity note).

WHY/DIR:   Operator-directed 2026-08-17 ("自己set goal和loop来drive这个moe模型！设计
           要发pr被approve之后再开始impl"), consolidating the 08-13..08-17 decisions:
           keep the blend; MoE = model-list filling a (sector×regime) table; no new
           data pipelines or training architectures ("成本太大"); fast/slow momentum
           separate; strategy names not algorithm names; candidate bar = the momentum
           bar (simple sort + walked our kill path). The bar is NOT a t-threshold:
           an earlier draft cited transfer t≈3.17, which is the iid figure; the
           dependence-adjusted one is +0.71
           `[VERIFIED — prior work, doc/research/2026-08-08-moe-stage-minus1-results.md:173]`;
           the later 278-date purged re-run reports ADJUSTED t = +3.17
           `[VERIFIED — prior work, doc/research/2026-08-08-moe-s10-confirmatory-kill.md]`
           — machinery validated at depth, still not an admission bar.

EVIDENCE:
  artifact:      `doc/design/2026-08-17-gi-moe-sector-regime-routing.md` + this doc.
                 No code, no config, no production/live path.
  prod or exp:   neither — design only; no computation run, no live change.
  existing data: sample geometry re-measured in-session this fix round `[VERIFIED —
                 kernel.hmm_regime_labels.compute_hmm_regime_labels(
                 data/ohlcv/SPY/1d.parquet), window 2019-01-14..2026-03-02, 1,792
                 trading days]`: BULL_VOLATILE 1,399 days / 80 raw day-level
                 episodes / m = 2 blocks after the §5b <60-calendar-day gap-merge;
                 BEAR 260/53/12; CHOPPY 63/28/13; BULL_CALM 70/9/6. The earlier
                 "17/8/5/3 episodes at ~3-week fold granularity" (uncommitted 08-13
                 session estimate) did NOT reproduce and is corrected visibly in
                 the design's §10; m = 2 is a joint property of the frozen merge
                 rule + 78% day-occupancy (§3 Sensitivity note). 33/44 cells
                 pre-emptively hard-wired `[DERIVED — 44 − 11 BULL_VOLATILE
                 cells]`; on measured geometry the realistic Stage-A outcome is
                 all-champion (m = 2 < 10). 11 GICS sectors / 304 tickers
                 `[VERIFIED — python read of data/ticker_sectors.json,
                 2026-08-17]`. Corpus span 2019-01-14..2026-03-02 = the 125-window
                 WF lineage cutoff range `[VERIFIED — prior work,
                 renquant-backtesting
                 doc/progress/2026-08-02-lineage-stage2-scoring-slice.md]`.
                 [VERIFIED — read 2026-08-17] blend + regime_router are registered
                 inference-only composition kinds in the pipeline model registry;
                 the momentum ledger emitter (weekly, hash-chained) is the live
                 pattern the candidate emitters clone — its home is the model
                 factory (`renquant-model`
                 `src/renquant_model_momentum/{train,ledger}.py`
                 [VERIFIED — read 2026-08-17]), which fixes emitter ownership per
                 RENQUANT_REPOS.md; GOAL-8 momentum transfer t(iid)=+3.17 /
                 t(n_eff-adjusted)=+0.71
                 `[VERIFIED — prior work, doc/research/2026-08-08-moe-stage-minus1-results.md:173]`
                 — and at 278 purged dates ADJUSTED t=+3.17
                 `[VERIFIED — prior work, doc/research/2026-08-08-moe-s10-confirmatory-kill.md]`
                 — no admission rests on a t-threshold either way; the
                 tail_q90_20d rationale's "DGTW t=2.92"
                 `[ASSUMED — appears only in doc/memory/mid-term/model-edge.md with no
                 research artifact behind it; demoted from evidence to hypothesis]`;
                 fundmom previously tested and REJECTED (kill list)
                 `[VERIFIED — prior work, doc/design/2026-06-28-renquant105-alpha-discovery.md:69
                 for the five canonical price-trend factors]`.
  best-known?:   yes — the design's degrees of freedom are bounded by the measured
                 power map (effective-sample-BEFORE-decision-rule, the #975/#976
                 lesson — applied for real this round: the in-session count says
                 m = 2, so the frozen rule is expected to no-op to champion rather
                 than have its floor quietly lowered) and by the frozen §5b
                 assignment rule; hard-wired cells are byte-identical to today by
                 construction; tested cells carry a bounded probabilistic downside
                 (Holm FWER ≤ 5%/batch over the FULL frozen manifest — valid
                 because the family is not reduced by same-corpus screening — with
                 Stage B as an operational fail-safe and the demotion ratchet
                 bounding exposure, not probability; the earlier blanket "worst
                 case = today by construction" claim was over-broad and is
                 corrected in §5b step 9); candidates are restricted to
                 zero-marginal-cost builds and must clear a cheap IC screen (run
                 only after the manifest freeze) BEFORE any prereg cathedral; an
                 incremental-information gate (|ρ|<0.7 `[ASSUMED — frozen diversity
                 threshold]`) blocks re-skinned duplicates; the kill list is
                 carried forward explicitly.
  scope:         "a design for the MoE v1 routing table (NOT executed, NOT
                 implemented). Authorizes no code, no config, no live change, no data
                 spend. Implementation is a separate phase of codex-gated PRs that
                 starts only after this design is approved; deploys remain
                 operator-gated. Does NOT claim to restore bull buying, learn routing,
                 weight components (AC5 deferred), or close the blend-level WF-gating
                 gap (deferred per #982)."

TESTS:     doc-only PR; focused repo checks run this round:
           `pytest tests/test_require_progress_doc.py tests/test_repos.py -q` → 22 passed.

NEXT:      codex review (design-review fixes personal) → on APPROVAL, impl phase:
           (1) emitter clones high52w/lowbeta/quality_gp + tail_q90_20d recipe;
           (2) §5b candidate-manifest freeze (before any corpus scoring);
           (3) cheap IC screen with recorded kill/advance verdicts; (4) router config
           schema + frozen hard-wire list + alias registry + AC1 offline contract
           test; (5) §5b Stage-A assignment batch; (6) §7 AC-GATE go/no-go —
           expected NO-GO on current geometry (m = 2 < 10): impl STOPS at the
           committed all-champion verdict, and the MoE shadow lane + AC4 replay
           attribution are built ONLY on a GO (≥1 admissible cell + ≥1 qualified
           candidate from a reviewed new corpus/estimand batch spec). Each its own
           codex-gated PR.
