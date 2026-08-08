# Routing table v0 + the 120-cell cube

STATUS:    delivered. The operator's requested final artifact exists: one
           table, regime x sector -> canonical ID, versioned in git, flip
           rules attached. v0 is honestly all-panel with the bear column
           policy-locked.

WHAT:      doc/design/2026-08-08-routing-table-v0.md (the table + flip
           rules; one row per sector_map sector — ten cube sectors plus
           three sub-floor sectors footnoted), data/2026-08-08-cube-v1.csv
           (120 cells) + re-runnable derivation: regime-posterior input
           committed as data/2026-08-08-regime-posteriors.csv, output
           written repo-relative; OHLCV stays read-only machine-local.
           Re-run regenerates the committed cube CSV byte-identically
           [VERIFIED — git diff clean after re-run, 2026-08-08].

WHY/DIR:   Operator: "最终应该有一个table来记录什么regime什么sector用哪个
           model" and "每个sector在每种regime下每个模型都应该试一下". Both
           delivered: the table exists; the cube tried 120 cells (10 sectors
           x 3 operative regimes x 4 style proxies, 2017-2026 daily) and
           ZERO cleared |t|>=2 — strongest datacenter_hw x bull_calm x
           mom63 at t +0.76 over 9.5 years.

EVIDENCE:  artifact:      cube CSV + derivation; production HMM posteriors
                          (argmax never selects choppy: 0/2347 days)
           prod or exp:   experiment — read-only over prod data
           existing data: no routing table existed; no regime-conditioned
                          style cube existed
           best-known?:   yes — first full cube with production regime labels
           scope:         design + research docs; zero production surface

TESTS:     none — research + registry-referencing design doc. Style proxies
           deliberately named *_proxy, not registry IDs.

NEXT:      operator decisions queued: (a) G-E pivot (same-window cash drag
           ~$4,820/yr [VERIFIED — prior work, orch#914 r3,
           doc/research/2026-08-08-pocket-layer-return-space.md] is the
           record's only correction-robust large number);
           (b) whether any cube cell earns a policy-grade `~candidate` mark
           despite t<2 — flip rules and fragility guard are in the doc.
