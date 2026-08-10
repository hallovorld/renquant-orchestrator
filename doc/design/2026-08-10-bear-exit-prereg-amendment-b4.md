# BEAR-exit prereg amendment B4 — the production regime model is the GMM (naming correction)

STATUS: FREEZE AMENDMENT to doc/design/2026-08-08-bear-exit-prereg.md,
per that prereg's own amendment instrument (a new dated document; the
frozen original is not edited). Scope: ONE naming correction with
evidence; nothing else in the freeze changes. orch#962 blocker B4.

## The defect

The frozen text says the regime series comes from "the production HMM."
Production does not load an HMM: the pinned config loads a legacy GMM
(`prod/spy-gmm-regime.json`) [VERIFIED — orch#962's derivation, config
path read from the pinned strategy-104 checkout].

## The evidence that the freeze MEANT the production GMM

* GMM argmax over 2017-01-01..2026-08-07 yields **75 BEAR days / 5
  episodes** — reproducing the prereg's own §3 planning estimate
  ("~77 days / ~4 episodes"), so the reconnaissance behind the frozen
  numbers was evidently run on the GMM [VERIFIED — orch#962 committed
  derivation + CSVs, verifier exit 0].
* The only on-machine HMM yields **211 BEAR days / 17 episodes** —
  incompatible with the frozen planning numbers.

## The correction (binding once this merges)

Everywhere the frozen prereg says "production HMM", read: **"the
production regime model — the pinned GMM at `prod/spy-gmm-regime.json`,
loaded exactly as the production pipeline loads it."** The episode
inventory committed in orch#962 (75 days / 5 episodes, per-row verified)
is the canonical realization of the frozen §3 window under this
correction.

## Explicitly NOT amended

* Blocker B3 (whether the frozen 2017-2026 window narrows to the
  sim-artifact-reachable span) is an OPERATOR ruling — untouched here.
* All arms, placebo counts, thresholds, and gates stay frozen as
  written. This amendment changes which MODEL the words point at, not
  any number.
