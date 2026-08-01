# Decomposing the gate answers the question #670 left open

**Bottom line.** #670 measured **0 unaided passes in 11 artifacts** and said the
distinction between *"the gate is right and the candidates are bad"* and *"the gate is
mis-specified"* could not be made while every admission is manual. Decomposing the
verdict into its sub-criteria makes it: **three sub-gates reject 11 of 11**, and **two of
them reject the same regime every single time.**

## The matrix `[本次实测 2026-07-31]`

| sub-criterion | fails |
|---|---:|
| `sanity` | **11/11** |
| `sanity_regime_ic` | **11/11** |
| `trade_monotonicity` | **11/11** |
| `wf` | 10/11 *(only the deployed artifact passes)* |
| `trade_contract` | **0/11** |

`trade_contract` passing 11/11 is the control that matters: the artifacts **are** being
evaluated, not merely erroring out, so the three 11/11 rows are verdicts and not crashes.

## The structural signature

| criterion | failing regimes | artifacts |
|---|---|---:|
| `sanity_regime_ic` | `BULL_CALM` | **11/11** |
| `sanity_regime_ic` | `CHOPPY` | **11/11** |
| `sanity_regime_ic` | `BULL_VOLATILE` | 10/11 |
| `trade_monotonicity` | `BULL_CALM` | **11/11** |

> **`BULL_CALM` fails two different sub-criteria on every artifact without
> exception.** Eleven vintages trained across a month, all failing the same regime on
> two criteria, is a stable structural signature rather than a per-vintage accident.

**Two things that sentence must NOT be read as saying**, because its first draft did:

- ~~*"two **independent** sub-criteria"*~~ — **not established.** `sanity_regime_ic` and
  `trade_monotonicity` are both evaluated on the same regime slice, so a single property
  of that slice's population could fail both. Two failures are not two pieces of
  evidence until their independence is shown, and nothing here shows it.
- ~~*"...is a property of the criterion or of that regime's population — **not eleven
  independently bad models**"*~~ — **withdrawn as a non-discriminating step.** All 11
  artifacts are the same recipe on overlapping data (see the population caveat below),
  so they are **not independent draws**. Their common failure is exactly what every
  hypothesis on the table predicts, including "the candidates are bad", so it separates
  none of them. Ruling out "eleven *independent* failures" rules out something the
  population never offered.

## What this licenses, and what it does not

**Licensed:** a criterion that rejects **100%** of the population it judges carries no
information about which candidate is better. It can reject; it **cannot rank**. That is
why the only path to production has been the operator override #670 documented — the
gate offers no gradient to improve along.

**Not licensed:** the conclusion that the gate is *wrong*. A 100%-reject gate can be
perfectly correct if all eleven candidates genuinely are bad in `BULL_CALM`. What the
measurement establishes is that **the gate cannot tell us which**, and that a month of
retraining moved none of these rows.

**Population caveat, stated rather than buried:** all 11 artifacts are the **same
recipe** (`alpha158_fund`) on overlapping data. "11/11" is over a narrow population,
nothing here generalises to a different recipe — **and, as above, the eleven are not
independent draws, so their agreement carries far less information than eleven
independent agreements would.** The caveat was already here; what was missing was
applying it to this document's own headline inference.

**Not reported:** I also tried to extract each artifact's `shuf_ic` against the enforced
`|shuf_ic| < 0.005` leakage bar. My extraction keyed on the wrong field and returned
**zero rows**, so there is no shuffled-IC result in this document. A zero-row extraction
is not a zero-count finding.

Tests: 5, including the `trade_contract` anti-vacuity control. Filed against
`renquant-backtesting#90`.


---

## Round N+1 2026-08-01 — bound to the artifacts, and one published rate moves

Reviewed `[codex on orch#673]`, two demands, both taken.

**1. A retracted inference was still live in executable text.**
`test_BULL_CALM_fails_two_independent_subgates_on_every_artifact` asserted the criteria
were *independent* and attributed the pattern to the criterion/regime rather than to the
model population — the exact claim this PR withdrew in prose while leaving it as an
assertion. Renamed to
`test_BULL_CALM_CO_FAILS_regime_ic_and_monotonicity_on_every_artifact` and rewritten to
the measured co-failure only.

**2. The matrix was unbound.** `ops/renquant104/subgate_matrix_extract.py` now emits every
row with its resolved path, the file's **sha256**, and a `content_group` shared by
byte-identical files; `--verify` re-derives the whole matrix and fails on drift; the
sidecar records the extraction command.

### Duplicate-content accounting — and it mattered

Over the full `panel-ltr.alpha158_fund*` glob there are **30 artifacts but only 12 distinct
content groups**, one holding **13 byte-identical files**. So a matrix over the wider set
would not have been 30 observations. **Among the eleven this document uses: 11 rows, 11
distinct digests, zero duplicates** `[本次实测 2026-08-01]` — the rates here are not
inflated, which is now checked rather than assumed.

### A published rate moves: `wf_fail_rate` 10/11 → **9/11**

Re-derivation disagreed with the hand-built matrix on exactly one cell:
`weekly_20260706T230931Z.staging.json` carries `passed: true` on disk and was recorded
`FAIL`. **Every other cell re-derived identically.** The summary is corrected rather than
the CSV bent to match.

### And the fact the single `wf` column was hiding

The deployed artifact's `wf` is `PASS` — but `gate_verdict_before_override` is **`FAIL`**
and `operator_authorized_override` is **`True`** (operator directive 2026-06-22). Two new
columns make that explicit. **No staging artifact was overridden**; the override is unique
to the served one, and a test pins both halves.

`wf` deliberately keeps its post-override meaning: silently redefining a published column
would move this document's numbers under its own conclusions.

---

## ROUND 3b — two readings of the same field, wrong in opposite directions

The extractor and the rename landed from the parallel session; its verification found a
real error the rebind alone could not (`wf_fail_rate` 10/11 → 9/11: one artifact carries
`passed=true` on disk and had been recorded FAIL). **Verifying published cells catches
things that recomputing them cannot** — a wholesale re-derivation replaces the numbers
instead of contradicting them.

One correction on top of it, and it is a disagreement worth recording because **both
readings were wrong, in opposite directions**:

`trade_monotonicity.regimes` is a **list of per-regime records**.

- the landed comment said it *"never names a regime"* and parsed the failing set out of
  `reason`. **It does name one** — every entry carries `regime`;
- reading that list naively **overstates** the failure. On
  `panel-ltr.alpha158_fund.previous.json`, `BULL_VOLATILE` (n=7) and `CHOPPY` (n=9) both
  carry `passed: false` with **`eligible: false`**, while the producer's own reason says
  *"failed in active regime(s): **BULL_CALM**"*. The producer counts only eligible
  regimes; a regime with n=7 is not a failure the gate asserts.

So the extractor now reads the **structure** (robust), respects **`eligible`** (correct),
and **cross-checks against the reason**, reporting a disagreement rather than silently
preferring one — *"BULL_CALM (reason says: CHOPPY)"* if they ever diverge.

Measured after the fix: `BULL_CALM` on **30 of 30** named artifacts, agreeing with the
reason string everywhere. Structure alone would have said three regimes; the reason alone
is prose.


---

## ROUND 4 — the recorded glob could not select the files it claimed

> *"the provenance sidecar records a non-executable artifact glob: its value ends in
> `*.json (deployed + *.staging.json)`, and the recorded extraction command passes that
> literal to `glob`, which cannot select the stated 11 files. This defeats the purpose of
> reproducible selection provenance."* `[codex on #673]`

Exact. **Prose was glued into a glob field**, so the command that was supposed to
regenerate the CSV selected nothing. Provenance that cannot be run is a description of
provenance.

The selection never needed narration — it is two patterns:

```
--artifact-glob '…/panel-ltr.alpha158_fund.json'
--artifact-glob '…/panel-ltr.alpha158_fund*.staging.json'
```

`--artifact-glob` is repeatable now and their **union** is the population, so the recorded
command is the command. The sidecar carries both the executable command **and** the
explicit `selection` list it produced, because a later reader whose store has drifted
needs to see which files the recorded run actually chose — and `--verify` compares the two
and **fails on selection drift before comparing any field**, so a matrix can never be
re-derived over a silently different population while every cell still "matches".

### Running it immediately showed the store had moved

The re-run selected **12** artifacts, not 11: `weekly_20260801T110005Z.staging.json`
landed today and did not exist when the matrix was first built. **The old prose-glob could
never have shown that** — it selected nothing at all, so nothing could disagree with it.

Rates over distinct content, 12 groups: `sanity` 12/12,
`sanity_regime_ic` 12/12,
`trade_monotonicity` 12/12,
`wf` 10/12, and the control
`trade_contract` **0/12**. The conclusion is unchanged and now rests on a
selection anyone can reproduce.

**Three count-pins removed** while I was in there — row count, distinct-digest count, and
the BULL_VOLATILE tally were each asserted as literals against a population that grows
daily. They are properties now (`one row per distinct content`, `bv == len(rows) - 1`).
Pinning a number against a moving subject is the defect this document already records
once; it was present three more times in its own tests.
