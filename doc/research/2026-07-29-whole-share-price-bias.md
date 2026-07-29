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

**Correction (this revision):** the original text read the umbrella's
fallback copy (`RenQuant/backtesting/renquant_104/strategy_config.json`) as
the live surface and reported both switches as absent (`null`). That copy is
stale — `scripts/daily_104.sh:113-119` resolves the **pinned**
`renquant-strategy-104` subrepo config first. Read against the pinned config
`[VERIFIED — read renquant-strategy-104/configs/strategy_config.json on
`main` this session]`, both switches already exist and are explicitly OFF,
not absent — the same umbrella-vs-pinned drift already documented in
`renquant-strategy-104#71`:

    execution.fractional_shares.enabled     -> false  (declared; S-FRAC v2, min_notional=1.0, min_fractional_trade_notional=25.0)
    sizing.one_share_floor_enabled          -> false  (declared; A-3)
    kelly_sizing.disable_extra_multipliers  -> unset  (genuinely absent — this one only)

The umbrella fallback copy shows `null`/absent for the first two keys and a
drifted `kelly_sizing.fractional=0.5` (pinned copy: `0.3`)
`[VERIFIED — read RenQuant/backtesting/renquant_104/strategy_config.json
this session]`. The conclusion is unchanged (both remedies are OFF in
production); "absent from config" was the wrong description — the correct
one is "declared, and explicitly disabled."

### The price bias is real. Measured, May-July live logs

`[VERIFIED — this session, canonical daily-prod logs only:
`ls logs/daily_104/ | grep -E '^2026-0[567]-[0-9]{2}\.log$'` (64 files);
`scripts/daily_104.sh:40` pins the canonical name to exactly `$LOG_DIR/
$DATE.log` with no suffix, which excludes 65 ad hoc `_shadow`/`_smoke`/
`_manual`/`_readonly`/`_after_fix`/`_multirepo`/etc. runs also present in
the directory. Then `grep -h "NEW_BUY"` / `grep -h "insufficient cash —
skip"` across those 64 files]`:

|                        |  n | median price | mean price |
|------------------------|---:|-------------:|-----------:|
| BOUGHT                 | 33 |     $160.59  |   $227.23  |
| SKIPPED (sized to 0)   | 11 |     $764.28  |   $810.43  |

**Skipped names are 4.76x more expensive at the median**
`[DERIVED — 764.28/160.59]`.

The skipped set: ASML $1,777 (twice), BLK $994.85, CAT $993.42, EME $782.08 /
$764.28 / $742.73, AVGO $360.34, TSLA $309.22, SPG $236.69, BWXT $177.07.

This is qualitatively worse than the idle cash. Lost deployment is opportunity
cost. This is a **factor exposure nobody chose**: the model ranked ASML, BLK,
CAT and EME highly enough to clear every admission gate, and integer share
arithmetic silently removed them. The portfolio carries an implicit
anti-high-price tilt produced by rounding, not by any risk decision.

It is not absolute — LLY at $1,142.81 was bought on 2026-06-09.

### The inferential claim is RETRACTED

A previous revision reported a one-sided Mann-Whitney U (U=323, p=6.6e-5) and
called the gap "statistically distinguishable from chance". **That test is not
admissible on this sample and the claim is withdrawn.**

The 33 and 11 rows are **repeated daily decisions, not independent draws**. The
skipped set alone repeats tickers — EME appears 3x (07-10, 07-13, 07-27), ASML
2x — and the bought side repeats ticker/session structure the same way. A rank
test that assumes 44 independent observations understates the uncertainty by an
amount I have not quantified, so no p-value from it means anything.

What survives is **descriptive**: bought median $160.59, skipped median
$764.28, a 4.76x ratio `[VERIFIED — logged prices]`. And separately, the
**mechanism**, which needs no inference at all.

## What this changes about #606

Sections 1-2 framed the problem as under-deployment. That framing was
incomplete.

**The demonstrated fact, which needs no statistics:** the whole-share execution
rule can zero a candidate that has already cleared every admission gate. The
sizing log records it happening, name by name, with the cash available at the
time. That is an execution-layer override of a ranking decision, and it is
proven by the log lines alone.

**Scoped back from the previous revision:** I wrote that "the live book is not
testing the model the model was validated as". That is a claim about the
validation contract, and I have not attached that contract here — I do not know
what execution assumptions the model's validation made. The supportable claim is
narrower and still worth acting on: **an execution rule silently overrides
ranked admissions, and the names it removes are systematically the expensive
ones.**

`[ASSUMED — not measured]`: whether the excluded high-price names would have
outperformed. That is the separate question and I am not estimating it from
1-2 days of forward return.
