# A shadow lane is an identity, not a list position

STATUS: complete. Monitor-side only — no live surface, no config, no artifact.

WHAT: `scorer_identity_monitor` keyed each shadow lane by its **index** in
`ranking.panel_scoring.shadow_models[]`. It now keys by the stamped artifact path.

WHY/DIR: `com.renquant.rq104-scorer-identity` is one of the 14 undispositioned failing
jobs (see `2026-08-05-triage-the-14-undispositioned-failing-jobs.md`). Its most recent
run reports **three CRITICAL "silent scorer swaps"**. The alarm is not a false
positive — a real change happened — but its description is wrong, and wrong in a way
that inflates it.

Read from the actual run bundles (`pipeline_runs.run_bundle_json`, read-only):

| run | slot 0 | slot 1 | slot 2 |
|---|---|---|---|
| `2026-07-31-live-381747dd` | `hf_patchtst_all_seed44_model.pt` | `shadow/panel-clf.top-decile.fwd60.json` | — |
| `2026-08-03-live-2499e454` | `shadow/panel-clf.top-decile.fwd60.json` | `momentum/momentum_artifact_ledger.jsonl` | — |
| `2026-08-04-live-df731314` | (same) | (same) | `momentum_fast/momentum_artifact_ledger.jsonl`, sha **None** |

The real event: **PatchTST left the shadow lineup** (retirement decided 2026-08-02)
and the **momentum lanes activated**. The list did not have its members replaced — it
had one removed and two appended, so every surviving member **shifted index**.

Keyed by index that renders as:

```
CRITICAL: shadow_models[0]: 07046963994d -> 1e644354e098 … silent scorer swap
CRITICAL: shadow_models[1]: 1e644354e098 -> 9aa2d8c9571b … silent scorer swap
CRITICAL: shadow_models[2]: (lane not st -> ?          … silent scorer swap
```

Note `1e644354e098` — the clf leg — appears as **lane 0's new value and lane 1's old
value in the same report**. Its artifact never changed. The monitor counted a silent
model twice as two swaps, and the one lane that genuinely retired
(`07046963994d` = PatchTST) is named only as a hash on the left of an arrow.

Keyed by identity the same three boundaries read as what happened: one lane retired,
one added, one new slot stamped with no hash, and the clf leg silent.

## Full path, not basename

2026-08-04 stamps `artifacts/momentum/momentum_artifact_ledger.jsonl` **and**
`artifacts/momentum_fast/momentum_artifact_ledger.jsonl` in two different slots. Their
basenames are identical. Keying on the basename would collapse them into one lane and
one would silently overwrite the other — **losing a lane is precisely the failure this
monitor exists to prevent**, so the key is the full stamped path.

A lane with no stamped path keeps its positional name
(`shadow:shadow_models[2](no stamped path)`). That is a real gap in the bundle, and
inventing a stable identity for it would hide it.

## The case that must not be lost

Identity-keying could make the monitor blind to the thing it is for: the **same path
serving a different artifact**. `test_a_lane_REPLACED_IN_PLACE_is_still_a_swap` pins
that — same path, new sha, still CRITICAL.

## A fixture that never exercised the real path

`_bundle()` stamped a shadow **hash** but no shadow **artifact_path**, so every
existing test ran the no-path fallback and none of them touched path-keyed lanes. The
fixture now stamps a realistic path, which is why two pre-existing assertions moved
from `"shadow_models[0]"` to `f"shadow:{SHADOW_PATH}"` — behaviour unchanged, coverage
gained.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| the three reported swaps are one retirement + one addition + one unstamped slot | see table | [VERIFIED — `artifact_hashes`/`artifact_paths` read from the three run bundles, `mode=ro&immutable=1`] |
| the clf leg is unchanged across the boundary | `1e644354e098` at 07-31 slot 1 and 08-03 slot 0 | [VERIFIED — same read] |
| basenames collide, full paths do not | `momentum/` vs `momentum_fast/` | [VERIFIED — same read] |
| module tests | **38 passed** (3 new) | [VERIFIED — `pytest -q tests/test_scorer_identity_monitor.py`] |
| the new tests are load-bearing | all 3 fail against the pre-change module | [VERIFIED — `git stash push src/…`, re-run: 3 failed] |
| neighbouring lane sentinels | 137 passed, 2 skipped | [VERIFIED — fleet-lane + shadow-scorer suites] |
| full suite | 5877 passed, 16 failed | [VERIFIED — `make test`; 15 are the standing host-environmental set, and the 16th is flagged below] |

**Unrelated red found while checking, NOT caused by this change:**
`tests/test_rq105_job_liveness_probe.py::test_the_LIVE_2026_08_04_session_refutes_the_stdout_reading`
asserts `rows["rq105-postclose-pairing"]["state"] == STATE_STALE_PRODUCT` against the
**live** 2026-08-04 session logs, whose state has since moved on. It fails identically
against unmodified `src` [VERIFIED — re-run on a docs-only branch]. A test pinned to
live state that keeps changing underneath it needs its own fix; raising it here rather
than letting it ride as background noise, which is the habit this whole batch is about.
