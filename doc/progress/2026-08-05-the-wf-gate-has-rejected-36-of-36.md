# The WF gate has rejected 36 of 36, and it is right to

STATUS: measurement only. Read-only over the job's own logs. **No gate, threshold,
model, config or live surface is touched, and none should be on the strength of this
alone.**

WHAT: parses every `VERDICT:` line in the 48 dated logs that
`weekly_wf_promote` writes, and reports the verdict series plus the placebo/real IC ratio the
enforced sub-gate actually tests. Measurement only — no code path changes.

WHY/DIR: `com.renquant.weekly-wf-promote` and `com.renquant.retrain-panel104` are two of
the 14 undispositioned failing jobs (see
`2026-08-05-triage-the-14-undispositioned-failing-jobs.md`). `retrain-panel104` is a
mirror — it delegates and reports whatever weekly-wf-promote returns — so both rows
resolve to one question: **is the promote job broken, or is it refusing correctly?**

It is refusing correctly. The finding is what the refusals are made of.

## 36 of 36

Every run that reached a verdict, over the whole retained window, rejected:

| | |
|---|---|
| runs with a `VERDICT:` line | **36** |
| span | 2026-05-24 → 2026-08-04 |
| `PASS` verdicts | **0** |

[VERIFIED — `VERDICT:\s*(\w+)` over the 48 dated logs in
`RenQuant/logs/weekly_wf_promote/`, 2026-08-05]

## Why, measured

The enforced criterion is the placebo sub-gate: the shuffled-label IC must come in
**below half** the aligned real IC (`threshold = 0.5 × |aligned_real_ic|`). The
observed ratio, across every run that logged both numbers:

| | |
|---|---|
| `placebo_ic / aligned_real_ic` | **0.876 – 0.986** (n=13) |
| what the enforced rule requires | **< 0.5** |

The shuffled-label run is recovering **88–99% of the "real" IC**. Whatever the
candidates are scoring on, a label permutation scores nearly as well.

The v3 difference-based criterion (shadow, not enforced) says the same thing in the
form this project already trusts — see the standing note that the embargo leaves a
**~+0.04 shuffled-label floor, so only placebo-clean *differences* mean anything**:

| run | aligned_real_ic | placebo_ic | genuine = real − placebo | bar |
|---|---|---|---|---|
| 2026-07-06 | +0.0651 | +0.0570 | **+0.0081** | +0.020 |
| 2026-07-18 → 07-25 | +0.0631 | +0.0598 | **+0.0033** | +0.020 |
| 2026-07-26 → 08-01 | +0.0589 | +0.0581 | **+0.0008** | +0.020 |
| 2026-08-02 | +0.0461 | +0.0432 | **+0.0029** | +0.020 |
| 2026-08-04 | +0.0452 | +0.0431 | **+0.0021** | +0.020 |

Best observed genuine IC in the window: **+0.0081**, against a +0.020 bar. Not
marginal — a factor of 2.5 short at its best and a factor of 25 short at its worst,
and the series **declines** across the period.

[VERIFIED — `aligned_real_ic=…, placebo_ic=…` parsed from the same logs]

## What this changes about the two "failing jobs"

Neither is broken.

- **weekly-wf-promote** refuses, correctly, on a measured criterion. Its most recent
  run (2026-08-04) even exits **0**: `Reject disposition: prod FRESH (trained
  2026-08-02, 2d ≤ 28d SLA) — governance nominal, calm notify, exit 0`. The retained
  nonzero code is from an earlier run whose escalation condition (stale prod) has since
  cleared.
- **retrain-panel104** has no independent failure at all:
  `=== retrain_panel delegated weekly_wf_promote FAIL at Sun Aug 2 10:22:11 ===`.

`com.renquant.rq104-silent-refusal` already reports the chronic half of this correctly
and in the right words: *"a gate refusing once is the gate working; nothing being
promoted cycle after cycle means the gate cannot be satisfied, its input stopped
advancing, or the job is failing before it decides"* — 11 non-acting runs, 2 crashed,
9 self-reported FAIL. This measurement answers which of its three branches applies:
**the gate can be satisfied in principle; the inputs are not clearing it.**

## What this does NOT establish, and must not be used to argue

- **Not** that the threshold is wrong. A bar the candidates miss by 2.5–25× is not a
  bar that needs lowering, and the enforced ratio rule and the shadow difference rule
  agree here — they would have to disagree before the bar itself became the question.
- **Not** why the models have no edge above the floor. This reads verdict lines; it
  does not open a model.
- **Not** that anything should be promoted. Nothing here is an argument for shipping a
  candidate, and a "the gate blocks everything" framing is precisely how a capital gate
  gets forced. The measured position is the opposite: the gate is the only part of this
  lane currently doing its job.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| verdicts | **36 FAIL / 0 PASS**, 2026-05-24 → 2026-08-04 | [VERIFIED — regex over 48 dated logs] |
| placebo/real ratio | 0.876 – 0.986 (n=13) vs a required < 0.5 | [VERIFIED — same logs] |
| best genuine IC in window | **+0.0081** vs a +0.020 bar | [VERIFIED — 2026-07-06 run] |
| newest run's own exit | **0**, "governance nominal" | [VERIFIED — `logs/weekly_wf_promote/2026-08-04.log`] |
| retrain-panel104 is a mirror | delegates, reports the delegate's result | [VERIFIED — `logs/retrain_panel/2026-08-02.log`] |

artifact: none. Nothing is produced, staged or promoted; the WF gate, its thresholds
  and the candidate artifacts are untouched.
prod or exp: neither. A read-only parse of logs the job already wrote. No run was
  triggered, no model scored, no configuration read into a decision.
existing data: yes, entirely — the 48 dated logs in `RenQuant/logs/weekly_wf_promote/`,
  written by the job itself between 2026-05-17 and 2026-08-04. Nothing was regenerated,
  and no gate was re-executed to produce these numbers.
best-known?: for the question asked ("is the promote job broken, or refusing
  correctly?"), yes — the job's own verdict lines are the primary record, and the two
  criteria it prints (the enforced placebo ratio and the shadow genuine-IC difference)
  agree. It is explicitly NOT a best-known answer to *why* the candidates carry no edge;
  that requires opening a model and is out of scope here.
scope: documentation only. One progress doc; no source file, test, config, schedule or
  ack is touched.

NEXT: a decision, not a fix. The gate is right and the two launchd rows it drives stay
loud; what is owed is whether a lane producing `genuine_ic ≈ +0.002` weekly is worth
continuing to run. Recorded so that decision is made against the series rather than
against an exit code. Deliberately NOT acked — an ack here would quiet the one signal
carrying the question.
