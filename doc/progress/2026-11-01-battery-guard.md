# 2026-11-01 — battery guard: page while the Mac is still on (hibernate took 104/105 dark for 5 days)

STATUS:   delivered, awaiting review. The launchd job is NOT installed by this PR (install is a separate
          ask-first landing); until installed, the drift scan will list the plist as declared-but-not-loaded.
WHAT:     `ops/battery_guard.py` (parses `pmset -g batt`; pages once per discharge band 40/25/15 %, resets when
          charging; unparseable output pages "UNREADABLE" and exits 1), plist `com.renquant.battery-guard`
          (every 900 s), manifest entry + digest, 6 tests.
WHY/DIR:  a powered-off machine cannot alarm, so the only place to catch a battery death is before it. Two
          weekday outages with no warning: 2026-09-11 (20 h, 1% -> Low Power Sleep) and 2026-10-27 (12:49 PDT
          Low Power Sleep -> hibernate until the charger returned 2026-11-01 08:32 = 5 days, zero daily/intraday/
          105 runs, no orders). The ops layer saw nothing until the next successful run.
EVIDENCE: see below.
  artifact:      ops/battery_guard.py, ops/renquant104/com.renquant.battery-guard.plist, ops/launchd_manifest.json, tests/test_battery_guard.py.
  prod or exp:   exp — read-only monitor; writes ~/.renquant/battery_guard.json (episode state) only.
  existing data: pmset -g log 2026-10-27 12:49:53 "Entering Sleep state due to 'Low Power Sleep'" then next Wake 2026-11-01 08:32:23 "Wake from Hibernate"; logs/daily_104 has no 2026-10-28..30 file; runs.alpaca.db last pipeline run 2026-10-27 [VERIFIED 2026-11-01]. 1100 launchd/plist/drift-related tests pass on this branch.
  best-known?:   yes for detection; it does not prevent the outage (that is physical: keep it plugged in).
  scope:         orchestrator ops + tests; no data/config/state of the trading system touched.
NEXT:     merge, sync -run, then (ask-first) copy the plist to ~/Library/LaunchAgents and bootstrap it.
