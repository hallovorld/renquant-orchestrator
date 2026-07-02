# Unified 107 master plan — design PR

STATUS:   design for review (docs only — no code/config/broker/risk/sizing change). Supersedes
          the task tables of PR #229 (recommend closing #229 in its favor); companion to PR
          #230 (route/evidence layer — gates, bounds, risk register, fallback ladder, POC
          verification all inherited unchanged).
REVISION: r1.
WHAT:     one unified plan re-deriving EVERY short/mid/long-term task against a single explicit
          objective — 107 reaches the quantified ordinary-professional bar (G* end-2028: total
          Sharpe ≥0.7, net alpha ≥0, DD ≤15%, institutional process; #230 §4) — organized by
          the terms of the value equation Book = β(FLOOR) + TC·IC·√BR_eff (active) + EXEC −
          LEAK(PROCESS). Contains: (§0) the current-vs-target STATE VECTOR with every row
          measured or a dated fact (IC ≈ 0 measured; TC ≈ 0.4 reasoned — its measurement is
          now task S-TC; BR_eff = 131/yr point [77,500] POC-A; EXEC leak +23–49bps/entry point
          POC-C; deployment 25%; floor below benchmark; gate mute since 05-18); (§1) all tasks
          grouped by the term they move, each with Δ + basis tier, guidance, AC, P, Plan B,
          downstream propagation — IDs retained from #229 for traceability, two NEW tasks
          (S-TC transfer-coefficient measurement; M-SIG the explicit 3-signal build+measure
          that G106 gates on); (§2) the same tasks time-sequenced NOW/SHORT/MID/LONG with the
          capacity priority; (§3) the POC delta log — what measurement changed in the plan
          (BR and EXEC promoted to first-class terms; lane A/B rationale rewritten from POC-B;
          IC stacking target discounted to 0.028–0.033 per POC-D; N2/N3 criticality raised);
          (§4) the standing MONTHLY measurement plan — the committed POC scripts are the
          instruments, the state vector is re-measured and appended as dated addenda.
WHY/DIR:  operator directive (2026-07-02): apply the POC standard to ALL roadmap content and
          re-derive the plan with catching-up-to-institutional-level as the explicit goal. The
          unification replaces horizon-first organization (#229) with objective-term-first
          organization so every task states WHICH variable of the goal equation it moves, BY
          HOW MUCH, and ON WHAT EVIDENCE TIER — and so the monthly re-measurement of the state
          vector shows goal progress directly instead of task completion as a proxy.
EVIDENCE: POC-A/B/C/D (scripts + JSONs on the #230 branch, verification memo
          `2026-07-02-roadmap-poc-verification.md`); A1/A2 audits; #256 persistence; embargo
          floor; E27/E33/E34/E35; PR #199 phase −1; SPIVA/HFRI medians and the G* bar (#230
          §4); Clarke–de Silva–Thorley TC; Grinold–Kahn BR; 07-01 run `01c54b39` (deployment,
          OXY fixture, shrinkage ×0.43).
NEXT:     Codex review; on merge, #229 is closed as superseded and this document becomes the
          single planning surface: N1–N3 execute immediately; July runs the PROCESS core
          first (S1–S5), then evidence generation (S8–S10, S-TC), then FLOOR (S6–S7); the
          monthly state-vector addendum starts 2026-08-01.
