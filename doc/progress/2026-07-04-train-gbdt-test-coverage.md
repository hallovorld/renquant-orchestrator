# 2026-07-04 train_gbdt unit test coverage

## What

Added `tests/test_train_gbdt.py` with 36 unit tests covering all public
functions and classes in `src/renquant_orchestrator/train_gbdt.py`.

## Coverage map

| Area | Tests | Notes |
|---|---|---|
| `parse_args` | 4 | Defaults, all flags, type coercion, `none` literal |
| `_default_strategy_config` | 2 | Subrepo-preferred vs legacy fallback |
| `_production_fingerprint` | 4 | Missing config, common import, legacy fallback, no-fallback |
| `_Seq` | 2 | Tasks property, empty list |
| `_SENTIMENT_FEATURES` | 1 | Constant value |
| `main` validation guards | 3 | cutoff/side-label, walkforward-path safety, accepted path |
| `main` pipeline assembly | 7 | skip-gate, drop-sentiment, combined excludes, nthread, config=none, custom label/rounds, sentiment-gate pipeline structure |
| `_record_and_refresh` | 4 | DB missing, existing DB, exception non-fatal, STRATEGY_DIR env |
| `SentimentGateTask` | 2 | Gate with contract, gate without contract |
| `main` end-to-end | 4 | Happy path, custom data-dir, default output path, exclude-features only |
| Module constants | 3 | _PIN_SRCS, DEFAULT_DATA_DIR, GITHUB |

## Approach

- All subprocess/file I/O mocked via monkeypatch and `unittest.mock`.
- No real model training runs.
- Style follows existing `test_retrain_common.py` / `test_retrain_alpha158_fund.py`.
