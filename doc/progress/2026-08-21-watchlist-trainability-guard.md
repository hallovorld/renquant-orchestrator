# Adding a ticker to the served watchlist could never make it tradeable

STATUS:   delivered. `check_watchlist_trainability` in the run-surface drift
          scan + 7 tests. It ALARMS on the current real state, which is the
          point: `{CRWV, RKLB, SPCX}`.

WHAT:     Two watchlists, in two repos, drifted, and nothing reported it.

            .subrepo_runtime/.../renquant-strategy-104/configs/strategy_config.json  145  ← daily decision
            backtesting/renquant_104/strategy_config.json                            142  ← weekly tournament

          The difference is exactly `{CRWV, RKLB, SPCX}`, and those are exactly
          the three names the daily run logs `no_artifact, skipping` every
          session. So a ticker added to the served watchlist is scored NEVER:
          artifacts come from a file nobody updated. The operator asked for
          CoreWeave on 2026-08-19, it was added to the served list, and it has
          been inert since with no signal beyond one WARNING among dozens.

          WHY A SUBSET TEST, NOT A DIFF. The tournament already handles
          "deliberately not trained" well — an explicit `non_trainable` map of
          ticker → justification, which is how SPY and the sector ETFs are
          accounted for. But that map is built by intersecting
          benchmark/`sector_etf_map`/`defensive_tickers` WITH THE TRAINING
          WATCHLIST, so a ticker absent from the training watchlist cannot even
          be *declared* non-trainable. It is invisible to the one mechanism
          designed to account for it. Hence `served ⊆ trained`: be in the
          training universe, then be excluded from it with a reason.

          The reverse direction (trained but not served) is reported as INFO,
          not a problem — an unused artifact is waste, not a live defect, and
          alarming on it would teach the operator to ignore this check.

WHY/DIR:  Same class as this module's stated purpose (run surface == reviewed
          surface), with the twist that BOTH surfaces are reviewed and neither
          knows about the other. `no_artifact` was a WARNING that nothing acted
          on — the "guards that REPORT instead of enforce" shape.

EVIDENCE:
  artifact:      `ops/run_surface_drift_check.py` (`check_watchlist_trainability`,
                 wired into `main`), `tests/test_run_surface_drift_check.py` (+7).
  prod or exp:   **exp** — read-only checker; it reads two config files and
                 writes nothing. No production path touched.
  existing data: measured, not assumed —
                 - 145 vs 142 and the exact 3-name difference [VERIFIED —
                   both configs parsed]
                 - the same 3 names log `no_artifact` [VERIFIED —
                   RenQuant/logs/daily_104/2026-08-20.log:214-216]
                 - SPY's `no_artifact` is BY DESIGN, declared with a reason
                   [VERIFIED — 2026-08-09.expected_non_trainable.json, 8 entries]
                 - RKLB has 1,332 rows vs APP's 1,344, the shortest name
                   currently in the tournament — it QUALIFIES and is a plain
                   omission; CRWV has 293, SPCX 48, NBIS no parquet at all
                   [VERIFIED — data/ohlcv/<T>/1d.parquet row counts]
                 - the check fires on the real state today [VERIFIED — run]
                 - mutation: inverting the subset direction turns 3 tests red
                   [VERIFIED]
                 - `make test`: 6540 passed, 1 failed — and the SAME 1 fails on
                   a clean baseline with this change parked (6533 passed, 1
                   failed), so it is pre-existing and not attributable here
                   [VERIFIED — both full runs]
  best-known?:   yes. Reporting the diff without an invariant would be another
                 line nobody acts on, which is the defect being fixed.
  scope:        one read-only check plus its tests. No config edited, no ticker
                added or removed — those decisions belong in orch#1020.

  NOT CLAIMED:  that 1,344 rows is a threshold. No coded minimum-history bound
                exists anywhere I could find in `backtesting/renquant_104/`;
                1,344 is the empirical floor of the current 142. Whether a
                293-row ticker would fail loudly or quietly train a bad model
                is UNMEASURED.

NEXT:      orch#1020 — RKLB into the training watchlist; CRWV/SPCX declared
           non-trainable with a reason and a revisit condition; NBIS needs data
           fetched before it is anything but a no-op.

REVIEW:    codex (haorensjtu-dev).
