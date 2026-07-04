# S-TC CLI entrypoint (`rq-tc`)

DATE: 2026-07-04

## What changed

Added a CLI wrapper for the transfer coefficient measurement module
(S-TC). The `rq-tc` command measures TC = corr(w_kelly, w_qp) per live
run, reports summary stats, regime breakdown, and TC loss decomposition.

## Usage

```bash
rq-tc                              # human-readable report
rq-tc --json                       # structured JSON output
rq-tc --db path/to/runs.db         # custom DB path
rq-tc --min-candidates 5           # filter threshold
```

Exit codes: 0 = healthy TC, 1 = negative TC, 2 = no qualifying runs.

## Files

- `src/renquant_orchestrator/transfer_coefficient.py` — added `main()`,
  `_render_summary()`
- `pyproject.toml` — added `rq-tc` console_scripts entrypoint
- `tests/test_transfer_coefficient.py` — 3 CLI tests (text, JSON, empty)
