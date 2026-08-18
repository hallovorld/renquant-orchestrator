# 2026-08-18 — vol-window activation-evidence readout (orch#1004 impl PR 2, orchestrator half)

STATUS:    delivered — readout script + synthetic-fixture tests. NOTHING is
           scheduled or deployed by this PR (no plist install, no
           `ops/launchd_manifest.json` entry — see §3); the paired umbrella
           PR wires the lane itself into daily_104.sh (Step 5f), and both
           halves activate only through operator-gated deploy steps.
WHAT:      `ops/renquant104/rq104_vol_window_readout.py` — the design-AC3
           readout over the vol-window lane's evidence stream: sweeps the
           lane's per-session license ledger
           (`backtesting/renquant_104/logs/vol_window_license.jsonl`,
           pipeline#294), freezes each session's lane universe from the
           lane's own runs DB (`data/runs.alpaca_shadow_vol_window.db`),
           appends one idempotent row per session to a HASH-CHAINED
           append-only ledger (`data/rq104_vol_window_readout/ledger.jsonl`),
           back-fills realized top-decile spreads from
           `ticker_forward_returns` once sessions mature on the table's own
           session calendar, and maintains the ACTIVATION-EVIDENCE counter.
WHY/DIR:   orch#1004 approved design §5 AC3 / §7 impl PR 2 (readout half):
           the shadow lane's ledger must itself accrue the pre-committed
           activation burden — >=20 ON-state sessions with positive realized
           top-decile spread `[DERIVED — orch#1001 prereg §5 base of the
           doubled PARTIAL burden; orch#1004 §5 AC3]` — before any operator
           ask. The rq104_blend_readout.py (pipeline#213) pattern is the
           declared template.
EVIDENCE:  see §4 below.
NEXT:      operator-gated deploy batch (§3); pipeline-side
           `ALLOWED_BROKERS` tag registration (declared in the paired
           umbrella PR's progress doc §3) before the lane's first session.

## 1. The estimand, as frozen by the reviewed design

- DECISIVE per-session readout: realized **h=60** top-decile spread —
  mean(fwd_60d over the session's recorded top decile) minus mean(fwd_60d
  over the lane's own universe) — the certification's horizon (`fwd_60d_excess`
  label, 60-td blocks) `[VERIFIED — prior work, orch#1001 prereg §3;
  orch#1003 results §8 pins; re-pinned in orch#1004 AC3 corrections]`.
- VELOCITY diagnostic: realized **h=20** spread in the same row — earlier
  visibility, NEVER decisive (the horizons measurably disagree in this
  system, orch#999; restated in orch#1004 AC3). The counter output prints
  both, labeled.
- Counter: ON-state sessions (`vol_verdict_on`, the certified strict
  vol20 > 0.135 verdict recorded by pipeline#294 at decision time) with
  positive realized DECISIVE spread, against the frozen >=20 burden; a
  window-restricted sub-count (ON ∧ ¬BEAR ∧ no kill) is printed alongside
  so the activation ask can show both cuts.
- Declared deviations, restated per AC3: universe-mean baseline (not the
  certified DGTW-adjusted construction), and the coverage rule below.

## 2. Mechanics (mirroring rq104_blend_readout.py, deviations declared)

- Session rows idempotent per date; sweep-based (every license-ledger date
  not yet in the readout ledger appends, oldest first) rather than
  today-only — the license ledger is authoritative for session identity
  here, unlike the blend readout's MLflow-artifact locator, and the lane may
  legitimately idle for weeks (design §4).
- HASH CHAIN: append-time payload (session identity, window state, top
  decile, frozen universe, `prev_sha`) is immutable;
  `entry_sha = sha256(canonical(payload))`, genesis `"0"*64`. Maturation
  touches ONLY mutable realization/telemetry fields; the chain is verified
  on every run BEFORE any write and a break alarms (exit 2) with the ledger
  left untouched. (The blend readout's ledger is not chained; the chain is
  this readout's addition, motivated by the ledger being the activation
  ask's evidence of record.)
- Maturity aging: the fwd table's OWN distinct-session calendar
  (`_aged_dates`, the Codex-BLOCKER-hardened blend technique — `fwd IS NOT
  NULL` is not aging evidence); 61 sessions for h=60, 21 for h=20.
- Realization per horizon: lane run found ∧ aged ∧ EVERY top-decile name
  resolvable ∧ universe coverage >= 0.90 (the declared floor; the universe
  mean is then over resolvable names, shortfall recorded per row). Strict
  100% universe coverage would let one lane-vs-backfill watchlist drift
  name zero the evidence stream forever — the failure shape the blend
  readout documents in its telemetry comment.
- Silent-feed parity (GOAL-1 AC3 shape), BOTH directions: license session
  with no full lane run (>=80 scored candidates, the house full-run bar) →
  alarm; full lane run with no license row → alarm ("the flag did not
  evaluate on a session the lane ran"). Exit 2; the row (where applicable)
  is still appended `lane_run_found=false` so the gap itself is on the
  record.
- Cross-field parity: the license row's own `universe_n` vs the lane DB's
  frozen universe count, recorded per row (`universe_parity`).
- READ-ONLY on every production surface: both SQLite handles open
  `mode=ro`; writes only the readout ledger (atomic `os.replace`, and only
  when rendered bytes differ — the blend readout's read-must-not-mutate
  fix, kept verbatim in intent).
- Not-yet-deployed is INFO exit 0 (license ledger and lane DB both absent);
  the pin advance that births the lane is a separate operator step and the
  readout must not page on a lane that does not exist yet.

## 3. Deliberately NOT in this PR: scheduling

`ops/launchd_manifest.json` entries assert DEPLOYED state: the run-surface
drift scan alarms on "manifested job missing from disk"
(`ops/run_surface_drift_check.py::check_launchd_disk`, the GOAL-5 AC2
surface), so a pending-deploy manifest entry would page daily until the
operator installs the job — manufacturing exactly the alarm the CONTAINMENT
rules say never to silence by editing the manifest outside review. Every
existing `ops/renquant104/*.plist` is manifested AND installed; there is no
house pattern for a committed-but-unmanifested plist, so this PR ships
neither. THE DEPLOY STEP (operator-gated, one reviewed batch, the
com.renquant.rq104-blend-readout precedent): (1) write
`ops/renquant104/com.renquant.rq104-vol-window-readout.plist` (daily,
after the daily-full completes — the blend readout's slot), (2) install to
`~/Library/LaunchAgents` + `launchctl bootstrap`, (3) add the
`ops/launchd_manifest.json` entry with `program_args_sha256`, all in the
same batch. Until then the readout is runnable manually:
`.venv/bin/python ops/renquant104/rq104_vol_window_readout.py`.

## 4. Evidence

(a) Conclusion: the AC3 readout exists, computes the frozen burden over the
certified decisive horizon with the h=20 velocity diagnostic recorded and
labeled never-decisive, refuses to attribute foreign-lane rows, alarms on
both silent-feed directions and on ledger tampering, and touches no
production surface.

(b)
- `artifact:` `ops/renquant104/rq104_vol_window_readout.py` +
  `tests/test_rq104_vol_window_readout.py` (this PR). The evidence ledger
  it maintains (`data/rq104_vol_window_readout/ledger.jsonl`) does not
  exist until the lane is deployed and produces sessions.
- `prod or exp:` neither — an ops readout script nothing schedules yet;
  wiring of the lane it reads is the paired umbrella PR; deploys
  operator-gated (§3).
- `existing data:` pattern and constants provenance: blend readout
  mechanics `[VERIFIED — ops/renquant104/rq104_blend_readout.py @ 622bd914:
  MATURITY_TDAYS=61 convention, _aged_dates, MIN_FULL_RUN_CANDIDATES=80,
  atomic only-if-changed write]`; license row schema `[VERIFIED — pipeline
  origin/main 43a66f8 vol_window_license.py: ledger relpath, row keys
  vol_verdict_on/window_on/top_decile/universe_n/lane_tag]`; lane DB schema
  `[VERIFIED — read 2026-08-18 mode=ro from runs.alpaca_shadow_blend.db:
  pipeline_runs(run_type='live') + candidate_scores(panel_score)]`;
  forward-returns surface lives ONLY in prod runs.alpaca.db `[VERIFIED —
  read 2026-08-18 mode=ro: lane-DB ticker_forward_returns rows = 0; prod =
  21400 rows / 646 dates, fwd_60d present]`; burden constant 20 `[DERIVED —
  orch#1001 prereg §5; orch#1004 §5 AC3]`.
- `best-known?:` honest scope — (i) all tests are synthetic fixtures; the
  script has not run against a real lane ledger because none exists until
  the lane's first deployed session (by design). (ii) The universe-mean
  baseline and the 0.90 coverage floor are declared operational deviations,
  restated in §1/§2 and printed nowhere as certification. (iii) The hash
  chain protects the append-time payload only; realization fields are
  recomputable from the chained inputs + the fwd surface, which is the
  designed trade (maturation must mutate them). (iv) ON-state sessions
  arrive only when the market provides them; a long 0/20 is correct
  behavior, not a defect (design §4).
- `scope:` one new ops script + one new test file + this doc; no deploy, no
  launchd change, no manifest change, no production writes, no change to
  any existing job.

Suite: baseline at origin/main `622bd914` = 6435 passed / 5 skipped /
3 failed (test_goal7_arm_a_producer cwd-revision pin,
test_goal7_arm_b_accrual_probe + test_position_cap_conformance LIVE-surface
record checks — pre-existing on the unmodified worktree, this machine)
`[VERIFIED — run 2026-08-18]`. After this PR = 6459 passed / 5 skipped /
the SAME 3 pre-existing failures (+24 new tests, all passing) `[VERIFIED —
run 2026-08-18]`.

## 5. Files

- `ops/renquant104/rq104_vol_window_readout.py` — new.
- `tests/test_rq104_vol_window_readout.py` — new (24 tests: hash chain
  append/verify/tamper/splice + chain-survives-maturation; session-calendar
  aging; h=20-before-h=60 velocity; spread arithmetic; top-decile and
  coverage-floor refusals; counter ON-classification / window cut / frozen
  burden; lane-tag filter; last-row-per-date; partial-run guard; main()
  end-to-end idempotency, read-does-not-mutate, both parity alarms,
  broken-chain refusal, not-deployed INFO, OFF-session recording).
- `doc/progress/2026-08-18-vol-window-readout.md` — this doc.
