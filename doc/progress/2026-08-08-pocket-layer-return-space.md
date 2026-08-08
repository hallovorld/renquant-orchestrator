# Pocket layer return space — r3: measured cash stats; r2: both review fixes + a fragility finding

STATUS:    delivered (r3). All codex findings on orch#914 fixed; r3 replaces
           the hardcoded live-cash statistics with values measured inside
           the committed derivation (read-only live_state_snapshots query on
           the benchmark's own dates). The r2 fixes surfaced a
           composition-fragility finding that withdraws the r1
           "chips are a trend pocket" read in BOTH directions.

WHAT:      research doc rewritten as r2, then r3: (1) rotation turnover now
           counts full-basket membership changes (r1 missed 54 top-2
           changes);
           (2) cash drag benchmarked on its own 62-day window (universe
           +11.63% total there -> missed ~$994 in the window, ~$4,820/yr at
           the window rate — LARGER than r1's cross-window figure); r3
           measures the cash stats in the script (mean cash 78.0%, median
           80.2%, book $10,961.59) instead of hardcoding them, correcting
           r2's 78.3% / ~$998 / ~$4,839;
           (3) NEW: restoring 43 names silently dropped by a missing
           dividend column (bare-except defect, mine) flips every
           within-pocket style spread — ai_chip momentum +16pp -> −18pp,
           reversal −24pp -> +28pp, all |t|<=0.2. Style spreads carry no
           policy weight in either direction.

WHY/DIR:   codex review r1 (two blocking findings) + the composition
           discovery during the fix. The routing-table candidate (chips x
           momentum) is WITHDRAWN; routing table v0 is honestly all-panel.

EVIDENCE:  artifact:      corrected derivation script (provenance-only,
                          machine-local OHLCV, 157 names, 1910 days; live
                          cash stats via read-only live_state_snapshots
                          query on the benchmark's own dates)
           prod or exp:   experiment — read-only
           existing data: supersedes r1/r2 of this same record
           best-known?:   yes — r3 replaces r2 wholesale; r1's style table
                          is withdrawn inside the doc, visibly, and r2's
                          hardcoded cash stats are corrected visibly
           scope:         research + this progress doc; no production surface

TESTS:     none — research. The script reruns end-to-end on this machine;
           numbers in the doc, including the cash statistics, are its
           verbatim output.

NEXT:      Land this r2, then drive G-E (task #24) as the return-space P0 —
           the cash drag is the only correction-robust large number in the
           record — pending operator confirmation.
