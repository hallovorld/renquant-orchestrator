# 2026-09-15 — model-freshness monitor: the tournament's declared non-trainable set is not missing coverage

## Conclusion

The 05:45 `RenQuant 104 model freshness BREACH` page has carried
`[breach] tournament: 141/142 present ... missing=1` on every run since the
watchlist carried SPY. The "missing" artifact is the benchmark, which the
per-ticker tournament never trains BY DESIGN: `weekly_tournament_retrain.sh`
derives an explicit non-trainable set (`benchmark`, every `sector_etf_map`
value, `defensive_tickers`, each only when in the watchlist) and writes it
to `logs/weekly_tournament_retrain/<date>.expected_non_trainable.json`
(2026-09-13: SPY, GLD, XLE, XLF, XLI, XLK, XLU, XLY). The monitor counted
those same names as coverage, so the tournament tier could never leave
BREACH on a fully healthy tournament.

`read_tournament_freshness` now takes `non_trainable` (ticker -> reason),
derived by `non_trainable_from_config` with the tournament's own rule; a
declared ticker is neither expected, nor missing, nor aged. The default
excludes nothing, so every caller that does not declare keeps the
fail-closed behaviour and the existing tests are unchanged.

## Evidence (§4(b))

Read-only run of the patched monitor against the live tree (no `--notify`,
explicit `--repo-root`/`--github-root`) `[VERIFIED 2026-09-15]`:

| field | before (05:45 page) | after |
|---|---|---|
| tournament | `141/142 present age min/med/max=12/12/145d missing=1` | `134/134 present age min/med/max=12/12.0/145d excluded=8 (GLD, SPY, XLE, XLF, XLI, XLK, XLU, XLY: declared non-trainable by the tournament)` |
| tournament tier | breach (missing=1 AND one 145d artifact) | breach (the 145d artifact only) |
| worst tier | breach | breach (prod-panel warn 104d; shadow-panel breach 217d — unchanged, genuine) |

The remaining tournament breach is real and now the ONLY tournament finding:
`CAT` is served from an artifact with `live_train_end 2026-04-23` (145d)
because every weekly tournament since then trains CAT and REJECTS the result
(`2026-09-13.log`: `TournamentJob OK best=Classification sharpe=-1.345
passes=False` → `tournament_acceptance[CAT]: REJECT`), so the runtime keeps
the last accepted policy. That is a policy question (serve a stale policy
vs. drop the name from admission), recorded here, not changed here.

Tests: 179 passed across the five freshness test files; six new tests cover
the exclusion (absent benchmark not missing; the undeclared default still
fails closed on SPY; an excluded ticker's artifact does not enter the age
spread; all-excluded fails closed; config derivation mirrors the tournament,
including the not-in-watchlist case; unreadable config excludes nothing).

## Deploy

The monitor runs from `renquant-orchestrator-run` (weekdays 05:45); live on
the next `-run` ff-sync after merge.
