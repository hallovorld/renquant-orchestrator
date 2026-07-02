# Unified 107 master plan — design PR

STATUS:   **DRAFT — dependency-index, not an execution source of truth** (Codex review,
          2026-07-02: cannot be authoritative while source plans #228/#230 and core IC evidence
          RenQuant#430/#431 are unresolved or blocked). Authoritative for STRUCTURE only (task
          sequencing, gate specification per new §1.5) until those converge. Supersedes the task
          tables of PR #229 once no longer draft (recommend closing #229 in its favor at that
          point, not before); companion to PR #230 (route/evidence layer — gates, bounds, risk
          register, fallback ladder, POC verification all inherited unchanged and NOT
          independently upgraded by this doc).
REVISION: r2 — addresses Codex round-1 review: STATUS reframed to draft/dependency-index; §0's
          BULL_CALM IC_combined cell corrected to flag the RenQuant#431 discrepancy instead of
          restating the disputed −0.003 as settled; S8's AC corrected (table regeneration is
          done and exact; the genuine_ic reproduction bar it originally claimed is not met as
          stated, per #431); new §1.5 gate specifications for the seven true decision gates
          (immutable artifact, evidence tier, owner, input deps, stop rule, rollback, capital
          authority, kill-vs-defer); §4(b) evidence block added below.
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

          §4(b) evidence block (this PR makes NO independent model/data claim — it is a
          synthesis/planning document that CITES other PRs' claims; the block below states that
          scope honestly rather than fabricating a standalone one):
          ```
          artifact:      doc/design/2026-07-02-unified-107-master-plan.md (this doc) — a synthesis
                         of #229/#230's task tables + POC-A/B/C/D (on the #230 branch) + the A1
                         audit + RenQuant#430/#431; not itself a model or data artifact
          prod or exp:   n/a — planning/design doc, no model trained or scored by this PR
          existing data: every numeric claim in §0's state vector traces to a cited source PR
                         (#230's POCs, the A1 audit, RenQuant#430/#431); this PR adds NO new
                         measurement of its own. The one place this doc previously stated a
                         cited number as more settled than its source PR does — the BULL_CALM
                         IC_combined cell — is corrected in §0 to flag the RenQuant#431
                         discrepancy explicitly rather than repeat the single disputed figure
          best-known?:   the state vector reflects the best-known figures AS OF the cited source
                         PRs' current (unresolved/provisional) state — not upgraded here; where a
                         source PR's number is disputed (BULL_CALM) or its AC not met as
                         originally stated (S8's genuine_ic reproduction), this doc says so rather
                         than presenting the more favorable of two readings
          scope:         this is a dependency-index/planning DRAFT, not a production or
                         experiment result; it is authoritative for STRUCTURE (task sequencing,
                         gate specification) only, per the STATUS header, until #228/#230/
                         RenQuant#430/RenQuant#431 converge
          ```
          [VERIFIED — this PR's own change: rebased onto post-#226 origin/main (no silent
          revert), every cited numeric claim traced to its source PR rather than re-measured,
          the one previously-overstated claim (BULL_CALM IC_combined) corrected in place. NOT
          independently verified: the underlying POC-A/B/C/D numbers themselves, which remain
          #230's claim to verify, not this PR's.]
NEXT:     Codex review; on merge, #229 is closed as superseded and this document becomes the
          single planning surface: N1–N3 execute immediately; July runs the PROCESS core
          first (S1–S5), then evidence generation (S8–S10, S-TC), then FLOOR (S6–S7); the
          monthly state-vector addendum starts 2026-08-01.
