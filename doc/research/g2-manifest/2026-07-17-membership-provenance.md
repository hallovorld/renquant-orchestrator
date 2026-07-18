# G2 pre-seal input manifest: membership-schedule provenance (prereg §3)

Date: 2026-07-17 (evidence retrieval) / 2026-07-18 (declaration committed)
Prereg: `doc/research/2026-07-17-g2-reversal-backtest-prereg.md` §3.
Frozen files in this directory:

- `crypto_membership_schedule.json` — the frozen membership-schedule file
  (snapshot ledger with per-interval source URLs + conservative listed
  intervals per pair).
- `crypto_ohlcv_sealed_manifest_candidate_1d.json` — the post-extension
  `crypto_ohlcv` store ingestion manifest (per-pair `content_sha256` +
  manifest fingerprint) = the sealed-manifest candidate. Manifest
  fingerprint:
  `sha256:0068eb93359ff3a7bc6e46e6be948d5b58ba6803940e4b5e80d0f4318d0c1cc1`.

---

MEMBERSHIP-SCHEDULE PROVENANCE — Alpaca spot crypto, USD-quote pairs,
window 2021-01-01 → 2026-07-16 (UTC days).

**Declared route: prereg §3(b) enumerated-censoring.** Route §3(a)
"verified-complete" is **FALSE** and cannot be produced: the 20 pairs of
the Phase-0 collection were NOT the complete set of USD pairs ever
tradable on Alpaca spot in-window. The historical support-page ledger
(Wayback captures of
`https://alpaca.markets/support/what-cryptocurrencies-does-alpaca-currently-support/`,
16 evidentiary captures 2021-10-29 → 2025-11-13, all retrieved
2026-07-17; exact capture URLs in the schedule file) proves at least
ALGO, MATIC, NEAR, TRX, DAI, PAXG, USDT and WBTC were listed USD pairs
in 2022-2023 and absent from the Phase-0 store, and the 2026-07-17
assets-API pull proves further post-2024 additions (XRP-wave, PEPE,
TRUMP, USDG, SKY, and the 2026 wave ADA/ARB/BONK/FIL/HYPE/LDO/ONDO/POL/
RENDER/WIF). "Survivorship handled by construction" on the Phase-0
20-pair store was therefore unfalsifiable in exactly the way §3(r2)
anticipated.

**Remediation executed before sealing (2026-07-17).** Every
data-API-servable omission was collected into the store with the
canonical collector (`renquant_base_data.crypto_bars`, D-C2 bar
convention and manifest path): 22 pairs, 10,694 daily bars added; the
42-pair manifest above is `universe_complete: true` with zero API
refusals; all 20 pre-existing pairs' per-pair `content_sha256` are
byte-identical to the Phase-0 collection (extension added pairs, it did
not mutate history).

**Sources and derivation rule.** "Listed on T" derives ONLY from
(i) the support-page snapshot ledger and (ii) dated data-API event
bounds — never from data presence in the collected store. The
conservative interpolation rule (frozen verbatim in the schedule file):
a pair counts as listed on day T only if T lies inside a maximal run of
consecutive evidentiary ledger points that ALL contain the pair; a dated
data-API event bound may only TIGHTEN an interval (MKR end
2025-09-05 = data delisting bound, earlier than the lagging 2025-09-20
support capture); the 2021 four (BTC/ETH/LTC/BCH) are floored at the
2021-11-22 trading launch. 43 pairs, 49 intervals. Stablecoins
(USDT/USDC/USDG/DAI) are present in the schedule but flagged
`excluded_by_rule: stablecoin` (never rankable universe members).

**Enumerated residual omissions (the registered censoring):**

1. **WBTC/USD — permanent, unobtainable.** Listed (conservative)
   2022-04-25 → 2023-01-29; the Alpaca data API serves NO WBTC history
   (purged after delisting). A delisting-bound coin missing from the
   store on days it was tradable is worst-case for a LONG-LOSER
   strategy: it is disproportionately a bottom-3 pick, so its absence
   **inflates net d_t and biases the §5 kill statistic toward PASS**.
   Bias direction REGISTERED: inflates PASS.
2. **Dark windows.** True list/delist dates inside inter-snapshot gaps
   are unknown (notably the ~2022-11 delisting wave for
   DOGE/SUSHI/YFI/AVAX between the 2022-10-03 and 2023-01-29 captures;
   the 2023 mid-year removals of ALGO/MATIC/NEAR/TRX/DAI/PAXG/SOL/WBTC
   between 2023-01-29 and 2023-09-12; the 2024-2025 relists). The
   schedule truncates conservatively to the bracketing containing
   captures — it UNDERCOUNTS listing on ambiguous days. For collected
   pairs this only shrinks the universe; it cannot repair the purged
   WBTC history, and any dark-window pair whose history the data API
   never served would share WBTC's PASS-inflating direction.
3. **Single-evidence-point listings.** Pairs first evidenced only by
   the 2026-07-17 assets-API pull
   (ADA/ARB/BONK/FIL/HYPE/LDO/ONDO/POL/RENDER/WIF; PAXG's relist) carry
   degenerate intervals at 2026-07-17 and contribute no in-window
   membership before that date under the conservative rule.

**Consequence (prereg §3(b), binding):** any feasibility PASS from the
historical exercise is downgraded to **CONDITIONAL**; this censoring
caveat must be carried **verbatim** into the paper-shadow registration,
whose fully prospective (censoring-free) result is controlling.

**Seal semantics:** the immutable input manifest = the store's per-pair
content digests + manifest fingerprint (the sealed-manifest candidate
file) + the frozen membership-schedule file + this declaration. The
historical exercise may not run until the PR carrying these files is
MERGED (= the seal); the backtest refuses unsealed inputs (fail-closed).
