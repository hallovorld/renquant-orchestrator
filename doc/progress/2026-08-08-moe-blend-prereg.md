# MoE blend prereg — one primary endpoint frozen before its data exists

STATUS:    design amendment only (§10 of the MoE design doc). Nothing runs,
           nothing deployed. Intentionally inert until orch#905 lands the
           541-date served matrix.

WHAT:      Design doc gains §10: the confirmatory blend protocol. ONE primary
           endpoint (slow momentum, rank blend w=0.25, whole book, paired ΔIC
           vs panel); a four-part pass rule (measurability → effect →
           economics → level guard) with the already-frozen conventions
           (ddof=1, n_eff-adjusted t ≥ 2.0, block-bootstrap gap ≥ H); a
           contamination rule making the 508 disjoint dates govern any
           disagreement with the full 541; and a standing two-step pattern
           (diagnostic generates → dated amendment preregisters → disjoint-
           governed confirmatory decides) that rb/clf must also follow.

WHY/DIR:   orch#911's diagnostics generated the 75/25 hypothesis but the
           diagnostic run was explicitly NOT the preregistered gate run. The
           541-date matrix does not exist yet — this is the only window in
           which the weight set and winner rule can be frozen without the
           data being able to steer them. After the matrix lands, any such
           choice is post-hoc by construction. Codex flagged exactly this
           class of defect twice on the design (thresholds choosable after
           results); this amendment closes the same hole for the blend stage.

EVIDENCE:  artifact:      doc/design/2026-08-07-moe-revision-2-power-and-membership.md
                          §10 (this PR); hypothesis source = orch#911 merged
                          diagnostics (33-date overlap)
           prod or exp:   experiment — design document only
           existing data: the design had no blend-stage prereg: C1 was
                          "equal-weight" with no weight set, no winner rule,
                          no FWER stance, no contamination handling
           best-known?:   yes — first confirmatory protocol for any MoE
                          combiner; supersedes the bare "C1" row in §7
           scope:         one design doc section + this progress doc. No code,
                          no config, no production surface.

           Key numbers carried into the freeze (all previously published in
           orch#911, none new): gate bound 0.0929 (ddof=1), ceiling 0.05,
           contamination 33/541 = 6.1%, adjusted-t convention >= 2.0.

TESTS:     none — a prose contract. Its "test" is that the confirmatory run
           can be judged entirely by reading §10.2/§10.3 with no live choices.

NEXT:      Implement the orch#905 wiring per the recon comment on that issue
           (backtesting `run_wf` served_sink + CLI flag; pipeline sink
           explicit-dir param if needed; gate output byte-identical when the
           sink is off) — the amendment stays inert until that lands.
