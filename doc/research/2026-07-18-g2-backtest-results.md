# G2 costed reversal backtest (H1) — results: FAIL, G2 NO-GO (tombstone)

Date: 2026-07-18
Prereg (FROZEN LAW): `doc/research/2026-07-17-g2-reversal-backtest-prereg.md`
(sealed by merged PR #546; inputs at `doc/research/g2-manifest/`).
Results artifact: `doc/research/g2-manifest/2026-07-18-g2-backtest-results.json`.
Script: `scripts/g2_reversal_backtest.py` (seeded, deterministic, fail-closed
seal check; reproduces the artifact byte-for-byte modulo timestamp).

## Verdict — FAIL [VERIFIED]

**Base-fee net lower bound = −29.9 bp/day (−0.002986), ≤ 0 ⇒ FAIL.**
The +10 bp stress lower bound is −38.0 bp/day (−0.003804), also ≤ 0 —
the frozen §5 rule fails on BOTH clauses independently.

Per prereg §5/§7 this **prevents the paper-shadow registration and records
a G2 NO-GO**. This section is the tombstone:

> **TOMBSTONE (G2, 2026-07-18).** H1 — liquid-tier cross-sectional 3-day
> reversal at 1-day horizon on Alpaca spot crypto, long-only, net of fees
> vs matched BTC buy-and-hold — FAILED the preregistered historical
> feasibility screen on the sealed 2021-11-26 → 2026-07-15 corpus
> (n = 1,693 scored days). Net MBB 90% lower bound: −29.9 bp/day at base
> fees, −38.0 bp/day at +10 bp slippage (both must be > 0). The gross
> (zero-fee) edge vs baseline was already ≈ 0 (−1.7 bp/day, t = −0.29);
> 25 bp/side on ~0.83×/day two-way turnover adds ≈ −20.8 bp/day. No
> member of the frozen 20-spec family has positive net mean d_t (best
> t = −0.48). The §3(b) registered censoring (WBTC purge, SHIB gap,
> dark windows) inflates PASS, so the FAIL is a fortiori robust to it.
> No paper shadow, no capital, no re-pitch of this family; any revival
> requires a NEW registration under a materially different hypothesis.

The §3(b) CONDITIONAL downgrade registered at seal time is moot: it only
downgrades a PASS, and the registered bias direction (censoring inflates
net d_t toward PASS) strengthens the FAIL rather than qualifying it.

## The numbers (H1: reversal 3→1, liquid-10, k=3)

| scenario | fee/side | mean d_t | t | MBB 90% LB | LB > 0 |
|---|---|---|---|---|---|
| gross | 0 | −1.68 bp | −0.29 | −9.1 bp | no |
| **base** | **25 bp** | **−22.5 bp** | **−3.82** | **−29.9 bp** | **no ⇒ FAIL** |
| **+10 bp** | 35 bp | −30.7 bp | −5.21 | −38.0 bp | no ⇒ FAIL |
| +25 bp (stress info) | 50 bp | −35.4 bp | −6.49 | −42.3 bp | no |

- n valid days: **1,693** (first execution 2021-11-26; last scored open
  2026-07-15 → open 2026-07-16).
- Names per day: mean 2.97 of 3; 97.6% of days fully invested at 3 names;
  minimum 1 (zero-volume/unexecutable days; allocations sat in BTC per the
  residue rule). No form day ever had < 3 rankable names, so the frozen
  "bottom-3" construction was always well-defined.
- Expected daily turnover (one-way): mean **0.416**, median 0.340. At
  25 bp/side the implied fee drag is ≈ 2 × 0.416 × 25 bp ≈ 20.8 bp/day —
  which reconciles the gross→base mean gap exactly (−1.7 → −22.5 bp).
- Block length (Politis-White automatic, fitted on base-fee d_t): 2 days;
  MBB percentile lower bound at α = 0.10, B = 10,000, seed 20260718.
- Edge cases (base): 2 forced delisting exits (cost-charged at last
  available price), 47 unexecutable buys, 49 frozen sells, 0 min-notional
  clips (the $10 floor never bound in either verdict scenario).

Reading: the failure is NOT a cost story alone. Gross of all costs the
long-loser tilt does not beat the BTC leg it must displace; costs then
bury it. There is no fee tier, spread assumption, or execution upgrade
that rescues a construction whose gross edge is ≈ 0 against its own
baseline.

## Family max-t diagnostic (prereg §1 — diagnostic only)

20-member frozen family ({momentum, reversal} × {3→1, 7→1, 7→7, 30→7,
90→20} × {full, liquid-10}, each the §4 template, k = 3), base-fee net
d_t on the common valid grid 2022-02-21 → 2026-07-15 (n = 1,606), joint
MBB (shared blocks, length 5), studentized reality-check max-t:

- **Every one of the 20 members has negative net mean d_t.** Observed
  max t across the family: **−0.48** (momentum 30→7, full tier).
- H1's observed t: −3.59; family-adjusted p (reality check) = 1.0.
- Turnover ordering behaves as expected: slow members (90→20, 30→7) lose
  least; daily-horizon members lose most. The family's best member is
  still a net loser to BTC buy-and-hold.

Context this gives the verdict: the #532 screen's apparent reversal
signal does not survive executable-portfolio construction and costs
anywhere in the searched family — the H1 selection was noise mining, and
the max-t diagnostic confirms there was nothing adjacent to it either.

## Seal verification (fail-closed, passed)

- Sealed candidate fingerprint == frozen constant
  `sha256:0068eb93359ff3a7bc6e46e6be948d5b58ba6803940e4b5e80d0f4318d0c1cc1` ✓
- Live store manifest re-derives the same fingerprint and is
  byte-identical to the sealed candidate ✓
- All 42 per-pair canonical content sha256 match the seal (store bars =
  sealed bars, tamper-checked at run time by the script) ✓
- Membership schedule (sha256
  `4481da45a6792f026765afe6d3832cb4b795f6b12da5fd6aa65b1bcde9dbdb86`) and
  prereg (sha256
  `fe5bd3866c93523685c5faa55516c471e7f8ae0f50b0b620517c52045b15f63b`)
  digests recorded in the artifact.

## Declared conventions (frozen text did not pin; all in the artifact)

The frozen construction left a small set of micro-conventions open; each
was resolved by the reading closest to the frozen text, declared in the
artifact's `accounting_declarations`, and none is outcome-relevant (the
gross edge is ≈ 0 before any of them can matter):

1. "full-20" family tier = the §4 template with the top-10 liquidity cut
   removed (all non-stablecoin pairs listed on T−1 per the sealed
   schedule). The "-20" names the #532 screen's store; a hardcoded
   20-pair list would violate the §3 point-in-time discipline.
2. Initial notional $10,700 (the G2 sleeve cited in §2); the $10
   min-notional never bound at base or +10 bp. Under +25 bp the
   compounding fee bleed deflates the sleeve until clips park it in BTC —
   a mechanical consequence of the frozen rules that only makes the
   reported +25 bp stress LESS negative (strategy-favorable direction;
   stress info only).
3. Block length rule = Politis-White (2004) automatic selection with the
   Patton-Politis-White (2009) correction (the standard fitted-
   autocorrelation selector), reused across scenarios with paired seeds.
4. Fee accounting: fees charged on every traded leg (incl. BTC residue
   legs, forced exits, baseline entry); rebalance targets scaled by a
   fixed-point factor so invested value = pre-trade value − fees (exact,
   no negative cash).
5. Horizon-h family members rebalance every h days with daily open-to-open
   marks (non-overlapping cycles).

No spec point required a STOP: every ambiguity had a unique reading
consistent with the frozen §4 template, and the verdict does not turn on
any of them.

## Disposition

- **G2 is killed** per prereg §7 ("Historical failure (base or +10 bp,
  §5) ⇒ G2 killed and the memo records the tombstone").
- No paper-shadow registration may be submitted for H1 or any member of
  the frozen family; a different hypothesis (different signal class,
  venue, or horizon structure with an economic rationale) would be a NEW
  registration and must clear its own §3 seal.
- Nothing here touches 104, live configs, or capital. Advisory record
  only.
