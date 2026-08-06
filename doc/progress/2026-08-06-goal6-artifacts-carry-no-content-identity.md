# GOAL-6: the fix I proposed for the fingerprint collapse cannot be implemented — the digest it needs does not exist

STATUS:   delivered (docs-only finding; corrects orch#862's proposed remedy).
WHAT:     shows orch#862's proposed fix ("incorporate the candidate's content digest into the
          fingerprint") cannot be implemented — all 36 artifacts have `content_sha256 = None`, so
          there is no digest to incorporate yet.
WHY/DIR:  GOAL-6 (model capability) needs a content-identity field before any ensemble/capability
          comparison built on these artifacts can be grounded; reorders the remedy to two steps —
          stamp a digest first, then key the fingerprint on it.
EVIDENCE: across the same 36 artifacts as orch#862, `content_sha256` is `None` 36/36 (the only
          shape-ish key present, `panel_shape`, is not a digest); under the single shared
          `candidate_recipe_fingerprint`, `wf_3cut_sharpe_mean` spans +0.0524 to +1.1656 (22x)
          across 10 distinct values. `[VERIFIED — this session, scanned all 36 artifacts this
          session]`
NEXT:     stamp a content digest into the panel artifact at write time (renquant-pipeline /
          artifact-writer change), then have `candidate_recipe_fingerprint` incorporate it or be
          replaced as the admission key; bt#109 remains blocked at 0 reviews and neither step
          depends on it.

**Date:** 2026-08-06
**Lane:** GOAL-6 (model capability)

## Bottom line

orch#862 established that 36 artifacts share one `candidate_recipe_fingerprint`
and proposed the remedy:

> *"The fingerprint should incorporate the candidate artifact's own content
> digest."*

**That remedy cannot be implemented as written.** Measured across those same 36
artifacts `[VERIFIED — this session]`:

```
content_sha256 values:  36 × None
sha/digest-bearing keys actually present:  panel_shape  (not a digest)
```

**The artifacts carry no content-identity field at all.** So the fix must be
ordered: *first stamp a content digest, then let the fingerprint incorporate it.*
Proposing step two without step one would have produced a change request that the
receiving repo could not act on.

## What the artifacts DO record

Under that single fingerprint, **43 metadata fields vary**:

| field | distinct values across the 36 |
|---|---:|
| `<top>trained_date` | 16 |
| `run_at` | 16 |
| `config_parity` | 16 |
| `wf_reason` | 10 |
| **`wf_3cut_sharpe_mean`** | **10** |
| `sanity_placebo_genuine_ic` | 9 |
| **`candidate_recipe_fingerprint` — what the gate admits on** | **1** |

The spread on the gate's own performance metric, under one admission key:

```
worst   wf_3cut_sharpe_mean = +0.0524   (weekly_20260805T031912Z.staging)
best    wf_3cut_sharpe_mean = +1.1656   (weekly_20260718T110005Z.staging)
```

**A 22× spread in measured Sharpe behind a single admission identity.**

## The reframing I nearly published, and why it was wrong

When the scan first reported `distinct content_sha256: 1`, I read it as *"all 36
artifacts have the same content digest — so they are one model re-evaluated, not
36 candidates"*, which would have **narrowed orch#862 substantially** and been a
tidy story.

It was `None`, 36 times. `1 distinct value` was `1 distinct **absence**`.

This is the **seventh** time an unverified key has produced a silent `None` that
read like a measurement, and the second tonight (the first was
`recipe_hash`/`recipe_sha256`/`hash` in orch#862, which returned `None` from all
37 and nearly became *"one hash across 37 artifacts"*). What caught it this time
was checking the *value* rather than the *cardinality* — a distinct-count over a
missing field is always 1, and 1 looks like agreement.

## What this does NOT establish

- **Not that the 36 are different models**, and not that they are the same one.
  Without a content digest **neither is knowable from the artifacts** — that is
  precisely the gap.
- **Not that the Sharpe spread means the gate is admitting bad models.** The
  spread is across evaluation records whose relationship to each other is
  undetermined for the reason above.
- orch#862's core measurement stands (36 share one fingerprint;
  `candidate_artifact_used` false on 37/37). Only its **proposed remedy** is
  corrected here.

## Next

Ordered, because the second step depends on the first:

1. **Stamp a content digest into the panel artifact** at write time. Until then
   no admission key can distinguish candidates, and no ensemble or capability
   comparison built on these artifacts can be grounded.
2. *Then* have `candidate_recipe_fingerprint` incorporate it — or drop the
   fingerprint as the admission key in favour of one that includes it.

Both are `renquant-pipeline` / artifact-writer changes (repo boundary).
**bt#109 remains blocked at 0 reviews**, and neither step depends on it.
