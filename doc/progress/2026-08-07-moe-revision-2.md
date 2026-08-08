# MoE revision 3 — champion/challenger per sector, with every threshold frozen

STATUS:    DESIGN. Supersedes revision 2 in the same file, addressing both codex
           P1s, an operator architecture correction, a second codex
           CHANGES_REQUESTED pass on revision 3 (2 more P1s), a third codex
           pass (1 HIGH: Stage 0' was not a runnable positive control for the
           champion/challenger path — now fully preregistered), and a fourth
           codex pass (1 HIGH: the recovery/calibration kill rows were
           tautological — estimand now defined through the frozen routed
           policy; detection + null discipline are the decision rows).
           Nothing deployed. Stages -1 and 0' run on data that already exists.

WHAT:      (a) Architecture replaced: experts are DIFFERENT MODEL FAMILIES
           (fast momentum / slow momentum / mean reversion / classifier), not
           additive corrections on one base. Panel is the per-sector champion by
           default; a challenger takes a sector only by clearing a frozen gate.
           (b) Every Stage -1 threshold frozen numerically BEFORE it runs, and
           the replay is now required to be walk-forward/point-in-time, not
           today's artifacts scored retroactively over 2024-2026.
           (c) Stage 0' rebuilt as a preregistered positive control for the
           ACTUAL champion/challenger selection path: a deterministic
           hash-seeded synthetic challenger score (seed list 1..200, tie rule
           frozen), an outcome perturbation TIED to that score within the
           target sector cell (rank-active, still return-unit bps as the
           primitive), the routed-vs-panel Spearman increment DELIVERED BY THE
           FROZEN ROUTING TABLE (zero for the target cell when the panel is
           kept) against the oracle increment under the known synthetic
           routing, and numeric pass/fail rules (detection >=80% at k=1.0,
           k=0 false-routing <= 8%; routed attenuation and CI coverage are
           reported descriptively with no kill weight). Injection covers BOTH partitions
           of the fold, re-applied independently after each split; fitting
           reads training rows only. Section 6 now also freezes the exact
           selection rule (sd(delta) gate + Bonferroni one-sided paired t +
           argmax) that Stage 0' exercises, and section 3 pins IC as per-date
           Spearman rank correlation.

WHY/DIR:   Three corrections, one operator and two codex passes.
           OPERATOR: revision 2's additive delta cannot express "chips use fast
           momentum, mega-cap tech uses mean reversion" -- those are different
           functional forms, not offsets. The correction form could never have
           expressed the hypothesis being tested.
           CODEX round 1 (orch#910, 2x CHANGES_REQUESTED, both P1): the MDE
           comparison target and the dIC->bps transfer were deferred, so the
           analyst could pick the threshold after seeing the result -- the kill
           condition was not falsifiable. Stage 0' froze none of the choices
           that decide whether the control measures recovery or leaks an
           outcome-shaped treatment across the split.
           CODEX round 2, on revision 3 (2026-08-08T07:15:04Z, 2 more P1):
           (i) Stage 0' injected the effect on training dates only, then asked
           for recovery on validation dates where the effect was absent --
           indistinguishable from a correctly-fitted model scoring an
           unperturbed target. (ii) the 541-date offline replay used TODAY's
           challenger artifacts scored retroactively, which is not
           point-in-time and can manufacture the very variance reduction the
           gate is supposed to detect honestly.
           CODEX round 3 (2026-08-08T07:37:08Z, 1 HIGH): Stage 0' still
           evaluated revision 2's "routed correction" -- undefined under the
           champion/challenger architecture -- and its uniform per-sector
           return shift is RANK-INERT: within-sector ranks can be unchanged,
           so the paired rank-IC routing statistic can legitimately stay at
           zero with the effect present. Its recovery language ("tracks
           injected delta", "no attenuation beyond what shrinkage predicts")
           named no statistic and no threshold. Fixed by preregistering the
           full fold-local DGP and numeric pass/fail in section 5.
           CODEX round 4 (2026-08-08T07:53:32Z, 1 HIGH): the recovery and
           calibration rows were tautological. The pipeline estimate read
           IC(c*) - IC(panel) directly on validation whether or not the
           frozen selector routed s* to c*, and the oracle was the SAME
           statistic on the SAME perturbed dates, so recovery bias was
           mechanically zero and CI coverage checked nothing -- the control
           could not expose a broken selector/router. Fixed by defining the
           pipeline estimate through the frozen routed policy (the increment
           of whatever model the table assigns to s*; identically zero when
           the panel is kept) and the oracle as the same validation increment
           under the known synthetic routing s* -> c*. The two now coincide
           IFF the selector routed correctly; since conditional on a correct
           route their gap is zero by construction, the gap carries only the
           selection event's information, so the recovery/calibration kill
           rows are withdrawn (descriptive only) and detection + null
           discipline remain the decision-bearing controls.

EVIDENCE:  artifact:      runs.alpaca.db candidate_scores(role='candidate') join
                          ticker_forward_returns.fwd_20d; per-DB coverage query
                          over RenQuant/data/runs.alpaca*.db; strategy_config
                          shadow_models inventory
           prod or exp:   prod -- the live runs DB, the live shadow lane DBs and
                          the pinned strategy config
           existing data: no power analysis, no effective-sample-size figure, no
                          positive control and no frozen threshold existed in
                          revision 1 or 2
           best-known?:   yes -- first measurement of sd(IC_t) from served
                          scores, and first per-lane coverage census. Supersedes
                          this doc's own revision-2 numbers, which used an
                          ASSUMED sd of 0.15.
           scope:         design document only. No code, config, pin or
                          production surface.

           MEASURED, live 33-date series (2026-05-04..07-10, median 71 names):
             sd(IC_t) = 0.1233     panel mean IC = +0.0223
           FROZEN ceiling: dIC = 0.05 (= 2.2x the panel's ENTIRE mean IC)
           MDE = 2.8 * sd / sqrt(n_eff):
             live 33 dates   n_eff  1.65   MDE 0.269   KILL
             full DB 541     n_eff 27.05   MDE 0.066   KILL
             need MDE<0.05   n_eff 47.7    -> 953 dates
           So the UNPAIRED comparison is dead on every history this book has.
           The gate therefore reduces to ONE measurable inequality:
             sd(paired dIC) < 0.0929 on the frozen 541-date history.

           LANE COVERAGE (why the sector x expert matrix cannot be built from
           live shadow data -- absence of data, not lack of power):
             panel 541 | clf 38 | blend 9 | momentum 4 | rb_mom 4
             momentum_fast 0 | rb_fast 0
           Those lanes activated 2026-08-02/04. The unblock is OFFLINE REPLAY of
           each challenger over the 541-date history, which needs no served
           matrix and is not blocked by orch#905.

VISIBLE CORRECTIONS in this revision:
           * revision 2 used an ASSUMED sd(IC_t) = 0.15; the measured value is
             0.1233. Direction of the conclusion is unchanged (sqrt(n_eff)
             dominates), but the assumed figure is withdrawn.
           * An earlier probe reported 4 usable dates and sd = 0.0953. That used
             "first run per date", and many runs persist ZERO candidate rows.
             Taking the run with the most candidates per date gives 33 dates.
           * An earlier statement that live history is 80 dates was the
             run_type='live' subset. runs.alpaca.db holds 541 scored dates back
             to 2024-01-02.
           * Stage 0' previously injected the synthetic effect on training
             dates only; corrected to inject identically across the ENTIRE
             fold (training + embargoed validation) while fitting still reads
             training rows only -- otherwise validation held no true effect to
             recover.
           * Stage 0's delta grid previously mixed units ("IC units" injected
             directly into a return series); corrected to an explicit
             return-unit (bps) grid, with any IC-equivalent reading derived
             from Stage -1's own frozen transfer, never the primitive.
           * Stage -1's 541-date replay previously implied scoring the full
             history with today's live challenger artifacts; corrected to
             require a walk-forward, point-in-time replay (retrain per fold or
             a verified pre-cutoff artifact), owned by
             renquant-model/renquant-backtesting -- the orchestrator consumes
             pinned output only.
           * Stage 0' previously injected a UNIFORM return shift per
             membership dimension and measured recovery by an undefined
             "routed correction"; a uniform shift is rank-inert (within-sector
             ranks unchanged), so the paired rank statistic need not move at
             all. Corrected to a score-tied injection whose cross-sectional
             shape is a preregistered synthetic challenger score, evaluated
             through the exact frozen selection rule and paired Spearman
             statistic, against an oracle truth.
           * The recovery phrases "tracks injected delta" / "no attenuation
             beyond what shrinkage predicts" are withdrawn as decision rules:
             no shrinkage estimator exists in the champion/challenger path, so
             the predicted attenuation was undefined. Replaced by the numeric
             kill thresholds in section 5.3 (two of which — recovery and
             calibration — codex round 4 later exposed as tautological; see
             the bullet below).
           * Stage 0's delta grid no longer routes through the section-4.3
             transfer beta-hat; the injection is parameterised directly by the
             target within-cell IC via the measured per-date cross-sectional
             sd of unperturbed fwd_20d. beta-hat remains in Stage 3 economics
             only.
           * Stage 0's recovery/calibration kill rows (|bias| > 0.005, CI
             coverage >= 90%) are WITHDRAWN: as previously defined the
             pipeline estimate and the oracle were the same statistic on the
             same perturbed validation data, so the bias was identically zero
             and the rows validated nothing. Routed attenuation and CI
             coverage stay as descriptive outputs; detection and null
             discipline are the decision-bearing controls.

TESTS:     none -- design only. Every figure above is reproducible from the two
           tables named under EVIDENCE; the paired sd(dIC) that decides the gate
           is Stage -1's first deliverable and is deliberately NOT asserted here.

NEXT:      Run Stage -1 as a walk-forward, point-in-time replay (owned by
           renquant-model/renquant-backtesting): replay each challenger over
           the frozen 541-date history using only artifacts trained through
           each date's fold cutoff (same cutoff rule for the panel arm),
           compute sd(dIC) per (sector, challenger) pair, and apply the frozen
           inequality sd(dIC) < 0.0929. Produce the dIC->bps transfer in the
           same pass. Blocked by nothing.

NOT DECIDED HERE:
  * Which challenger wins any sector. The routing table is selected inside each
    fold and frozen before embargoed dates; choosing now is the failure mode
    section 6 exists to prevent.
  * Universe expansion: breadth helps every date immediately, but NO expansion
    changes n_eff -- only dates do. It is also a live-system change (traded
    universe, shadow config fingerprint re-stamp, history backfill).
  * orch#905 still blocks Stages 1-4. Stages -1 and 0' deliberately do not.
