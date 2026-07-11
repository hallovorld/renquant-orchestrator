# model-identity regression tripwire — #484 fix C

STATUS:   done (new module, DARK by default; wire-ready, no scheduled job invokes it).
WHAT:     `model_identity_tripwire` (sibling of the #480 outage monitor, same headline
          vocabulary) compares the latest run bundle's `artifact_hashes.panel` against the
          previous session's bundle and the #477 deployment manifest
          (`~/.renquant/deploy/deployment-manifest.json`) plus an optional promotions
          ledger. Identity unchanged, or changed-with-a-pin-advance/promotion, is quiet
          INFO; identity changed with NO pin advance and NO promotion (the 06-25 shape)
          pages `RENQUANT-104 OUTAGE MODEL-IDENTITY <date>` at priority 5, exit 2. A
          supporting check compares the manifest's generation against the durable
          expected-generation record and adds a DEGRADED contribution on stale/replayed/
          torn state. CLI: `renquant-orchestrator identity-tripwire --bundle-dir …`.
WHY/DIR:  orchestrator#484 (ZM/NFLX forensics) found the prod panel artifact silently
          regressed 06-21 → 05-18 between the 06-25/06-26 sessions and served a
          39-45-day-old model for 5 sessions, unalerted — nothing existing noticed a
          DIFFERENT model was serving. This closes that detection gap the same way #480
          closed the funnel/data-availability alerting gap.
EVIDENCE: `tests/test_model_identity_tripwire.py` — 20/20 passed `[VERIFIED]`: the 06-25
          regression shape alerts; pin-advance and promotion-ledger cases pass quiet;
          missing-previous-bundle / missing-panel-hash / missing-or-invalid-manifest all
          fail-soft; generation-mismatch note; bundle discovery; CLI exit codes. Full repo
          suite: 3653 passed (2 pre-existing environment failures — shadow-ab
          portable-timeout, twin-parity manifest-current — fail identically on clean
          origin/main in this environment).
NEXT:     wiring into a scheduled job is a separate, ask-first machine landing (same
          posture as #480). Fix D (fill-truth in the runs DB, pipeline-owned) ships as a
          separate renquant-pipeline PR.
