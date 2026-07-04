# Decision-ledger attribution engine (107 sprint D3)

DATE: 2026-07-03 · STATUS: implemented (read-only analysis tool, no prod wiring)
Package: `src/renquant_orchestrator/attribution/` (`ledger.py`, `decompose.py`, `report.py`).

## Objective

The 107 master plan's PROCESS/TC terms need per-decision dollar attribution:
not "what did SELECTED vs VETOED earn in forward returns" (that is
`decision_pnl_attribution`, graduated in PR #145 and unchanged here), but
"of what each decision made or lost, how much was the pick, how much the
fill prices, how much the sizing pipeline, how much cost". This engine is the
first piece of the 107 skeleton: a unified read model over the run DB plus an
exact decomposition identity with an enforced sum-check.

## The identity (decompose.py)

With `N_i` = intended notional (`kelly_target_pct x portfolio_value`),
`N_r` = realized notional (shares x confirmed entry fill), `r_ref` the
round-trip return at decision-session reference closes, `r_spy` the benchmark
return over the same window, `r_real` the return at confirmed fills:

```
TOTAL  = N_r*r_real − cost = MARKET + SIGNAL + SIZING + TIMING + COST,  RESIDUAL ≡ 0
MARKET = N_i * r_spy               benchmark/beta component
SIGNAL = N_i * (r_ref − r_spy)     the pick vs benchmark, intended sizing
SIZING = (N_r − N_i) * r_ref       shrinkage stack + whole-share artifact
TIMING = N_r * (r_real − r_ref)    fills vs session reference (POC-C leak)
COST   = −(fees + spread proxy)    proxy is opt-in and flagged as estimate
```

The sum is exact by construction (`MARKET+SIGNAL = N_i·r_ref`; `+SIZING =
N_r·r_ref`; `+TIMING = N_r·r_real`), so the per-record residual must be ~0;
`assert_identity` raises otherwise. The prompt-level "signal vs benchmark"
phrasing requires the explicit MARKET leg — without it the benchmark
component would fall out of the identity and the sum-check would be theatre.

Open positions are marked at the latest recorded close, which is used as
BOTH the real and the reference exit price, so their TIMING leg isolates
entry-side slippage exactly.

## Read-model contracts (ledger.py) — measured, not assumed

- **Reference price = decision-session close** (`ticker_forward_returns.
  close_price`). Open/VWAP are not persisted anywhere in this DB; the record
  carries `ref_px_kind='close'` so a future quote-corpus upgrade is additive.
  Weekend/holiday run_dates join via the S5 as-of backfill rows
  (backtesting#60 session semantics).
- **Fill-confirmation censoring (#253).** Live runs stopped writing
  `action='buy'` fill rows after 2026-05-22; June-era entries are
  `buy_pending` submissions whose `price` is a submit-time reference (the
  order can be canceled pre-open — OXY 2026-07-01/02). Submissions are
  represented with `entry_fill_confirmed=False` and the reference kept in a
  separate field; TIMING/SIZING/COST/TOTAL are censored with a
  machine-readable reason, never imputed. Same for `sell_pending` exits.
- **Same-day duplicates + cross-day re-records.** The same broker event is
  re-recorded across same-day run_ids (exact dedupe) and — early live era —
  across days at the identical price (e.g. one NET 207.07 fill echoed over
  04-25/26/27 with share counts 2/3/39). Same-price runs with no
  opposite-side event inside their span collapse to the first-dated row;
  when echoes disagree on share count the realized notional is ambiguous and
  is censored (`shares_conflict`), never guessed.
- **Round trips are a live-stream tool.** Sim commingles 37,647 parallel
  runs; FIFO pairing across them is unreliable, so `build_round_trips`
  refuses `run_type='sim'` (class-level sim attribution stays with #145).
  Unmatched exits (positions opened before the window) are surfaced as
  `exit_unmatched` records, not dropped.

## Coverage boundary (measured on the live DB, 2026-07-03)

| legs | covered | censored |
|---|---|---|
| SIGNAL/MARKET (intended sizing, reference px) | 2026-04-27 → 2026-07-02 | 6 earliest records lack kelly/pv; scattered `ticker_forward_returns` close gaps 05-03→05-17 |
| TIMING/SIZING/COST (need confirmed fills) | 2026-04-23 → 2026-05-22 only | 2026-06-09 → now: `entry_fill_unconfirmed(#253)` — 30 records; plus 3 shares-conflict re-record clusters |

Unblocking the censored era = the umbrella-side fill-confirmation writer
(#253's stated external precondition), not more inference here.

## Non-goals / boundaries

- No writes anywhere near prod: DB opened `mode=ro`; the reporter refuses
  output paths under the umbrella `data/`/`runtime/` trees.
- No broker API calls; only already-persisted data (a read-only orders-API
  join can be added later behind the same censoring contract).
- No signal/decision internals — this is measurement plumbing, in-boundary
  for the orchestrator.
