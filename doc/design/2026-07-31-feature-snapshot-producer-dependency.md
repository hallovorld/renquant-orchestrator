# The shadow feed's blocker and "serving features are never persisted" are one blocker

**Bottom line `[本次实测 2026-07-31]`.** orch#647 concluded shadow-serving stays dead
until *"a producer that materialises and stamps a T-1 daily snapshot"* exists. Task #17
independently records that **serving feature vectors are never persisted**. These are
the same blocker seen from two ends, and nothing linked them — so the producer cannot be
built, because **the values it would stamp are discarded by the run that computes them.**

## The contract, measured

`FeatureSnapshot.from_mapping` needs exactly three keys:

```json
{ "feature_cutoff": "<T-1 EOD as-of>",
  "feature_builder_version": "<feature-builder identity>",
  "features": { "TICKER": { ...frozen T-1 values... } } }
```

`cutoff` and `builder_version` are cheap. **`features` is the whole problem.**

## Where the values go today

| | measured |
|---|---|
| keys in the daily `run_bundle.json` containing "feature" | **0** |
| `decision_trace` rows in the newest bundle | **290** |
| what those rows carry | `panel_score`, `expected_return`, `confidence`, `qp_*`, admission reasons — **the scores** |
| what they do **not** carry | the feature vector that produced each score |
| files anywhere constructing a `FeatureSnapshot` | **0** (the two matches are the *consumer* modules) |

> **The daily run builds the feature matrix, scores with it, records the scores, and
> throws the features away.** That is why #647 found a class that can be read and never
> written: there is nothing to write.

## This is the third instance of one shape tonight

1. GOAL-7's momentum runs computed per-date series and persisted **none** — so the
   dependence bar cannot be recalibrated today (model#131 fixes it going forward, and
   the 2026-07-30 run is permanently un-recalibratable).
2. GOAL-4's Phase-0 persisted its series, and **that one file** made a model-free
   dependence calibration possible.
3. Here: the serving features are computed, used, and dropped — and two independent
   investigations (#647, task #17) each hit the wall from a different side.

**The rule this repeats:** a run that persists only its *conclusions* makes every future
question about *how it got there* unanswerable, and the cost is paid by someone who
cannot tell it was ever computed.

## The minimal ordered plan

1. **Persist the serving feature vectors** in the daily run, keyed by ticker, with the
   cutoff and builder identity that produced them. This is the actual Stage-3
   prerequisite and it belongs upstream of any producer.
2. **Then** the producer is a formatting step: read step 1's artefact, emit the
   three-key payload, let `from_mapping` compute the digest.
3. Only then does `run_shadow_serving.sh`'s second guard become satisfiable.

**Explicitly not proposed:** pointing the wrapper at
`realtime_data_plane.py --output-json`. #647 already measured that it emits a
*reference to* a snapshot (`feature_snapshot_digest`), not a snapshot, and that
`build_realtime_snapshot()` **takes** a `FeatureSnapshot` as input — the module is a
consumer. Satisfying a file-exists guard with the wrong artefact is this programme's
signature defect.

**Not done here:** step 1 touches the daily run's persistence path. It needs its own
review and a behaviour-invariance argument, not a drive-by commit.

Tests: 2, pinning that the bundle carries no feature vectors today, so the day one
appears is visible.
