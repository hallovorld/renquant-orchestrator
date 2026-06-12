# Decision Record — Engineering (#108) Before Model Research (#106)

**Date:** 2026-06-12 · **Decider:** operator · **Status:** ACTIVE

## Decision
Model evidence is currently untrustworthy BECAUSE of engineering quality —
therefore the #108 program executes FIRST; #106 model-capability work is
BLOCKED until the evidence substrate is green.

## Supporting evidence (this week)
Same-input scoring differed **8.6 IC points** between pipelines (−0.0054 vs −0.0915,
unresolved = bug #1); DOE headline was winner-picked (0.203 vs full-run mean
+0.0507); artifacts lacked provenance (no dataset hash, no env hash); panel
drifted untracked; breadth claims contradicted by the internal experiment logs E5/E17/E34/E45 (each measured IC degradation on expansion); those experiments additionally lack full provenance, which is itself part of this decision's rationale.

## Unblocking milestones for #106 (each makes model evidence trustworthy)
1. Week-0 disaster guards (G1 broker GTC stops, G2 adapter breaker).
2. DRPH + golden corpus green (experiments become reproducible).
3. Provenance stamps complete: dataset_sha256 + config fingerprint + pin
   digest + env hash in every run fingerprint.
4. ArtifactResolver + census CI (numbers can be trusted as measured).
Then #106 items run in order (cross-stock A/B with DSR/PBO per #109 errata,
scale sweep, etc.), each gated by the WF gate.

## What continues regardless
WS-2 PIT retrains already in flight (model #2 training) finish their gate
retake — they are evidence ABOUT the current model, not new model research;
daily ops, audits, and reviews unchanged.
