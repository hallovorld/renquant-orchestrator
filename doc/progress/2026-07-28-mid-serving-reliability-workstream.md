# Progress: MID-tier update — serving-reliability workstream + PatchTST serving read

STATUS:   CONFIRMED and merge-ready. The workstream was proposed on 2026-07-28;
          operator confirmed opening it directly in-session (2026-07-28/29, in
          response to an explicit recommendation to proceed) — this PR carries
          the POST-decision record for the workstream itself.
          CORRECTION (visible, not silent, per long-term-agreements.md entry 10).
          Earlier versions of this doc and of `model-edge.md` disagreed with each
          other about the 43-fold PatchTST corpus. Reconciled status, each claim
          separately checked on 2026-07-29:
            * the corpus EXISTS and is now content-addressed
              `[VERIFIED — model#91 index, root digest b8aa2d99…; 43 fold dirs /
              43 checkpoints / 43 calibrators; Modal dispatch app ids
              ap-RIc3qj4D3yFfU9z7tAx4Rd, ap-HHid4LhAAD0heLm7Mlk4aW]`. It lives in
              quarantined session scratch because its own prereg forbids it from
              entering any repo, which is why a repo-history search found nothing
              and concluded, understandably but wrongly, that it was fabricated.
            * model#85's statistical design has NOT cleared review — that PR is
              still under change request `[VERIFIED — gh pr list, 2026-07-29]`.
              Any earlier text here saying otherwise was wrong.
            * model#85's UNDERPOWERED verdict and model#87's CLOSE verdict are
              both SUPERSEDED regardless, by an evaluation-harness defect found
              on 2026-07-29 (cross-lag statistics computed on a drifting sample)
              and re-derived under model#90.
          What this record therefore asserts: the corpus is real and citable; no
          PatchTST verdict is currently admissible; the workstream direction is
          confirmed.

WHAT:     Opens `doc/memory/mid-term/serving-reliability.md` as a new MID
          workstream (peer of `model-edge.md`, not a subtask), lists it in
          `_north-star.md`, and appends a 2026-07-28 entry to `model-edge.md`
          recording a readonly end-to-end serving-path preflight with a
          fresh PatchTST artifact as primary scorer.

WHY/DIR:  The MID tier had not moved since 2026-06-17 while a full day of work produced
          three landed lanes and four defects of one class — a served model's opinion
          never reaching the decision line, with the failure presenting as an ordinary
          "no trade". That class has no owner in the current workstream list: the north
          star assumes edge automatically reaches the order path. `model-edge.md` answers
          "does the model have edge"; nothing answered "is the model actually deciding".

EVIDENCE: artifact:      `/tmp/ptserve_e2e.log` (readonly full-funnel preflight, fresh
          PatchTST as primary scorer, no orders/state/ntfy written)
          `[VERIFIED — direct log read]`.
           prod or exp:   experiment (readonly preflight run on this machine; no
          production artifact, config, or state touched).
           existing data: four defects of the same class, each with its own landed
          or in-flight PR: unsatisfiable freshness SLA on `rawlabel` (RenQuant#541)
          — weekly PatchTST retrain refused every Saturday at rc=0, served pin
          `staleness_days=622` `[VERIFIED —
          backtesting/renquant_104/logs/shadow_scorer_health.jsonl, per
          doc/progress/2026-07-28-shadow-staleness-horizon-design.md's own
          verification]`; over-specified inference-frame cache key (orch#589,
          design MERGED 2026-07-29T07:14:15Z; the implementation itself has not
          landed, see AC4 below) — cold rebuilds observed at ~795s and
          ~1201s, and a third run hit a hard 1800s timeout and ABORTED
          `[VERIFIED — /tmp/ptserve_e2e.log (795s), /tmp/ptprod_e2e2.log (1201s),
          /tmp/ptprod_e2e.log (1800.07s TimeoutError)]`; raw-vs-probability
          `rank_score` unit mismatch (pipeline#219 + RenQuant#542) — 75/75 vetoed
          and reported as "no trade" `[VERIFIED — pipeline#219 / RenQuant#542]`;
          umbrella kernel fork lag (RenQuant#540, #542). Decisive serving read:
          calibrated fresh PatchTST scored 82/82, of which 75 were evaluated
          against the buy floor and 10 cleared it, VLO selected slot 1 at
          0.5245, `Kelly=0 — skip`, 0 orders, with `CALIBRATOR-SATURATED: rank_score
          IQR=0.011` (warn floor 0.050) and held names spanning 0.4959–0.5090
          `[VERIFIED — /tmp/ptserve_e2e.log]`; same-day prod XGB reached
          conviction 0.58 on TSLA and traded (8-share NEW_BUY)
          `[VERIFIED — /tmp/daily_live_early.log line 269]`.
           best-known?:   n/a — no IC/Sharpe number is claimed; this is a
          conviction-distribution read at the decision line, not a model-quality
          comparison.
           scope:         "this is an experiment-scope readonly preflight read
          (calibrated conviction sits on the coin-flip point, Kelly correctly sizes
          to zero) motivating a new MID workstream, not an IC/Sharpe/model claim —
          the §4(b) sanity triad does not apply."

NEXT:     The workstream and its 5 acceptance criteria are confirmed AS A DIRECTION —
          this does NOT mean any of the 5 is satisfied. Status of each, checked
          2026-07-29 `[VERIFIED — gh pr list]`: AC4 (warm serving path): its design
          dependency orch#589 is now **MERGED** `[VERIFIED — gh pr list --state
          merged, 2026-07-29]`, so AC4 moves from blocked to OPEN — the design is
          landed, the implementation (allowlist cache key + scheduled warm step)
          is not; AC5 (silent-refusal telemetry)
          now HAS a PR, orch#592, also open — earlier text here saying AC5 had no
          PR is stale. AC1-AC3 remain unstarted.
          On the PatchTST question: the corpus exists and is citable (model#91),
          but no verdict on it is currently admissible — model#85 (UNDERPOWERED)
          and model#87 (CLOSE) were both computed with the defective harness, and
          model#90's corrected re-derivation is itself still under review. The
          third-blend-leg question therefore stays OPEN, behind the standard gate
          chain, with no result to carry forward.
