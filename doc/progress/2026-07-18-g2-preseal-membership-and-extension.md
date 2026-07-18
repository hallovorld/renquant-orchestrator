# Progress: G2 pre-seal data work — store extension + membership schedule + provenance

Date: 2026-07-18

## What

- **Store extension (Part 1).** Extended the experimental G2 crypto
  store (`<github-root>/data/crypto_ohlcv/`, NOT a 104 production path)
  from 20 to 42 USD pairs with the canonical collector
  (`renquant_base_data.crypto_bars`, one `ingest_crypto_bars` call over
  the full 42-pair universe; polite per-pair fetch, 1.5 s sleep):
  22 pairs, 10,694 daily bars, 2021-01-01 → 2026-07-16 where served,
  zero API refusals, `universe_complete: true`. All 20 pre-existing
  pairs' `content_sha256` unchanged. New manifest fingerprint
  `sha256:0068eb93359ff3a7bc6e46e6be948d5b58ba6803940e4b5e80d0f4318d0c1cc1`.
- **Membership schedule (Part 2).**
  `doc/research/g2-manifest/crypto_membership_schedule.json` (identical
  copy lives next to the store manifest): 43 pairs, 49 conservative
  listed intervals derived ONLY from the 16 evidentiary Wayback
  captures of the Alpaca support article (2021-10-29 → 2025-11-13, per-
  interval source URLs) + the 2026-07-17 assets-API pull + dated
  data-API event bounds (tighten-only). Includes the 2021-11-22 trading
  launch floor (BTC/ETH/LTC/BCH), the DOGE/SUSHI/YFI/AVAX delist
  windows, the SOL hole (2023-01-29 → 2025-04-15 conservative), MKR end
  2025-09-05, stablecoins flagged `excluded_by_rule: stablecoin`, and
  WBTC as `obtainable: false` permanent registered omission.
- **Provenance declaration + sealed-manifest candidate (Part 3).**
  `doc/research/g2-manifest/2026-07-17-membership-provenance.md`
  (the §3(b) MEMBERSHIP-SCHEDULE PROVENANCE block: route (a)
  verified-complete is FALSE; enumerated-censoring declared, bias
  direction inflates-PASS registered, CONDITIONAL downgrade bound) and
  `doc/research/g2-manifest/crypto_ohlcv_sealed_manifest_candidate_1d.json`
  (the post-extension store digests).

## Why

Prereg `doc/research/2026-07-17-g2-reversal-backtest-prereg.md` §3
fail-closes the historical exercise until exactly one of
(a) verified-complete / (b) enumerated-censoring is produced and the
inputs are sealed. The support-page ledger proves (a) is FALSE (the
Phase-0 20-pair store omitted ≥8 in-window tradable USD pairs), so this
PR executes the (b) route: collect every servable omission, freeze the
membership schedule with provenance, and put the sealed-manifest
candidate under review. The backtest still may not run until this PR is
MERGED (= the seal). No backtest was run.

## Verification

- 42/42 pairs `status: ok`; refusals log empty.
- Pre/post manifest diff: 20 existing pairs byte-identical content
  digests; 22 new pairs listed with row counts in the PR body.
- Schedule intervals mechanically derived from the ledger by the frozen
  conservative rule (generator kept in session scratch; the JSON is the
  frozen artifact).
