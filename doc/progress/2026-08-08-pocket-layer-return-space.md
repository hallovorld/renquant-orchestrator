# Pocket layer return space — r2: both review fixes + a fragility finding

STATUS:    delivered (r2). Both codex findings on orch#914 fixed; the fixes
           surfaced a composition-fragility finding that withdraws the r1
           "chips are a trend pocket" read in BOTH directions.

WHAT:      research doc rewritten as r2: (1) rotation turnover now counts
           full-basket membership changes (r1 missed 54 top-2 changes);
           (2) cash drag benchmarked on its own 62-day window (universe
           +11.63% total there -> missed ~$998 in the window, ~$4,839/yr at
           the window rate — LARGER than r1's cross-window figure);
           (3) NEW: restoring 43 names silently dropped by a missing
           dividend column (bare-except defect, mine) flips every
           within-pocket style spread — ai_chip momentum +16pp -> −18pp,
           reversal −24pp -> +28pp, all |t|<=0.2. Style spreads carry no
           policy weight in either direction.

WHY/DIR:   codex review r1 (two blocking findings) + the composition
           discovery during the fix. The routing-table candidate (chips x
           momentum) is WITHDRAWN; routing table v0 is honestly all-panel.

EVIDENCE:  artifact:      corrected derivation script (provenance-only,
                          machine-local OHLCV, 157 names, 1910 days)
           prod or exp:   experiment — read-only
           existing data: supersedes r1 of this same record
           best-known?:   yes — r2 replaces r1 wholesale; r1's style table
                          is withdrawn inside the doc, visibly
           scope:         research + this progress doc; no production surface

TESTS:     none — research. The script reruns end-to-end on this machine;
           numbers in the doc are its verbatim output.

NEXT:      Land this r2, then drive G-E (task #24) as the return-space P0 —
           the cash drag is the only correction-robust large number in the
           record — pending operator confirmation.
