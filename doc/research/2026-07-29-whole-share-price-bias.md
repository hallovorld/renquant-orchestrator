# Whole-share rounding gives the book an unchosen anti-high-price tilt

**Date:** 2026-07-29. Follow-up to #606, which framed the idle half of the book
as under-deployment. That framing was incomplete.

---

## The finding

Chasing the 2.2%-vs-6.1% target gap led to a code comment that had already
diagnosed this on 2026-07-01, and to a consequence nobody had measured.

`kernel/pipeline/task_selection.py:244-259` (S6 A-3, dated 2026-07-02):

    The multiplicative sizing stack (Kelly x conviction x sigma-mult) can
    compound a target notional below ONE share of a high-price name
    (2026-07-01 OXY forensics: BLK target $324 < 1 share ~$1.1k ->
    size_insufficient_cash -> **selection drifts toward LOW-price names**).
    ... Default OFF; inert until strategy-104 defines
    `sizing.one_share_floor_enabled: true`.

So there are TWO dark switches for the same defect, not one, and BOTH are
absent from the live config `[VERIFIED]`:

    sizing                                  -> null   (one_share_floor)
    execution.fractional_shares             -> null   (S-FRAC v2)
    kelly_sizing.disable_extra_multipliers  -> unset

### The price bias is real. Measured, May-July live logs `[VERIFIED]`

|                        |  n | median price | mean price |
|------------------------|---:|-------------:|-----------:|
| BOUGHT                 | 33 |     $160.59  |   $227.23  |
| SKIPPED (sized to 0)   | 11 |     $764.28  |   $810.43  |

**Skipped names are 4.76x more expensive at the median** `[DERIVED]`.

The skipped set: ASML $1,777 (twice), BLK $994.85, CAT $993.42, EME $782.08 /
$764.28 / $742.73, AVGO $360.34, TSLA $309.22, SPG $236.69, BWXT $177.07.

This is qualitatively worse than the idle cash. Lost deployment is opportunity
cost. This is a **factor exposure nobody chose**: the model ranked ASML, BLK,
CAT and EME highly enough to clear every admission gate, and integer share
arithmetic silently removed them. The portfolio carries an implicit
anti-high-price tilt produced by rounding, not by any risk decision.

It is not absolute — LLY at $1,142.81 was bought on 2026-06-09 — but the 4.76x
median gap is not noise at n=33 vs n=11.

## What this changes about #606

Sections 1-2 framed the problem as under-deployment. That framing was
incomplete. The ranking is also being overridden by an arithmetic artifact,
which means the live book is not testing the model the model was validated as.
Any conclusion about live performance inherits that.

`[ASSUMED — not measured]`: whether the excluded high-price names would have
outperformed. That is the separate question and I am not estimating it from
1-2 days of forward return.
