# GOAL-4 — 30 artifacts, 1 admission identity, 12 distinct models; nothing promoted in 15 days

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-4 (ensemble) / GOAL-6 (eval path)

## The question

GOAL-4's blocker has been stated as *"the WF gate cannot distinguish the artifacts"*,
supported by four artifacts sharing recipe fingerprint `cfdd6cb8e950da0f`. That is a
claim about the gate's **identity function**, and it had never been measured against the
learned models themselves. An ensemble needs members that **differ** and that can be
**told apart by whatever admits them**. Only the second half had been examined.

## Measured on the bytes `[本次实测 2026-07-31]`

`ops/renquant104/booster_identity_census.py`, over
`prod/panel-ltr.alpha158_fund*.json`:

```
30 artifact(s), 0 unreadable
COLLAPSE  recipe sha256:cfdd6cb8e950da0f|canonical:
          30 artifact(s) -> 12 distinct booster(s)
```

| | |
|---|---:|
| artifacts | **30** |
| distinct **recipe fingerprints** (what admission is keyed on) | **1** |
| distinct **boosters** (sha256 over `booster_raw_json`) | **12** |

**The gate's collapse factor on this corpus is 30 : 1**, hiding **12** genuinely
different trained models behind a single admission identity.

**So the ensemble premise divides cleanly.** Diversity is **not** the blocker — twelve
distinct learned models already exist in `prod/`. What is missing is **attribution**:
nothing in the admission path can name which of them produced any given result. That is
a narrower and far more tractable statement than "the ensemble cannot be evaluated".

## The promotion series — and this is the live-system part

Comparing every staged candidate's booster digest with the **served** one:

```
served booster    : 73dd849797b8377c…
staged candidates : 10  (10 distinct), 0 equal to the served booster
rollback snapshots: 17, booster changed on: ['2026-07-09', '2026-07-16']
```

- The served booster has been unchanged since **2026-07-16** — **15 days**.
- Between 2026-07-06 and 2026-07-30 the retrain produced **10 candidates with 10
  distinct boosters**, and **none of them is the served model**.

So the retrain pipeline is alive and producing genuinely new models on schedule. **The
models are being made and are not reaching production.**

## What is NOT established — stated because both readings are tempting

- **A digest mismatch means different learned models, not different behaviour.** Nothing
  is scored here. Two boosters can differ byte-wise and rank a panel almost identically;
  this tool makes no claim either way, and the scope note says so in the output.
- **"No staged candidate equals the served booster" establishes only that none was
  promoted by byte identity.** Rejection at the gate, a failed promotion job, and a
  promotion path that rewrites bytes are all consistent with it. **No reason is inferred
  here**, and the printed scope note refuses that reading explicitly.
- The `weekly_rollback_*` files are read as snapshots by their filename convention only.
  Their booster series is reported as an observation, not as proof of what prod held on
  each date.

## Where this points

The chronic-reject playbook already on the register predicts this shape. What is new is
that it is now measured **on artifact bytes** rather than inferred from logs, with a
date — **2026-07-16** — and a count — **10 candidates, 0 promoted**.

## Tests

11, aimed at how an identity census can be reassuring and wrong: a **missing** booster
yields `None` and cannot collide with an **empty** one (that collision would be this tool
committing the defect it measures); the fingerprint **source** is recorded, so canonical /
legacy / no-stamp stay distinct; a non-object root is unreadable, not an artifact; an
**empty** census exits `2`, because "no subjects" must never read as "one identity per
model"; the served artifact must be **named, never guessed**; a genuinely **promoted**
candidate is detected, or "nothing was promoted" would be unfalsifiable; and both scope
notes are asserted present, so a byte fact cannot be read as a behavioural one.
