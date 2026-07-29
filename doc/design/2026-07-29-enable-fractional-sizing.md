# DESIGN (for operator sign-off): switch on fractional sizing for strategy-104

**Status:** proposal. **No config changed by this PR.** The change it proposes
is a live capital gate and needs explicit sign-off.

**The change itself is four lines of config.** The reason this is a design doc
and not a flag flip is that it alters what reaches the broker.

---

## 1. What is being proposed

Add to `strategy_config.json` (strategy-104, the PINNED subrepo copy):

```json
"execution": {
  "fractional_shares": {
    "enabled": true,
    "min_notional": <TBD, see §6>
  }
}
```

Today that block is **absent entirely**. The live `execution` object holds only
`_settlement_reason_2026_05_24`, `enabled`, `t2_settlement_days`,
`buying_power_mode` `[VERIFIED — live strategy_config.json]`.

`kernel/sizing.py:204` states the contract plainly: *"no behaviour change
unless strategy-104 opts in via `execution.fractional_shares.enabled`"*. The
S-FRAC v2 machinery is built, merged and pinned in the pipeline. **Strategy-104
never opted in.** It has been dark since it landed.

## 2. What it fixes, measured

When a name's position target is below one share price, integer sizing floors
it to zero and the candidate is dropped after passing every quality gate.

2026-07-27, an unblocked session `[VERIFIED — logs/daily_104/2026-07-27.log]`:

```
118 tickers -> 109 candidates -> 80 (vol gate) -> 15 (weak-buy floor)
-> 4 (conviction gate) -> Kelly sizes 4/4 non-zero, avg 6.1%

TSLA  sized to 0  (remaining_cash=$9301  price=$309.22)
AMZN  NEW_BUY 1 share @ 231.33  ($231, 2.2% target)
SPG   NEW_BUY 1 share @ 231.70  ($232, 2.2% target)
EME   sized to 0  (remaining_cash=$8838  price=$742.73)

2 orders placed, $463 of $9,301 cash = 5.0% deployed
```

Size-zero skips across the visible July sessions `[VERIFIED]`:

| date | size-zero skips | placed / cash | deployed |
|---|---:|---|---:|
| 07-02 | 2 | $240 / $8,434 | 2.8% |
| 07-10 | 1 | $800 / $9,140 | 8.8% |
| 07-13 | 2 | $661 / $9,908 | 6.7% |
| 07-27 | 2 | $463 / $9,301 | 5.0% |
| 07-28 | 1 | $0 / $6,868 | 0% |

Names hit: TSLA ($309.22), EME ($742.73), SPG ($236.69).

## 3. What it does NOT fix — read this before expecting a large effect

On 2026-07-27 fractional sizing would have given TSLA and EME their target
notional (~$231 each) instead of zero, taking the session from **$463 to
roughly $925** `[DERIVED — 2 skipped names at the emitted 2.2% target]`. That
is still only **~10% of available cash**.

The larger constraint is the **target itself**. Kelly produced an average 6.1%
target; the emitted orders carried **2.2%**, scaled by conviction
(`conv=0.44`, `conv=0.40`) `[DERIVED — emitted log line vs the Kelly line;
mechanism not read from source]`. Fractional sizing does not touch that.

**So: fractional is necessary and not sufficient.** Anyone signing this off
expecting the idle half of the book to deploy will be disappointed. It removes
one of at least three constraints; the other two are the wash-sale block
(pipeline#223) and the conviction scaling of the target (unexamined).

An unexplained observation found while measuring, NOT resolved here: the
config says `kelly_sizing.fractional = 0.5` but the runtime logged
`fractional=0.30` `[VERIFIED — both lines]`. That discrepancy should be
understood before or alongside this change, since it also scales every target.

## 4. Why the risk is lower than it looks

- The **broker-side guard is the authority**, not this config.
  `sizing.py:266-271` documents sizing-time eligibility as **advisory**: the
  fail-closed check is `renquant-execution` stage 1 (`is_fractionable` +
  no-submit classification). A name that is not fractionable at the broker
  cannot be submitted fractionally regardless of this flag.
- **Whole-share remains the fallback path**, not a removed one. A name that
  cannot be fractionally sized takes the existing A-3 route unchanged.
- **A known-non-fractionable blocklist already exists**
  (`execution.fractional_shares.non_fractionable_tickers`) and a malformed
  blocklist **fails closed for all names** `[VERIFIED — sizing.py:279]`.
- The pipeline carries `tests/test_fractional_sizing_stage2.py` (15 tests)
  covering the whole-share/fractional split.

## 5. What could go wrong

1. **Dust orders.** Small targets produce small fractional notionals. This is
   what `min_notional` is for; it must be set deliberately (§6), not defaulted.
2. **More positions, same book.** Removing the floor admits names that were
   silently dropped, so position count rises. `max_concentration = 0.12` and
   `max_position_pct = 0.15` still bind, but sector caps and the position-count
   behaviour should be re-checked against a full-funnel sim.
3. **Exit-side asymmetry.** If entries can be fractional, partial exits and the
   tax-lot logic must handle fractional quantities. This is claimed by S-FRAC
   v2 stages 0-2 but is NOT verified by this document.
4. **Settlement / buying-power interaction** with `t2_settlement_days` and
   `buying_power_mode` is unexamined here.

## 6. What must happen before this is switched on

- [ ] Choose `min_notional` explicitly, with the reasoning recorded. A floor
      that is too low creates dust; too high reproduces the current problem.
- [ ] **Full-funnel sim** on the live config with the flag on vs off, per the
      live-tree mutation preflight rule — "committed = safe" is false here.
      Compare: orders placed, notional deployed, position count, sector
      exposure, and that no EXISTING order changes.
- [ ] Confirm exit/tax-lot paths accept fractional quantities (risk 3).
- [ ] Operator sign-off, because this changes what reaches the broker.

## 7. Rollback

Remove the `execution.fractional_shares` block, or set `enabled: false`. The
whole-share path is unchanged and untouched by this proposal, so reverting
restores exactly today's behaviour. No artifact, model, or pin is involved.

## 8. Provenance

All figures `[VERIFIED]` from `RenQuant/logs/daily_104/2026-07-*.log`, the live
`strategy_config.json`, and `renquant-pipeline/kernel/sizing.py` — all read
READ-ONLY. The two `[DERIVED]` quantities are marked at the point of use. No
production surface was modified.

Related: hallovorld/renquant-orchestrator#606 (the funnel investigation),
renquant-pipeline#223 (wash-sale materiality), renquant-pipeline#224 (the
misleading skip message this investigation started from).
