# Three misreads in one afternoon, none caught by a tool

**Date:** 2026-07-30 · GOAL-5 · orchestrator
**Operator directive:** *"彻底解决这类型问题"* — solve the class, not the instances.

## 1. The class

An append-only log is a **concatenation of runs**. A line in it means nothing until
it is attributed to one. Every reader I used today attributed by *proximity* —
grep, or `mtime` — and proximity is not attribution.

Three failures, all mine, all on 2026-07-30 `[VERIFIED — each corrected in-session]`:

| # | file | what I nearly reported | truth |
|---|---|---|---|
| 1 | `logs/rq104/launchd_dawn_preflight.out` | today's dawn preflight died on `No module named 'live'` | today's run **reached a decision, rc=0**; that line is historical |
| 2 | `logs/preopen_gate/stderr.log` | **6 pending orders cancelled this morning** (AVGO, PANW, MU, AMZN, CRWD, CSCO) | that cancellation was **2026-06-23**, five weeks earlier. Today: `cancelled=[]` |
| 3 | `logs/rq104_shadow_scorer_sentinel.log` | the sentinel already ran today (mtime `14:45`) | file was **2026-07-29**; at 14:26, 14:45 had not happened |

**Two were caught by re-reading. One was caught by noticing that 14:45 has not
happened at 14:26.** That is luck wearing the costume of diligence. #2 would have
put a false capital-relevant claim in front of the operator.

## 2. The rule, now mechanical

`ops/log_attribution.py`. Exactly two ways to attribute a line:

* the **filename** carries the date → the whole file belongs to that date;
* the **line** carries a timestamp **at its start** → filter by it.

Anything else returns **`UNATTRIBUTABLE` with NO lines**. Never the whole file —
returning the whole file on failure is precisely the shape that produced all three.

Three deliberate refusals, each one a trap I could have walked into next:

- **A dated file for another day is refused**, not silently searched. Trap 3.
- **A date *inside* a line is not the line's date.** `trained_date=2026-07-30` is
  **data**. Matching it loosely would *invent* evidence, which is worse than
  refusing. The pattern is anchored to the line start.
- **A stream where under half the lines are timestamped is refused.** The rest are
  continuations — tracebacks, tables — and filtering would silently drop the body
  of every multi-line record while looking like it worked.

## 3. Verified against the three real files

`[VERIFIED — run this session]`

| file | result |
|---|---|
| `launchd_dawn_preflight.out` | **UNATTRIBUTABLE**, rc=3 |
| `rq104_shadow_scorer_sentinel.log` | **UNATTRIBUTABLE**, rc=3 |
| `preopen_gate/stderr.log` | attributed by timestamp — returns **exactly today's 3 lines**: the `PASS`, and `cancelled=[]`. The June cancellation does **not** appear. |
| `daily_104/2026-07-30.log` | attributed by filename |

For contrast, `grep -c PREOPEN_CANCEL` on that same file returns **1** — and that
one hit belongs to June. The tool and the habit disagree, and the habit was wrong.

## 4. Suite

13 tests. The three real traps are **regression fixtures**, not prose. Plus the
line-internal-date refusal, the low-coverage refusal, a missing file, a bracketed
timestamp, an **anti-vacuity** control that the happy path really does return
lines, a CLI control that an unattributable read prints **nothing** to stdout, and
two live-machine checks that the real append-only files are refused.

## 5. Scope

This makes the class **detectable and refusable**. It does not retrofit the five
existing `ops/` log readers (4 already do some date handling; `rq105_status.py`
does none) — that is a follow-up, and doing it in the same PR would mix a new
guarantee with five behaviour changes.
