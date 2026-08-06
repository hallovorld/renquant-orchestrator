# Six sessions decided on a skeleton model fleet and nothing alarmed   (PR)

STATUS:   delivered — new detector, wired into the daily ops-audit. No production
          surface touched; read-only.

WHAT:     Adds `ops/renquant104/model_load_coverage_scan.py` and registers it as an
          `ops_audit` member, so a daily run whose model fleet failed to load stops
          reporting as an ordinary no-trade.

WHY/DIR:  GOAL-5 P0 (operator-escalated). The 30-session audit behind the v2 capital
          design found 3 sessions with an empty buy universe. Measuring the model
          count directly finds **six**, and two of them **placed orders**.

EVIDENCE:
artifact:      `RenQuant/logs/daily_104/<date>.log`, the runner's own
               `Loaded models for N/M symbols` line
prod or exp:   prod — these are the live daily sessions
existing data: no ops detector read this number at all. `grep -rl "Loaded models
               for" ops/` returned **empty** before this PR. The runner logged it
               daily and nothing consumed it.
best-known?:   yes — this is the first measurement of model-load coverage in this
               repo. There is no prior series to compare against.
scope:         this is `logs/daily_104`, prod, over the 45 most recent dated
               sessions, and it is an AVAILABILITY claim — how many artifacts the
               runner could open. It is not a comparison against any existing best
               and asserts no IC, Sharpe or return figure.

          Measured `[VERIFIED — this session, 2026-08-06]`, trailing median **80.3 %**:

          | date | loaded | coverage | alerts fired | placed orders? |
          |---|---|---:|---:|---|
          | 2026-06-30 | 7/145 | **4.8 %** | 0 | no |
          | 2026-07-06 | 58/145 | **40.0 %** | 0 | **yes, 2** |
          | 2026-07-07 | 58/145 | **40.0 %** | 0 | **yes, 1** |
          | 2026-07-08 | 4/145 | **2.8 %** | 0 | no |
          | 2026-07-09 | 4/145 | **2.8 %** | 0 | no |
          | 2026-07-15 | 11/145 | **7.6 %** | 0 | no |

          A further **6 sessions carry no `Loaded models` line at all** and are
          reported `UNREADABLE`, not OK.

          On the collapsed days the only tickers with a loadable model were **the
          names already held** — so every candidate scored against nothing and the
          universe emptied to `0 candidates from 0 tickers`. The run then reported a
          clean no-trade.

NEXT:     This detects; it does not explain. Why the artifacts became unopenable on
          those dates is unmeasured and is the next step. Two of the six sessions
          traded on a 40 %-loaded fleet, so the question is not only "why no trade".

## Design notes a reviewer should check

**Two floors, deliberately OR-ed.** An absolute floor (< 50 % of universe) catches a
collapse on its own terms; a relative floor (> 40 % below the median of the
sessions **before** it) catches a fleet decaying from a high base that an absolute
floor tuned low would sleep through.

**The baseline is strictly PRIOR sessions** `[VERIFIED — scan(), min_history=3]`.
An earlier revision took one median over the whole window and judged every row
against it, so a **sustained partial decline dragged its own baseline down and
evaded both checks**: 140,140,80,80,80 of 145 has a window median of 80, giving
the 80-rows a drop of zero while 55 % clears a 50 % absolute floor — invisible in
exactly the shape the relative floor exists for (codex on this PR). A row with
fewer than 3 prior readable sessions is `INSUFFICIENT_HISTORY`, never OK; the
absolute floor still applies to it, so the state is not a hole. Requiring **both** would let each veto the other. Both directions are
pinned by test, including the twin case where a uniformly low fleet drags the
trailing median down so only the absolute floor can fire.

**A collapse outranks an unreadable neighbor, not the reverse.** `UNREADABLE`
exits 2 when it is the ONLY problem in the window — `2` is not declared as a
finding exit in `MEMBERS`, so an unreadable-only window lands on HARNESS. But
exit 1 fires whenever `n_collapsed` is nonzero, even alongside unreadable
sessions: the live logs carry three unreadable historical sessions in the same
30-day window as the six collapsed ones this detector exists to catch, and an
earlier revision let UNREADABLE's exit 2 win that race — `ops_audit` reads exit
2 as `unusable`, silently discarding the collapse finding on the one path this
detector is wired into (codex on this PR). `render()`'s first line now names the
collapsed dates too, so the truncated `detail` the aggregate surface prints is
no longer the generic `model-load coverage — N session(s)` header.

**First match wins** when reading the log: shadow lanes replay the same bar and log
their own counts, so reading the last match would report a shadow lane's fleet as
prod's. Pinned by test.

## What this does NOT establish

- **Not why the models failed to load.** Availability only.
- **Not that a healthy count means the models are correct.** This counts artifacts
  the runner could open — not whether any is fresh, well-fit, or the right one.
- **Not that the six sessions would have traded.** Whether a full fleet would have
  produced buys is unmeasured, and the two that did trade complicate that question
  rather than settling it.

---

# CORRECTION — the cause is model STALENESS, not unopenable artifacts `[VERIFIED — 2026-08-06]`

The section above said the six sessions "decided on a skeleton model fleet" and
that *why the artifacts became unopenable is unmeasured*. Measured now: **they
were never unopenable.** The per-ticker fleet had aged past its staleness limit
and the gate refused it — correctly.

```
2026-07-08  live.runner: AAPL stale_76d_limit_60:live_train_end, skipping
```

| date | loaded | stale-skip lines | oldest model |
|---|---|---:|---|
| 2026-06-30 | 7/145 | 126 | **61d** vs limit 60 |
| 2026-07-06 | 58/145 | **0** | — |
| 2026-07-08 | 4/145 | 129 | **76d** |
| 2026-07-09 | 4/145 | 129 | **77d** |
| 2026-07-15 | 11/145 | 520 † | **83d** |
| 2026-07-10 | 125/145 | 0 | — |
| 2026-08-05 | 120/145 | 0 | — |

† 520 exceeds the 145-symbol universe because shadow lanes replay the same bar
and log their own skips into the one file. The count is lanes × symbols, not
symbols. Reported as measured rather than silently divided.

## What this changes, and what it does not

**Changes:** the staleness gate is not the defect. It did exactly its job on four
of the six sessions.

**Does not change — and sharpens — the finding:** the fleet crossed the limit on
**2026-06-30 at 61 days, one day over**, and nothing retrained it for **ten
days**, by which time it had reached **83 days**. Through that window the book
scored candidates against **4 to 11 models out of 145**, and:

- **zero alerts fired** `[VERIFIED — grep over each session log]`
- **no ops detector read the loaded-model count** — `grep -rl "Loaded models for" ops/`
  was empty before this PR

A guard that correctly refuses 129 of 145 models for two weeks, while nothing
escalates, is not a working control. **The refusal was right and the silence was
the defect.**

## One session still unexplained

**2026-07-06 loaded 58/145 with ZERO stale-skip lines**, so its cause is
different from the other five and is **not established here**. It is also one of
the two sessions that **placed orders** while under-loaded. That remains open.

## The detector's verdict is unchanged

`model_load_coverage_scan.py` still flags all six, and should: its subject is
*how many models the run actually had*, which is the decision-relevant quantity
regardless of why. The `does_NOT_establish` field already said it "does not
establish why the models failed to load" — that limit was correctly stated, and
this section fills it in for five of the six.

---

# The one session left open is now closed — and it is a DIFFERENT defect `[VERIFIED — 2026-08-06]`

The correction above closed five of six sessions as model **staleness** and left
2026-07-06 open: *"58/145 with ZERO stale-skip lines, so its cause differs from
the other five and is NOT established here."*

Established now. `runner.py:452-454`:

```python
meta_path = models_dir / symbol / f"{symbol}-policy-metadata.json"
if not meta_path.exists():
    log.warning("%s no_artifact, skipping", symbol)
```

`no_artifact` means the model's **metadata file is absent from disk** — not stale,
not unreadable, **not there**.

| date | loaded | `no_artifact` | `stale` | class |
|---|---|---:|---:|---|
| 2026-06-30 | 7/145 | 12 | **126** | stale |
| **2026-07-06** | 58/145 | **240** | **0** | **MISSING FILES** |
| **2026-07-07** | 58/145 | **80** | **0** | **MISSING FILES** |
| 2026-07-08 | 4/145 | 12 | **129** | stale |
| 2026-07-09 | 4/145 | 12 | **129** | stale |
| 2026-07-15 | 11/145 | 16 | **520** | stale |
| 2026-08-05 (healthy) | 120/145 | 4 | 0 | — |

Counts exceed the 145-symbol universe on the worst days because shadow lanes
replay the same bar into one log; the figure is lanes × symbols. Reported as
measured.

**So the six sessions are two defects, not one:**

- **four** were the staleness gate correctly refusing a fleet that had aged past
  its 60-day limit and stayed there ten days (already recorded above);
- **two — 07-06 and 07-07 — had model metadata files missing from disk**, and
  these are exactly the two sessions that **placed live orders** while
  under-loaded.

Baseline `no_artifact` on a healthy session is **4**. On 07-06 it was **240**.

## What this does NOT establish

- **Not why the files were absent.** A plausible reading is that a rebuild had
  them mid-write (240 on 07-06 → 80 on 07-07 → 12 on 07-08, by which point the
  files existed and were merely stale). **That sequence is consistent with a
  rebuild and I have not verified it** — no retrain log was consulted, and the
  monotone decay could equally be several causes.
- **Not that the orders placed on 07-06/07-07 were wrong.** They were sized from
  the 58 models that did load. Whether the missing 87 would have changed the
  selection is unmeasured.
- **Not that files are missing now.** The current session reads `no_artifact = 4`.

The detector's verdict is unchanged: both classes present the same way — a run
deciding on a fleet far below its trailing coverage — which is why the probe
measures *how many models the run had* rather than *why*.
