# Retrain: delisted ticker resilience + no-trade root cause

**Date**: 2026-07-09
**Status**: Fix implemented (code) + operational steps documented
**Trigger**: 2 consecutive no-trade days (07-08, 07-09)

## Bottom line

Two independent problems caused 0 candidates on 07-08 and 07-09:

1. **Per-ticker tournament models frozen at `live_train_end=2026-04-23`** (77 days
   stale, limit 60) → 129/144 buyable tickers blocked → 0 candidates → no trade.
   Root cause: `com.renquant.weekly-tournament-retrain` launchd job was NEVER
   INSTALLED (plist exists in scripts/launchd/, never loaded).

2. **Weekly panel retrain blocked by IAC** — yfinance returns "possibly delisted;
   no price data found" for IAC. The freshness guard's zero-tolerance default
   (`freshness_max_stale_fraction=0.0`) fails the entire retrain because 1/294
   tickers (0.34%) is stale. Production panel model (07-06) still working but
   will degrade without fresh retrains.

## Fix: `--exclude-tickers` CLI arg

Added `--exclude-tickers` to `retrain_alpha158_fund.py` so newly-delisted tickers
can be excluded from the panel universe without updating the versioned inventory.
This supplements (not replaces) the inventory's `delisted_tickers` list.

Changes:
- `RetrainContext.exclude_tickers: set[str]` field
- `_resolve_panel_universe()` merges `exclude_tickers` into the delisted set
- Provenance audit trail: `n_cli_excluded`, `cli_excluded` in provenance dict
- CLI: `--exclude-tickers IAC,PARA` (comma-separated, uppercased)
- 3 new tests in `test_retrain_ohlcv_coverage.py`

Usage: `python -m renquant_orchestrator.retrain_alpha158_fund --exclude-tickers IAC`

## Operational steps required (not code — live-tree actions)

### A. Pass `--exclude-tickers IAC` in weekly_wf_promote.sh (umbrella PR)

In `scripts/weekly_wf_promote.sh`, add `--exclude-tickers IAC` to the
`daily_retrain_alpha158_fund.sh` invocation so the next weekly retrain passes.

### B. Install tournament retrain launchd job

```bash
cp scripts/launchd/com.renquant.weekly-tournament-retrain.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.renquant.weekly-tournament-retrain.plist
```

Then run manually once to immediately refresh per-ticker models:
```bash
bash scripts/weekly_tournament_retrain.sh
```

### C. Update inventory (permanent fix for IAC)

Add IAC to `delisted_tickers` in `data/transformer_universe_inventory.json`.
This is the versioned-universe mechanism the freshness guard is designed around.
After this, `--exclude-tickers IAC` becomes redundant.

## Evidence

### Per-ticker staleness (all 90 tickers uniform)

```
AAPL: trained_date=2026-07-08, live_train_end=2026-04-23
MSFT: trained_date=2026-07-08, live_train_end=2026-04-23
NVDA: trained_date=2026-07-08, live_train_end=2026-04-23
META: trained_date=2026-07-08, live_train_end=2026-04-23
AMZN: trained_date=2026-07-08, live_train_end=2026-04-23
```

Models retrained recently (07-08) but training data ends at 04-23 because
the OHLCV data for non-watchlist tickers froze at 05-12 (no refresh cadence).

### Panel retrain failure (07-09 log)

```
$IAC: possibly delisted; no price data found (1d 2026-07-03 -> 2026-07-09)
freshness guard TRIPPED: 1/294 panel tickers stale (0.3% > 0.0%)
RuntimeError → FAILED
```

### OHLCV data freshness (150/294 stale)

```
Watchlist (daily refresh):  AAPL=07-09, MSFT=07-09, NVDA=07-09
Non-watchlist (no refresh): ABNB=05-12, ABT=05-12, IAC=05-12
```

150/294 universe tickers have on-disk OHLCV frozen at 05-12.

### launchd job NOT installed

```
launchctl list | grep tournament  →  (no output)
ls scripts/launchd/com.renquant.weekly-tournament-retrain.plist  →  exists (2.9k)
```
