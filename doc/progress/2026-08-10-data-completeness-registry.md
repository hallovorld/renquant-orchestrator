# Per-ticker data completeness registry (PR #TBD)

STATUS:    delivered
WHAT:      Task #15 measurement deliverable: committed derivation script
           (`scripts/data_completeness_registry.py`), registry CSV
           (`doc/research/data/2026-08-10-data-completeness-registry.csv`,
           295 tickers × 31 source metrics over 2023-01-01..2026-08-07), and
           research note (`doc/research/2026-08-10-data-completeness-registry.md`).
           NO pipeline code changes — the registry is the deliverable.
WHY/DIR:   P0 "per-ticker data completeness check in the pipeline": before an
           enforcement hook can exist, the ground truth had to be measured.
           Headline: 9/145 ACTIVE WATCHLIST names are DEGRADED, every one in
           the SEC-fundamentals source (AEP/ASML/SPOT/TSM/CRWV/SPCX zero SEC
           rows → fund vector median-imputed; C fiscal_period_end frozen at
           2025-12-31 — missed Q1-2026 10-Q; V/SPG 3/5 fund cols null; SPCX
           additionally 39 OHLCV bars). Zero active names BROKEN; OHLCV,
           earnings-surprise, sentiment clean for all 147 active names. The
           148-name inactive corpus tail classifies BROKEN naturally via the
           uniform OHLCV-freshness rule (cross-checks the 08-09 ≈144-158
           active-count discovery).
EVIDENCE:  artifact: doc/research/data/2026-08-10-data-completeness-registry.csv;
           prod or exp: measurement over prod data (read-only);
           existing data: 08-09 found ≈144-158 active vs 292 total — this
           registry reproduces the split (144 corpus-active) independently;
           best-known?: first per-ticker × per-source completeness registry;
           scope: "295-name union universe (292 corpus + pinned strategy-104
           watchlist e00d9356), 4 sources, window 2023-01-01..2026-08-07".
           Full §4(b) block + per-number provenance tags in the research note.
NEXT:      Enforcement hook (named follow-up, separate PR/issue): pipeline
           pre-scoring completeness gate — refuse or receipt DEGRADED
           watchlist names instead of silent median-imputation. Data fixes:
           ingest C's Q1-2026 10-Q; add AEP + CRWV to the SEC harvest;
           V/SPG XBRL tag mapping.
