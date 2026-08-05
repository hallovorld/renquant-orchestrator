# 2026-08-05 — GOAL-7 Arm A RESULT (exploratory; certifies nothing)

**Registration:** `doc/research/2026-08-05-goal7-momentum-per-regime-prereg.md`,
frozen earlier today, before this arm was computed.
**Arm:** A — RECONSTRUCTION. Registration §3: *it can motivate; it cannot
certify.* Only Arm B (the served ledger, ≥30 matured BULL_CALM dates, ~2027)
certifies. Any claim below that does not name its arm is inadmissible.

## Bottom line

**All four §6 conditions hold on the primary regime — and that certifies
nothing.** `[VERIFIED — this session]`

The decision this asks for: **run Arm B when the ledger matures** (~2027), and
**do not re-weight anything now**.

## What was run

The served momentum member's construction (`train_momentum_artifact` under the
served artifact's own params, `content_sha256 a824c480…`, window 252 / skip 21)
scored over **every matured panel date** — 2016-11-16 … 2026-05-07,
**2,380 dates, 661,622 rows** — and the resulting per-row score went into the
WF gate's own helpers. No statistic is re-implemented here: `build_regime_series`
supplied the production regime label, `regime_diagnostics` the per-regime IC,
`regime_shift_diagnostics` the 2×-horizon placebo leg.

Regime dates: BULL_CALM 1684 · BEAR 412 · BULL_VOLATILE 183 · CHOPPY 101.

## E1(R) with both matched placebos

`genuine = E1 − placebo`. Trust the placebo-clean **differences**, not the raw
IC.

| regime | n_dates | E1 | placebo_shuffle (worst of 5) | genuine_shuffle | placebo_shift (2×) | genuine_shift |
|---|---:|---:|---:|---:|---:|---:|
| **BULL_CALM** (primary) | **1684** | **+0.0298** | +0.0006 | **+0.0291** | +0.0230 | **+0.0067** |
| BEAR | 412 | +0.0025 | +0.0024 | +0.0001 | −0.0730 | +0.0755 |
| BULL_VOLATILE | 183 | −0.0477 | +0.0029 | −0.0506 | −0.0082 | −0.0395 |
| CHOPPY | 101 | +0.0895 | +0.0075 | +0.0820 | +0.0503 | +0.0391 |

§6 on BULL_CALM: `n≥30` ✔ · `E1>0` ✔ · `E1>max_k shuffle` ✔ · `E1>placebo_shift` ✔
→ **EXPLORATORY — NOT A CERTIFICATION.**

## What I will not let this number become

- **The shift leg is the tight one.** `genuine_shift = +0.0067` on BULL_CALM:
  the 2×-shifted label alone reproduces +0.0230 of the +0.0298. Most of the raw
  IC is label persistence, not signal. The shuffle leg is nearly free
  (+0.0006), so the two placebos are testing different things and the shift is
  the binding one.
- **CHOPPY's +0.0895 is not a finding.** n_dates = 101 clears §5's floor, but
  §2 pre-commits the primary regime *precisely* so a secondary number cannot be
  promoted to the headline after the fact — the error the pooled figure already
  commits. Recorded, not led with.
- **BULL_VOLATILE is negative on both legs** (−0.0506 / −0.0395) at n = 183.
  Also secondary; also not the verdict.
- **BEAR's `genuine_shift = +0.0755` is an artefact of a negative placebo**
  (−0.0730), not a strong signal: E1 itself is +0.0025.
- **This is a reconstruction, not the served artifact.** It is what the recipe
  *would* have produced over history. The served member's only ledger row is
  `cutoff 2026-08-02`, whose label matures ~2026-10-27.

## Three implementation choices, declared before the run

The registration did not fix them, so they are named in the producer's docstring
and were fixed **before** any number was computed:

1. **Window = every matured panel date.** No range selected — the only choice
   with no freedom in it.
2. **Universe per date = the panel's own names**, the rule `momentum_eval_run.py`
   already uses.
3. **The label is clipped to ±0.5 inside `regime_diagnostics`** — the gate
   helper's own behaviour, not a choice here, but load-bearing enough to state:
   on the served scorer that same clip moved the paired per-date IC by +0.00521
   `[VERIFIED — orch#817/#822]`.

## Provenance, after review `[codex on orch#825]`

The first payload recorded summary counts and the served artifact's own hash.
That is not enough to re-derive anything: the producer reads **mutable**
surfaces, so a later run over revised OHLCV — or the same params through revised
feature code — would report different numbers under an identical-looking
payload. And reading the artifact FILE and trusting its own `content_sha256`
proves only that the file is self-consistent; **the served object is the
ledger's row.**

**Round 2 sharpened it further** `[codex on orch#825]`: the first correction
*claimed* integrity checks it did not perform. `ledger_row_for` only parsed JSON
and matched a **declared** sha — a forged-but-parseable ledger passed, and
carrying `prev_row_sha` in the output made it look checked. Verification is now
delegated to the model package's own APIs rather than re-implemented here, where
a second copy would drift exactly when it mattered:

- `renquant_model_momentum.ledger.load_and_verify_ledger` — row ordering,
  `prev_row_sha` linkage and each row's self-digest;
- `renquant_model_momentum.train.verify_artifact_content_sha` — the artifact's
  identity **recomputed**, not read off the field it carries.

Tampered-chain and tampered-artifact tests exercise both, built with the
package's own `append_chained_row` so the fixture satisfies the contract
production writes.

Two smaller corrections rode with it: the scored-table hash is a canonical
ordered **list**, since a `(ticker, date)` dict silently overwrites duplicates
(*the live panel has none — 726,128 rows, 726,128 unique pairs
`[VERIFIED]` — so this closes a latent collision rather than changing a
measurement*); and the orchestrator revision comes from **this file's repo
root**, not `Path.cwd()`, which identifies whatever checkout the caller stood in.

The producer REFUSES unless a verified ledger row carries the artifact's sha (an
absent ledger, a broken chain, a row missing the chain fields, or an unmatched
sha all refuse — "I could not check" must not read like "it checks out"), and
the payload carries:

| field | value `[VERIFIED — this session]` |
|---|---|
| ledger row | cutoff `2026-08-02`, **is_ledger_tail true**, `n_scored` 144, `row_sha` `5c6b8263…`, chain verified by `load_and_verify_ledger` |
| input surfaces read | **293**, itemised, rolled up to `sha256:684a7601…` |
| panel file | `sha256:870f68eb…` |
| scored table | `sha256:9241e590…` over **661,622** ordered rows |
| code revisions | orch `b85c19dd` · model `81064619` · backtesting `cbe9532a` · pipeline `5d41b312` |

**Re-run twice under the changing provenance code, and every number reproduced
both times** — 661,622 rows over 2,380 dates, all four regimes' `E1` and both
placebos identical across all three runs. That is a reproduction, not a
restatement.

## What lands

- `scripts/goal7_arm_a_producer.py` — the producer. Separate from the runner on
  purpose: the harness that JUDGES must never be the harness that CHOOSES. It
  refuses outright if the served params no longer match the packaged
  construction (§1).
- `doc/research/data/2026-08-05-goal7-arm-a-per-regime.json` — the payload, with
  its provenance block, so the numbers above can be re-derived rather than
  believed.
- 27 tests, incl. that the shuffle stays within-date, that changed params are
  refused, that an absent ledger / a broken chain / a row missing the chain
  fields / a tampered artifact all refuse, that a reconstruction of a
  **superseded** row must say so, the mutation test (flip
  one surface's digest → the roll-up no longer matches, so the runs are not
  comparable even though every summary count is identical), and that **all four
  conditions holding still yields `EXPLORATORY — NOT A CERTIFICATION`**.
