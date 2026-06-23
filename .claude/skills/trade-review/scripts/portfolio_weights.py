#!/usr/bin/env python3
"""Post-fill portfolio weights + concentration from the live broker (Alpaca).

Reads current positions + open (queued) orders, estimates fills at the latest trade
price, and reports the POST-FILL book: per-name weight (% of equity and % of long
book), total invested vs cash, HHI concentration and effective number of names.

Read-only on the broker (queries only — never places/cancels orders).

Usage:
    portfolio_weights.py [--json]

Env: ALPACA_API_KEY / ALPACA_SECRET_KEY (source the strategy .env first).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

EXPECTED_ACCOUNT = "212830627"  # live guard; override with --account


def _clients():
    from alpaca.data.historical import StockHistoricalDataClient  # noqa: PLC0415
    from alpaca.trading.client import TradingClient  # noqa: PLC0415

    key, sec = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        sys.exit("ALPACA_API_KEY / ALPACA_SECRET_KEY not set — source the strategy .env first.")
    return TradingClient(key, sec, paper=False), StockHistoricalDataClient(key, sec)


def post_fill_book(expected_account: str = EXPECTED_ACCOUNT) -> dict:
    from alpaca.data.requests import StockLatestTradeRequest  # noqa: PLC0415
    from alpaca.trading.requests import GetOrdersRequest  # noqa: PLC0415
    from alpaca.trading.enums import QueryOrderStatus  # noqa: PLC0415

    tc, dc = _clients()
    acct = tc.get_account()
    if expected_account and acct.account_number != expected_account:
        sys.exit(f"account guard: connected to {acct.account_number}, expected {expected_account}")
    equity = float(acct.equity)

    shares: dict[str, int] = {}
    for p in tc.get_all_positions():
        shares[p.symbol] = shares.get(p.symbol, 0) + int(float(p.qty))
    for o in tc.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)):
        q = int(float(o.qty)) * (1 if o.side.value == "buy" else -1)
        shares[o.symbol] = shares.get(o.symbol, 0) + q

    def px(t):
        try:
            return float(dc.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=t))[t].price)
        except Exception:
            return 0.0

    vals = {t: sh * px(t) for t, sh in shares.items() if sh != 0}
    long_total = sum(v for v in vals.values() if v > 0) or 1.0
    invested = sum(vals.values())
    names = {}
    for t in sorted(vals, key=lambda x: -vals[x]):
        names[t] = {
            "shares": shares[t],
            "value": round(vals[t], 0),
            "pct_equity": round(vals[t] / equity * 100, 1),
            "pct_long_book": round(vals[t] / long_total * 100, 1),
        }
    ws = [v / long_total for v in vals.values() if v > 0]
    hhi = sum(w * w for w in ws) if ws else 0.0
    return {
        "account": acct.account_number,
        "equity": round(equity, 0),
        "invested": round(invested, 0),
        "invested_pct": round(invested / equity * 100, 1),
        "cash_pct": round((equity - invested) / equity * 100, 1),
        "hhi_long_book": round(hhi, 3),
        "effective_n_names": round(1 / hhi, 1) if hhi else 0,
        "names": names,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--account", default=EXPECTED_ACCOUNT)
    a = ap.parse_args()
    res = post_fill_book(a.account)
    if a.json:
        print(json.dumps(res, indent=2))
        return
    print(f"account {res['account']}  equity ${res['equity']:,.0f}  "
          f"invested {res['invested_pct']}%  cash {res['cash_pct']}%  "
          f"HHI {res['hhi_long_book']}  eff_N {res['effective_n_names']}")
    print(f"{'sym':6}{'sh':>5}{'value':>10}{'%eq':>7}{'%book':>8}")
    for t, m in res["names"].items():
        print(f"{t:6}{m['shares']:>5}{m['value']:>10,.0f}{m['pct_equity']:>6.1f}%{m['pct_long_book']:>7.1f}%")


if __name__ == "__main__":
    main()
