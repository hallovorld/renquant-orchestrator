# 2026-09-21 — MoE L2 paper bandit: the four arms are the same live account; the bandit now refuses

## Conclusion

The L2 paper bandit (`renquant_orchestrator.l2_paper_bandit`, live since
2026-09-03) has been reporting `mixture_minus_champion ≈ −3.5%` and "every
shadow arm trails the champion". That number measures nothing. Each arm's
daily return is `live_state_snapshots.portfolio_value` of its lane DB, and the
three shadow lanes run READ-ONLY against the SAME Alpaca account: their marks
are within 0.5% of the champion's on 39/39, 34/34 and 34/34 shared dates
(median 1.5–2.7 bps, max 34 bps); since 09-03 `cash` is identical to the cent
and `n_holdings` identical on every shared date `[VERIFIED: read-only query
on data/runs.alpaca*.db]`. Same-day returns agree within ≤ 9 bps. The lanes
hold no paper book.

The −3.5% is coverage: the shadow DBs start 07-28 / 08-04 while the champion
starts 04-24, so on the 71–76 dates the shadow arms were not marked the
champion compounded +3.6% / +8.5% and the arms sat at 1.0. `arm_value ×
champion_compounded_on_unheld_dates` = 1.0646 / 1.0682 / 1.0672 against the
champion's 1.0683 — residual ≈ 0 `[VERIFIED from l2_moe_mixture.jsonl, 108 rows]`.

The §2 contract (orch#918) presumed "expert PAPER books that the shadow-lane
infrastructure already marks daily". That premise is false, so the regret
series and the daily MoE readout (hand-sent 09-15 / 09-16 as "NOT a prod
candidate, −3.5%") were coverage artefacts — retracted to the operator. The
arithmetic of the bandit is correct; its input is not what the design assumed.

## Change

- `load_book_identity` / `same_book_as_champion`: a shadow arm whose marks lie
  within 0.5% of the champion's on ≥ 90% of ≥ 5 shared dated snapshots is the
  same account (distinct books with their own positions diverge by percents
  within days); `cash` / `n_holdings` identity is reported as corroboration.
- `main()` refuses (`REFUSED`, exit 1, nothing appended, no mixture written)
  when any arm is the same book, naming the evidence per arm. Fewer than 5
  shared dates → not judged. The self-verifying log contract is unchanged.
- Tests: same-account arms are refused and nothing is published; arms with
  their own books are priced; too-few-dates / column-less fixtures are not
  judged. 27 passed (`test_l2_paper_bandit.py` + the manifest evidence-glob
  test).

## Evidence (§4(b))

Patched module against the live DBs with a scratch `--log-dir` (the real log
untouched): `REFUSED — profile_blend: marks within 0.5% of the champion's on
39/39 shared dates (100%) …; profile_blend_mom 34/34; profile_blend_rb_mom
34/34`. `[VERIFIED 2026-09-21]`

## What this does NOT do

It does not make the lanes comparable. That needs a paper book per shadow
lane — simulate fills from the lane's own recorded daily decisions, mark
daily, charge the cost model — and a bandit re-run from those books: a design
PR (allocation machine §2 premise repair). Until then the scheduled job exits
1 daily with the reason above, which is the honest state; the memory record
is `moe-l2-bandit-audit-20260921`.
