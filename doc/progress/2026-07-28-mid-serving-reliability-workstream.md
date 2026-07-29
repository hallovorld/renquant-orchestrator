# Progress: MID-tier update — serving-reliability workstream + PatchTST serving read

STATUS:   CONFIRMED and merge-ready. The workstream was proposed on 2026-07-28;
          operator confirmed opening it directly in-session (2026-07-28/29, in
          response to an explicit recommendation to proceed) — this PR carries
          the POST-decision record for the workstream itself.
          CORRECTION (visible, not silent, per long-term-agreements.md entry 10):
          an earlier version of this doc and of `model-edge.md` claimed the
          frozen 43-fold PatchTST evaluation (model#85) had already run and
          returned UNDERPOWERED, attributed to a Modal run
          (`wf-pt-b4e47e2c-batch1`, "$18.30 of the $25 cap"). That run does not
          exist under any name in this repo's history; the checkpoint path the
          analysis script reads from does not exist in the live checkout; and
          model#85's own statistical design (dependence-correct estimator,
          calibrated-vs-raw threshold) was still under active review at the time
          — a result cannot be valid for a test whose design isn't frozen yet.
          Retracted, not restated. The 43-fold evaluation has NOT run. Only the
          workstream proposal + the readonly serving-preflight diagnostic below
          are confirmed; the PatchTST capability question stays open pending
          model#85 landing and the corpus actually being generated and scored.

WHAT:     (1) New workstream `doc/memory/mid-term/serving-reliability.md` with 5 proposed
          ACs; (2) `_north-star.md` lists it as a peer workstream and states why;
          (3) `model-edge.md` gains the 2026-07-28 fresh-PatchTST end-to-end serving read
          (diagnostic only — see correction above).

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
          still an open, unmerged design) — cold rebuilds observed at ~795s and
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
          this does NOT mean all 5 are satisfied. AC4 (warm serving path) depends
          on orch#589's cache-key design, itself an open, unmerged PR blocked on
          its own provenance/rebase conditions; AC4 is PENDING until #589 (or a
          successor) is separately approved. AC5 (silent-refusal telemetry) is the one
          with no PR yet and is the direct antidote to how #541 stayed invisible for
          months. The PatchTST question moves to `model-edge.md`'s third-blend-leg
          test via the standard gate chain: model#85's statistical design needs to
          clear review, then the 43-fold corpus needs to actually be generated
          (model#82/backtesting#81/#82 dispatch tooling is ready) and scored against
          the frozen design — neither has happened yet.
