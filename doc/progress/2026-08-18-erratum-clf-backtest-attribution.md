# ERRATUM: the momentum "drag" was dilution — orch#1007's two misread contrasts

STATUS:    delivered. Docs only — one new erratum memo, five inline
           withdrawal banners in the memo it corrects. No src, no config,
           no runner, no data file, no live surface. Nothing re-run: the
           correction is a re-DERIVATION, and every arithmetic value in
           orch#1007 reproduced exactly.

WHAT:      orch#1007 merged before its double-audit finished. The audit
           (required by the LONG ledger for any capital-adjacent
           conclusion) overturns two of its readings while leaving its
           frozen verdict and all of its arithmetic intact.

           WITHDRAWN #1 — **"the momentum leg drags production below
           solo-xgb."** `A − D = −0.03073` is not the momentum leg's
           contribution. orch#1007 §3 item 3 correctly says an UNWEIGHTED
           z-sum dilutes each leg when a leg is added, and then reads the
           same artefact as an attribution when it shows up in `A − D`.
           Under the null "momentum carries ZERO information" the
           mechanically predicted `A − D` is **−0.03565** at
           ρ(xgb,mom)=0 — MORE negative than the −0.03073 measured;
           dilution-corrected the contrast is **+0.00424, NW t +0.139**.
           It also collapses **86%** under the run's own winsorized ±0.50
           column (−0.03073 → −0.00430) — a column the runner computed for
           every arm and the memo reported only for `B − A`. And it was
           never established: NW t −0.810 vs crit 1.703, 9/28 blocks
           positive, 0/28 LOBO subsets establish `D > A`.
           NET: the momentum leg's own information is **unidentifiable**
           from this run in either direction. ρ(xgb,mom) was not persisted
           and no weighted/orthogonalized arm was run.

           WITHDRAWN #2 (opposite direction) — **"the certification does
           not reproduce."** There is no shrinkage. 84% of model#76's
           certified +0.06873 comes from the 645 dates AFTER orch#1007's
           corpus ends (2023-09-30..2026-04-28: +0.19372). Restricted to
           the matched window, model#76's OWN instrument gives **+0.01554,
           CI90 [−0.04481, +0.07117]** — it would have returned
           INCONCLUSIVE. orch#1007's +0.02843 is therefore LARGER than the
           certification's same-window number, not "~41% of the
           magnitude". The clf leg is not impeached by that backtest.
           What survives: +0.0687 is a recent-regime number, and its
           published CI used block length = label horizon (60 = 60) — the
           geometry this program retracted in
           renquant-model doc/research/2026-07-30-erratum-block-length-equals-horizon.md.

           DOWNGRADED — orch#1007 §4a graded the harness control "PASSES
           (this is the strong one)". Structural checks do pass exactly
           (340/340 refit cutoffs, 340/340 panel-usable counts, frozen
           geometry). The LEVEL does not: `D_solo = +0.12171` here vs the
           sibling committed vol-switch run's unconditional `+0.13919` on
           the identical corpus = **−12.56%**, r = 0.829. §4a attributes
           it to the declared ~1.3% momentum-universe restriction; a
           random 1.3% restriction moves the level −0.29%, **43× short**.
           Unexplained. Arm LEVELS from this harness carry an unquantified
           offset; the paired contrasts (offset cancels) are the reads to
           trust — which is why the §1 verdict is unaffected.

           SURVIVES UNCHANGED: `B_3leg − A_prod = +0.05863` SD/60d, NW
           t=+2.122 (crit 1.703), CI90 lower +0.01157, bootstrap
           q05=+0.01061, 28 blocks / ESS 17.98 / 21 positive, bar
           inherited from model#75. And the descriptive ordering
           `{B, C} > D > A` in all four available reads.

           CONSEQUENCE: **no production configuration change is supported
           by orch#1007.** Neither "drop the momentum leg" nor "add the
           clf leg" has evidence behind it after this correction.

WHY/DIR:   Guards the bull-alpha program's decision surface, and it is a
           CORRECTION of my own work, not a new line. The operator's
           2026-08-18 policy ("用backtest代替所有数据积累") makes backtests
           the evidence that collapses accumulation clocks — which raises,
           not lowers, the bar on what a backtest is allowed to conclude.
           orch#1007 is the first run under that policy and it merged
           before its double-audit landed; two of its readings then failed
           the audit. Left standing, they point at a live configuration
           change (drop the momentum leg / add the clf leg) that nothing
           supports, on the SERVED blend, in the direction the operator is
           actively pushing to ship. Withdrawing them keeps the program's
           speed without letting speed decide capital. It also converts a
           one-off mistake into a reusable bound: on an UNWEIGHTED z-sum,
           arms with different leg-counts are not comparable as leg
           attributions — which constrains every future MoE/blend
           experiment (G-I AC5 weighting is exactly the change that would
           lift the bound). Direction unchanged: B−A stands, the vol-window
           shadow lane keeps accruing, and the next momentum verdict needs
           its own prereg rather than a diagnostic borrowed from this run.

EVIDENCE:
  artifact:      doc/research/2026-08-18-erratum-clf-backtest-attribution.md
                 (new); five withdrawal banners in
                 doc/research/2026-08-18-served-blend-plus-clf-backtest.md
                 (header + §1a + §3 + §4a + §4b)
  prod or exp:   **exp** — docs-only worktree off main `58cd53a6`. No
                 code, no config, no data file, no runner, no live
                 surface, no deploy. Nothing was re-executed.
  existing data: re-read by me from the already-committed outputs of
                 orch#1007 and orch#1003, no new run:
                 - `A_prod` per-date +0.08925514, w50 +0.01514608;
                   `D_solo` per-date +0.12170871, w50 +0.01944492; block
                   means +0.08865760 / +0.11938510 → `A−D` block
                   −0.03072750, winsorized −0.00429884 (86% collapse)
                   [VERIFIED — doc/research/data/2026-08-18-served-blend-plus-clf-results.json]
                 - vol-switch `positive_control.unconditional_primary_mean_spread`
                   = +0.13919291 vs `D_solo` +0.12170871 → −12.56%
                   [VERIFIED — doc/research/data/2026-08-18-vol-switch-results.json]
                 The dilution null (−0.03565), the dilution-corrected
                 contrast (+0.00424, t +0.139), the window decomposition
                 of model#76 (+0.06873 / +0.01554 / +0.19372) and the
                 −0.29% random-restriction reference are [DERIVED] by the
                 independent audit, which first reproduced model#76's
                 published CI to all digits. I did not re-run those; they
                 are tagged as second-derivation in the erratum, not as
                 my own measurements.
  best-known?:   yes for what it claims — it withdraws claims rather than
                 making new ones. The two numbers I assert as VERIFIED I
                 read myself from committed artifacts. The audit's
                 [DERIVED] figures are carried as attributed
                 second-derivations; a third derivation would strengthen
                 the dilution constant but would not change the verdict,
                 which already follows from the winsorized collapse and
                 the failed significance alone.
  scope:        docs. Does not touch orch#1007's numbers, runner, tests or
                data files — those reproduced exactly and stay as the
                record of what was computed.

NEXT:      Not an automatic step. Three things this makes concrete, none
           of them a deploy:
           1. The −12.56% baseline gap needs an explanation before any
              arm LEVEL from this harness is cited again.
           2. Any momentum verdict needs its own preregistration with
              ρ(xgb,mom) persisted and a weighted/orthogonalized arm —
              `A − D` was post-hoc on a run frozen for `B − A`.
           3. GOAL-7 Arm B (the only arm that may CERTIFY the momentum
              model) projects eligibility **2027-05-24** from the live
              ledger's observed cadence [VERIFIED — ops/renquant104/
              goal7_arm_b_accrual_probe.py against the live ledger,
              2026-08-18: 3 BULL_CALM cutoffs, 0.154/day, primary share
              1.0]. Under the operator's 2026-08-18 backtest-replaces-
              accumulation policy that clock is meant to be collapsed by a
              backtest — and this erratum says orch#1007 is not that
              backtest.

REVIEW:    codex (haorensjtu-dev). Design-review fixes on this one are
           mine personally: the withdrawn claim is my own.
