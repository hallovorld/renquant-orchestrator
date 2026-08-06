# GOAL-6: the content identity already exists in the artifact — the fix needs no writer change

**Date:** 2026-08-06
**Lane:** GOAL-6 (model capability)

## Correcting orch#868's remedy, in the cheaper direction

orch#868 established that these artifacts carry **no `content_sha256`**, and
concluded the fix must be ordered: *first stamp a content digest at write time,
then let the fingerprint incorporate it.* Step one is a change to the artifact
writer.

**That step is unnecessary.** The artifact already contains the model
`[VERIFIED — this session]`:

```
booster_raw_json    str, 374,432 chars
train_run_id        str, 8 chars
config_fingerprint  str, 23 chars
```

A content identity is computable from what the gate already reads.

## Measured over the 36 artifacts sharing one recipe fingerprint

| key | distinct values | discriminates? |
|---|---:|---|
| `candidate_recipe_fingerprint` (what the gate admits on) | **1** | no |
| `config_fingerprint` | **1** | no |
| **`sha256(booster_raw_json)`** | **15** | **yes** |
| **`train_run_id`** | **16** | **yes** |

And the booster digest is nearly a *function* of the performance the gate
measures — each digest maps to essentially one Sharpe:

| booster digest | n | `wf_3cut_sharpe_mean` under it |
|---|---:|---|
| `73dd849797b8377c` | 15 | `[0.6973]` |
| `cf96dfa6c5be9307` | 6 | `[0.7778]` |
| `a953fdba37494b6a` | 2 | `[0.6018]` |
| `43285f13e98f21ac` | 2 | `[0.0524, 0.6018]` |
| `4871e6689a981b62` | 1 | `[0.692]` |
| `ccd2986ae0222643` | 1 | `[0.692]` |

That is the behaviour an admission key should have: **one model, one identity**,
and the metric moves with it.

## What the one anomaly means, and why it is correct

`43285f13e98f21ac` carries **two** Sharpe values (`0.0524` and `0.6018`). That is
not a defect — it is the same booster **evaluated twice against different
windows**. A booster digest identifies the **model**, not the **evaluation**,
which is exactly the right granularity for an admission key: the gate should be
able to say *"I have seen this model before"* and still record two evaluations of it.

## Revised fix, and it is small

The gate reads the candidate artifact already. It can compute
`sha256(booster_raw_json)` in place. No writer change, no migration, no backfill
— **every artifact on disk today can be identified retroactively**, which is why
the table above was computable at all.

`train_run_id` is an even cheaper alternative (8 chars, already a string, 16
distinct). The digest is the stronger key because `train_run_id` is an assigned
label and could in principle repeat or be reused, whereas the digest is derived
from the model bytes.

## What this does NOT establish

- **Not that 15 boosters means 15 good candidates.** Discriminating is not
  ranking. Every `genuine_ic` measured in orch#862 remains far below the
  (unenforced) 0.02 bar.
- **Not that `candidate_artifact_used = false` is fixed by this.** That flag says
  the gate never scored the candidate's own booster; giving the booster an
  identity does not make the gate score it. Two separate defects.
- **Not that the recipe fingerprint should be deleted.** A recipe identity is
  useful; the finding is that it is being used for a job it cannot do.

## Next

Amend renquant-pipeline's admission key to `(recipe_fingerprint,
sha256(booster_raw_json))`, or replace it with the latter. This supersedes
orch#868's "stamp a digest first" ordering — there is nothing to stamp.
