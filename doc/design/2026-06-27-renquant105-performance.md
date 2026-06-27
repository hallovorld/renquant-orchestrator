# renquant105 — performance analysis (latency / compute / storage)

2026-06-27. Part of the renquant105 suite. Scope: low-frequency intraday (1Min/5Min
bars), ~50 liquid names, CPU/MPS on a Mac, XGBoost `rank:pairwise` + small
PatchTST/PatchTSMixer ranker. Runtime figures are engineering estimates from the live
104 code + published benchmarks; lines marked **[MEASURE]** must be benchmarked on the
target Mac before go-live.

## Bottom line
1. **Latency is NOT the bottleneck.** Full bar-close decision ≈ **0.2–0.8 s typical,
   ~1.0 s worst-case** vs a **60 s** (1Min) / **300 s** (5Min) budget → >98% margin.
   The dominant cost is the Alpaca order REST round-trip (100–400 ms, a network
   constant), and IEX minute bars can themselves arrive **up to ~30 s late** — both
   external, neither fixable by faster local code. **No sub-second/HFT engineering.**
2. **CPU/MPS suffices, decisively — no GPU.** GBDT predict µs-scale; PatchTST
   ~0.1–0.3 M params, PatchTSMixer <50 k. Inference on 50 names 15–80 ms CPU. Nightly
   retrain <30 min total. A forward/backward pass is <10⁹ FLOPs — a GPU would be
   launch-overhead-bound (MPS↔CPU transfer can make it *slower* at batch 50).
3. **Storage is modest.** 50-name intraday history ≈ **0.15 GB/yr (1Min)**,
   0.03 GB/yr (5Min); 5 yr of 1Min ≈ 0.74 GB. Working panel ~13 MB (1 day) to
   ~0.14 GB (1 raw year) RAM. Flat per-name Parquet suffices; no DB engineering.

## 1. Latency budget per stage (~50 names, one bar-close decision)
| Stage | 1Min est. | Note |
|---|---|---|
| a. receive closed bar — websocket push | 0.05–0.5 ms | push, near-instant on wire; **IEX bars can lag ~30 s** [MEASURE per ticker] |
| a′. receive bar — REST poll (current code path) | 50–300 ms | `fetch_intraday_bars()` IEX REST; recommend websocket for 105 |
| b. feature compute (172 feats × 50 names) | 30–150 ms [MEASURE] | vectorized pandas, alpha158 cached per ticker/bar |
| c. GBDT inference (50 rows) | 1–5 ms | ≤3,100 nodes |
| c′. PatchTST/Mixer inference (50 names) | 15–80 ms [MEASURE] | small transformer; MPS may not win at batch 50 |
| d. gate stack G0–G8 | 1–10 ms | boolean/small-vector ops |
| d′. QP rotation solver (~50 names) | 30–120 ms | code: "99-ticker ~50–200 ms" |
| e. order construct + Alpaca REST submit | 100–400 ms | **dominant**; OMS-internal <1.5 ms, client↔API RTT dominates |
| **end-to-end (websocket+CPU)** | **~180–770 ms** | typical |
| **end-to-end (REST-poll worst case)** | **~1.0 s** | still <2% of 1Min budget |

Margin used: **0.3–1.3% (1Min)**, **0.06–0.3% (5Min)**. Engineering posture = robustness
(timeouts, stale-bar guards, idempotent submit), not speed.

## 2. Training compute (nightly batch)
| Model | Device | Train time | Peak RAM |
|---|---|---|---|
| GBDT `rank:pairwise` (100 trees, d5, ~172 feat, 50 names × intraday bars) | CPU | **~1–5 min** [MEASURE] (104 daily = ~32 s @717k rows) | 2–6 GB |
| PatchTST ranker (d64, 2L, seq 78–390, 5 epochs, early-stop) | MPS | **~5–20 min** [MEASURE] | 3–8 GB |
| PatchTSMixer (d16, 2L, <50 k params) | MPS/CPU | **~3–12 min** [MEASURE] | 2–5 GB |

All three retrain in **<30 min** overnight. **GPU verdict: refuted as necessary.**

## 3. Storage (measured 30 bytes/bar, Snappy Parquet)
| Horizon | 1Min (50 names) | 5Min (50 names) |
|---|---|---|
| 1 yr | 0.15 GB | 0.029 GB |
| 5 yr | 0.74 GB | 0.147 GB |

Working panel (50×390×172 f32) ≈ 13 MB/day. Ingestion (Alpaca free 200 req/min): full
50-name refresh ≈ **<2 s** via multi-symbol bars endpoint. Keeping the cache fresh
intraday adds ~1.5 KB/min on disk — negligible.

## 4. Throughput & scalability
- Compute per bar (~80–365 ms) has **~150–700× headroom** vs the 60 s budget.
- Scale to 145 names: still <1 s (<2% budget); QP solver (≈O(N²)) feels it first.
- 500 names + minute bars: QP + feature compute could hit 0.5–2 s (still < budget),
  and 500-name REST backfill could brush the 200 req/min cap unless multi-symbol-batched.
- **First wall as you grow = the QP rotation solver + feature compute**, not inference
  or storage. None bite at 50–145 names.

## 5. [MEASURE] before go-live
PatchTST/Mixer forward time at intraday seq_len on the real Mac; feature-compute wall
time; intraday retrain wall-clock; real Alpaca IEX bar-delivery lag for the 50 names;
Alpaca order REST RTT from this location. Conclusions hold with wide margin even if
every estimate is off 3–5×.

Sources: Alpaca usage-limit + streaming docs; Redpanda (OMS <1.5 ms); Alpaca forum
(IEX/SIP ~30 s bar lag); Intel oneDAL (XGBoost CPU predict); GetStream / HF (small
transformer CPU latency; PatchTSMixer 2–3× faster than PatchTST).
