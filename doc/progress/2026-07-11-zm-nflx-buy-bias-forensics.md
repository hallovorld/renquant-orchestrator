# Progress — ZM/NFLX buy-bias forensics (mirror of the META fade)

**Date:** 2026-07-11 · **Author:** claude · **Type:** research forensic (read-only; no
production path written; isolated clone; local compute)
**Deliverable:** `doc/research/2026-07-11-zm-nflx-buy-bias-forensics.md`

## What was asked

Operator: the live model repeatedly recommends buying ZM and NFLX (ZM "bought" 07-07,
ZM+NFLX admitted 07-10) — find the root cause with the same four-layer rigor as the META
studies (#473/#475/#476), on the opposite side.

## Verdict (one paragraph)

Same chain as META, mirrored: every ZM/NFLX admission in 4 weeks is a pure
dispersion-credit pick from the same unvalidated STD-family tilt (ex-STD SHAP both names
score NEGATIVE on every admission day, all three model vintages), produced by models that
failed BULL_CALM regime-IC/monotonicity and reached primary via operator override (06-21
and 07-06 models) or via a silent file regression (05-18 model, 06-26..07-02). NFLX is
the FTNT mirror — 86.5% of its STD60 is a −31%/60d crash TREND; true returns-vol is the
panel median; #44's v2 features de-rank it 30pp. ZM is genuinely high-dispersion (trend
13%, resid-vol 86th pct) — v2 does not de-rank it; only the gated-retrain/F4 lane
addresses it. ZM is also valuation-blind (ey/b2p never finite → #43), though real ratios
would likely RAISE its score. Scoreboard honesty: the picks have not lost money — total
realized = −$3.68 (one NFLX round trip whipsawed by the exit plane); ZM paper picks beat
SPY (+5.0/+0.9/+3.8pp); street is Buy on both.

## New engineering findings (beyond the META chain)

1. **Exit-plane whipsaw** made the only realized loss: ModelProtectionExitTask sold NFLX
   24h after entry on `mu=-0.0505 strikes=3/3` from the stale holding re-score plane
   (per-ticker vintage `live_train_end=2026-04-23`) while the panel that bought it
   scored +0.066 same-day; sold the local low, NFLX +2.8% since.
2. **06-25 live-tree incident collateral:** (a) prod panel artifact silently regressed
   06-21→05-18 for 5 sessions (byte-verified via run-bundle shas + exact replay of the
   committed 05-18 artifact), unalerted, violating the 28d freshness policy; (b) NFLX's
   wash-sale stamp (written 06-25 after the loss sale) vanished from live_state by
   06-26 → the 07-10 NFLX buy submission went out 15 days into the 30d window,
   `blocked_wash=0` (only the order cancel prevented a wash-sale re-entry).
3. **ZM was never actually bought** — 5 broker orders, 0 fills (pre-open cancel gate +
   morning re-selection); the trades DB records intents only, no fill truth.

## Fix mapping

Existing stack covers: #44 v2 features (quantified: NFLX −30pp, FTNT −20..26pp, ZM
unmoved — correctly), F4 #479 override consequences, base-data #43 (ZM's ey/b2p),
gated retrain. New fixes proposed (§8 of the research doc): exit/entry plane coherence
+ freshness fail-close on protection mu (pipeline), durable broker-reconciled wash-sale
ledger (pipeline + orchestrator checker), model-identity regression tripwire
(orchestrator monitor), fill-truth in the runs DB (execution/pipeline).

## Method / evidence

- Facts: runs DB (candidate_scores/trades/ticker_daily_state/live_state_snapshots,
  copied before opening) + Alpaca orders/activities (read-only GET) + daily/intraday logs.
- Attribution: #475's sealed reproduction method; July days read from the already-sealed
  renquant-artifacts #18 bundle (ZM byte-exact, diff 0.000000); June days replayed
  against the byte-verified 06-21 backup (corr 0.95-0.97, disclosed); regression window
  replayed against the committed 05-18 artifact (ZM/FTNT exact).
- Honest view: v2 features computed with the merged renquant-model #44 module verbatim;
  trend-share decomposition; live fundamentals feed finiteness; WebSearch street
  consensus (ZM ~$115 MB, NFLX ~$113 SB).

## Constraints honored

Read-only on all production paths; no git in the live umbrella tree or any primary
checkout (fresh isolated clone); local compute only; PR left for Codex review — not
self-merged.
