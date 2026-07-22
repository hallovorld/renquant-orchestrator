# AC4 — Transactional Artifact Bundles (GOAL-5 P0, month-1)

**Status:** DESIGN / RFC — claude draft, codex review. No code in this PR.
**Goal:** GOAL-5 AC4. Kill the *binding-orphan* failure class: a promote or
rollback of the live serving pair must be an **atomic pointer flip** — a crash
at any instant can never leave the live run reading a *mixed* pair (panel scorer
from vintage A + calibrator from vintage B). Verified by a kill-injection test.
Includes the M6 finish: collapse the 4 fingerprint implementations to 1 and flip
`accept_legacy_stamps=false`.

---

## 1. The failure class (precisely located)

The live daily-104 run loads a **serving pair** of two flat files:

- `RenQuant/backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`
  — the panel scorer, carrying `model_content_fingerprint`.
- `RenQuant/backtesting/renquant_104/artifacts/prod/panel-rank-calibration.json`
  — the pooled calibrator, carrying `metadata.scorer_model_content_fingerprint`.

They are **bound**: the daily run asserts
`calibrator.metadata.scorer_model_content_fingerprint == scorer.model_content_fingerprint`
(`backtesting/renquant_104/kernel/panel_pipeline/calibration.py:82`, mirror of
`renquant-pipeline/.../job_panel_scoring.py:2240`). A mismatch is a hard
`ValueError` → zero candidates → **no trade**. This is the exact mechanism by
which the book has silently fail-closed **four times** (2026-05-27, 06-22, 07-01,
07-14→16); see [[calibrator-scorer-fingerprint-triple-impl-bug]] and
[[incident-20260716-book-drained-to-cash]].

### The crash window

The live pair is promoted by `RenQuant/scripts/weekly_wf_promote.sh` **Step 5**,
which replaces the two files **independently and in sequence**:

```
:359  shutil.copy2(cal_src, cal_incoming)     # stage new calibrator
:361  promote(model_src, model_dst)           # (A) panel scorer -> NEW vintage  (atomic per-file)
:362  os.replace(cal_incoming, cal_dst)       # (B) calibrator   -> NEW vintage  (atomic per-file)
```

Each line is individually atomic (temp + `os.replace`). **The pair is not.**
A crash, `kill`, power loss, or disk-full between **(A) and (B)** leaves:

> panel scorer = **NEW** vintage, calibrator = **OLD** vintage → fingerprints
> disagree → next daily run fail-closes to no-trade.

Filesystem evidence of exactly this split having happened on the incident day:
the two prod files carry mtimes **~3 hours apart** (`panel-ltr…json` Jul 16
10:25 vs `panel-rank-calibration.json` Jul 16 13:38), surrounded by manual
surgery files (`…pre-binding-fix-20260716T203819Z.json`,
`…accepted_receipt-20260715T212711Z_13553.json`).

**Rollback has the same gap.** There is no atomic rollback of the pair: Step 2
(`weekly_wf_promote.sh:224-231`) pre-copies the current pair to
`…weekly_rollback_$DATE.json` via two separate `cp`s; reverting is an operator
`cp`-ing the two files back — a second two-file non-atomic window. The prod dir
is littered with `weekly_rollback_*`, `monthly_rollback_*`, `.previous.json`
copies — the fossil record of repeated hand-surgery. `model_bundle.rollback_pin`
(`src/renquant_orchestrator/model_bundle.py:207`) only restores a *subrepo pin*,
never the artifact pair.

## 2. Invariant (what the design must guarantee)

> **I1 (pair atomicity):** At every instant, any reader that resolves the active
> serving pair observes two files whose fingerprints are mutually consistent.
> There is no observable interleaving in which panel and calibrator come from
> different vintages.
>
> **I2 (crash safety):** For any crash point during promote or rollback, on
> restart the active pair is either wholly the prior vintage or wholly the new
> vintage — never a mix, and never a half-written file.
>
> **I3 (rollback symmetry):** Reverting to the immediately-prior vintage is the
> same primitive as promote (one pointer flip), not file surgery.

## 3. What already exists (and why it is not enough yet)

The transactional machinery is **already built** but scoped to the
byte-identical genesis case and **not wired to the live promote path**:

- `renquant-artifacts` store (`bundle_store.py`, `bundle_schema.py`; RFC
  RenQuant#492): PREPARE (fsync) → ACTIVATE, `rollback_to`, generation
  directories. `bundle_schema.py:52-55` defines the AC4 member set as **exactly**
  these two files.
- `renquant-orchestrator/src/renquant_orchestrator/bundle_seal.py` (origin/main,
  #559/#561):
  - `seal_serving_pair()` (:422) publishes the *current* pair as generation 1 via
    the store's PREPARE→ACTIVATE.
  - `_refuse_if_flat_pair_would_change()` (:391) — preflight that makes the seal
    all-or-nothing across store + flat views.
  - `regenerate_flat_views()` (:288) — writes each active-bundle member to its
    flat path as a 0444 read-only view; Phase-1 whole-pair byte-identity
    pre-check, Phase-2 per-file `tmp→fsync→os.replace`, dir fsync, with a
    `crash_hook` fault-injection seam (:368).

**The gap:** `regenerate_flat_views` **refuses any *changing* pair**
(`bundle_seal.py:340-348`) and the module explicitly **defers the changing-content
pair-atomic publisher to AC4 P2/P3** (:304-326). So today it hardens the F-7
*genesis* publication, not the weekly promote that actually *changes* the pair —
which is the recurring incident source. The one crash test that exists
(`tests/test_bundle_seal.py::test_crash_between_the_two_view_writes_never_exposes_a_mixed_pair`)
proves the *byte-identical* seal is safe; **nothing tests the real
`weekly_wf_promote.sh` 361→362 window or the two-`cp` rollback.**

## 4. Design

### 4.1 Mechanism — generation directory + atomic pointer flip

Replace the two independent flat-file replaces with **one atomic symlink swap**.

```
artifacts/prod/
  bundles/
    gen-0007/                      # immutable once written
      panel-ltr.alpha158_fund.json
      panel-rank-calibration.json
      BUNDLE.json                  # {generation, both members' sha256+fingerprint, created_at}
    gen-0008/
      …
  active -> bundles/gen-0008       # THE pointer (single symlink)
  panel-ltr.alpha158_fund.json     -> active/panel-ltr.alpha158_fund.json   (compat symlink, fixed)
  panel-rank-calibration.json      -> active/panel-rank-calibration.json    (compat symlink, fixed)
```

**Promote** (crash-safe, single flip):
1. Write the new pair into a **fresh, immutable** `bundles/gen-<N+1>/` (both
   files + `BUNDLE.json`), `fsync` each file and the dir. *No live pointer has
   moved; a crash here leaves an orphan gen dir, harmless — GC later.*
2. **Preflight the binding inside the new gen dir** (fingerprints agree) *before*
   any flip — reuse the `_read_flat_pair_binding` check. Refuse the flip if the
   staged pair is itself mixed (defence in depth against a bad build).
3. Create `active.tmp` symlink → `bundles/gen-<N+1>`, then
   `os.replace('active.tmp', 'active')`. **`rename(2)` on a symlink is a single
   atomic syscall** — readers see `active` pointing wholly at gen-N or wholly at
   gen-N+1, never between. `fsync` the parent dir to persist the flip.

**Rollback (I3):** `os.replace` `active` to point back at the prior `gen-<N>`.
Identical primitive; no file surgery. The prior generation dir is retained by
the retention policy (§4.4).

### 4.2 Reader side — kill the resolve-time TOCTOU

A reader that opens the two *compat symlinks* separately could still straddle a
flip (open panel → flip → open calibrator = mixed). Close it by making readers
**resolve the active generation once, then read both members from that concrete
path**:

- `calibration.py:82` and the WF loader (`…/loader.py:537`) resolve
  `os.path.realpath(prod/active)` to a concrete `gen-<N>` **once per run**, then
  load `panel-ltr…` and `panel-rank-calibration…` from that same directory.
- Because gen dirs are **immutable**, a concrete-path read is inherently
  consistent regardless of any concurrent flip. (Promote is weekly and off the
  13:55 decision schedule, so concurrency is already unlikely; this makes it
  *impossible* rather than *unlikely*.)

The fixed compat symlinks (`prod/panel-ltr…json`, `prod/panel-rank-calibration…json`)
keep every **hardcoded** reader path valid during migration.

**Reader-inventory gate (revised per review — I1 admits no exceptions).** An
earlier draft let non-daily compat readers accept a "small" straddle risk; that
contradicts I1 and is a real correctness gap, not a negligible one — so it is
removed. Before P2 cutover is allowed to activate a *changing* pair:
1. **Inventory every process that reads the serving pair** — grep the fleet for
   the two flat basenames + `artifacts/prod/panel-` + the config keys
   `panel_ltr.artifact_path` / `global_calibration.artifact_path`, across all
   repos (daily run, WF loader, shadow/AB jobs, sentinels, tooling, tests).
   The inventory is a checked-in artifact reviewed on the P2 impl PR.
2. **Every inventoried reader is either** (a) migrated to single-resolve
   (realpath the active generation once, read both members from it), **or**
   (b) provably reads at most one member (cannot straddle a pair).
3. **Until (1)+(2) are complete, changed-content activation stays refused** — the
   existing `regenerate_flat_views` refusal (bundle_seal.py:340-348) remains the
   safety interlock. P2 cutover flips from "refuse changing pair" to "atomic
   flip" **only** once the inventory shows no straddle-capable reader remains.
So I1 holds for *every* reader at cutover, not just the two daily ones; there is
no residual "astronomically small" window.

### 4.3 Where the flip lives

Promote/rollback become a **single orchestrator entry point** —
`bundle_seal`-adjacent (extend it to the *changing-content* case its docstring
defers): a `publish_serving_pair(new_panel, new_calibrator)` that does §4.1
steps 1-3, and a `rollback_serving_pair()` that does §4.1 rollback. Two seams:

- **Primary (recommended):** the generation-dir + symlink flip above, owned by
  the orchestrator, writing under `artifacts/prod/`. Minimal blast radius, **no
  new runtime dependency** on the daily capital path, directly closes the 361→362
  window. `weekly_wf_promote.sh` Step 5 calls this one function instead of the
  `promote()`-then-`os.replace()` pair; the two-`cp` rollback is deleted in favour
  of `rollback_serving_pair()`.
- **Convergence (P3):** route the two daily readers through the
  `renquant-artifacts` store's active-bundle pointer directly (the store already
  does PREPARE/ACTIVATE/`rollback_to` over generation dirs), retiring the flat
  compat symlinks entirely. Deferred because it couples the live decision path to
  store presence/sync — a larger blast radius that should land only after the
  primary has proven itself and the store is on-machine for the daily run.

**Decision:** ship the **Primary** as AC4 P2 (it is the reliability fix and is
self-contained); keep **Convergence** as P3. Rationale: a P0 capital-path fix
should minimise new failure surface — the symlink flip adds one atomic syscall
and zero runtime dependencies, whereas store-routing adds a load-bearing
dependency to the 13:55 run. Both share the same generation-dir substrate, so P2
is a strict step toward P3, not throwaway.

### 4.4 Retention & GC

Keep the last **K=4** generations (covers the weekly cadence + a month of
rollback targets) plus any generation reachable by `active`. GC orphan/stale gen
dirs in the same reviewed retention policy that already prunes
`weekly_rollback_*` (`src/renquant_orchestrator/retention_policy.py`). Never GC
the active or immediately-prior generation.

### 4.5 Initial migration protocol (added per review)

Converting today's two flat files into `bundles/gen-0001/` + the `active` symlink
+ two compat symlinks is **itself a multi-step transition** that must not create a
transient mixed/missing pair. It runs as a one-time, **quiesced** migration, not
during a promote:

1. **Quiesce:** run only in a window with no daily/shadow/promote job scheduled
   (e.g. immediately after the 13:55 run completes, before the next). Verify via
   the run-surface state that no serving read is in flight.
2. **Stage:** create `bundles/gen-0001/`, copy the *current* prod pair into it,
   `fsync`; assert `_read_flat_pair_binding(gen-0001)` is consistent (the current
   live pair is already consistent by definition — if it is *not*, abort: that is
   a pre-existing orphaned binding to fix first, not to freeze into gen-0001).
3. **Publish `active` FIRST, then flip the compat paths (order corrected per
   review).** The compat symlinks point *through* `active` (`→ active/<member>`),
   so `active` must exist and be durable before any compat path is repointed —
   otherwise the first `os.replace` swaps a real flat file for a symlink that
   resolves through a not-yet-existing `active`, i.e. a **dangling serving path**
   (the earlier draft's "flat file remains real until its symlink replaces it"
   was true but missed that the *replacement itself* dangles). Concretely:
   1. **3a — create `active`:** create `active.tmp` → `bundles/gen-0001`,
      `os.replace('active.tmp', 'active')`, `fsync` the parent dir. No compat
      path has moved yet; both flat paths are still their original real files, so
      every reader is unaffected and `active/<member>` already resolves.
   2. **3b — flip each compat path:** for each of the two flat paths, create the
      compat symlink at a tmp name → `active/<member>` and `os.replace` it over
      the flat file. Because `active` now exists and points at the
      **byte-identical** `gen-0001`, at *every* instant each flat path resolves
      to consistent bytes — before its flip it is the original real file; after,
      a symlink that resolves through `active → gen-0001` to the same bytes.
      Never missing, never dangling, never a mixed vintage (a half-flipped state
      is old-real-file + gen-0001-symlink, both the *same* vintage).
4. **Verify:** re-resolve each flat path through the symlinks and assert the pair
   binding is consistent and byte-identical to the pre-migration pair; assert
   **neither serving path is dangling** (each `os.path.realpath` resolves to an
   existing file under `bundles/gen-0001/`); assert no leftover tmp; record a
   migration receipt.
5. **Reversibility:** until step 4 passes, the pre-migration flat files are
   recoverable from `bundles/gen-0001/` (byte-identical copies). A failed
   migration restores the two plain files and leaves the world exactly as before.

The migration ships as its own reviewed step with a dry-run + a drill on a copy
of the prod dir before it touches the live tree ([[live-tree-mutation-preflight-required]]).
The drill asserts the **no-dangling / no-missing** invariant *after every step*
(3a and each 3b flip, not only at the final verify): after each `os.replace`,
both serving basenames must exist and `os.path.realpath` each to an existing file
whose bytes equal the pre-migration pair — the check that would have caught the
`active`-before-compat ordering bug.

## 5. M6 fingerprint finish (folded into AC4)

The binding assert is only trustworthy if *both* sides compute the fingerprint
**identically**. Four implementations still exist (census
`doc/design/2026-07-02-m6-fingerprint-unification.md`); consolidation to
`renquant-common/model_fingerprint.py:471` is the AC4 M6 finish:

1. **Delete the last live divergence:** the deployed
   `backtesting/renquant_104/kernel/panel_pipeline/panel_scorer.py:108`
   subtractive-denylist `model_content_sha256` still carries a *local* impl; make
   it import `renquant_common.model_fingerprint` like the source repos already
   do. (Impls 2/3 are already common-delegating wrappers.)
2. **Staged flip:** add `ranking.panel_scoring.fingerprint.accept_legacy_stamps:
   false` to the strategy-104 config. It currently defaults **True**
   (`fingerprint_dispatch.py:87`, key absent from live config → dual-accept window
   open). The census (`scripts/fingerprint_census.py`) is **green 47/47**, so the
   flip is unblocked — but it is a **capital-admission behaviour change**, so it
   ships **behind a shadow verdict** (one clean daily-full where the strict-only
   binding still admits the same candidates), never coincident with the P2 plumbing
   change ([[fix-wave-protect-production.md]]: plumbing and behaviour changes are
   separate PRs).
3. **Later (post-window):** remove the `_legacy_model_content_sha256` shim.

Sequencing: P2 plumbing (pointer flip) is **fingerprint-behaviour-invariant** and
lands first; the M6 flip (2) lands second, alone, behind its shadow verdict.

## 6. Verification — the kill-injection test (the AC4 acceptance gate)

Extend the existing `crash_hook` seam (`bundle_seal.py:368`) to cover the new
`publish_serving_pair`/`rollback_serving_pair`, and assert I1/I2 at **every**
crash point:

| Crash point | Restart state must be |
|---|---|
| during gen-dir write (before fsync) | active = OLD; partial gen-<N+1> is orphan, ignorable |
| after gen-dir fsync, before symlink `os.replace` | active = OLD (whole) |
| after symlink `os.replace`, before parent-dir fsync | active = **OLD-or-NEW, either wholly consistent** (see note) |
| after parent-dir fsync | active = NEW (whole, durable) |
| any point during rollback flip | active = target-or-source, whole, never mixed |

**Note on the un-fsync'd flip (revised per review):** after `os.replace` but
before the parent-dir `fsync`, the rename is atomic in the page cache but **not
yet guaranteed durable** — a power-loss restart may recover the directory entry
as either OLD or NEW depending on writeback. That is acceptable: the invariant is
I1/I2 (*consistency*, never a mix), **not** "NEW is guaranteed." An earlier draft
claimed "flip already durable" here — that overclaimed durability; corrected. The
only guarantee that matters is that both recoverable states are whole. Promote is
idempotent-safe: on an OLD recovery the weekly job simply re-runs and re-flips.
Each case asserts `_read_flat_pair_binding(active-resolved)` returns a
**consistent** pair (never the mixed-pair detector's failure). Add a
**scripted** test that drives the *real* `weekly_wf_promote.sh` Step 5 through
the new entry point under `kill -9` injection (the gap presently untested per
§3). Acceptance = the whole matrix green + a live-shadow promote drill that flips
a generation and rolls it back with the book observing a consistent pair
throughout.

## 7. Scope, ownership, rollout

- **orchestrator:** `publish_serving_pair`/`rollback_serving_pair` (extend
  `bundle_seal.py`), retention GC, the kill-injection tests. (This repo owns
  GOAL-5 reliability + the seal.)
- **umbrella `RenQuant`:** `weekly_wf_promote.sh` Step 5 + rollback call the new
  entry point; one-time migration that lays down `bundles/gen-0001/` from the
  current prod pair and converts the two flat paths to compat symlinks.
- **deployed kernel readers:** `calibration.py` + WF `loader.py` single-resolve
  (§4.2); **behaviour-invariant** (same bytes, same binding) — provable by an
  A/B daily-full diff.
- **pipeline/common:** the M6 import unification (§5.1).

**No flag day:** the migration keeps the flat paths valid as symlinks, so every
un-migrated reader keeps working; the flip mechanism and the reader single-resolve
land independently; the M6 behaviour flip is last and shadow-gated. Each bullet
is a separate reviewed PR under this design.

## 8. Out of scope

Multi-artifact bundles beyond the panel+calibrator pair (e.g. bundling the WF
manifest or feature spec) — the schema supports it but AC4's acceptance is the
*pair*. Store-routing of all readers is P3 (§4.3). No change to *what* gets
promoted or to any capital gate; this is purely *how* the pair cuts over.

[[incident-20260716-book-drained-to-cash]]
[[calibrator-scorer-fingerprint-triple-impl-bug]]
[[goal-5-daily-run-reliability]] [[fix-wave-protect-production]]
[[never-touch-production-inputs-on-live-tree]]
