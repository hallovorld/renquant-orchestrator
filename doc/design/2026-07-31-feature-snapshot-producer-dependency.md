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

## The artefact, specified

**Round 1 review: "ticker plus cutoff and builder identity cannot establish that the
persisted vectors are the exact values consumed by a scored run."** Correct — that
triple identifies a *rebuild*, not the run. Two rebuilds with the same cutoff and
builder can differ if the input data moved underneath them, and the whole point of the
artefact is to answer "what did THIS scored run see". So the contract is specified
rather than left to the implementer:

**Owning repository: `renquant-orchestrator`.** The daily run owns its own run bundle
and already writes `run_bundle.json`, `decision_trace.json` and `submitted_orders.json`
beside it. A feature snapshot is another receipt of the same run, so it belongs where
the other receipts are. It is explicitly **not** `renquant-model` (which owns
scorers, not runs) and **not** `renquant-artifacts` (which owns trained artefacts,
not per-run evidence).

**Schema** — `feature_snapshot.json`, one object:

| field | why it is required |
|---|---|
| `schema_version` | int. Absent = refuse; this repo has been bitten by silently-migrating shapes |
| `run_id` | **binds the snapshot to the run**, not to a rebuild. Same value as `run_bundle.json`'s |
| `scorer_run_binding` | the scorer identity + config fingerprint the run actually loaded — so "the values consumed by a scored run" is checkable, not asserted |
| `feature_cutoff` | T-1 EOD as-of |
| `feature_builder_version` | builder identity |
| `input_fingerprint` | sha256 over the **input feature data** the builder read, not over its output. Two rebuilds at one cutoff differ here iff the data moved — which is exactly the case the triple could not distinguish |
| `features` | `{ticker: {name: value}}` |
| `features_digest` | sha256 over `features` canonically serialised, so the payload is self-verifying |

**Atomic write.** Same directory as the run bundle, written `feature_snapshot.json.tmp`
then `os.replace()` onto the final name. A partial snapshot that looks complete is
worse than an absent one: the guard downstream would pass on it.

**Retention and size.** ~145 tickers × ~158 features × 8 bytes ≈ **200 KB/run**, so a
year of daily runs is under 60 MB — small enough that retention is a policy choice, not
a constraint. Registered policy: keep with the run bundle under the same retention as
`decision_trace.json`, and refuse to write above **5 MB** rather than silently emitting
an artefact nobody budgeted for.

**What this still does NOT establish.** It binds the snapshot to a run and makes the
payload self-verifying. It does not prove the scorer *read* these exact values rather
than recomputing — that needs the scorer to consume the snapshot instead of the builder,
which is Stage-3's own work and is not claimed here.

### Determinism — the digests, byte for byte

Round 2 review: the three fields are *named* but not *deterministically specified*, so
"two implementations can produce different valid receipts". That is the same defect this
programme hit on model#122 — a quantity pinned by name while its construction stays
open — so it is closed the same way, in the text, before anyone writes code.

**Canonical serialisation, used for BOTH digests.** UTF-8 JSON, `sort_keys=True`,
`separators=(",", ":")` (no whitespace), floats via `repr()` round-trip, `NaN`/`Inf`
**rejected** rather than encoded — a snapshot containing a value JSON cannot represent
is not a receipt of anything. Digest = `sha256` of those bytes, lowercase hex.

**`features_digest` — exact source inventory.** The digest covers **the `features`
object and nothing else**: `{ticker: {feature_name: value}}`, both levels sorted by key,
after the run's own admission filtering. It does **not** cover `run_id`, timestamps or
any other envelope field — otherwise two runs with identical feature vectors would
disagree, and the digest could no longer answer "are these the same vectors".

**`input_fingerprint` — exact source inventory.** `sha256` over the sorted list of
`(path relative to a NAMED corpus root, sha256 of file bytes, size)` for **every input
file the feature builder read**, plus the builder's own config digest. Relative paths,
because an absolute one makes the fingerprint machine-specific and two correct runs on
two boxes would disagree. If the builder cannot enumerate its reads, **that is the
blocker to fix first** — a fingerprint over a guessed input set is worse than none,
because it certifies an inventory nobody verified.

**`scorer_run_binding` — enumerated, not descriptive.** Exactly two fields:
`artifact_sha256` (the immutable trained-artifact digest the run loaded) and
`config_sha256` (the canonical digest of the resolved strategy config). Both taken from
what the run **actually loaded**, not from what the pin file says it should have — the
gap between those two is a defect this repo has shipped before.

### Failure behaviour — loud, never silent

Also round 2: what happens when the cap or the atomic write fails. **Never a silent
drop.** In every failure the run continues — the snapshot is a receipt, and losing a
receipt must not cost a trading day — and the failure is recorded where a reader
looking for the snapshot will find it:

| failure | behaviour |
|---|---|
| serialised payload **> 5 MB** | do not write. Emit `feature_snapshot_status: REFUSED_OVER_CAP` into the run bundle with the measured byte count, and log at ERROR. The cap exists so an unbudgeted artefact cannot appear unnoticed; silently truncating would defeat it |
| `NaN`/`Inf` in `features` | do not write. `feature_snapshot_status: REFUSED_UNSERIALISABLE`, naming the first offending `(ticker, feature)` |
| atomic rename fails (disk full, permissions) | do not leave the `.tmp`. Remove it, set `feature_snapshot_status: WRITE_FAILED` with the OS error, log at ERROR |
| builder cannot enumerate its inputs | do not write a snapshot with a partial `input_fingerprint`. `feature_snapshot_status: REFUSED_UNFINGERPRINTABLE` |

**`feature_snapshot_status` is written on EVERY run, including success
(`WRITTEN`).** A status field that appears only on failure is indistinguishable from a
build that never had the feature — the absent-versus-zero shape this programme found in
`floor_eligible_count` the same week.

## The minimal ordered plan

1. **Persist the serving feature vectors** in the daily run — under the schema in
   §"The artefact, specified" below. This is the actual Stage-3 prerequisite and it
   belongs upstream of any producer.
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
