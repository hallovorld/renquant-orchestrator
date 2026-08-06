# 2026-08-05 — GOAL-4: a second date, and the reason two lanes have never produced anything

STATUS:   delivered.
WHAT:     adds a `--baseline` option to `ops/renquant104/fleet_divergence_probe.py` (4 new tests,
          30 total) so lane-vs-lane comparison is measurable before prod's daily 13:55 PT score
          exists; second measured date shows the fleet DOES disagree (blend vs blend_mom spearman
          0.61, 4/10 top-k overlap — 08-04's near-agreement was not a permanent property); and
          root-causes why 2 of 5 lanes (`shadow_blend_mom_fast`, `shadow_blend_rb_fast`) have never
          produced a score: both point at `artifacts/momentum_fast/`, which does not exist, and
          launchd has exactly one momentum training job (the slow-clock one) — the recipe exists,
          the producer job does not.
WHY/DIR:  GOAL-4 (multi-model ensemble) — gives the census line "3 of 5 lanes produced no
          separating evidence" its cause: 1 lane agreed with prod, 2 were never fed. `--baseline`
          is validated identically to the default reference (absent/empty/too-few-names all
          refuse) so a choosable reference does not become an unchecked one.
EVIDENCE: today's lane-vs-lane spearman: blend<->blend_mom 0.6123 (4/10 top-k, n=84),
          blend<->blend_rb_mom 0.8451 (6/10, n=84), blend_mom<->blend_rb_mom 0.9220 (7/10, n=85);
          `artifacts/momentum_fast/` confirmed absent from disk; `ops/launchd_manifest.json` has
          exactly 1 momentum training job (`com.renquant.momentum-train-weekly`, slow clock) while
          `params_v1_fast()` exists in the model package. `[VERIFIED — this session, probe run +
          launchd manifest + artifact directory checked this session]`
NEXT:     the actionable item is a fast-momentum producer job, filed separately (orch#845); until
          it exists, F2/F3 are two configs, two DBs, two launchd slots and zero evidence.

## Two things this round establishes

### 1. The fleet DOES disagree — when its lanes actually run

08-04 was the worrying picture: `blend_mom` picked prod's **entire top 10**
(`SAME_TOP_K_AS_PROD`, residual 1.1 % of dispersion). One date, and I said so.

Today gives a second `[VERIFIED — this session, lane-vs-lane]`:

| pair | n | spearman | top10 ∩ |
|---|---:|---:|---:|
| blend ↔ blend_mom (S1) | 84 | **0.6123** | **4/10** |
| blend ↔ blend_rb_mom (F1) | 84 | 0.8451 | 6/10 |
| blend_mom ↔ blend_rb_mom | 85 | 0.9220 | 7/10 |

So the 08-04 agreement was **not** a permanent property of `blend_mom`. Two
dates is still two dates — this is the second observation of a series, not a
finding about any model.

### 2. Two of the five lanes cannot run AT ALL, and now I know why

`shadow_blend_mom_fast` (F2) and `shadow_blend_rb_fast` (F3) both name

```
artifacts/momentum_fast/momentum_artifact_ledger.jsonl
```

**That directory does not exist** `[VERIFIED — this session]`. And launchd
carries exactly **one** momentum training job, `com.renquant.momentum-train-weekly`
(the v0 *slow* clock). `params_v1_fast()` exists in the model package — **the
recipe is there, the producer job is not.**

So two of five fleet lanes have been failing closed **since birth**, and the
GOAL-4 census line *"3 of 5 lanes produced no separating evidence"* now has its
cause: one agreed, and two were never fed. That is scaffolding deployed without
the upstream that makes it live.

## The probe change that made today measurable

Prod scores its buy funnel **once a day at 13:55 PT**. Before that the reference
does not exist and the probe — correctly — refuses. But the fleet had already
run, and *"do the candidates disagree with EACH OTHER"* is the ensemble question
regardless of whether prod has scored yet.

> Refusing to answer a question the evidence supports is its own kind of silence.

`--baseline` makes the reference choosable. It is **still validated identically**:
an absent run, an empty one, or too few names to define the requested top-K
refuses the whole probe. **A choosable reference must not become an unchecked
one**, and a test pins that a chosen baseline which scored nothing still refuses.

## Not claimed

Nothing about which lane is better. Two dates cannot rank models, and the
comparison here is of *rankings*, not of realised returns. What it says is what
evidence the fleet is accumulating — and that **40 % of it is structurally
unable to accumulate any**.

Suites: 30 tests (was 26) · full suite green.

## Next

The actionable item is a **fast-momentum producer job** — filed separately. Until
one exists, F2 and F3 are two configs, two DBs, two launchd slots and zero
evidence.
