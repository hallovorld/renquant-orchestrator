# Served blend + clf leg — paired backtest: B beats A, but by dilution

STATUS:    delivered. Runner + its four outputs + results memo. Research
           only — no src change, no config, no live surface, no production
           path touched. Executed under the operator's 2026-08-18 policy
           ("用backtest代替所有数据积累" — backtests replace
           evidence-accumulation waits). NOT a preregistered confirmatory
           and NOT a live shadow readout; nothing here authorizes a deploy.

WHAT:      Answers the deployment-gating question — on the SERVED
           construction, does adding the top-decile classifier leg beat
           what production serves today? Four arms on one common per-date
           universe, per-date unweighted cross-sectional z-sum (the served
           `blend_scorer.BlendPanelScorer.score` contract, ddof=0,
           NaN-propagating):
             A_prod  z(xgb)+z(mom)          — today's served blend
             B_3leg  z(xgb)+z(mom)+z(clf)   — the candidate
             C_2leg  z(xgb)+z(clf)          — model#76's certified arm
             D_solo  z(xgb)                 — model#76's baseline

           VERDICT (frozen primary: paired per-date B−A over the 28
           complete 60-td blocks of 2017-01-03..2023-09-29, 340 weekly
           cross-sections): **BEATS** — block mean **+0.05863** SD/60d,
           NW(1) t=+2.122 (crit 1.703) CI90 lower +0.01157 AND stationary
           bootstrap q05=+0.01061 (q95 +0.10596), no disagreement,
           winsorized ±0.50 SD difference +0.01107 ≥ 0. Guards counted
           BEFORE the verdict: 28 blocks ≥ 15, ρ̂₁=+0.218, ESS=17.98 ≥ 6,
           21/28 blocks positive. Bar = CI90 lower bound > 0, INHERITED
           verbatim from model#75's frozen rule (the rule model#76
           passed) — not invented and not tuned here.

           Recorded because it changes how the verdict should be read:
           **A_prod is the WORST of the four arms** (+0.08926 vs D_solo
           +0.12171, C_2leg +0.15420, B_3leg +0.14928). Diagnostic
           decomposition on the same 28 blocks: the clf leg's OWN
           contribution C−D = +0.02843 does NOT clear the bar (boot q05
           −0.0058); B−D = +0.02790 does not either; the momentum leg's
           own contribution A−D = **−0.03073** (32% positive blocks); and
           C−B = +0.00053, i.e. once the clf leg is present the momentum
           leg contributes ~nothing. Because the served scorer is an
           UNWEIGHTED z-sum, a third leg cuts each existing leg's share
           from ½ to ⅓ — so B−A sums "clf adds signal" and "momentum's
           drag gets diluted" and this design cannot separate them. The
           honest line: the candidate beats what is served, but the
           cleanest reading of why is that the momentum leg is not
           earning its half of the served blend.

           Computability finding (asked first): the served momentum
           ledger holds **3 rows**, genesis cutoff 2026-08-02 — ZERO
           coverage inside the corpus. That is a serving-surface fact, not
           a data limit: `momentum_residual_v0` has no fitted state, so
           the leg is recomputed per scoring date through the owning
           library (`renquant_model_momentum.train_momentum_artifact`,
           pure over readers) at `params_v0()` — the recipe the served
           config pins. All four arms are computable on the full primary
           corpus; nothing was fabricated and no ledger row extrapolated.
           The runner fails closed if the ledger ever does cover the
           corpus, so the rationale cannot go stale silently.

WHY/DIR:   The clf leg has sat shadow-only since 2026-07-28 on the
           strength of model#76's +0.0687 certification, which was
           measured against SOLO-XGB — never against the blend production
           actually serves (that blend became z(xgb)+z(mom) at orch#777).
           Nobody had measured the deployment-relevant contrast. Under the
           operator's backtest-over-waiting policy this replaces waiting
           for shadow accumulation. It also produces the FIRST performance
           number on the served momentum leg: orch#777 §"FROZEN S1
           acceptance" is explicit that S1 measures serving reliability
           only and that "No performance readout happens at S1" — so the
           −0.031 here is a flag that GOAL-8's S2 comparison matters, not
           a result that pre-empts it.

EVIDENCE:
  artifact:      doc/research/data/2026-08-18-served-blend-plus-clf-results.json
                 + …-series.csv + …-blocks.csv + …-refit-ledger.json
                 (written by the run); memo
                 doc/research/2026-08-18-served-blend-plus-clf-backtest.md;
                 runner doc/research/data/2026-08-18-served-blend-plus-clf-derivation.py;
                 tests/test_served_blend_clf_runner.py (42 tests)
  prod or exp:   **exp** — isolated worktree; run executed at main
                 `0a48d13f`, branch rebased onto main `58cd53a6` (both
                 reused runners are byte-identical at the two commits —
                 vol-switch `e6002a85…`, tail_q90 `df5c1d66…` — so the
                 rebase does not touch the run's provenance); all inputs
                 READ-ONLY (panel parquet `02b611cd…5fa4d041`, served
                 artifact `6461b827…ecc546d15` fp sha256:f8fb2259b2bf1537,
                 clf shadow artifact `1e644354…` fp sha256:1d8f167f…,
                 pinned served config `343328e3…`, momentum ledger
                 `3734b1b5…`, sector map `ec26bb1e…`, SPY store
                 `4b79cdd4…`, production-trainer helpers imported
                 read-only); wrote ONLY doc/research/data/ inside the
                 worktree (G13); xgboost 2.1.4; no production path, no
                 live tree, no deploy.
  existing data: model#76's certification (renquant-model
                 doc/research/2026-07-26-blend-confirmatory-v2-results.md)
                 +0.0687 CI90 [+0.0156,+0.1269] for C vs D — this harness
                 measures that SAME arm pair at +0.02843, CI90 lower
                 −0.0058/−0.0072, NOT DISTINGUISHABLE. Same sign, ~41% of
                 magnitude, intervals overlap on [+0.0156,+0.0616], so no
                 contradiction — but it did NOT land near +0.0687 and that
                 is reported as a failed-to-reproduce cross-check, not
                 dressed up as a passed positive control. The two
                 instruments genuinely differ (model#76: 10-seed-averaged
                 placebo-differenced clean TOP-10 spread over 5 purged
                 folds; here: DGTW-adjusted TOP-DECILE spread on an
                 expanding quarterly ladder) and that was labelled in the
                 runner BEFORE the run.
                 The HARNESS control PASSES separately and is the strong
                 one: vs the committed vol-switch run (orch#1003) over the
                 identical corpus/grid/estimand/recipe — frozen geometry
                 1,697 td / 821 ON days / 28 blocks / 340 weekly all EXACT;
                 refit cutoff selected identical on 340/340 dates;
                 panel-usable names identical on 340/340 dates; solo-xgb
                 level +0.12171 (momentum-restricted universe) vs its
                 committed +0.13919 (full panel universe), per-date
                 Pearson r=0.829. Gap attributed to the declared universe
                 restriction PLUS input-store vintage (panel + SPY digests
                 differ between runs; value-level identity NOT verified —
                 no cleaner attribution is claimed).
  best-known?:   B_3leg is not the best arm measured — C_2leg (+0.15420)
                 edges it (+0.14928). That is a diagnostic read of this
                 backtest, NOT a preregistered "drop the momentum leg"
                 test; acting on it would be selecting an arm after seeing
                 results, and the memo says so.
  scope:         "this is doc/research/data/2026-08-18-served-blend-plus-clf-results.json,
                 exp, vs existing best model#76 C−D = +0.0687/60d
                 (certified) which this harness reproduces only as
                 +0.0284, not significant"

DEVIATIONS / HONESTY:
  - The FIRST execution aborted on the runner's OWN G10 guard at scoring
    date 2018-01-23: I had written the momentum PIT assertion backwards
    (`nominal ≤ measured`), but the measured cutoff lands on or BEFORE the
    nominal bound when that bound is a holiday (nominal 2017-12-25
    Christmas → measured 2017-12-22). Corrected to the chain the
    artifact's contract defines, `measured ≤ nominal < scoring date`, and
    re-run. NO output file was written by the aborted run and NO statistic
    was computed or seen before the fix; the fix touched a guard direction
    in this runner's new code, never a frozen quantity, arm, statistic or
    bar. Every number shipped comes from the single completed run.
  - NO V2-style byte-identity-vs-origin/main guard. The vol-switch
    freeze-then-review-then-run protocol governs preregistered one-shot
    confirmatories; this is a backtest whose runner, outputs and memo land
    in ONE PR, so that guard is deliberately absent and its absence is
    declared in the runner docstring rather than faked. The one-shot
    marker (G1) IS kept, so the committed results cannot be silently
    overwritten.
  - Both legs are trained on the production-gated (sentiment
    trained_zeroing) frame for parity; the deployed clf shadow artifact
    carries no such stamp. Declared deviation from that artifact's own
    preprocessing.
  - Survivorship (292-name survivor panel + today's OHLCV store), a
    current-vintage sector map read for historical dates, and a corpus
    ending 2023-09-29 all stand as declared, uncorrected caveats. The
    ON-state sub-read (SPY vol20 > 0.135) is +0.06253 over 19 blocks and
    would be NOT DISTINGUISHABLE on its own; OFF is larger (+0.09592), so
    the effect is NOT concentrated in the ON state.

NEXT:      Operator/design decision, not an automatic step. This supports
           putting B_3leg — and, given the decomposition, the prior
           question of whether the momentum leg is earning its place —
           into the normal design/shadow path. GOAL-8's own S2 comparison
           (frozen before unblinding) is the thing that answers it on live
           data; a PIT-universe rerun is what would answer the
           survivorship objection. No production change is authorized by
           this PR.
