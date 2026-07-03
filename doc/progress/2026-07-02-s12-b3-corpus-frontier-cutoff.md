# S12 B3 — derive the weekly PatchTST retrain cutoff from the corpus frontier

STATUS:   BUILT + TESTED — orchestrator half of the two-PR B3 fix (umbrella wrapper wiring is
          the companion RenQuant PR; merge THIS first, then the wrapper, which fail-closes with
          an explicit "pin predates" error until the orchestrator pin/sync advances). No retrain
          was run; live data touched read-only (verification only).
WHAT:     `renquant_orchestrator.patchtst_weekly_cutoff` — a standalone `python -m` module (the
          `build_patchtst_wf_manifest` invocation convention) that derives the WEEKLY-mode
          retrain cutoff from the TRAINING CORPUS itself instead of the static WF source
          manifest: (1) frontier = max fully-labeled `date` in the corpus parquet (label-NaN
          tail rows never inflate it; reads only `date` + label columns); (2) quantized DOWN to
          the Monday of its ISO week — the grid all 39/39 static-manifest cutoffs sit on — so
          intra-week reruns are idempotent; (3) FAIL-CLOSED staleness: the implied bar frontier
          (`frontier + lookahead_days` BDays, mirroring the #213 monitor's horizon-adjusted
          `label_observation_cutoff` semantics, lookahead parsed from the label name) must be
          within `--max-staleness-days` (default 28) of today; (4) the static manifest is ONLY a
          `--lower-bound-manifest` sanity (derived cutoff must not regress behind its tail) and
          can NEVER source the cutoff — corpus-missing refuses with exactly that message;
          (5) stdout carries ONLY the ISO cutoff (command-substitution safe), diagnostics on
          stderr, non-zero exit on any refusal. Everything downstream is untouched: seeds,
          embargo, trainer/calibrator argv, and `build_patchtst_wf_manifest` semantics are
          unchanged (cutoffs stay date-based end to end — the `val_tail_pct` lesson).
WHY:      S12 diagnosis §4-B3 (`doc/research/2026-07-02-s12-panel-refresh-diagnosis.md`, PR
          #257): `weekly_retrain_patchtst.sh` pinned `LATEST_CUT` to the static
          `walkforward_manifest_v2_20260602.json` tail (2026-03-09), so even after the B1 corpus
          refresh (RenQuant #434 + base-data #31) the retrain would advance ONCE, then re-train
          the same cutoff weekly, `cutoffs_advance` correctly refuses, and the served pin
          re-freezes. §5.3 remediation: derive the cutoff from the refreshed corpus's max
          labeled date. Logic lives here (not in bash) because the wrapper's own contract is
          "no training logic in this wrapper — delegate to the orchestrator-owned pipeline" and
          the umbrella takes no new code.
EVIDENCE: `tests/test_patchtst_weekly_cutoff.py` (14 cases: fresh corpus ⇒ advanced
          Monday-grid cutoff past the static tail; stale corpus ⇒ fail-closed STALE;
          manifest-only ⇒ refuses with "NEVER source the cutoff"; NaN-tail, regressed-frontier,
          future-dated, all-NaN, missing-lower-bound, label-horizon, quantization, CLI
          stdout/exit contracts). Full suite green: 1292 passed, 3 skipped. Ground-truth
          verification (read-only): real frozen corpus (frontier 2026-02-10) ⇒ FAIL-CLOSED
          "bar frontier 2026-05-05, 58d old > 28d"; relaxed-staleness ⇒ the lower-bound guard
          fires instead (2026-02-09 < 2026-03-09); prod fund panel (the B1 recipe's source,
          labeled frontier 2026-04-02) ⇒ derives 2026-03-30, a genuine advance past the frozen
          tail.
LANDING:  S12 order — B1 (base-data #31 → pin → RenQuant #434) → B2 (RenQuant #433) → B3 (this
          PR → orchestrator pin/sync → RenQuant wrapper PR) → then the single umbrella-ops
          landing command on the live tree: `bash scripts/weekly_retrain_patchtst.sh`.
