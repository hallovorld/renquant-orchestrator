# 2026-07-06 rq105 paper trading mode

## What changed
- Added `MODE_PAPER` to intraday session scheduler alongside shadow/live
- `--mode paper` CLI arg overrides strategy config mode without editing pinned config
- `_build_paper_submitter()` connects to Alpaca paper account (PA3XS7DXTPYZ, $100K) using `ALPACA_SHORTS_API_KEY`/`SECRET_KEY`
- `_FrozenScoreScoringJob` replaces the full feature-build pipeline with a stub that injects frozen T-1 daily scores + `default_quantity=1`
- `AlpacaLiveStateSource` routes to paper account keys when `paper=True`
- Decision trace stripping restored for no-trade ticks
- Tick cadence set to 180s (3 min)

## Verified results
- 3 BUY orders submitted and FILLED on paper account: FTNT x1 @ $163.11, BLK x1 @ $1,003.99, GRMN x1 @ $242.51
- Scheduler running via launchd in paper mode (3-min ticks)
- 3124 tests pass (7 pre-existing failures unrelated)

## Pipeline: frozen score → order intent → paper order
1. `_StubFeatureMatrixTask`: injects stub feature matrix from `market_snapshot["panel_scores"]`, sets `default_quantity=1`
2. `ApplyScoresTask` → `ApplyGlobalCalibrationTask` → `RegimeModelAdmissionTask` → `VetoWeakBuysTask`: standard pipeline on frozen scores
3. `SelectionJob`: rank + select top candidates
4. `EmitAttributedOrderIntentsTask`: produce `order_intents` with sizing from `default_quantity`
5. `_paper_submitter`: submit market orders to Alpaca paper API

## Known limitations
- `default_quantity=1` means 1 share per pick regardless of price ($163 FTNT vs $1,004 BLK) — proper sizing requires QP integration
- Paper account live_state reflects paper positions (not live), so the two books diverge
- No exit/sell logic wired yet for paper positions
