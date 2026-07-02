# RS-6 weekly KPI scorecard — research PR

STATUS:   research deliverable (RS-6 of the unified 107 master plan #231): script + first
          committed measurement + standing definitions. Read-only against all production
          inputs; no code/config/broker/risk/sizing change.
REVISION: r1.
WHAT:     `scripts/kpi_scorecard.py` — one read-only command emitting a dated JSON scorecard
          for every #231 §0 state-vector metric (each with value + source + method +
          measured_at; every metric degrades to {"status":"unavailable","blocker":...}
          instead of crashing) to `doc/research/evidence/kpi_scorecards/kpi_<date>.json` +
          a compact printed table. `doc/research/2026-07-02-rs6-kpi-scorecard.md` — the
          per-metric definition table (metric | source | exact query/method | cadence |
          owner), the first scorecard's values, and 7 stated limitations. First measurement
          committed: `doc/research/evidence/kpi_scorecards/kpi_2026-07-02.json`.
WHY/DIR:  #231 §0's state vector and §4's standing measurement plan name the metrics but had
          no runnable instrument — "gate-verdict age" and "ledger coverage" were prose facts,
          not queries. RS-6 freezes exact, reproducible definitions BEFORE the tasks they
          read out (S4 verdict, S5 ledger, M4 recentering, N1/N2 collectors) land, so their
          ACs are judged by a pre-existing instrument rather than post-hoc measurement.
          Definition constants are pinned in the script; changing one requires a PR touching
          the research doc, not a silent edit.
EVIDENCE: first scorecard (2026-07-02, all 8 metrics ok, none unavailable):
          deployed_fraction 0.214 (trailing-5 0.223; target ≥95% incl. sleeve) ·
          floor_gap_vs_spy +3.48pp of book foregone (46 sessions 04-24→07-01, avg cash
          weight 72.1%, SPY span +4.5%; descriptive, not annualized per RS-1 §1) ·
          gate_verdict_age "mute since 2026-05-18 (45 days)" (freshest serving-artifact
          stamp is diagnostic_only=true/passed=false, run_at 06-22; gate_verdicts table
          0 rows) · ledger_coverage 86.2% fwd_20d over 5,199 aged rows (S5 AC ≥95%) ·
          pit_accrual_days 1 (2026-07-02) · collector_liveness live (pilot ticks 0.01h,
          rq105 quote log 0.42h but zero-byte-flagged) · calibrator_sign_laundered 44
          (2026-07-01 run — counter found in pipeline_runs.counters_json, NOT pending-S5)
          · buy_side_decision_tc 0.288 mean (SE 0.167, n=4 measured of 10 canonical runs;
          post-retrain runs unmeasurable, ≤2 admission survivors).

          Canonical evidence-block subfields (`doc/AGENT-RETROSPECTIVE.md` §4(b)):
          ```
          artifact:      doc/research/evidence/kpi_scorecards/kpi_2026-07-02.json
                         (+ scripts/kpi_scorecard.py, the generating instrument)
          prod or exp:   experiment / research readout — reads prod stores (runs.alpaca.db
                         mode=ro, serving artifact JSON, log mtimes, snapshot dirs) but
                         changes nothing live
          existing data: no prior committed KPI scorecard exists; the #231 §0 table cited
                         one-off measurements (25% deployed 07-01, "gate mute since 05-18",
                         44/90 laundered) — this PR's values are consistent with all of
                         them under pinned definitions
          best-known?:   yes for the definitions (first standing instrument); the TC number
                         is explicitly EXPLORATORY (POC-S-TC round-3 caveats apply
                         verbatim, imported not re-implemented)
          scope:         weekly standing readout of the state vector, vs no existing
                         instrument; floor_gap_vs_spy deviates from RS-1 §1's snapshot
                         (72.1%/3.48pp vs 75.5%/2.88pp — RS-1 didn't pin canonical-row
                         selection; this script does, and the delta is stated in the
                         research doc §3.2 rather than reconciled away)
          ```
          [VERIFIED — ran `scripts/kpi_scorecard.py` once in this session against the live
          read-only stores; every number above is from the committed JSON, re-printed from
          the file (not from memory); the wf_gate_metadata stamp fields were read directly
          from the serving artifact; sqlite opened mode=ro.]
NEXT:     Codex review. Then: run weekly on a trading day (candidate for the existing
          weekly-monitor launchd pattern — scheduling is a separate ops PR, not this one);
          §4 monthly re-baseline reads the accumulated JSONs; when S4/S5/M4 land their ACs
          are read from THIS instrument; the zero-byte rq105 quote log wants a look at the
          next close; buy_side_decision_tc graduates to a per-run ledger series with S5.
