# 2026-08-05 — GOAL-6: two thirds of a P0 was already fixed and nobody knew

## Re-measuring orch#726, four days on

orch#726 filed three defects against the serving artifacts on 2026-08-01.
Re-measured today `[VERIFIED — `wf_corpus_coverage.py` plus a direct read of the
prod artifact and the pinned config]`:

| claim (08-01) | today |
|---|---|
| the prod scorer's WF manifest points at `/tmp` (gone) | **RESOLVED** — the manifest resolves, 43 folds |
| its override rollback points at `/tmp` (gone) | **RESOLVED** — no `/tmp` path survives anywhere in the artifact |
| the clf lane has no gate stamp at all | **UNCHANGED** |

### But the prod artifact is NOT clean — my first version of this probe said it was

`[codex on orch#820, reproduced by the corrected probe]` The prod stamp
references **59** paths. **One does not exist**:

```
metadata.wf_gate_metadata.config_parity.candidate_artifact
  → …/artifacts/prod/panel-ltr.alpha158_fund.weekly_20260802T170002Z.staging.json
```

So the *dangling-reference* condition orch#726 is about **is still present on the
prod artifact** — just not under `/tmp`. My first probe enumerated `/tmp` strings
plus two manifest keys and therefore reported `HAS_CHECKABLE_CLAIM`, which is
exactly the enumerate-instead-of-invert error this project keeps catching. It now
walks **every** path-shaped string in the stamp.

Corrected reading of orch#726: the two `/tmp` pointers are gone; the class of
defect they were instances of is not.

**Nobody noticed for four days**, because checking meant reading two artifacts by
hand. A three-claim P0 sitting two-thirds fixed is exactly how a reader learns to
discount P0s.

## What also moved, and reframes orch#788

The clf corpus is no longer absent `[VERIFIED — read from disk]`:

```
artifacts/walkforward_clf_top_decile_fwd60_v1/
  corpus_manifest.json   n_windows = 43   recipe_id = walkforward_only_v1
  RUN_CLAIM.json         status = built_unscored
                         manifest_sha256 = a8a41ff4021e8535…
```

So the blocker chain is now explicit: **score the 43 built windows → produce a
stamp → only then say anything about the clf lane's OOS behaviour.** orch#788's
title ("has no OOS corpus") is a generation out of date; both issues have been
commented with the measurement.

## What lands

`ops/renquant104/serving_certification_probe.py` — one question per serving
artifact: **does it make a walk-forward claim that can be checked at all?**

Four states, and the distinctions are the point:

- `HAS_CHECKABLE_CLAIM` — a stamp whose referenced paths resolve;
- `CLAIM_POINTS_AT_A_MISSING_PATH` — **worse than no claim**, because it reads as
  certified. That was orch#726's first two halves;
- `NO_GATE_STAMP` — absent from **both** the canonical
  `metadata.wf_gate_metadata` and the legacy top-level key (an artifact carrying
  only the legacy key *does* make a claim, and calling it stampless would be the
  wrong-object error one level in — tested);
- `ARTIFACT_UNREADABLE` — **not** an absent claim, its own state.

**It deliberately does not judge the claim.** Fold counts are counts of manifest
rows and say nothing about leakage or quality; conflating "a claim exists" with
"the claim is good" is what let one lane's 43 folds read as coverage for a lane
with zero. A test asserts the output says so.

Two more states, added in review because the first version blessed things it
should not have `[codex on orch#820]`:

- `CLAIM_REFERENCES_NO_PATH` — a stamp naming nothing cannot be checked, whatever
  else it says. The first version returned `HAS_CHECKABLE_CLAIM` for a legacy-key
  stamp with no paths at all;
- `STAMP_MALFORMED` — a container that is present but the wrong shape. Collapsing
  that to "no stamp" reports a broken artifact as an honestly uncertified one,
  and `wf_corpus_coverage.py` / `gate_stamp_parity.py` already fail closed here.

Run against the live serving set: prod **`CLAIM_POINTS_AT_A_MISSING_PATH`**
(1 of 59 referenced paths), clf `NO_GATE_STAMP`, exit 1.

Suites: 15 tests, one bound to the live serving set · 5688 passed, 2 skipped `[VERIFIED — measured]`.
