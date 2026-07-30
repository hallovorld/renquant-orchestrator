# The rq104 degradation sentinel alarms on the agent PR loop and a killed programme

**Date:** 2026-07-30 · GOAL-1, issue #622 defect 3 · orchestrator
**Stacked on** `goal1/acks-must-name-the-exit-code` (#641) — same function, so
branching from `main` would have conflicted.

**Bottom line:** the sentinel is named for rq104 degradation and takes **every**
`com.renquant.*` nonzero exit `[VERIFIED — check_launchd_exits, no label filter]`.
Measured today, **13** jobs were nonzero, and the flat list mixed the live trading
path with `agent-pr-loop` (my own automation) and `crypto-session` (a programme
**KILLED 2026-07-18**) `[VERIFIED — launchctl list]`. Reported that way, *"the
trading system is degraded"* and *"an automation job failed"* are indistinguishable
— and a reader who learns the second is common stops reading the first.

## 1. Group, do not drop

Dropping out-of-scope jobs would trade a **legibility** problem for a **coverage**
problem, which is the worse of the two here. Every nonzero exit still appears and
still makes the sentinel exit 1. What changes is that the reader can see which is
which.

Real output after the change `[VERIFIED — run against this machine, 2026-07-30]`:

```
[TRADING-PATH] rq104-scorer-identity (2), rq104-shadow-scorer-sentinel (1),
               weekly-apy104 (2)
| [adjacent]   rq105-batch-scores-export (1) [ACK EXPIRED 10d], rq105-shadow-serving (1),
               run-surface-drift (1), shadow-ab-daily (3)
| [unrelated]  agent-pr-loop (1), crypto-session (2)
```

**3 / 4 / 2** — nine loud entries, none lost.

## 2. The default is the load-bearing decision

An **unclassified** job is scoped **TRADING**, not unrelated. A job nobody has
classified is exactly the one whose failure you cannot afford to file under noise.
The cost of this default is a misfiled alarm; the cost of the other is a missed one.

It is not hypothetical: `weekly-apy104` matches no rule and lands in TRADING-PATH in
the run above. That is the default working, not a gap.

## 3. Empty groups print no header

A permanently-present `[unrelated]` with nothing after it teaches the reader to skip
the line, which is the same disease in a smaller font. Tested.

## 4. Suite

`tests/test_sentinel_scope_partition.py` — 11 tests. The one that matters most is
`test_NOTHING_is_dropped_by_grouping`: every label must still appear in the alarm.
Plus the unknown-default, longest-prefix-wins, empty-group, and two anti-vacuity
controls (a clean fleet still yields **no** alarm; an unrelated-only failure still
exits nonzero rather than being silently downgraded to clean).

With the ack and existing sentinel suites: **73 passed**
`[VERIFIED — pytest, this session]`.

## 5. Not addressed

The three TRADING-PATH failures are real and need their own diagnoses:
`rq104-scorer-identity` (exit 2), `rq104-shadow-scorer-sentinel` (exit 1),
`weekly-apy104` (exit 2). This PR makes them legible; it does not explain them.
