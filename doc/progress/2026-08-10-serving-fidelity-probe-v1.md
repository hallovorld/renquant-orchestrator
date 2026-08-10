# Serving-fidelity probe v1 — identity + distribution + coverage (orch#958)

STATUS:    implementation PR; read-only probe, seconds-scale; NO
           launchd install in this PR (job install = operator grant,
           named follow-up).

WHAT:      scripts/serving_fidelity_probe.py — three layers over the
           day's canonical run: L1 identity (one artifact identity per
           day; golden blend pins vs artifacts on disk incl. the
           momentum ledger-tail sha chain — the #908 silent-swap
           class); L2 distribution (frozen-score alarm at <10 distinct
           values — the documented SPOT incident class; cross-sectional
           std within [0.25, 4.0] x the trailing-20-day median std,
           v1.1: baseline conditioned on the day's active_scorer after
           the live smoke correctly alarmed on the SANCTIONED 08-04
           blend cutover scale change — first-day-after-switch skips
           with a recorded note); L3 coverage (>=30 scored, no NULL
           regimes). Exit 0/1 alert-ready; optional JSONL probe ledger.
           tests/test_serving_fidelity_probe.py: 7 controls on the real
           code path (clean PASS / wrong pin / frozen scores / low
           coverage / blown std / mixed identity / switch-day skip).

WHY/DIR:   G-F increment 1 (orch#958): the probe fleet answers "did it
           arrive", never "was it correct". v1 closes the seconds-scale
           two-thirds (identity + distribution + coverage) with alarm
           classes taken from failure modes this project has ACTUALLY
           had. v2 (daily offline re-score via the #949/#950
           reconstruction machinery) stays tracked in #958 — it needs
           the corpus-recipe feature rebuild and is not seconds-scale.

EVIDENCE:  artifact:      scripts/serving_fidelity_probe.py +
                          tests/test_serving_fidelity_probe.py
                          [VERIFIED — pytest 7 passed; live read-only
                          smoke on 2026-08-07: PASS, cs_std 1.4349 vs
                          same-scorer trailing median 1.4461 over 3
                          blend days, exit 0]
           prod or exp:   read-only tooling; the only write is an
                          optional ledger path the caller chooses
           existing data: golden config pins (s104), momentum ledger
                          chain (m221 conventions), ticker_daily_state
           best-known?:   yes — v1/v2 split stated; the switch-day skip
                          is a recorded note, not a silent pass
           scope:         probe + tests + this doc; no install, no
                          launchd, no manifest change

TESTS:     pytest tests/test_serving_fidelity_probe.py — 7 passed;
           live smoke exit 0.

NEXT:      (a) review; (b) the install grant request (launchd job after
           daily104 + alerts wiring) as its own operator batch;
           (c) v2 reconstruction probe per #958.
