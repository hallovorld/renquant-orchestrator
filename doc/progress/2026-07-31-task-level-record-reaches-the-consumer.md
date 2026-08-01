# The producer named the record; the consumer still dropped it

**Bottom line.** `renquant-pipeline#240` made the zero-shadow health record name its lane
`__task_level__` so it would stop being discarded. Reviewed `[codex on pipeline#240]`:

> *"the producer-side normalization belongs in renquant-pipeline, but it does not make
> the task-level record visible to the deployed consumer… `__task_level__` matches no
> configured lane, so the record is still dropped before classification; exercising
> `is_valid_v1_record` alone tests parsing, not the consumer path the PR claims to
> repair."*

Correct on every point. This is the **coordinated consumer half**, in the repo that owns
the reader.

## What was actually broken

`_read_from_pipeline_sink` retains a record only when its `shadow_name` matches a watched
lane. A task-level record matches none, so renaming it on the producer side moved it from
"discarded for having no name" to "discarded for having the wrong one". **Two changes, no
observable difference** — which is why a parse-level test could pass while the path stayed
broken.

## The fix, and the one thing it must not become

A task-level record says the shadow task did not run **for any lane**, so it is evidence
about *every* watched lane rather than none. `_is_task_level` makes it match whichever
lane is being read.

The danger is that this becomes "retain everything", which would let one lane's health be
reported as another's. Two guards:

- a record for a **different named lane** is still dropped — asserted directly against
  `_read_from_pipeline_sink`, the stage the review named;
- a **lane-specific record always beats a task-level one** for the same date. The reader
  is last-record-wins, so without this a real lane FAULT could be silenced by a
  "the task skipped" line written afterwards. Asserted in **both orders**, so the
  precedence is about specificity rather than arrival.

And `__task_level__` decides only which records are **visible**, never whether they are
faults — `status` does that. A task-level FAULT still alarms.

## The operational outcome for `no_shadow_models`, which the review also asked for

`expected_skip` is deliberately quiet, so the win is not that the sentinel stops alarming
— it is **why** it stays quiet:

| | before | after |
|---|---|---|
| record reaches the classifier | **no**, dropped at the reader | yes |
| the day's evidence | falls through to the fallback; a lane with no runs DB yields `feed_present=False` | an explicit "the task ran, there were no shadow models" |
| sentinel verdict | **FEED_DARK** — an alarm manufactured out of a healthy no-op | `HEALTHY`, quiet **for a stated reason** |

Silence that is indistinguishable from a missing check is the failure mode this whole
programme is about. A quiet outcome only counts when the evidence for it arrived.

## Why the constant is duplicated rather than imported

This sentinel must keep reading records on a host whose `renquant-pipeline` predates
`TASK_LEVEL_SHADOW_NAME`, and a failed import would silently restore the drop it exists to
fix. The cost is that the two literals can diverge, so each side pins the string in a
test.

## A defect in my own test, caught before it shipped

`test_a_record_for_ANOTHER_lane_is_still_dropped` passed the sink stage and then read a
record out of **this machine's** shadow runs DB (`source='shadow_runs_db_fallback'`), so
the assertion was about the operator's disk rather than the reader. That is the defect
this programme has now caught six times in two days — and it appeared **inside the test
written to fix the sixth**. The fixture silences both fallbacks; these tests are about one
edge, sink → reader → classifier, and the fallbacks have their own.

Tests: 7. Two mutations of the real consumer fail them — reverting the task-level
allowance, and dropping the specificity precedence.
