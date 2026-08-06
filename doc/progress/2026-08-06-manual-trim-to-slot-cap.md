# 2026-08-06 — Manual exit of two positions to bring the book under its slot cap

STATUS:   SUBMITTED, PENDING FILL — four sell orders placed against the live book
          (two by the daily-full runs, two by hand under an explicit operator
          grant). Market was CLOSED at submission; all four are DAY market orders
          targeting the 09:30 ET open. As of this snapshot the only established
          facts are the order ids and their submitted status — market orders can
          be rejected, canceled, or partially filled, so nothing below the order
          table is a completed outcome yet. This is a RECORD of a live-capital
          action, not a code change. See RECONCILIATION below for the required
          post-open follow-up.

WHAT:     Operator grant, verbatim: **"你直接帮我把当前模型不看好的几个仓位卖出就好了，
          一次性工作，不需要写代码了，直接看数据就行"** (just sell the few positions
          the model doesn't favour; one-off, no code, read the data).

          | ticker | qty | ≈value | placed by | reason |
          |---|---:|---:|---|---|
          | MRVL | 1 | $207 | daily-full 04:43 | `model_protection` |
          | NVDA | 1 | $221 | daily-full 05:12 | `model_sell` |
          | **GOOG** | **1** | **$358** | **manual** | worst model rank of all ten holdings |
          | **WELL** | **3** | **$701** | **manual** | lowest model expected return of all ten |

          **Projected, contingent on all four fills** — Book 10 -> 6 positions,
          `open_slots` -2 -> +2, cash ≈47.3% -> ≈61.0% (≈$1,487 released). These
          are the outcome IF all four DAY orders fill at submission size; a
          reject, cancel, or partial fill on any of the four changes them. See
          RECONCILIATION for the actual post-open figures.

WHY/DIR:  The operator's directive of the same day sets `max_concurrent_positions=8`.
          The book held 10, so `open_slots = 8 - 10 = -2` and `PrepareSelectionTask`
          returned `no open slots` on every run — the buy path was closed regardless
          of any sizing change. Nothing in the system trims a book that is over its
          cap; it only declines to buy and waits for model-driven exits. Two exits
          fired on their own today; two more were needed to reopen a slot, and the
          operator chose to take them by hand rather than wait.

EVIDENCE:
artifact:      Alpaca order ids `38b3752d` (GOOG), `f67cea9f` (WELL), `cec40153`
               (NVDA, system), `8f17321b` (MRVL, system)
prod or exp:   **prod — live capital.** Four real sell orders on the live Alpaca
               account. Not reversible once filled.
existing data: per-name model view read from the production rotation tree in
               `logs/daily_104/2026-08-06.log` (the `ROTATION_TREE ... held=` lines),
               joined against the live positions API [VERIFIED — this session]:

```
ticker  mktval$   %equity  unreal%   model_er   model_rank  held_d
GOOG        358      3.3    -5.72    +0.0252     0.104        108   <- worst rank
WELL        701      6.4    +0.53    +0.0008     0.142          1   <- lowest er
MRVL        207      1.9    -1.58    -0.1143     0.188          2   (system exit)
NVDA        221      2.0    +1.83    +0.0077     0.219        111   (system exit)
PANW        358      3.3    +6.68    +0.0573     0.229         43   kept
LRCX        306      2.8    -0.98    +0.0560     0.239          2   kept
DDOG        233      2.1   -19.43    +0.0292     0.287          1   kept
VLO         609      5.6    -2.40    +0.0684     0.301          1   kept
SOFI        162      1.5    -3.94    +0.0126     0.312         37   kept
TSLA      2,571     23.7    +4.83    +0.1675     0.340          9   kept (best rank)
```

best-known?:   yes for "which names the model rates lowest today" — it is the
               production scorer's own output for this session. **No** for "selling
               them is profitable"; see NOT ESTABLISHED.
scope:         one-off manual trim; no config, code, or scheduled job was touched.

NEXT:     Required reconciliation after the 09:30 ET open (see RECONCILIATION
          below) — pull the four order ids from the Alpaca orders API, record
          actual fill/reject/cancel/partial status and fill price per order,
          and recompute the real post-open position count, `open_slots`, and
          cash from the live positions API rather than from the projection
          above. Only after that reconciliation is filled in does `open_slots
          = 2` become an established fact; until then it is the projection
          this doc already flags as contingent. Once reconciled, whether the
          book then actually buys depends on `VetoWeakBuysTask`'s relative
          floor (108 scanned -> 84 ranked -> 2-3 admitted today), not on slot
          count alone.

## RECONCILIATION (fill in after the 09:30 ET open)

| order id | ticker | side | submitted qty | status | filled qty | fill price |
|---|---|---|---:|---|---:|---:|
| 38b3752d | GOOG | sell | 1 | **TODO — not yet reconciled** | | |
| f67cea9f | WELL | sell | 3 | **TODO — not yet reconciled** | | |
| cec40153 | NVDA | sell | 1 | **TODO — not yet reconciled** | | |
| 8f17321b | MRVL | sell | 1 | **TODO — not yet reconciled** | | |

Actual post-open book: **TODO** (position count, `open_slots`, cash %, $
released) — read from the live positions API after the open, not carried
forward from the projection in WHAT.

## NOT ESTABLISHED

1. **That selling these two is profitable.** Not backtested, not pre-registered.
   The model rates them lowest *today*; that is a ranking, not a forecast of the
   realised difference against holding them.
2. **That the model's per-name `rank` is calibrated across names.** All ten
   holdings score 0.10-0.34 while the rejected buy candidate CRWD scored 3.050 —
   a 9-21x gap. The within-book ordering was used; the absolute levels were not
   interpreted.
3. **WELL was bought one day earlier.** Selling a 1-day-old position is the churn
   that `min_hold` exists to prevent; that guard was bypassed by acting by hand.
   It is recorded here rather than smoothed over.
4. **DDOG at -19.43% was NOT sold** despite being the largest unrealised loss,
   because the model still rates it mid-pack (`rank` 0.287, `er` +0.0292). The
   selection followed the model, not the P&L.

## REVERT

A filled trade cannot be reverted. If the intent is undone before 09:30 ET the
orders can be cancelled by id (`38b3752d`, `f67cea9f` — the two manual ones);
after the open, restoring the book would require four new buys at whatever the
market then offers, which is a different decision and should be taken as one.
