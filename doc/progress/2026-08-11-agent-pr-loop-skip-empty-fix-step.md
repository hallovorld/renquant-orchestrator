# agent-pr-loop: skip-when-empty control-plane guard (reviewed-surface primitive)

STATUS:    in-progress — reviewed-surface CONTROL-PLANE PRIMITIVE landed and
           unit-tested; it is NOT yet wired into the running loop, so this PR by
           itself does NOT change the false-failure behavior. The incident fix
           is the umbrella wiring, which is a separate operator-gated live-tree
           change (see NEXT). This PR is deliberately an explicitly-unused API +
           its regression tests; it is not the incident fix.
WHAT:      Add a control-plane guard (`run_agent_fix_step` / `fix_step_is_noop`)
           and a first-class `queue_empty` plan signal to `agent_workflows.py` —
           the reviewed orchestrator surface that "owns queue resolution +
           policy". The guard encodes skip-when-empty (an idle review/fix cycle
           must not spawn the local `claude`/`codex` CLI, so a spend-cap rc!=0 on
           a no-op can't fail the run) while still SURFACING a real fix failure
           on a NON-empty queue (never swallow-all-errors).
           IMPORTANT (codex P1, 2026-08-12): nothing in the running loop calls
           this helper yet. The umbrella `RenQuant/scripts/agent_pr_loop.py`
           (`_run_review_or_fix`, lines 245-263) ALREADY skips exec on an empty
           aggregated queue and writes `status.json` — that script is where the
           reported `error:"claude fix failed"` originates, and it is out of
           scope for an orchestrator PR (live-tree/operator-gated). So this PR
           lands the tested primitive on the reviewed surface; it does not, on
           its own, alter loop behavior.
WHY/DIR:   Loop-idempotence / ops hygiene for the recurring review→fix→merge
           agent-pr-loop (doc/design/2026-06-27-autonomous-ops-loops.md §1A).
           An idle cycle is a success, not a failure; a monthly spend cap on the
           agent CLI is an operator ops action, not a loop fault, and must not
           turn every 5-minute iteration red. This keeps the compliance/health
           channel trustworthy (same "a gate that cannot go green trains everyone
           to ignore it" reasoning as the merge-audit window, orch#830).
EVIDENCE:  [VERIFIED] code + unit tests below; no model/data claim.
  artifact:      src/renquant_orchestrator/agent_workflows.py
                 (+ tests/test_agent_workflows.py)
  prod or exp:   prod (deterministic control-plane logic; no model, no data,
                 no trading path)
  existing data: n/a — this is a loop-idempotence guard, not a model/data claim.
                 Ground truth read before editing: the claude-fix step and
                 `logs/agent_pr_loop/status.json` are written by the umbrella
                 `RenQuant/scripts/agent_pr_loop.py` (`_run_review_or_fix`
                 lines 245-263 already `skip` exec on `queue_total == 0`; the
                 `raise RuntimeError(f"{agent} {workflow} failed")` is line 388).
                 `n_open_prs`/`queue` are computed in this file's
                 `run_agent_workflow` / `build_queue`.
  best-known?:   n/a (hygiene change, not a variant under comparison)
  scope:         "this is agent_workflows.py control-plane logic, prod — a pure
                 skip-when-empty loop guard + tests; no model/data claim, no
                 change to any trading/order path"
NEXT:      Operator-gated umbrella follow-up (NOT in this PR, live-tree/run
           surface): point `RenQuant/scripts/agent_pr_loop.py`
           `_run_review_or_fix` / `main` at `run_agent_fix_step` so the
           skip-empty / surface-failure policy has a single tested home on the
           reviewed orchestrator surface. This PR lands that policy + guard here;
           the umbrella already skips empties, so no live behaviour regresses.

## Detail

`run_agent_fix_step(queue, runner)` is the guard:

```
* empty queue     -> SKIP: runner NOT called; step is ok (idle cycle == success)
* non-empty queue -> run runner(); rc != 0 stays ok == False (fail-closed)
```

`runner` is a zero-arg callable returning an int rc or a mapping carrying `rc`.
`fix_step_is_noop(queue)` accepts the resolved queue (a sequence), its length
(an int), or `None`, and is the single predicate the loop uses to decide whether
to spawn the agent. `run_agent_workflow` now also emits
`plan["queue_empty"]` (True for a review/fix plan with an empty queue) so the
"nothing to do" decision is first-class and greppable in the plan JSON the loop
consumes.

Tests (tests/test_agent_workflows.py):
- `test_agent_fix_step_skips_when_queue_empty` — empty (and int-0 / None) queue:
  the runner is never invoked, `skipped is True`, `ok is True`.
- `test_agent_fix_step_surfaces_failure_on_nonempty_queue` — non-empty queue
  with a failing runner (rc=1): the runner runs, `ok is False`, `rc == 1`; a
  passing runner (rc=0) is `ok`.
