# G2 crypto Phase 0: data-quality go/no-go gate

Date: 2026-07-17
Decision rule (operator, 2026-07-13): if backtest data quality is poor —
specifically NO cross-sectional signal — kill G2 early, BEFORE Phase 1.
Data: Alpaca crypto daily bars (v1beta3, paper-account keys; the crypto
data API needs no crypto agreement — operator-verified), collected via
`renquant_base_data.crypto_bars` (D-C2 ingestion: UTC-day keyed,
watermarked, fingerprinted manifests), 20 pairs, 2021-01-01 → 2026-07-16.

## 1. Collection & quality

- 20/20 pairs ingested `status=ok`; 928–2023 daily bars per pair.
- Zero bad prices (no nonpositive closes) across all pairs.
- Findings: MKR-USD history ENDS 2025-09-05 (delisting — must be excluded
  or survivorship-handled per RFC §survivorship); thin pairs carry
  zero-volume days (YFI 410, SUSHI 202, UNI 126, MKR 117) — stale-close
  risk, motivating the liquidity-tier control below.
- Store: slug-keyed parquet + manifests (crypto_ohlcv). Note: running the
  collector from the sibling checkout resolves the default store to
  `<github-root>/data/crypto_ohlcv` (repo-relative path bug, one-line
  follow-up; not a production path).

## 2. Cross-sectional signal screen (rank-IC, PIT-aligned)

Past-k-day return (through t-1) vs forward-h-day return, Spearman across
pairs, daily; t = mean/se over days.

Full 20-pair universe (2021→2026):

| k→h | mean IC | t |
|-----|---------|---|
| 3→1 | −0.023 | −3.34 |
| 7→1 | −0.020 | −2.84 |
| 7→7 | −0.020 | −2.83 |
| 30→7 | −0.012 | −1.77 |
| 90→20 | −0.024 | −3.36 |

Liquid-10 subset (BTC/ETH/SOL/DOGE/LTC/BCH/AVAX/LINK/XRP/DOT — the
stale-price control):

| k→h | mean IC | t | split-half (→2023 / 2024→) |
|-----|---------|---|-----------------------------|
| 3→1 | **−0.022** | **−2.32** | −0.019 / −0.026 (same sign) |
| 7→1 | −0.009 | −0.93 | — |
| 7→7 | +0.002 | 0.24 | — |
| 30→7 | −0.002 | −0.26 | — |
| 90→20 | +0.018 | 1.82 | **+0.073 (t 4.9) / −0.048 (t −3.6) — SIGN FLIP** |

Reading:
- The medium-horizon "reversal" in the full universe is largely a
  thin-pair stale-price artifact — it dies on the liquid tier.
- 90d momentum is regime-unstable (sign flip across halves): not a signal.
- ONE spec survives every control: **short-term (3d) cross-sectional
  reversal at 1d horizon** — IC ≈ −0.022, sign-stable across universes and
  halves, |t| 2.3 (liquid) / 3.3 (full).

## 3. Verdict: GO (narrow), with the economic bar named

The kill criterion ("no cross-sectional signal") is NOT met — a
statistically real, sign-stable signal exists. G2 proceeds to Phase 1
**restricted to the validated direction**:

- Universe: liquid tier only (survivorship-handled; thin pairs excluded
  from signal evaluation).
- Signal family: short-horizon cross-sectional reversal. The
  medium/long-horizon momentum menu is EMPTY on this data — do not build
  for it.
- The decisive Phase-1 question is ECONOMIC, not statistical: a 1-day
  rebalance reversal must clear crypto taker fees (~25bp/side) and the
  RFC's BTC-buy-and-hold baseline gate. Phase 1 = net-of-fee backtest of
  exactly this spec vs BTC baseline; if net edge ≤ 0, THAT is the kill
  point (same discipline as the 104 intraday-alpha NO-GO).

No capital, no orders, no Phase-2 work authorized by this memo.
