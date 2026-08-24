# S3-P4a: the intraday entry DECISION core — pure, guarded, inert

STATUS:   delivered. Third implementation PR of the Stage-3 ladder. Decides,
          never executes: no broker import, no order path, no scheduler
          wiring, nothing reads it yet. The execution leg is S3-P4b; the live
          flip is S3-c and remains an explicit operator ask.
WHAT:     `intraday_entry_decision.py` — v1 admission = batch ∩ intraday
          (intraday can VETO a batch admission, never create one; a censored
          quote is a veto, fail closed), plus every approved-design guardrail
          as data (frozen Guardrails: 2 entries/day, $1,500/day, 15-min
          session edges, SHARED max_concurrent_positions, halt env), applied
          unconditionally in fixed order. Budgets hold BY CONSTRUCTION — the
          plan cannot exceed them for an executor to catch. Every non-entered
          name carries exactly one named reason (the #598/#599/#600 lesson at
          the source).
WHY/DIR:  shipping the decision core alone keeps the capital-adjacent surface
          reviewable in isolation, and the S3-b shadow window can exercise the
          exact production decision path with zero order risk.
EVIDENCE:
  artifact:      the module + 21 hermetic tests.
  prod or exp:   exp — pure functions; the orchestrator suite covers tests/
                 wholesale.
  existing data: 8 targeted mutants (halt, window, both entry budgets,
                 notional, shared cap, batch gate, censor gate), each
                 compile-checked first so a syntax-broken mutant cannot count
                 as "killed" — ALL KILLED [VERIFIED]. Three successive fixture
                 revisions of one test each tripped a DIFFERENT real guardrail
                 (notional, then shared cap) before passing — recorded in the
                 test as evidence the limits compose.
  best-known?:   yes — guardrails as frozen data mean a caller cannot omit
                 one; the plan records which Guardrails produced it.
  scope:        one pure module + tests. NOT wired anywhere.
REVIEW:    codex (haorensjtu-dev).
