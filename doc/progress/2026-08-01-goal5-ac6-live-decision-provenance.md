# GOAL-5 AC6 — what the live trade log can and cannot tell you, and a false reading it invites

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-5 (AC6 / orch#564)

## What I set out to find, and what already existed

I started measuring AC6 R4's gap — *"no shared run-bundle schema/validator rejects a run
bundle missing override provenance"* — and found `0 of 7` `.subrepo_runs` bundles carrying
it. **That is exactly what merged PR #685 already measured and fixed**, in the right place:
`src/renquant_orchestrator/wf_gate_provenance.py` + `daily.py`, with #685's own note that
all seven predate #669 and evidence the historical gap.

So the headline I was about to write was a duplicate. What survives is narrower and is
about a different surface.

## What survives: the live trade log is not the bundle

`daily.py` — the path #685 fixed — does **not** write
`RenQuant/live/logs/renquant-104/<date>.json`. Those per-date records come from the
intraday runners. Measured over the 14 July records, 63 decision rows
`[本次实测 2026-08-01]`:

| | |
|---|--:|
| records carrying any artifact digest (`sha256`/`fingerprint`/`artifact_id`/`trained_date`) | **0 / 14** |
| BUY rows with `active_scorer: None` | **14 / 24** |

`active_scorer` **is** recorded — so the log names a *scorer family*, not an artifact. A
reader of the trade log cannot tell which of the 12 distinct boosters (orch#712) produced a
decision.

**This is stated as a property, not a defect.** A trade log is not the audit bundle, and
whether artifact identity belongs in it is a design question I have not answered. The
bundle is where AC6 put the provenance and #685 delivered it there.

## The part worth keeping: a false reading, refuted mechanically

`active_scorer` is `hf_patchtst` on **38** rows, which reads as *the 625-day-stale PatchTST
checkpoint is deciding the book*. Split by action:

| action / active_scorer | rows |
|---|--:|
| SELL / hf_patchtst | 38 |
| BUY / None | 14 |
| BUY / panel_ltr_xgboost | 5 |
| BUY / blend | 5 |
| SELL / blend | 1 |

**All 38 are SELLs** — the scorer that *entered* the position historically. Every BUY row
carries `None`, `panel_ltr_xgboost` or `blend`. A KILL claim in this programme was already
retracted once for mistracing a PatchTST checkpoint (#569 → #570), so the tool computes the
split and carries it in its output as a `not_a_finding` field rather than leaving the next
reader to re-derive it.

## Three checks that shrank this finding

1. **Wrong population.** `.subrepo_runs` newest bundle is `artifact_id:
   subrepo-smoke-gbdt`, `fingerprint: sha256:smoke-model`, `dry_run: True` — a **smoke**
   bundle, not the daily run's.
2. **Already fixed.** #685 covers the bundle path. Checking merged work before publishing
   is the difference between a finding and a duplicate.
3. **"It doesn't name the model" was too strong** — the rows carry `active_scorer`. The
   accurate claim is: no artifact **digest**, and `None` on 14 of 24 buys.

## Not claimed

That AC6 R4 is unmet — #685 met it for the bundle. That artifact identity *should* be in
the trade log. That any of the 14 scorer-less buys was mis-decided.

## Tests

8, including the refutation as an executable check (a SELL row must not count toward the
buy-side scorer), unreadable-is-not-missing, and no-records **SKIPs with 3**.

Suite: **4849 passed, 2 skipped**.
