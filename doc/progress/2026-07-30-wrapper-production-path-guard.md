# Any copy of a job wrapper writes production by default — DESIGN   (PR pending)

STATUS:    design proposal under review. NOTHING is implemented — no wrapper changed,
           no plist touched, no job behaviour moved. Per LONG#7 this is not merged
           while under discussion.
WHAT:      doc/design/2026-07-30-wrapper-production-path-guard.md — proposes that a job
           wrapper refuse to write the production umbrella when it is running from an
           unreviewed copy, unless a dedicated acknowledgement names the target.
WHY/DIR:   Occasioned by the stray process terminated 2026-07-30 (issue #639): an
           orphaned wrapper from a WORKTREE held write access to production paths for
           7 days 18 hours. Every wrapper resolves the production umbrella by default
           (`RQ_ROOT="${RQ_ROOT:-…/RenQuant}"`), which is correct for the scheduled job
           and identical in every copy of the file.
EVIDENCE:  n/a — this PR makes no measurement claim of its own. The three counts it
           cites (grep scope; the 32/18/1 root split) are tagged in the design doc and
           were measured before it was written.
NEXT:      Review must settle §4 before any implementation PR. Rollout, if accepted, is
           one file first (`run_quote_logger.sh`) then a mechanical sweep.

## Review round 1 — the escape hatch was not an escape hatch

Codex: `RQ_ROOT` being set **is not proof of deliberate production access** — an
inherited shell environment, an editor task configuration, or a copied worktree command
can set that generic variable accidentally, recreating the bypass the design exists to
stop.

That is right, and it makes the opt-in worthless. `RQ_ROOT` is a **destination**
variable that already exists for ordinary reasons. A guard whose acknowledgement is
satisfied by a variable people already set for unrelated purposes converts nothing into
a choice — it adds a condition that is usually already true. I had conflated *where
should this write* with *am I permitted to write production from an unreviewed copy*.

Revised: the two are separate. `RQ_ROOT` keeps its meaning; a **purpose-named**
`RQ_PRODUCTION_WRITE_ACK` carries permission, and its value must **equal the canonical
production root** rather than being a truthy flag — a bare `=1` is rejected, precisely
because `=1` is how an accidentally-inherited flag propagates.

The revision also fixes a priority I had backwards: an experiment pointed at a sandbox
(`RQ_ROOT=/tmp/x`) now needs **no** acknowledgement, while the first version demanded
ceremony for that harmless case and accepted a stray variable for the dangerous one.

## Three open questions are now decided, not deferred

Codex asked for these before acceptance rather than at implementation time. Each is
load-bearing on whether the guard works at all:

* **Trusted prefix source** — an absolute literal per wrapper, compared on canonical
  paths, with CI asserting each literal equals the prefix the manifest actually invokes
  that job from. Not an env var (a copy inherits it) and not a relative path (a copy's
  relative path resolves to the copy). **Stated limit rather than overclaimed:** a copy
  whose literal is *edited* defeats this, as it defeats any guard living inside the
  thing it guards. The threat model is an accidental copy, not an adversary.
* **The dev-checkout job** — a uniform "must be under `-run`" rule would have **broken a
  reviewed configuration**: one scheduled job legitimately runs from the dev checkout
  (roots measured 32 / 18 / 1). The allowed prefix is now **per-job from its manifest
  row**, so the invariant is "running from where the reviewed manifest says", which is
  the property actually wanted. "Under `-run`" was a proxy that happened to hold for 11
  of 12.
* **Canonicalisation** — specified, not left to implementation: symlinks and `..`
  resolved, comparison on path **components** so `…-run-backup` cannot match a `…-run`
  prefix, and **refusal when canonicalisation fails** rather than falling back to the
  raw string. This programme has repeatedly shipped guards that read "could not check"
  as "checked and fine"; that is the specific hole being pre-closed.

`run_liveness_check.sh` (no manifest row, nothing calls it) gets `TARGET`-only logic:
with no reviewed location the guard reduces to *writing production requires the
acknowledgement, wherever you are*. Deletion stays on the table as a separate change;
leaving it unguarded because it is awkward is the one option ruled out.

## Live-surface impact

None. One design document and this note. No wrapper, plist, config, artifact or state
is touched, and nothing is implemented.
