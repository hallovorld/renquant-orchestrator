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
           (estimand + pinned champion comparator, coverage minima, Holm FWER ≤ 5%
           across the candidate×cell family, ΔIC ≥ +0.02 minimum effect, no-decision
           ⇒ champion, two-stage assignment/confirmation separation, demotion
           ratchet, honest downside guarantee — added on codex review 2026-08-17),
           serving via the existing blend/regime_router composition machinery,
           measurable AC1–AC6, and an explicit honesty ledger.

WHY/DIR:   Operator-directed 2026-08-17 ("自己set goal和loop来drive这个moe模型！设计
           要发pr被approve之后再开始impl"), consolidating the 08-13..08-17 decisions:
           keep the blend; MoE = model-list filling a (sector×regime) table; no new
           data pipelines or training architectures ("成本太大"); fast/slow momentum
           separate; strategy names not algorithm names; candidate bar = the momentum
           bar (simple sort + survived our kill machine, transfer t≈3.17).

EVIDENCE:
  artifact:      `doc/design/2026-08-17-gi-moe-sector-regime-routing.md` + this doc.
                 No code, no config, no production/live path.
  prod or exp:   neither — design only; no computation run, no live change.
  existing data: [VERIFIED/DERIVED] the 2026-08-13 sample-geometry groundwork — regime
                 episodes over the 125-fold WF set (BULL_VOLATILE 17 / BEAR 8 / CHOPPY 5
                 / BULL_CALM 3; fold-granularity caveat stated) → 33/44 cells
                 pre-emptively hard-wired; 11 GICS sectors from data/ticker_sectors.json
                 (304 tickers). [VERIFIED] blend + regime_router are registered
                 inference-only composition kinds in the pipeline model registry; the
                 momentum ledger emitter (weekly, hash-chained) is the live pattern the
                 candidate emitters clone — its home is the model factory
                 (`renquant-model` `src/renquant_model_momentum/{train,ledger}.py`
                 [VERIFIED — read 2026-08-17]), which fixes emitter ownership per
                 RENQUANT_REPOS.md; GOAL-8 momentum transfer t≈3.17; DGTW tail
                 skill t=2.92 (the tail_q90_20d rationale); fundmom previously tested
                 and REJECTED (kill list).
  best-known?:   yes — the design's degrees of freedom are bounded by the measured
                 power map (effective-sample-BEFORE-decision-rule, the #975/#976
                 lesson) and by the frozen §5b assignment rule; hard-wired cells are
                 byte-identical to today by construction, tested cells carry a
                 bounded probabilistic downside (FWER ≤ 5%/batch + prospective
                 confirmation + demotion ratchet — the earlier blanket "worst case =
                 today by construction" claim was over-broad and is corrected in
                 §5b step 9); candidates are restricted to zero-marginal-cost
                 builds and must clear a cheap IC screen BEFORE any prereg cathedral;
                 an incremental-information gate (|ρ|<0.7) blocks re-skinned
                 duplicates; the kill list is carried forward explicitly.
  scope:         "a design for the MoE v1 routing table (NOT executed, NOT
                 implemented). Authorizes no code, no config, no live change, no data
                 spend. Implementation is a separate phase of codex-gated PRs that
                 starts only after this design is approved; deploys remain
                 operator-gated. Does NOT claim to restore bull buying, learn routing,
                 weight components (AC5 deferred), or close the blend-level WF-gating
                 gap (deferred per #982)."

TESTS:     none — doc-only PR.

NEXT:      codex review (design-review fixes personal) → on APPROVAL, impl phase:
           (1) emitter clones high52w/lowbeta/quality_gp + tail_q90_20d recipe;
           (2) cheap IC screen with recorded kill/advance verdicts; (3) router config
           schema + frozen hard-wire list + alias registry; (4) MoE shadow lane;
           (5) AC4 replay attribution. Each its own codex-gated PR.
