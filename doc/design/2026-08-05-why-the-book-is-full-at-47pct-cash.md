# DESIGN — the book is "full" with 47 % of equity in cash. Three separate defects.

**Status: DESIGN ONLY. Nothing here is implemented.** Every number below is
`[VERIFIED — 2026-08-05, this session]`, measured from the live Alpaca account,
the pinned strategy config, and the pipeline source.

---

## The state that prompted this

```
equity  $10,939.17
cash    $ 5,141.57   = 47.0 %
10 positions, invested $5,797.60 = 53.0 %
```

| ticker | mv | % equity |
|---|---:|---:|
| TSLA | $2,571.36 | **23.5 %** |
| WELL | $711.18 | 6.5 % |
| VLO | $604.78 | 5.5 % |
| PANW | $364.14 | 3.3 % |
| GOOG | $360.54 | 3.3 % |
| LRCX | $308.77 | 2.8 % |
| DDOG | $282.90 | 2.6 % |
| NVDA | $220.03 | 2.0 % |
| MRVL | $210.30 | 1.9 % |
| SOFI | $163.60 | **1.5 %** |

Eight of ten positions are **≤ 3.3 %**. One is **23.5 %**. The operator's
question — *"仓位是什么鬼？还有很多现金啊！"* — is the right question, and the
answer is three independent defects that happen to compose.

---

## Defect A — the slot cap is a NAME count, and its value was never chosen

`task_selection.py:31-34`:

```python
max_positions = int(regime_params.get(
    "max_concurrent_positions",
    config.get("max_concurrent_positions", 8),      # <- hardcoded fallback
))
```

**`max_concurrent_positions` is not set anywhere in the pinned
`strategy_config.json`** — not top-level, not in any `regime_params` block
`[VERIFIED]`. So the live cap is **8**, from a code default nobody selected.

The book holds **10**. Therefore `open_slots = 8 − 10 = −2`, and
`PrepareSelectionTask` logs *"no open slots"* on every run. **No new buy can be
admitted at all**, regardless of how much cash is idle.

Two things are wrong, and they are separate:

1. **The cap counts names, not capital.** Ten dust positions consume ten slots
   whether they hold 1.5 % or 12 % of the book. Capital deployment is not what
   the constraint constrains.
2. **The book is already OVER the cap.** Getting to 10 under a cap of 8 means
   some buy path does not enforce it — prod placed **6 buys on 2026-08-04**
   `[VERIFIED — trades table]`. So one path admits past the cap and another then
   locks the book out entirely. That asymmetry is the actual bug; the number 8
   is only the symptom.

### Candidate directions (NOT decided)

- **A1.** Set `max_concurrent_positions` explicitly per regime in the strategy
  config, so the live value is a reviewed choice rather than a fallback. This
  alone changes nothing about cash deployment — it just stops the number being
  accidental.
- **A2.** Gate on **deployed capital** as well as name count: admit while
  `invested_pct < target_invested_pct`, still bounded by a name cap. This is the
  change that would actually deploy the 47 %.
- **A3.** Find and close the path that bought past the cap. **This must land
  before A1/A2**: raising a cap that one path already ignores makes the drift
  larger, not smaller.

**Order matters.** A3 → A1 → A2. Doing A2 first would deploy cash through a
door we know is unenforced.

---

## Defect B — rotation is vetoed by a 75-day-stale artifact, and the message names the wrong pair

Today's veto: `ROTATION_REJECT swap=SOFI→CRWD reason=correlation_guard`.

But **ρ(SOFI, CRWD) = 0.30** `[VERIFIED]` — far below the 0.70 threshold. Of the
ten holdings, exactly **one** exceeds it: **PANW at 0.845**.

So the guard is doing something defensible — checking the buy candidate against
the whole post-swap book — while the log line names `SOFI→CRWD`, whose actual
correlation is 0.30. A reader is told the wrong relation. Same family as
orch#842.

And the input is stale:

```
watchlist-correlation.json   as_of_date 2026-05-22   lookback 60d   (file mtime 2026-05-23)
```

**75 days old.** Every rotation veto since May is decided by correlations
measured 2026-02-27 → 2026-05-22.

### Candidate directions (NOT decided)

- **B1.** Name the binding holding in the reject line
  (`reason=correlation_guard(PANW,ρ=0.845)`). Pure observability; no behaviour
  change; unblocks diagnosis immediately.
- **B2.** Refresh the correlation artifact on a schedule, and **fail closed on
  staleness** rather than silently using a 75-day-old matrix.
- **B3.** Only then ask whether 0.70-vs-whole-book is the right rule. **Do not
  touch the threshold while the input is stale** — that would be tuning a knob
  against a measurement error.

---

## Defect C — TSLA is 23.5 % against a 12 % regime cap

`regime_params.BULL_CALM.max_position_pct = 0.12`; TSLA is **23.5 %** of equity
`[VERIFIED]`. Nothing trims a position that drifts above the cap through
appreciation — the cap appears to bind at BUY time only.

This is the reverse of Defect A and it matters for the same reason: the book's
actual risk shape is not the one the config describes. **A concentration cap
that only applies at entry is a cap on intent, not on exposure.**

### Candidate direction (NOT decided)

- **C1.** Measure first: is there any trim path at all, and has it ever fired?
  I have not established that, and will not propose a trimmer before I do.

---

## What I am NOT proposing

- No threshold tuning (0.70, 0.12, 8) before the enforcement asymmetry (A3) and
  the stale input (B2) are fixed. Tuning a number whose gate is inconsistently
  applied, or whose input is 75 days old, produces a number that means nothing.
- No "just raise the cap" — the book is already **over** the current cap.
- Nothing about whether the new model should hold different names. That question
  cannot be answered while the portfolio constraint is this far from what the
  config says, because **the book is not currently expressing the model.**

---

## Where these land, and what that costs

| defect | repo | reaches live via |
|---|---|---|
| A1 (explicit cap) | renquant-strategy-104 | config PR → pin advance |
| A2 (capital-aware admission) | renquant-pipeline | code PR → pin advance |
| A3 (enforcement asymmetry) | renquant-pipeline | code PR → pin advance |
| B1 (name the holding) | renquant-pipeline | code PR → pin advance |
| B2 (refresh + staleness gate) | renquant-orchestrator + artifact job | PR → **new scheduled job** → authorisation |
| C1 (measure the trim path) | measurement only | — |

**Every behavioural item requires a `subrepos.lock.json` pin advance**, and the
pin-advance batch **orch#808 is already blocked awaiting operator
authorisation**. So none of A/B can change tonight's live behaviour without that
gate being opened first. Saying otherwise would be the speed-pressure failure
this project keeps a rule about.

## Immediate, no-authorisation-needed next step

**B1 and C1 are the two that cost nothing and unblock the rest**: one makes the
rotation veto legible, the other establishes whether a trim path exists at all.
Both are measurements or log text — no live behaviour changes.
