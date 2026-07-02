# 2026-H2 execution roadmap — design PR

STATUS:   design for review (docs only — no code/config/broker/risk/sizing change in this PR).
          The TIME-PHASED execution companion to the thematic capability program (PR #228).
REVISION: r2 (2026-07-02) — addresses Codex CHANGES_REQUESTED: added an explicit dependency-DAG
          table to §1 (RenQuant#431 IC reconciliation gates S9/Track A/D3/L1; RenQuant#430 gates
          S9; #224+#227 gate N1/M1/M2; S1-S3 gates S4/M10); constrained §8's monthly re-baseline
          to forecasts/estimates only, never silently touching a pre-registered estimand/
          threshold/confirmation-data/stop-rule; added cost caps + vendor exit criteria to N3 and
          RS-3; clarified M2's canary scope as operational/safety validation only, never economic
          authorization; corrected S8's AC to reflect its actual (disputed, not clean-passed)
          outcome per RenQuant#431 and hard-gated S9 on that reconciliation; added this §4(b)
          evidence block. Also rebased onto current main to pick up #226 (A3)'s already-merged
          changes to `model-freshness-governance.md`, which this branch had gone stale against.
REVISION: r3 (2026-07-02) — addresses Codex CHANGES_REQUESTED (execution-order self-contradiction):
          split N1 into N1a (build/test the collector-scheduling mechanism — `#232`'s actual
          scope — unblocked, execute now) and N1b (activate live collection — hard-BLOCKED until
          #224 AND #227 both merge to main, per the Dependency DAG's own #224/#227→N1 gate);
          updated the horizon-map header to show the split. Also corrected every "#431's frozen
          reconciliation protocol" claim (DAG table, S9's hard-gate note, §8's re-baseline
          exclusion list) to accurately state the protocol is PROPOSED/INCOMPLETE as of 2026-07-02
          (Algorithm B's estimand, shift values, and the untouched adjudication slice are not yet
          pinned) — a hard gate cannot cite an input as settled/frozen when it is still open to
          researcher discretion.
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

          §4(b) evidence block (`doc/AGENT-RETROSPECTIVE.md`), added per Codex review 2026-07-02:
          ```
          artifact:      doc/design/2026-07-02-h2-execution-roadmap.md (this PR — a scheduling/
                         sequencing document, not a model or data artifact)
          prod or exp:   n/a — this PR makes no model/data claim of its own; it is a scheduling
                         layer over items whose OWN evidence blocks live in their source PRs
                         (#228, #223, RenQuant#430/#431). Where this doc cites a measured fact
                         (e.g. the 2026-07-01 `01c54b39` run, σ_oc≈150bps), the citation traces to
                         that fact's own originating PR/doc, not to a new claim made here.
          existing data: this is the first roadmap doc of its kind in this repo (no prior
                         "H2 execution roadmap" to diff against); its dependency-gate content was
                         cross-checked against the actual current state of the PRs it cites
                         (RenQuant#430/#431's real findings, not assumed outcomes) as part of this
                         revision
          best-known?:   n/a (scheduling document, not a model variant)
          scope:         this is a sequencing/dependency-gate document only; it asserts no IC,
                         Sharpe, or other quantitative model claim itself — S8/S9's status section
                         above is the one place it reports a measured outcome, and that section
                         states the AC as UNRESOLVED/disputed rather than met, per RenQuant#431
          ```
NEXT:     Codex review of this roadmap; operator confirmation of the §9 sign-off list. On
          agreement: N1–N3 execute immediately (data spend already authorized); S1–S3 gate-repair
          PRs open in backtesting/model; RS-3 (data-vendor stack) and RS-2 (lane-A timing)
          research memos due first week. Monthly re-baseline lands as dated addenda to the
          design doc — never silent edits.
