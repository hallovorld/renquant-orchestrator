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

**`UNREADABLE` exits 2, not 1.** A session that could not be checked outranks one
that was checked and found bad — the same rule the aggregator uses, and the reason
`2` is not declared as a finding exit in `MEMBERS`.

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
