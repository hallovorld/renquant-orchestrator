# S8 second half — orchestrator pick-table regeneration driver (run-gated on backtesting #59)

STATUS:   BUILT + TESTED, **NOT RUN** — the real regeneration is a separate landing action
          gated on backtesting #59 (`feat/sanity-dump-predictions`) merging. The driver
          preflights that gate mechanically and refuses to score without it. No production
          input was touched; no scoring was executed anywhere (tests mock the subprocess seam).
WHAT:     `scripts/regen_oos_pick_table.py` — the THIN orchestrator driver for the durable OOS
          pick table (#231 Term EXEC row S8; direction-decision §4). It composes the exact
          backtesting #59 invocation (`analyze_manifest_sanity_placebo --dump-predictions`
          against `walkforward_manifest_gbdt_prod_recipe_v2.json`, umbrella-tree inputs,
          output `data/exp/oos_pick_table_recipe_v2.parquet`) and enforces, in order:
          (0) hard refusal of any output not under `<umbrella>/data/exp/` (no override; the
          driver also never passes `--allow-production-path`); (1) a mechanical #59 run-gate
          preflight (`pick_table.{build_pick_table_manifest, verify_pick_table,
          canonical_table_content_hash, default_sidecar_path}` + `analyze_manifest(
          dump_predictions=...)`); (2) staging-path write (`__staging` names chosen so the
          contract's `default_sidecar_path` cannot clobber the committed RenQuant#430
          sidecar); (3) FAITHFULNESS GATE — regenerated `genuine_ic` (`aligned_real_60_ic −
          placebo_60_ic`, read from the sanity gate's own JSON output) must reproduce the
          committed 0.0417 to ±0.001 (the A1 bar), hard-fail otherwise; (4) row-count sanity
          (508 dates exact, 147,066 rows ±1%); (5) staging→final promotion, then post-write
          `verify_pick_table` on the FINAL artifact; (6) report-only comparison of the fresh
          canonical content hash vs the committed #430 anchor. `--dry-run` prints the exact
          commands/paths and executes nothing. Tests: `tests/test_regen_oos_pick_table.py`
          (20 cases — dry-run correctness, faithfulness pass/fail/fail-closed, counts drift,
          exp-path refusals, mocked end-to-end promotion + verification wiring, closed run
          gate, exit-code mapping).
WHY/DIR:  #231 S8's second half: RenQuant#430 owns the umbrella-side generator; the #59 review
          moved the owning contract into renquant-backtesting and made the umbrella generator
          a thin wrapper. This driver is the orchestrator-side regeneration entry point so the
          durable Track-A evidence table can be regenerated (and PROVEN faithful, not merely
          re-shaped) from the control-panel repo, without forking any scoring/hash logic.
          KNOWN DISPUTE carried honestly: per RenQuant#431 the committed genuine_ic bar itself
          is disputed (leak-controlled rerun +0.076 overall / +0.044 BULL_CALM vs cited
          figures, sign disagreement in BULL_CALM). The driver therefore treats a faithfulness
          hard-FAIL as a legitimate, expected outcome until #431's reconciliation protocol is
          frozen and executed — it fails closed rather than loosening the bar.
EVIDENCE:
          artifact:      `scripts/regen_oos_pick_table.py`, `tests/test_regen_oos_pick_table.py`
                         (this PR); contract read read-only from renquant-backtesting branch
                         `feat/sanity-dump-predictions` @ 5e56808e (`src/renquant_backtesting/
                         analysis/pick_table.py`, `analyze_manifest_sanity_placebo.py`).
          prod or exp:   EXP only — output pinned under `data/exp/` (the RenQuant#430-sanctioned
                         experiment area); the driver mechanically refuses `data/` outside
                         `data/exp/`, `artifacts/`, and out-of-umbrella targets. No prod path
                         is writable through it.
          existing data: committed reference values read from the umbrella tree: genuine_ic
                         0.041680989995517316 (`metadata.wf_gate_metadata.model_placebo_profile
                         .pooled.1x.genuine_ic`, prod GBDT bundle staging JSONs) and the #430
                         sidecar `data/exp/oos_pick_table_recipe_v2.manifest.json` (147,066
                         rows / 508 dates / content anchor). No new data produced.
          best-known?:   best available interface pin — the #59 branch is still IN REVIEW, so
                         the contract could change before merge; the preflight makes any drift
                         a hard run-gate failure instead of a silent mis-invocation.
          scope:         driver + tests only; NO real run, NO scoring, NO live-tree writes.
                         Full suite: 1278 passed, 3 skipped (make test with sibling srcs).
NEXT:     (1) after backtesting #59 merges: execute the real regeneration (landing action) —
          `python3 scripts/regen_oos_pick_table.py` (dry-run first), using the umbrella venv
          interpreter via `--python`; (2) record the faithfulness verdict either way — a FAIL
          feeds RenQuant#431's reconciliation, it does not license loosening `--ic-tolerance`;
          (3) S9 (Track A conditional pick-quality test) stays blocked on #431 regardless of
          this driver's outcome (#231 dependency DAG).
