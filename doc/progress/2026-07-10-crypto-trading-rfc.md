# Progress — Crypto Trading Capability RFC (GOAL-2)

- Date: 2026-07-10
- Branch: `design/crypto-trading-rfc`
- Deliverable: `doc/design/2026-07-10-crypto-trading-rfc.md` (design-only; no code)

## What

Design RFC for Alpaca spot crypto trading as an isolated $1–2k sleeve: 24/7
intraday loop (fork of the 105 scheduler bones, always-open UTC-day sessions),
new `renquant-strategy-crypto` config repo, asset-class abstraction threaded
through pipeline/execution/base-data, and a new XGB crypto panel model
(price/volume only, h=20 calendar days) under the same WF-gate governance plus
a NEW fee-aware net-of-cost gate requirement.

## Basis

Read-only audit of live checkouts (execution, pipeline, base-data,
strategy-104, orchestrator) + direct verification of alpaca-py 0.43.4 crypto
surface (CryptoHistoricalDataClient v1beta3, CryptoDataStream, GTC/IOC,
stop_limit for crypto, per-asset increments, `crypto_status`). All gaps cited
file:line in RFC §2; unverifiable broker-side facts marked [GUESS] and routed
to the Stage-0 paper battery.

## Key findings

- Central breaks: TIF=DAY hardcoded in every submit path; reconciliation
  filters `asset_class=US_EQUITY` (crypto orders invisible); no fee model
  anywhere; NYSE calendar hardwired into freshness/hold-clocks/settlement;
  wash-sale engine has zero asset-class awareness; fundamentals gates
  hard-block a no-fundamentals asset class; `BTC/USD` slash breaks every
  symbol-derived file path; WF gate has NO transaction-cost model (grep-verified
  absence) — fee-aware evaluation is a new capability.
- Crypto advantage: broker-resident GTC stop-limit in native fractional qty is
  SDK-supported → machine-death protection better than the equity fractional
  case.

## Operator decisions carried (2026-07-10)

sleeve $1–2k from the $10.7k account (exact at canary sign-off) · direct to
model (pipeline+model together) · full ~20-pair universe · 24/7 loop on this
Mac.

## Next

Codex adversarial review of the RFC; on merge, implementation PRs D-C1..D-C13
per RFC §7 (strict merge order, orchestrator last, default-OFF). Boundaries
honored: no Deployment Governor / D6 / shadow-AB files touched; design-first —
this RFC merges before any implementation PR.
