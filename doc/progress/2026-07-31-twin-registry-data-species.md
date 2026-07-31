# GOAL-3: the twin registry gains a species it did not have — the twin is in the DATA

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-3 (audit + register)

**Bottom line.** R1–R7 are all *code* twins: two implementations, and nothing says which
executes. **R8 and R9 are the same failure one level down — in the artifacts.** They cost
**three defects in one evening, two of them published claims I had to retract**, which is
more than any single code twin in the registry has cost.

## R8 — one gate stamp, two locations, and they disagree

| | measured `[本次实测 2026-07-31, direct JSON inspection]` |
|---|---|
| prod `panel-ltr.alpha158_fund*.json` | **29** |
| carrying `metadata.wf_gate_metadata` (canonical) | **29** |
| *also* carrying a legacy top-level copy | **14** |
| carrying **only** the legacy copy | **0** |
| where both exist: agree / **disagree** | 12 / **2** — the legacy block has no `sanity_eval_scope` while the canonical one records `walkforward_manifest` |

**What reading the legacy key alone cost:**

| | claim made | reality |
|---|---|---|
| backtesting#89 | *"fifteen census rows asserted an observation nobody made"* — **a fabrication accusation** | all 29 rows real; **retracted** |
| orch#680 | *"ten of the eleven artifacts cannot re-derive the table"* | all 11 can; 44/44 rows re-derive exactly; **retracted** |
| orch#683 | `bundle_seal` sealed from the legacy key | correct today **by luck**; on 15 of 29 panels it would write `UNSTAMPED` and drop 7 override-provenance fields |

**Why a data twin is worse than a code twin.** A code twin misleads whoever reads the
source. A data twin misleads **every tool that reads the artifact, independently**, and
each fails differently — a census under-counts, a seal writes `UNSTAMPED`, an audit cries
fabrication. The failure is silent and direction-dependent: the wrong key returns `None`,
which every reader interprets as *"the thing isn't there"* rather than *"I looked in the
wrong place."*

## R9 — one basename, 23 paths, 3 digests

`panel-ltr.alpha158_fund.json` resolves to **23 paths** with **3 distinct sha256** — 21
inside `diagnostics/modal_sweep_*/bundle/kernel/artifacts/prod/`. An `rglob` +
`sorted(hits)[0]` silently measured a **diagnostic copy** and moved `BULL_CALM`'s median
from `0.022029` to `0.021927` **with no error raised**. Caught only because two runs of
the same tool disagreed. This is *"which copy executes"* displaced one step: **which copy
gets measured** — inside the tool written to make a measurement auditable.

## The tripwire — the "executable pointer" the registry asks for

`tests/test_twin_r8_canonical_gate_key.py` walks this repo's `src/`, `scripts/`, `ops/`
by **AST** and fails if any reader takes `wf_gate_metadata` from the top level **without
consulting the canonical location first**. Four files are allow-listed as documented
fallbacks, and a second test fails if an allow-list entry stops reading the key at all —
so the exemption cannot silently widen.

**AST, not grep, and the reason is measured.** The sweep that found R8 first flagged
**six** production files; **five were false positives**, because a line-oriented regex
cannot tell whether the receiver of `.get("wf_gate_metadata")` is the whole payload or
the `metadata` sub-dict. This is the third time in one evening a line regex produced a
wrong count.

**Mutation, both directions** — a tripwire that flags everything is as useless as one
that flags nothing:

| planted | result |
|---|---|
| a new legacy-only reader | **fails** ✔ |
| a correct canonical-first reader | **passes** ✔ (no false positive) |

## What the sweep also established, and it is good news

The **live daily path is clean.** `preflight.py`, `job_panel_scoring.py`,
`model_acceptance.py`, `latest_run_docs.py`, `assemble_track_b_verdict.py`,
`model_bundle.py`, `model_freshness_enforcer.py` and
`check_model_bundle_consistency.py` all read the canonical key first. **Only the audit
tools written that evening had the bug**, plus `bundle_seal` (orch#683).

## Not claimed

That the legacy copy should be deleted — it exists on 14 artifacts and nothing here
establishes what still writes it. That any run bundle sealed to date is wrong. That the
other repos need this tripwire; it is written against this repo's tree and the sweep
found their readers already correct.

Tests: 3 added. Suite **4835 passed, 2 skipped**.
