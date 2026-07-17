# G2 Phase 0: crypto data collected, go/no-go gate run

STATUS: delivered
WHAT: ran the D-C2 crypto ingestion for 20 pairs (2021→2026-07-16, daily,
paper-account keys, data-only), quality-checked coverage/plausibility, and
ran the operator-mandated cross-sectional signal screen with liquidity and
split-half controls. Verdict memo:
doc/research/2026-07-17-g2-crypto-data-quality-gonogo.md — GO (narrow):
one surviving spec (3d cross-sectional reversal @1d, IC −0.022,
sign-stable), thin-pair/medium-horizon results are artifacts, 90d momentum
sign-flips. Phase 1 scope = net-of-fee viability of exactly that spec vs
the BTC baseline.
WHY/DIR: G2 gate rule (2026-07-13): check data quality BEFORE Phase 1;
kill early if no signal. Signal exists → no kill; economic bar named as
the next kill point.
EVIDENCE: ingestion summary 20/20 ok; screen tables in the memo
(reproducible from the crypto_ohlcv store manifests).
NEXT: Phase 1 net-of-fee backtest (narrow spec); collector default-path
one-liner fix; MKR survivorship handling in the panel builder.
