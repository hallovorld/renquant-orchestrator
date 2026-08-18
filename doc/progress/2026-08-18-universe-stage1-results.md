# Universe-extension Stage 1 — the ONE authorized run: DEPRIORITIZED (transfer bar fails)

STATUS:    the separately-authorized single execution of the merged, reviewed
           runner (spec orch#995; runner orch#998; the #990
           freeze-then-review-then-run sequencing completed end-to-end). The
           one-shot budget is SPENT — U10's marker is armed by the committed
           outputs; U11 verified the executed bytes against freshly-fetched
           origin/main `9d73d546` before any work. Exit 0, one execution, no
           fix-and-rerun, runtime 782.8 s.

WHAT:      Commit the run's outputs
           (`doc/research/data/2026-08-18-universe-stage1-results.json` +
           `…-obs.csv`), the results memo
           (`doc/research/2026-08-18-universe-stage1-results.md`, verdict
           first), the VERDICTS.md row (ledger's own same-PR rule), and the
           one designed test transition (the runner-PR "ships un-run" test now
           asserts the post-run invariant: U10 REFUSES; 32/32 runner tests
           pass; the runner file itself untouched).

VERDICT:   **DEPRIORITIZED** (h=60, Arm A, frozen §5 rule) — reason string
           from the run: `transfer: no costable bucket with ArmA >= ArmW`.
           Bars 1–3 PASSED (net Δ +0.007517 > 0; block-t 1.580 ≥ 1.0; 73.7%
           of 19 blocks positive); bar 4 FAILED: best costable bucket (≥$25M
           ADV) gross Δ +0.013026 vs Arm W +0.071816 (0.18×), $10–25M bucket
           NEGATIVE (−0.0217), $5–10M bucket no data at the 10-name floor.
           Arm-W positive control PASSED BEFORE Arm A was computed: +0.68298σ
           ≥ frozen floor +0.08013 (2.84× ref — under the 3× telemetry line;
           in-sample inflation declared expected in the frozen U3 rationale).
           Per spec §1 this parks the down-cap thesis at ~zero cost — it
           kills nothing, authorizes nothing (Stage-2 PIT program NOT
           unlocked, no serving/retrain/capital change).

WHY/DIR:   Universe-extension workstream (operator-directed "真正的alpha").
           The structural down-cap thesis is now measured, not assumed: the
           served pin's tail-spread edge transfers out-of-ticker at ~1/5
           watchlist strength in the MOST institutional extension band and
           decays to negative below it — the opposite gradient to the thesis.
           Arm B shows the 14 fundamental-family features (not ticker count)
           are load-bearing. Both facts recorded for any future re-pitch,
           which requires a NEW frozen spec (out-of-sample-in-time design)
           and cannot reuse this corpus.

EVIDENCE:
  artifact:      results JSON + obs CSV (sha256 `8a058490…a7c7` /
                 `e64054bc…a1cd`, recorded in the memo §8) + the memo + the
                 VERDICTS.md row. Run log retained in session scratch.
  prod or exp:   **exp** — read-only on every input; outputs land only in
                 this isolated worktree's doc/ tree; corpus intermediates
                 went to the runner's RQ_STAGE1_SCRATCH (session-isolated,
                 outside every repo; U7 write-guarded every write). No
                 serving surface, no data store, no live config touched.
  existing data: [VERIFIED — this run's own outputs] U1–U11 all passed; U3
                 control +0.68298σ before Arm A; U2 cascade landed EXACT on
                 609/1,955/145; 233 cross-sections (rule governs vs spec's
                 ~231, recorded); one h=60 obs edge-trimmed (2026-02-13,
                 pre-declared); 19/19 + 58/58 blocks with data; zero dropped
                 cross-sections (floor_paired=0 everywhere).
  best-known?:   yes — the merged reviewed runner executed VERBATIM (byte-
                 verified vs fetched origin/main by U11, its own guard);
                 caffeinate held the machine awake; every number in the memo
                 carries a provenance tag; deviations (U1 pin reading, 233 vs
                 231, the one edge-trim, runtime 13 min vs ~1h estimate,
                 cascade intermediate-stage counts) reported, not papered
                 over.
  scope:         docs + run outputs + one designed test flip. Merging records
                 the verdict; it authorizes nothing further and changes no
                 behavior anywhere.

TESTS:     tests/test_universe_stage1_runner.py — 32/32 pass after the
           designed post-run flip of the ships-un-run invariant test
           (`test_one_shot_spent_outputs_committed_marker_armed`: U10 must
           now REFUSE). No other code touched.

NEXT:      codex review → merge. The thesis sits DEPRIORITIZED in the ledger;
           the only path back is a NEW frozen spec addressing the
           in-training-ticker (W) vs out-of-ticker (A) asymmetry on a PIT
           universe — never a re-run of this corpus (U10 armed).
