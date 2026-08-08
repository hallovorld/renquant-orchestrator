# Expert naming standard and registry

Operator directive 2026-08-08: model naming must be standardized. This doc is
the single source of truth for canonical expert IDs. The routing table
(regime × sector → model) references ONLY these IDs.

## The standard

```
<family>_<method>_<clock>[_<variant>]
```

* **family** — the hypothesis class: `xgb` (gradient-boosted learner), `mom`
  (momentum composite), `rev` (short-term reversal), `val` (value composite),
  `lowvol` (defensive/low-volatility), `qual` (quality), `fund` (fundamental).
* **method** — what it emits: `rank` (cross-sectional ranking), `clf`
  (classification probability), `resid` (factor-residualized composite).
* **clock** — the dominant horizon in TRADING DAYS: formation window for
  composites, label horizon for learners.
* **variant** — optional, only when two experts differ in nothing else.

Rules:
1. Canonical IDs live in the design/config layer. **Production artifact
   filenames never change for naming reasons** — a rename would re-stamp every
   fingerprint for zero benefit. The registry maps ID → artifact.
2. A new expert MUST be registered here (one PR) before its shadow lane
   exists. The routing table may not reference an unregistered ID.
3. IDs are immutable once registered; a changed construction is a NEW ID.

## Registry (v1, 2026-08-08)

| canonical ID | artifact | status | notes |
|---|---|---|---|
| `xgb_rank_60d` | `artifacts/prod/panel-ltr.alpha158_fund.json` | **prod champion** | label `fwd_60d_excess` [VERIFIED — artifact `label_col`] |
| `xgb_clf_60d` | `artifacts/shadow/panel-clf.top-decile.fwd60.json` | prod blend leg (shadow profiles) | top-decile hit probability |
| `mom_resid_252` | `artifacts/momentum/momentum_artifact_ledger.jsonl` | prod blend leg | slow clock 252/21, frozen params v0 |
| `mom_resid_63` | `artifacts/momentum_fast/momentum_artifact_ledger.jsonl` | shadow patrol only | fast clock 63/5, frozen params v1_fast; **negative Δ in blends** (orch#911/#913) — patrol, not a blend leg |
| `val_yield_252` | — not built — | proposed | E/P + B/P composite from the panel dataset's fundamental columns; momentum-template build |
| `rev_21` | — not built — | proposed | 21-day loser rebound; NOTE measured 2024-26: reversal in `ai_chip` loses ~24pp/yr to pocket EW — pocket-dependent by construction |
| `lowvol_63` | — not built — | proposed | realized-vol inverse rank |

Retired, kept for lineage: `patchtst` (transformer, retired 2026-08-02).

## Naming appears in

* the routing table (regime × sector → canonical ID),
* shadow lane names (`wf_replay_*` for replays — bt#110 enforces the prefix),
* research docs and heatmaps (the 312-cell cube uses canonical IDs only).
