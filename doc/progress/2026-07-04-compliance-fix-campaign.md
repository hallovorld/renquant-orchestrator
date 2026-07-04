# Compliance fix campaign plan — progress record

STATUS:   design/decision (leader synthesis of the 4-way audit); docs only. REVISION: r1.
WHAT:     doc/design/2026-07-04-compliance-fix-campaign.md — groups A (live-behavior bugs,
          operator-visible: PatchTST mirror fix, Sunday-tournament gate, kelly fail-loud,
          canary enforcement), B (multiplicity收编 ×8 families), C (mirror-drift governance:
          pipeline = kernel authority, drift CI, staged sim-leg cutover fixing the
          gate-validates-on-frozen-code finding), D (P1/P2 waves); sequencing with wave 1
          = A2/A3/A4/B1/B2; the operator's protection contract governs every PR.
WHY/DIR:  the operator ordered the deep audit + "don't break the order-placing system";
          9 P0/72 P1/78 P2 across four memos need one sequenced, safety-governed campaign,
          not ad-hoc fixes.
EVIDENCE: pipeline#168, orch#295, orch#296, RQ#444.
NEXT:     wave-1 agents (A2 before Sunday's tournament); operator inputs pending: IGV
          strategy ownership; A1 ack.
