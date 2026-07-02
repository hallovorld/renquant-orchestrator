# RS-2 lane-A timing recommendation — research PR

STATUS:   research recommendation under the delegated-decision protocol (operator NOTIFIED;
          docs only; the config PRs themselves follow the normal control plane).
REVISION: r1.
WHAT:     `doc/research/2026-07-02-rs2-lane-a-timing.md` — RS-2 deliverable (#231 §6): split
          lane A by admission semantics. A-1 (qp_cash_drag_lambda 0→0.05, un-disabling the
          solver's shipped default) + A-3 (one-share floor, artifact removal) = ENABLE NOW
          after the 10-session shadow sweep — they re-express ALREADY-admitted conviction
          (zero new-name admission; the buy-side-TC 0.09 deficit S-TC measured is exactly
          what they repair). A-2 (top_n 3→5–6) = DEFER behind D1-or-M3, whichever first.
WHY/DIR:  new measurement: the floor-clearing pool is **~80–88% thin-margin post-retrain**
          (mu within 25% of the 0.03 floor; 07-01: 15/17) — the conviction floor separates
          almost nothing, so widening the daily window multiplies exactly the OXY-class pick
          the forensics flagged, unguarded (M3 haircut unbuilt, D1 verdict unrendered). At
          top_n=6 worst case ≈ +3 thin-margin entries/day ≈ +9pp/day unvalidated exposure.
          Deployment AC unaffected: lane B carries ≥60% per POC-B's ~40–43% lane-A ceiling.
EVIDENCE: reproducible SQL (in-memo) over runs.alpaca.db full runs; POC-B ceilings; S-TC
          buy-side 0.09; OXY forensics (2026-07-01).
NEXT:     Codex review; then two config PRs (A-1 sweep harness + A-3 pipeline change) enter
          the normal review lane; A-2 waits on D1/M3 and is re-cut as its own PR then.
