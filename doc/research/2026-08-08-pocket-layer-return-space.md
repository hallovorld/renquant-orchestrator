# The pocket layer in return space — r2: corrected turnover, same-window drag, and a fragility finding

Operator direction (2026-08-08): judge the pocket×style machine in RETURN
space. This is r2 of the record, after codex review of orch#914 found two
defects — both fixed — and the fixes surfaced a third finding that outranks
the numbers they correct.

Derivation: `data/2026-08-08-pocket-layer-derivation.py` — PROVENANCE ONLY
(machine-local OHLCV, **157 names**, 1910 days 2019-01-02..2026-08-07,
production TR primitive). All numbers `[VERIFIED — script output, r2 run]`.

## 0. THE FINDING THAT OUTRANKS THE TABLES — style spreads flip with universe composition

r1 loaded 114 names: 43 were silently dropped by a missing `dividend` column
(a bare `except` — my defect). Restoring them **flips the within-pocket style
story wholesale**:

| cell (2024..now) | r1 (114 names) | r2 (157 names) |
|---|---|---|
| ai_chip × momentum | **+71.2%** (+16pp vs EW) | +37.9% (**−18pp** vs EW) |
| ai_chip × reversal | +31.0% (−24pp) | **+84.3%** (**+28pp**) |
| giant_tech × momentum | +25.4% (−2pp) | +37.3% (+10pp) |

All |adj t| ≤ 0.2 in both runs. **Conclusions this fragile — sign-flipping on
which names load — carry no policy weight in either direction.** The earlier
"chips are a trend pocket" read is withdrawn; so is its opposite. What stands:
within-pocket style spreads on this book's pockets are unresolvable at this
history, full stop.

## 1. Sector rotation, corrected turnover (r2 fix 2)

r1 charged switch costs off the FIRST pick only; 54 top-2 basket changes went
uncounted (codex). r2 counts full-basket membership changes (one unit = a
complete K-name replacement, 20 bps):

| strategy | 2024..now net | 2019..now net |
|---|---|---|
| universe EW | +36.3% | +28.2% |
| equal-sector | +35.2% | +25.2% |
| rotation top-1 | +12.1% | +11.4% |
| rotation top-2 | **+39.3%** | +17.8% |

Top-2 beats the universe on the 2024 window and loses on the 2019 window —
**window-sensitive, not a robust win**. Top-1 loses everywhere. The rotation
line stays closed for evidence reasons; the r1 phrasing "loses before costs
in every window" was too strong and is corrected to the table above.

## 2. Cash drag, benchmarked on its own window (r2 fix 1)

r1 compared the 63-day cash measurement to a 2024..now benchmark — different
windows, mislabelled as same-window (codex). Recomputed on the cash window
itself (2026-05-11..08-07, 62 trading days):

```
universe EW on the cash window: +11.63% total, ann +56.4%, Sharpe 3.42, maxDD −5.0%
book: mean cash 78.3% (median 80.6%, max 94.7%)  [VERIFIED — live_state_snapshots]
same-window missed return: ≈ $998 over the 62 days on the $10,962 book
annualized at the window rate: ≈ $4,839/yr
```

The correction makes the drag LARGER, not smaller. Long-run proxy (2024..now
universe +36.3%/yr → ≈ $3,000/yr) is retained, labelled as a proxy. Either
way: **no pocket-routing effect measured in this record is within an order of
magnitude of the cash drag.** Capital deployment (G-E, task #24) remains the
return-space P0.

## 3. Standing state

* Rotation: closed (no robust win; window-sensitive at best).
* Within-pocket styles: **unresolvable and composition-fragile** (§0); no
  policy weight either direction; revisit only with a longer history or an
  explicitly preregistered pocket definition frozen before the test.
* Cash drag: the dominant, correction-robust number — larger under r2.
* Routing-table v0: every cell stays `panel`; the sole "~candidate" (chips ×
  momentum) is WITHDRAWN under §0. The table's honest v0 is all-panel +
  BEAR-column-locked-by-policy.
