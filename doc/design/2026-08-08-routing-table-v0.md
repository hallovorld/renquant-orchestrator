# Routing table v0 — regime × sector → canonical expert ID

The operator's final deliverable for the pocket×style machine (2026-08-08
directive): ONE table recording which model serves which regime × sector cell.
Cells reference only registry IDs (`2026-08-08-expert-naming-registry.md`).

## The table (v0, 2026-08-08)

| sector \ regime | bull_calm | bull_volatile | bear |
|---|---|---|---|
| ai_chip | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| datacenter_hw | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| software | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| giant_tech | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| industrial | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| finance | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| consumer | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| healthcare | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |
| energy / utility / rest | `xgb_rank_60d` | `xgb_rank_60d` | POLICY: no trade |

Notes: the production HMM's argmax never selects choppy on 2017-2026 (0 of
2347 days), so the operative regime axis is three states; `bear` totals 77
days and is locked by strategy policy (G-B), not by modelling.

## Why every cell is the panel — the cube, not a refusal

`data/2026-08-08-cube-v1.csv` (+ derivation, machine-local OHLCV provenance):
**120 cells** = 10 sectors × 3 regimes × 4 style proxies (`mom63_proxy`,
`mom252_proxy`, `rev21_proxy`, `lowvol63_proxy` — trailing-price proxies,
deliberately NOT registry IDs), 2017-01..2026-05 daily, spread vs own-sector
EW, n_eff-adjusted t. Result `[VERIFIED — derivation output]`:

```
cells with n >= 40:   120 / 120
cells with |t| >= 2:  0
strongest cell:       datacenter_hw x bull_calm x mom63  (t = +0.76, 9.5y)
```

Every cell was tried, none is distinguishable from its sector baseline. That
is the measured answer to "try every model in every sector under every
regime" — tried, and at this history no override earns a cell.

## How a cell flips (standing rules)

1. A candidate appears (cube refresh, new expert build, or operator policy
   pick) → the cell is marked `~candidate` by a dated PR.
2. The candidate runs a SHADOW lane and the §10-pattern confirmatory
   (diagnostic → dated amendment → purge-governed run).
3. PASS → the cell records `✓<id>` with the evidence PR; FAIL → back to
   `xgb_rank_60d`. Every flip is a reviewed PR; the table is append-only in
   git history.

Fragility guard (learned 2026-08-08, orch#914 r2): within-pocket style
spreads flipped sign when 43 names were restored to the loader. A cell
candidate must therefore show sign-stability across universe compositions
before shadow, or it does not graduate.
