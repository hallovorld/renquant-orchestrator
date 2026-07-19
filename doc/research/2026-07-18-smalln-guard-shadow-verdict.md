# Small-n guard §4 shadow verdict — frozen REPLAY

Date: 2026-07-18
Status: FROZEN shadow verdict (read-only replay; gates the production key-flip)
Author: hallovorld (single-identity commit — author == committer, no co-author/session trailer)
Companion artifact: `doc/research/2026-07-18-smalln-guard-shadow-verdict.json`
Reproducer: `scripts/smalln_guard_shadow_replay.py`
Normative spec: renquant-pipeline `doc/design/2026-07-18-smalln-guard-eligibility-ledger.md` §4

## Verdict

**REPLAY-CONSISTENT / INSUFFICIENT-N.** Not GO (only 2 operative CLEAN sessions
vs the frozen `N_shadow = 10`), and **not NO-GO** (no partition mislabel, no
gate bypass, no new alarm class — no blocking defect found). The replay is
**strong positive evidence** toward GO; reaching the volume bar needs accrual
(see recommendation). **Do NOT flip the production key on this replay alone.**

## Method (containment-safe)

Recorded `candidate_scores` for the frozen replay corpus were fed through the
**DEPLOYED pinned** guard + eligibility ledger:

- pipeline pin `d32f7017` (`#205` guard stage-1 + `#207/#208` eligibility
  ledger); functions driven directly: `smalln_eligibility.evaluate_clean`,
  `job_panel_scoring._smalln_guard_params` / `._apply_smalln_guard`.
- guard keys from `strategy_config.shadow.json`: `buy_floor_min_n=12`,
  `buy_floor_absolute_smalln=0.5`, `buy_floor_min=0.20`.
- `runs.alpaca.db` opened `mode=ro&immutable=1`; **zero live orders**; all
  writes to a temp dir. Replay reproduces the recorded live floors exactly
  (07-16 → 0.5611 vs recorded 0.561; 07-17 → 0.5765 vs 0.577), confirming the
  harness is faithful.

## Corpus (frozen)

The 14-session set is the `#543`/`#544` evidence-script PART-3 target set
(latest live run per date **with** candidate rows; `n<10 OR mean+1σ all-veto`),
which already contains 07-16/07-17. Corpus digest `3da8fcdc7ce595b17d8d37fc`.

| date | n | CLEAN | sq floor (mean+1σ) | branch | operative | delta (prod) |
|---|---|---|---|---|---|---|
| 2026-04-23 | 5 | ✅ | 0.268 | acted | no | — (compressed; relax→status quo) |
| 2026-04-24 | 0 | ❌ | — | suppressed | no | unknown reason: tier/defensive_non_bear |
| 2026-04-25 | 2 | ❌ | 1.119 | **suppressed** | yes | unknown reason: tier/defensive_non_bear |
| 2026-04-26 | 9 | ✅ | 0.344 | acted | no | — (compressed) |
| 2026-04-27 | 6 | ✅ | 0.298 | acted | no | — (compressed) |
| 2026-05-03 | 2 | ✅ | 0.427 | acted | no | — (compressed) |
| 2026-05-04 | 43 | ✅ | 0.260 | not_small_n | no | — (n≥N0; guard inert) |
| 2026-05-06 | 45 | ✅ | 0.260 | not_small_n | no | — (n≥N0; guard inert) |
| 2026-05-12 | 0 | ❌ | 1.003 | **suppressed** | yes | unknown reason: kelly_zero:mu_none |
| 2026-05-13 | 0 | ❌ | 1.005 | **suppressed** | yes | unknown reason: kelly_zero:mu_none |
| 2026-05-14 | 0 | ❌ | 1.005 | **suppressed** | yes | unknown reason: kelly_zero:mu_none |
| 2026-05-15 | 0 | ❌ | 1.007 | **suppressed** | yes | unknown reason: kelly_zero:mu_none |
| **2026-07-16** | 5 | ✅ | 0.561 | **acted** | **yes** | **{ATI, EME, BWXT}** |
| **2026-07-17** | 5 | ✅ | 0.577 | **acted** | **yes** | **{ATI, EME, BWXT}** |

- Affected (CLEAN & n<N0): 6. **Operative & CLEAN: 2** (07-16, 07-17).
- On 07-16/07-17 the guard relaxes the floor 0.561/0.577 → 0.50 and admits
  exactly `{ATI, EME, BWXT}` (all μ>0); `XLI`/`XLY` (μ<0) stay vetoed. Matches
  base-RFC AC-a / amendment AC-A exactly.

## GO criteria (§4), over operative affected sessions

| criterion | result |
|---|---|
| volume `N ≥ 10` | ❌ **2 < 10** (only structural bar not met) |
| (i) zero partition mislabel | ✅ 07-16/17 correctly CLEAN; every real failure-residue day suppressed or inert; synthetic AC-B/AC-F/AC-G + marker all NOT-CLEAN |
| (ii) delta traceable, no gate bypass | ✅ {ATI,EME,BWXT} μ>0 → pass calibrated-μ gate; floor is downstream of `risk_gate_vol`, upstream of Selection/QP/Kelly → skips no gate |
| (iii) admits ≥1 name on ≥70% operative | ✅ 2/2 = 100% (N=2, underpowered) |
| (iv) no new alarm class | ✅ only `smalln_guard_suppressed` (designed sentinel `#549`), fires solely on suppressed days |

**NO-GO triggers — none tripped:** no operative-session mislabel; no delta-name
gate bypass; sentinel `#549` deployed and fires on suppressed days.

## The eligibility ledger works on REAL failure-residue (the P0 payoff)

The strongest result is not the synthetic tests but the **real** suppressions:
- **05-12…05-15** (μ-none score inflation, `kelly_zero:mu_none`): a naive
  option-(a) guard would have relaxed the floor to 0.50 and **mass-admitted
  33–38 names** on a failure day. The `#207/#208` eligibility precondition
  correctly returns NOT CLEAN (unknown reason) → **suppressed**.
- **04-24/04-25** (unknown `tier`/`defensive_non_bear`): NOT CLEAN → suppressed
  (fail-closed on unrecognized reasons).
- Synthetic (DEPLOYED predicate): AC-F generation-starve (expected 145, entered
  5) → NOT CLEAN `mass_balance`; AC-B `score_missing>0` → NOT CLEAN
  `funnel_integrity`; AC-G wash-share 40% → NOT CLEAN `share_bound`; healthy
  governed n=5 and under-bound wash → CLEAN.

## Critical caveats (must inform the activation decision)

1. **Replay cannot validate the mass-balance-vs-INDEPENDENT-counter protection
   (the P0 core, AC-F) on historical sessions.** `expected_universe` is emitted
   by the candidate-generation stage — instrumentation that **postdates** every
   replay session — so it is reconstructed as `entered_scan + recorded
   exclusions`, which makes mass-balance vacuously true in replay. That
   protection is validated here **only** by the synthetic AC-F test (deployed
   code returns NOT-CLEAN); real-data confirmation needs the live counter.
2. **Config floor-mode mismatch.** Guard keys are staged in the shadow config
   which runs `buy_floor=adaptive_quantile`, whereas **production** runs
   `adaptive_mean_std` (guard keys absent, correctly awaiting GO) — and the
   07-16/17 incident occurred under production `adaptive_mean_std` (floor
   0.561). The replay evaluated **both**: under mean+1σ the delta is
   {ATI,EME,BWXT} (faithful to production); under q0.80 the guard still admits
   {ATI,EME,BWXT} but with a smaller delta. **Implication:** live shadow accrual
   under the *current* shadow config exercises the guard against the quantile
   floor, where `q80 ≤ scores` makes the relax-only `min()` usually degrade to
   status quo → **few/zero operative sessions**. Live shadow accrual is thus a
   *weak* path to `N_shadow=10`; the faithful production-behavior evidence is
   the mean+1σ replay.
3. Score-**scale-collapse** (05-04/05-06) is not caught by the eligibility
   ledger (known gap; needs a separate calibrator-scale integrity check).
   Harmless to the guard here because those days are `n ≥ N0` (branch inert).

## Recommendation (activation sequence unchanged)

Reach GO by accruing to `N_shadow=10` operative affected sessions — **preferably
via an expanded historical replay under the production `adaptive_mean_std`
floor**, since shadow-arm quantile accrual is a weak proxy — then explicit
operator authorization on the record, then the pin PR restoring keys to
production + golden (superseding RenQuant#498). Neither agent may self-authorize.
Do NOT flip the production key on this replay. No merge of this PR implies
activation; it commits the frozen verdict only.
