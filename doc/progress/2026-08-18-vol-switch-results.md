# Vol-switch confirmatory — the authorized one-shot run: CONFIRMED

STATUS:    delivered. The ONE authorized execution of the frozen, reviewed
           runner (prereg orch#1001, runner orch#1002) has happened; the
           vol-switch confirmatory's one-shot budget is SPENT. Verdict under
           the frozen §5 decision rule: **CONFIRMED** — which authorizes ONLY
           a design PR for a vol-gated bull deployment window
           (shadow/sizing-first, operator-gated; no direct production
           change). Results + memo only — no src change, no config, no live
           surface.

WHAT:      Executed `doc/research/data/2026-08-18-vol-switch-derivation.py`
           VERBATIM from orchestrator main `88c589c0` (byte-identity vs a
           freshly FETCHED origin/main asserted by the runner's own V2 guard;
           file sha256 `e6002a85…7fe296`), once, under caffeinate, in an
           isolated worktree, against read-only local stores. Commits the
           runner's four outputs (results JSON + weekly-series CSV +
           block-table CSV + refit-ledger JSON, all new files) and the
           results memo `doc/research/2026-08-18-vol-switch-results.md`.

           Verdict (primary corpus 2017-01-03..2023-09-29, fixed ON
           definition vol20 > 0.135, 19 ON-eligible blocks): CONFIRMED —
           positive control +0.13919 (checked FIRST, V13); P1 ON-state block
           mean +0.18400 with NW t=+1.952 (crit 1.734) AND stationary-
           bootstrap q05=+0.02096, no disagreement, winsorized guard
           +0.03609 ≥ 0; P2 paired ON−OFF diff +0.12769, block-t=+2.378 over
           11 paired blocks; guards N=19 ≥ 15, ρ̂₁=+0.205, ESS=12.55 ≥ 6.
           Recorded honestly: the non-decisive expanding-tercile sensitivity
           variant FAILS its P1-style legs (NW t=+1.533, boot q05=−0.011)
           and its P2-style t (0.790) on the same corpus — the certification
           is specific to the frozen fixed threshold; this bound travels
           with any downstream design PR. Runtime 168.7 s; all V1–V14 guards
           passed, exit 0, zero deviations, no fix-and-rerun.

WHY/DIR:   The last standing near-term bull-alpha lead after the kill
           machine closed 0/5 zero-cost candidates (#992, #999, #1000).
           Prereg §6 sequencing (prereg merged #1001 → runner committed AND
           reviewed #1002 → ONE run on the merged copy) held end to end —
           third consecutive family run under the freeze-then-review-then-run
           contract. CONFIRMED's §5 consequence is narrow by construction:
           design PR only; survivor-clean confirmation deferred to the
           PIT-universe / live-shadow stage; nothing deployment-shaped is
           authorized beyond the design document.

EVIDENCE:
  artifact:      doc/research/data/2026-08-18-vol-switch-results.json
                 + …-series.csv + …-blocks.csv + …-refit-ledger.json
                 (written by the run); doc/research/2026-08-18-vol-switch-results.md
  prod or exp:   exp — the authorized one-shot confirmatory; isolated
                 worktree of main `88c589c0`; read-only inputs (panel
                 parquet `870f68eb…29bf7e`, served artifact
                 `6461b827…546d15` fingerprint sha256:f8fb2259b2bf1537,
                 SPY store `68665523…b0ee`, production-trainer helpers
                 imported read-only); wrote only doc/research/data/ inside
                 the worktree (V14); no production path touched.
  existing data: the merged prereg's frozen geometry (1,697 td / 821 ON days
                 / 28 blocks / 19 eligible / 340 weekly dates) reproduced
                 EXACTLY by the run's V9 recompute; the formation bundle
                 doc/research/data/2026-08-18-tail-switch-exploratory/
                 (+0.67..+0.76 exploratory effect — the realized confirmatory
                 effect +0.184 is smaller but clears the frozen bar); SPY
                 store digest identical to the #992/#999 runs.
  best-known?:   yes — the only measurement of this hypothesis on the
                 strictly pre-exploration corpus, produced by the reviewed
                 frozen runner with every guard green; per the one-shot rule
                 it is FINAL for this corpus. The known limits are recorded
                 in the memo: definition-sensitivity (expanding variant
                 fails) and state-dependent survivorship (undischarged here,
                 deferred to PIT/live-shadow by the prereg itself).
  scope:         "this is the authorized vol-switch confirmatory run, exp,
                 on the survivor-tilted current-panel corpus; CONFIRMED
                 authorizes ONLY a vol-gated deployment-window design PR
                 (shadow/sizing-first, operator-gated) — no production
                 change, no sizing change, no deploy, and the PIT-universe /
                 live-shadow stage still gates anything real."

TESTS:     none added/changed — `tests/test_vol_switch_runner.py` (merged
           with #1002) already asserts one-shot behaviour on tmp_path
           fixtures rather than repository state (the #999 lesson), so the
           authorized run's committed outputs break nothing: 54 passed on
           this head before commit. Full `make test` run on this head —
           pass count in the PR body.

NEXT:      per the merged prereg §5: draft the vol-gated bull deployment
           window DESIGN PR (shadow/sizing-first, operator-gated), carrying
           the two recorded risk bounds (expanding-variant failure;
           state-dependent survivorship) and the PIT-universe / live-shadow
           confirmation stage as its activation gate. The one-shot marker
           (V1) forbids re-execution against the committed output paths.
