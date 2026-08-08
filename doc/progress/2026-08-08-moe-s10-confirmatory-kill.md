# §10 confirmatory run executed — KILL; the panel stays champion everywhere

STATUS:    delivered. The preregistered protocol (orch#912) executed with zero
           live choices; the governing purged row fails 3 of 4 steps. Per
           §10.2 the answer is "keep the panel alone"; per §1 that is a
           successful outcome and this record is the deliverable. Nothing
           deployed; no production surface touched at any point.

WHAT:      doc/research/2026-08-08-moe-s10-confirmatory-kill.md — the verdict
           record. data/2026-08-08-s10-confirmatory-rows.csv (280 paired
           rows) + data/2026-08-08-s10-confirmatory-derivation.py — the
           derivation artifacts, committed per the #911 review requirement.

WHY/DIR:   The 33-date diagnostics generated the 75/25 panel/slow blend
           hypothesis (mean D +0.0204, t +0.50, recorded undetectable). The
           bt#110 emitter produced the point-in-time panel arm the same day;
           §10 ran immediately as frozen. The sign REVERSED: mean D −0.0108
           on 278 governed dates. The two-step (diagnostic generates →
           purged confirmatory decides) did exactly what it was built for.

EVIDENCE:  artifact:      emitted replay matrix (1685 dates, lane
                          wf_replay_panel, run wfreplay-2026-08-08; config
                          recorded on orch#905 BEFORE compute) ⋈ Stage −1
                          slow-momentum raw scores ⋈ fwd_20d
           prod or exp:   experiment — read-only replays over prod data
           existing data: no confirmatory result existed; the only prior
                          number was the 33-date diagnostic this run refutes
           best-known?:   yes — first execution of the frozen gate on
                          point-in-time data; supersedes the diagnostic's
                          blend read entirely
           scope:         research record + derivation artifacts. The §10
                          machinery, the emitter, and the frozen conventions
                          are unchanged.

           Governed row (purged, n=278, n_eff=13.9):
             1 measurability sd(D,ddof=1)=0.0558 < bound 0.0666  PASS
             2 effect        mean D=−0.0108, adj t=−0.72,
                             CI95=[−0.0250,+0.0024]              FAIL
             3 economics     beta=+3115 bps/IC (adj t +3.17, transfer CLEARS);
                             implied −33.7 bps vs 10 bps          FAIL
             4 level guard   +0.0323 vs +0.0431                   FAIL
           Full-sample row (280 dates) matches in shape. Purge: 2 dates
           contaminated (replay ends 2026-05-07; hypothesis window starts
           2026-05-04).

           Subsidiary findings: the §4.3 transfer now CLEARS at the frozen
           convention (adj t +3.17 at 278 dates) — future challengers inherit
           a working economics gate; the replay panel is a stronger champion
           (+0.0431) than the served sample suggested (+0.0223). Also
           resolved: "rb" is NOT a model — rb_mom's components are
           panel+clf+slow-momentum [VERIFIED — config read]; no separate
           mean-reversion scorer exists to replay.

TESTS:     the derivation script is committed and re-runnable; steps 1/2/4
           recompute from the committed CSV alone, step 3 from its r_top3
           column. The emitter itself carries 5 tests (bt#110, merged).

NEXT:      clf (fwd60) is the one unexplored challenger: per §10.4 it needs
           its own diagnostic → dated amendment naming ONE primary (with the
           horizon mismatch handled in the amendment, not at run time) →
           purged confirmatory. No other MoE work remains open — the panel is
           champion everywhere, and that verdict is final for every arm
           tested tonight.
