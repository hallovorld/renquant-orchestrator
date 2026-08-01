# An attributed liveness verdict was being demoted to AMBIGUOUS (GOAL-5 / 105)

## The symptom, on this machine

`com.renquant.rq105-shadow-serving` reported:

```
STALE_AMBIGUOUS_SHARED_LOG_DIR com.renquant.rq105-shadow-serving
  14 scheduled firings have elapsed since the log was last written (2026-07-13T13:45:05),
  size 2048B | 6 manifested jobs write to .../logs/rq105, so no file there can be
  attributed to this one. Declare an `evidence_glob` in the manifest to make this
  judgeable.
```

The advice was already satisfied: the manifest entry declares
`evidence_glob=.../logs/rq105/shadow_serving_*.log`, and the glob had resolved this job's
own newest file — `shadow_serving_2026-07-13.log`, 2048B, exactly the file and size in the
message.

## The defect

`corroborate()` branched on directory sharing alone:

```python
owners = dir_owners.get(os.path.realpath(d), set())
if len(owners) > 1:
    r["status"] = STALE_AMBIGUOUS_SHARED_LOG_DIR
```

Everything in that function exists to qualify a verdict computed from a **proxy** surface
(`StandardOutPath`). A verdict computed from the job's own `evidence_glob` is already
attributed, and running the corroboration over it does the opposite of its purpose: it
discards the attribution and reports "we cannot tell" about a definite finding. The
sibling-rescue branch is worse — it would promote an attributed row because a *neighbour's*
file is newer, which is precisely the cross-object attribution the AMBIGUOUS state exists
to prevent, arriving through the other branch.

Fix: skip corroboration entirely when `evidence_surface == "evidence_glob"`.

## Measured effect [本次实测 2026-08-01]

```
before: STALE_AMBIGUOUS_SHARED_LOG_DIR  com.renquant.rq105-shadow-serving
after : NO_EVIDENCE_STALE               com.renquant.rq105-shadow-serving
        14 scheduled firings ... since 2026-07-13T13:45:05
        launchctl LastExitStatus raw=256 => exit code 1
```

The `exit code 1` line is the corroborating detail the AMBIGUOUS label was hiding, and it
matches the standing note that rq105 shadow-serving exits 1.

Fleet totals after the fix: `NO_EVIDENCE_STALE` 2, `STALE_AMBIGUOUS_SHARED_LOG_DIR` **6**,
`STALE_BUT_SIBLING_FILE_IS_NEWER` 10, `UNJUDGEABLE_NO_PLIST` 3, `UNJUDGEABLE_NO_SCHEDULE`
2. The AMBIGUOUS state is not disabled — six jobs without a declared glob still land there,
and a test pins that.

## Not in this change

`com.renquant.rq105-liveness` declares no `evidence_glob` at all and so cannot be judged
by this route. That is a manifest change and a separate reviewed decision; it is not
bundled here.

Tests: 3 added (attributed row survives a shared directory; a proxy row in the same
directory is still AMBIGUOUS; an attributed row is not rescued by a fresh sibling).
Suite: 50 passed in the two liveness files.
