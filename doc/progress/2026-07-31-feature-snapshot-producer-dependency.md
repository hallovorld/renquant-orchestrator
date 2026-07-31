# The shadow feed's blocker and "features are never persisted" are ONE blocker — DESIGN

STATUS:    design proposal under review. NOTHING is implemented — no persistence path
           is touched, no wrapper changed, no job behaviour moved.
WHAT:      doc/design/2026-07-31-feature-snapshot-producer-dependency.md — shows that
           the shadow-feed producer cannot be built until the daily run persists its
           serving feature vectors, and specifies the artefact that would do it.
           tests/test_feature_snapshot_dependency.py — 2 tests pinning that the run
           bundle carries no feature vectors TODAY, so the day one appears is visible.
WHY/DIR:   `run_shadow_serving.sh`'s second guard requires a snapshot payload that
           nothing produces. The obvious fix — point the wrapper at
           `realtime_data_plane.py --output-json` — is wrong: #647 measured that it
           emits a *reference to* a snapshot and that `build_realtime_snapshot()`
           TAKES a FeatureSnapshot as input. The module is a consumer, so satisfying
           a file-exists guard with it would be this programme's signature defect.
EVIDENCE:  n/a — this PR makes no measurement claim of its own. The counts it cites
           (~145 tickers, ~158 features) are sizing estimates, tagged as such in the
           design, and nothing here is a run result.
NEXT:      Review must settle the artefact schema before any implementation PR. Step 1
           touches the daily run's persistence path and needs its own
           behaviour-invariance argument.

## Review round 1 — a triple that identifies a rebuild, not a run

Codex: *"ticker plus cutoff and builder identity cannot establish that the persisted
vectors are the exact values consumed by a scored run."*

Correct, and it is the difference between an artefact that looks auditable and one that
is. **Two rebuilds at the same cutoff with the same builder can differ if the input data
moved underneath them** — and the whole question the artefact exists to answer is *"what
did THIS scored run see"*. The triple answers a different question.

Specified in the design rather than left to whoever implements it:

* **owning repo** — `renquant-orchestrator`. The daily run already writes
  `run_bundle.json`, `decision_trace.json`, `submitted_orders.json`; a feature snapshot
  is another receipt of the same run. Not `renquant-model` (owns scorers, not runs), not
  `renquant-artifacts` (owns trained artefacts, not per-run evidence).
* **`run_id`** — binds the snapshot to the run, which is the fix for the finding.
* **`scorer_run_binding`** — the scorer identity and config fingerprint the run loaded,
  so "consumed by a scored run" becomes checkable instead of asserted.
* **`input_fingerprint`** — sha256 over the **input** feature data, not the output. Two
  rebuilds at one cutoff differ here iff the data moved: precisely the case the triple
  could not distinguish.
* **`features_digest`** — sha256 over the payload, so the artefact is self-verifying.
* **atomic write** — `.tmp` then `os.replace()`. A partial snapshot that looks complete
  is worse than an absent one, because the downstream guard would pass on it.
* **retention/size** — ~200 KB per run, under 60 MB a year; kept with the run bundle
  under `decision_trace.json`'s retention, and a refuse-above-5 MB cap so it cannot
  quietly become an artefact nobody budgeted for.

**Stated rather than glossed:** this binds the snapshot to a run and makes the payload
self-verifying. It does **not** prove the scorer *read* those values rather than
recomputing them — that requires the scorer to consume the snapshot, which is Stage-3's
own work and is not claimed here.

Also added this progress doc, which the `progress-doc` check was failing for.

## Live-surface impact

None. One design document, one progress note, two tests that assert today's absence.
Nothing is implemented.

## Review round 2 — named is not specified

Codex: the three digest fields were *named* but not *deterministically specified*, so
**two implementations could produce different valid receipts**. That is the model#122
defect exactly — a quantity pinned by name while its construction stays open — and it
is closed the same way: in the text, before anyone writes code.

* **canonical serialisation** for both digests: UTF-8 JSON, sorted keys, no whitespace,
  `NaN`/`Inf` **rejected** rather than encoded. A snapshot holding a value JSON cannot
  represent is not a receipt of anything.
* **`features_digest`** covers the `features` object **and nothing else** — no
  `run_id`, no timestamps. Include the envelope and two runs with identical vectors
  disagree, at which point the digest can no longer answer the one question it exists
  for.
* **`input_fingerprint`** covers `(relative path, file sha256, size)` for every input
  the builder read, plus the builder config digest. **Relative**, because an absolute
  path makes two correct runs on two machines disagree. And if the builder cannot
  enumerate its reads, that is the blocker to fix first — **a fingerprint over a
  guessed input set is worse than none, because it certifies an inventory nobody
  verified.**
* **`scorer_run_binding`** is exactly two fields: `artifact_sha256` and `config_sha256`,
  taken from what the run **actually loaded**, not from what the pin file says it should
  have. The gap between those two is a defect this repo has shipped before.

**Failure behaviour, which the review also asked for and which I had left implicit.**
Four named refusals — over-cap, unserialisable, write-failed, unfingerprintable — each
recording a status and logging at ERROR, and in every case the run continues, because a
receipt is not worth a trading day.

`feature_snapshot_status` is written on **every** run including success. A status field
that appears only on failure is indistinguishable from a build that never had the
feature — the same absent-versus-zero shape found in `floor_eligible_count` this week.
