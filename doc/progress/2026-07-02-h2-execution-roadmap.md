# 2026-H2 execution roadmap — design PR

STATUS:   design for review (docs only — no code/config/broker/risk/sizing change in this PR).
          The TIME-PHASED execution companion to the thematic capability program (PR #228).
REVISION: r1.
WHAT:     a NOW (≤72h) / SHORT (July) / MID (Aug–Sep) / LONG (Q4→H1'27) execution roadmap in
          which EVERY item carries concrete guidance (repos, scripts, order) and a measurable
          acceptance criterion; four dated decision gates (D1 first WF-gate verdict on the live
          primary; D2 down-cap screen go/no-go; D3 Track B structural decision; D4 105 canary
          economic authorization); a weekly KPI dashboard spec; six author-OWNED research
          assignments (RS-1…RS-6) converting the former open questions into recommendation
          memos; pre-registered thesis reviews (M10/L7) carrying the macro kill/pivot criteria;
          and the short list of remaining operator sign-offs (capital-risk changes only).
          Artifact: `doc/design/2026-07-02-h2-execution-roadmap.md`.
WHY/DIR:  operator directives 2026-07-02: (1) the plan must be concrete and executable with
          per-item guidance + acceptance criteria; (2) **DATA SPEND IS AUTHORIZED** — N3 (FMP
          Starter) and the RS-3 data-vendor stack move from pending-approval to execute-now;
          (3) the remaining open decisions are DELEGATED to the author as owned research (§6) —
          each produces a researched recommendation with evidence, not a menu; the operator
          retains recorded sign-off only where the capital-risk profile changes (§9: sleeve
          beta-risk, canary envelope, Track B / book scaling, thesis reviews). Sequencing logic:
          NOW items are time-irreversible (PIT accrual) or unblock data collection (collectors);
          SHORT is dominated by the critical path (gate repair → D1 first verdict; ledger
          wiring) plus the operator-visible cash-drag fix (lanes A/B); MID builds 105 Stage-1 to
          a frozen canary and executes the structural refactors (R1 tournament shadow
          migration, R2 fingerprints) plus the read-only alpha screens (down-cap M7, cluster
          wave-1 M8); LONG holds the decision gates that depend on accrued evidence (D3, D4,
          §9.4 prereg, book scaling) and the second thesis review.
EVIDENCE: item IDs and rationale trace to PR #228 (capability program: P0–P3, lanes A/B/C,
          R1–R7) and PR #223 (design-review amendments, merged: verified intraday-margin
          regime, exits-always-allowed, #213 horizon-aware freshness semantics, prereg
          integrity); measured facts cited per item — 2026-07-01 run `01c54b39` (75% idle cash,
          $336/session deploy rate, OXY fixture), pinned config (`qp_cash_drag_lambda=0`,
          `panel_buy_top_n=3`), `portfolio_qp/tasks.py:2042` (solver default 0.05),
          failed-experiments E27/E33/E34, A1/A2 audits, #256 persistence decomposition,
          phase −1 NO-GO (PR #199), σ_oc ≈ 150bps (upper-bound scenario only).
NEXT:     Codex review of this roadmap; operator confirmation of the §9 sign-off list. On
          agreement: N1–N3 execute immediately (data spend already authorized); S1–S3 gate-repair
          PRs open in backtesting/model; RS-3 (data-vendor stack) and RS-2 (lane-A timing)
          research memos due first week. Monthly re-baseline lands as dated addenda to the
          design doc — never silent edits.
