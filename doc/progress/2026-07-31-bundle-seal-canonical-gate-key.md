# The bundle seal reads the gate stamp from the wrong key — correct today by luck

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 (override provenance) / GOAL-1

**Bottom line.** `bundle_seal.extract_bindings` read `panel["wf_gate_metadata"]` — the
**legacy top-level** key. The canonical location is **`metadata.wf_gate_metadata`**. On
a panel stamped only canonically the read returns `None`, the seal records
`wf_gate_verdict: "UNSTAMPED"`, and **all seven override-provenance fields are silently
dropped**.

That is load-bearing because the function's own docstring says it *"closes the GOAL-5
'override provenance not in the run bundle' gap"*. **A recorder that silently writes
`UNSTAMPED` reports a gap as closed while recording nothing.**

## Measured, before changing anything

`[本次实测 2026-07-31, direct JSON inspection of the 29 prod panel artifacts]`

| | |
|---|---:|
| `panel-ltr.alpha158_fund*.json` in `artifacts/prod` | **29** |
| carrying the canonical `metadata.wf_gate_metadata` | **29** |
| *also* carrying the legacy top-level copy | **14** |
| carrying **only** the canonical block → would seal `UNSTAMPED` | **15** |
| the **currently-deployed** panel | carries **both** — so the old read works |

The deployed panel carries both copies, with all seven keys in each. **So this is not a
live incident: the seal is correct today.** It is correct by luck. The 15 exposed panels
are the `weekly_rollback_*` and restamp set — exactly the artifacts a rollback would
promote.

Dropped fields, had one of the 15 been served: `passed`,
`gate_verdict_before_override`, `operator_authorized_override`, `override_applied_at`,
`override_reason`, `diagnostic_only`, `gate_version`.

## The fix

`_wf_gate_block()` reads the canonical key first and falls back to the legacy copy, with
the precedence **stated** rather than incidental — the two copies are known to disagree
on other artifacts (on 2 of the 14 that carry both, the legacy block has no
`sanity_eval_scope` while the canonical one does).

## How it was found, and what it cost to be sure

A sweep for `wf_gate_metadata` readers across seven repos, prompted by the same key-path
defect producing **two false findings** earlier the same evening (backtesting#89's
retracted *"fifteen rows were invented"*, and orch#680's retracted *"ten of eleven cannot
be re-derived"*).

**The sweep's first pass flagged six production files. Five were false positives** — a
regex cannot tell whether the receiver of `.get("wf_gate_metadata")` is the whole payload
or the `metadata` sub-dict, and `preflight.py`, `job_panel_scoring.py`,
`model_acceptance.py`, `latest_run_docs.py` and `assemble_track_b_verdict.py` all handle
the canonical key correctly. Reading each one settled it; the count came from grep and
the finding came from the code.

## Not claimed

That any run bundle sealed today is wrong. That the other repos' readers need changes —
they do not. That the legacy copy should be removed: it exists on 14 artifacts and
nothing here establishes what still writes it.
