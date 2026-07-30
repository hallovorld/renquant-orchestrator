# Phase 3 of the 9-ticker atomic batch: proposed sector_map / sector_etf_map

> **DO NOT MERGE while ARM / ENTG / SNDK are undecided.** LONG ledger row 7:
> *"Design docs are not merged while under discussion."* Three bucket calls in §2
> are still flagged low/medium confidence and §8 needs an operator decision, so
> this document is **not** merge-ready and should not sit in the merge queue.
> The review raising this is **correct and accepted** — see §8.
>
> The analysis is kept open for that decision, not as a pending merge.

**Status:** proposal under discussion — **not merge-ready**. **No config
changed.** These entries are part of the atomic batch (watchlist + sector maps +
retrained artifacts land together); landing any piece alone hard-fails buys for
all 154 names.

**Why this needs review rather than a script:** `sector_map` and
`sector_etf_map` are both `config_fingerprint` fields, and P-SECTOR-MAP
(`renquant-pipeline/.../preflight_pipeline/tasks/sector_map.py:49-82`)
hard-fails buy mode if any buyable watchlist ticker lacks a `sector_map` string
OR if any bucket value lacks a `sector_etf_map` entry. `require_sector_map_for_buys
= true` `[VERIFIED — strategy_config.json:427]`. The taxonomy is hand-curated
and finer than GICS; no script produces it.

---

## 1. Mechanics established before proposing anything

- `max_positions_per_sector = 6`
  `[VERIFIED — strategy_config.json:665]`.
- The cap groups on the RAW BUCKET VALUE, not the ETF
  `[VERIFIED — task_selection.py:39-40, task_joint_actions.py:155/244,
  portfolio_qp/tasks.py:1501-1536]`. So several buckets sharing
  one ETF (ai_chip / giant_tech / datacenter_hw / software all → XLK) do NOT
  merge their caps. `sector_etf_map` is relative-strength metadata, not a cap key.
- The cap limits **simultaneously HELD positions per bucket**, not watchlist or
  candidate-pool size
  `[DERIVED — same enforcement path cited in the bullet above:
  task_selection.py reads max_positions_per_sector against the in-progress
  selection of positions to hold, not the watchlist or candidate pool]`.
- Precedent for stretching an existing bucket rather than minting one:
  `_activation_log` records LITE + COHR folded into
  `datacenter_hw` on addition
  `[VERIFIED — strategy_config.json:1338-1341]`.

## 2. Proposal

| ticker | bucket | closest incumbents | confidence |
|---|---|---|---|
| NXPI | `ai_chip` | ADI, MCHP, ON | **already mapped** `[VERIFIED — strategy_config.json:511]` — no decision |
| GFS | `ai_chip` | TSM (the other pure-play foundry) | high |
| SWKS | `ai_chip` | QCOM, ADI, MRVL | high |
| QRVO | `ai_chip` | SWKS, QCOM, ADI | high |
| TER | `ai_chip` | AMAT, LRCX, KLAC | high |
| ENTG | `ai_chip` | AMAT, LRCX, KLAC | **medium** — see §3 |
| ARM | `ai_chip` | QCOM, AVGO, NVDA | **low** — see §3 |
| STX | `datacenter_hw` | WDC (direct HDD competitor) | high |
| SNDK | `datacenter_hw` | WDC (spin-off parent), DELL, SMCI | **medium** — see §3 |

**No new `sector_etf_map` entries are required** — both buckets already map to
XLK `[VERIFIED — strategy_config.json:649-650]`.

## 3. The three calls I am not confident about, stated as such

**ARM (low).** Pure IP/royalty licensing: no fab, no COGS, no unit sales. Every
current `ai_chip` incumbent actually manufactures or sells physical silicon or
equipment. `ai_chip` is the best AVAILABLE fit — same sector news-flow, tariff
and export-control exposure — but it is a genuine qualitative stretch. A precise
fix is a new `chip_ip_licensing` bucket, which would need its own
`sector_etf_map` entry; there is no clean ETF for a licensing-only sub-industry,
so it would also default to XLK and the new bucket would be **cosmetic rather
than substantive**. Recommendation: accept `ai_chip` unless you want the
precision for its own sake.

**ENTG (medium).** Materials and filtration consumables, versus capital-equipment
sellers (AMAT/LRCX/KLAC). Recurring-revenue business against a capex cycle. Not
severe enough to block, but the second-loosest call here.

**SNDK (medium).** Defensible either way — `datacenter_hw` on storage-media and
literal spin-off lineage, or `ai_chip` on the memory-chip comp with MU. Chose
`datacenter_hw`. A judgment call, not a clean-cut case.

## 4. Concentration — the counts, and an open measurement question

Two corrections to the first version's counts, one of them raised in review and
one not.

**(i) `ai_chip` was counted wrong by me.** The first version used 19 =
sector_map ENTRY count. Only **17** of those 19 are on the watchlist
`[VERIFIED — sector_map entries whose ticker is in watchlist, this session]`.
`max_positions_per_sector` caps HELD positions among watchlist names, so the
watchlist-relative figure is the one a cap can ever see. Entry count overstates
it.

**(ii) `datacenter_hw` differs between the two configs, and both readings are
correct.** The review reproduced **13**; I read **14**. Neither is a counting
error — the two files have genuinely diverged.

Measured precisely this session, the drift is **3 tickers**, all present in the
pinned config and all absent from the umbrella copy
`[VERIFIED-now — set difference on `sector_map` and `watchlist`]`:

| ticker | bucket | affects the counts below? |
|---|---|---|
| **CRWV** | `datacenter_hw` | **yes** — this one ticker is the entire 14-vs-13 gap |
| RKLB | `industrial` | no |
| SPCX | `industrial` | no |

The drift is one-directional: **0** tickers are in the umbrella copy but missing
from the pinned one `[VERIFIED-now]`. Pinned `sector_map` = 159 entries /
`watchlist` = 145; umbrella = 156 / 142 `[VERIFIED-now]`.

The live runner loads the pinned config (`daily_104.sh:113`, via
`renquant_strategy_config "$SUBREPO_ROOT"`); the trainer loads the umbrella copy
(`train_104.py:193`, `REPO_ROOT / "backtesting" / args.strategy`)
`[VERIFIED-now — both lines read this session]`. That divergence is filed as
`hallovorld/RenQuant#544` (OPEN, and it cites these same two loader lines)
`[VERIFIED-now — gh issue view]`.

| bucket | now (watchlist-relative) | net new | after | growth |
|---|---:|---:|---:|---:|
| `ai_chip` | **17** | +6 | **23** | +35.3% |
| `datacenter_hw` (PINNED, runner) | **14** | +2 | **16** | +14.3% |
| `datacenter_hw` (umbrella, trainer) | **13** | +2 | **15** | +15.4% |

Both `datacenter_hw` rows are stated on purpose: until #544 is resolved there is
no single answer, and picking one silently would hide the divergence.

`now` `[VERIFIED — sector_map entries per bucket RESTRICTED to watchlist
members, this session]` — see correction (i); the earlier version used
unrestricted entry count. `net new` `[DERIVED — §2 proposal table, rows
per bucket excluding NXPI (already mapped)]`. `after` `[DERIVED — now + net
new]`. `growth` `[DERIVED — net new / now]`.

`ai_chip` goes from third-largest to within one ticker of the largest
(`software`, 26 entries `[VERIFIED — strategy_config.json sector_map count, this
session]`), and becomes by far the largest semiconductor-cycle-correlated
bucket. 23 watchlist names would compete for the same 6 held slots.

**Whether the 6-slot cap binds in practice is an open question, not settled by
this PR.** #610 (merged `[VERIFIED — d69b7393, `git merge-base --is-ancestor`
this session]`) reports a `mu >= 0.03` admission rate of 2-6 names per session
across the whole cross-section, but it is a pooled/read-only measurement, not
a per-session strategy-side admission study, and it changed no config or
admission rule. This doc does not use that number to conclude the cap "cannot
bind today," and does not predict what #223/#608/#610 "would cause." That
conclusion is deferred to a canonical, reproducible per-session strategy-side
admission-rate measurement — re-run whenever admission-affecting work lands —
which is out of scope for this bucket-assignment proposal.

## 5. The sharpest concentration point, called out separately

WDC is already in the watchlist and already in `datacenter_hw`
`[VERIFIED — strategy_config.json:513]`. Under this proposal **WDC + SNDK +
STX** all sit in `datacenter_hw` — a three-name storage cluster inside a
16-name bucket (15 under the umbrella copy; see §4 correction (ii)).

WDC and SNDK are not merely correlated, they share **direct corporate lineage**:
SNDK is WDC's own NAND-flash spin-off, so they share the underlying cost
structure and cyclicality. The correlation guard — enabled by
`qp_correlation_cap_enabled` `[VERIFIED — strategy_config.json:829]` and
gated at `correlation_guard_threshold = 0.70`
`[VERIFIED — strategy_config.json:210]` — is what would have to arbitrate.
Flagging it explicitly rather than leaving it inside a bucket-growth
percentage, because a 0.70 threshold on same-lineage names is where a
generic guard is least likely to behave as intended.

## 6. What I am NOT claiming

- Not that these buckets are optimal — three are flagged as judgment calls.
- Not that the 6-slot cap does or does not bind today, and not that
  concentration is safe at a higher admission rate — §4 defers both to a
  canonical strategy-side measurement this PR does not perform.
- Not that the correlation guard handles WDC/SNDK correctly. I did not test it.

## 7. Provenance

All figures read READ-ONLY from the canonical, strategy-owned
`renquant-strategy-104/configs/strategy_config.json` (the PINNED config; see
§4(ii) for where it and the umbrella copy diverge) on `main`
(sector_map lines 485-645, sector_etf_map 646-664, cap 665, require flag 427)
and the pipeline enforcement paths cited in §1. Admission figures from
orchestrator#610. Nothing written; no config changed.

**Path citation — a correction to the correction.** A prior revision replaced the
`.subrepo_runtime/...` citation on the grounds that it "does not exist on this
machine." **That was wrong, and is withdrawn.** The path exists; it was merely
cited as a bare relative string, which does not resolve from
`renquant-orchestrator`. Rooted at the umbrella it is present:

```
/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/
    renquant-strategy-104/configs/strategy_config.json   (66K, 2026-07-28)
```

`[VERIFIED-now — stat, this session]`. It is also the file RenQuant#544 names as
the live runner's config, so asserting its absence contradicted this doc's own
cited issue.

Both surfaces were therefore re-read this session, and for the fields that matter
here they agree exactly: `sector_map` and `watchlist` are **identical** between
the pinned mirror and `renquant-strategy-104` `main`
`[VERIFIED-now — dict equality on both fields]`. So every count below is
unchanged by which of the two is cited; the pinned mirror is the authoritative
one for what the runner loads, and it is quoted as such.

All cited line numbers re-verified against
`renquant-strategy-104/configs/strategy_config.json` on `main` — 210
(`correlation_guard_threshold: 0.7`), 427 (`require_sector_map_for_buys: true`),
511 (`NXPI: ai_chip`), 513 (`WDC: datacenter_hw`), 649-650 (both buckets → XLK),
665 (`max_positions_per_sector: 6`), 829 (`qp_correlation_cap_enabled: true`),
1338-1341 (the LITE + COHR `_activation_log` entry) — **8 of 8 reproduce exactly
as stated** `[VERIFIED-now]`.

The count divergence (13 vs 14 `datacenter_hw`) is §4(ii)'s pinned-vs-umbrella
finding, not a provenance error.

## 8. The decision this document is waiting on

Per LONG row 7 this stays **unmerged** until the operator rules on the three
flagged buckets. **ARM is the one that genuinely has no data answer**, so it is
laid out as options rather than resolved. Deliberately not picked here: a
confidently-stated bucket that is really a coin-flip is worse than an
acknowledged one, and nothing measurable separates these.

### ARM — the options, and what actually argues for each

**What is not in dispute** `[VERIFIED-now — config read]`: ARM is absent from
`sector_map` and from `watchlist`, so P-SECTOR-MAP would hard-fail buy mode for
the whole watchlist the moment ARM is added to the watchlist without a bucket.
Some bucket must be chosen; "leave it out" is only viable if ARM is also dropped
from the batch.

**Option A — `ai_chip` (the proposal).**
- Shares the sector's news-flow, tariff and export-control exposure, which is
  what a sector bucket is used for downstream: relative-strength grouping and the
  6-slot concentration cap.
- No new `sector_etf_map` entry needed — `ai_chip` → XLK already exists
  `[VERIFIED-now — line 649]`.
- Against it: every one of the 19 current `ai_chip` incumbents sells physical
  silicon or the equipment to make it `[VERIFIED-now — bucket membership read]`.
  ARM sells IP licences and collects royalties — no fab, no unit COGS. On the
  business model it is the odd one out.
- Cost if wrong: ARM occupies one of `ai_chip`'s 6 held slots and is treated as
  correlated with NVDA/AVGO/TSM. Given ARM's royalty revenue does track
  industry unit volumes, that correlation is directionally defensible.

**Option B — a new `chip_ip_licensing` bucket.**
- Taxonomically precise, and the taxonomy is explicitly finer than GICS.
- Against it: it needs its own `sector_etf_map` entry, and there is no clean ETF
  for a licensing-only sub-industry, so it would map to **XLK** anyway — the same
  ETF `ai_chip` uses `[VERIFIED-now — line 649]`. Since the ETF is the only thing
  the map feeds, the new bucket changes exactly one behaviour: it gives ARM a
  private 6-slot cap instead of sharing `ai_chip`'s. With one member, a 6-slot cap
  is inert.
- So B is **substantively equivalent to A on relative strength and differs only
  by exempting ARM from `ai_chip`'s concentration cap** — which is arguably the
  wrong direction, since the cap is the mechanism that would stop the book
  loading up on one semiconductor cycle.

**Option C — `software`.** Rejected, and this one *is* decidable: ARM's revenue is
royalty-per-unit on shipped silicon, so it moves with semiconductor volumes, not
software spend. Grouping it with ADBE/CRM/NOW would put it in the wrong
correlation cluster. Not recommended.

**Where that leaves it.** A and B differ only in whether ARM is subject to
`ai_chip`'s 6-slot cap. That is a **risk-policy question, not a taxonomy
question**, and it is the operator's call. Flag stays **low confidence**.

### ENTG and SNDK

Both remain **medium**, both are defensible either way, and neither blocks:
- **ENTG** — consumables/filtration versus the capital-equipment sellers it would
  sit beside. Recurring revenue against a capex cycle.
- **SNDK** — `datacenter_hw` on storage lineage, or `ai_chip` on the MU memory
  comp. If `datacenter_hw` is chosen, §5's WDC/SNDK same-lineage cluster is the
  live concern and is untested.

### On repo ownership (the standing review objection)

The objection that the eventual `sector_map` / `sector_etf_map` **edit** belongs
in `renquant-strategy-104`, reviewed atomically with the retrain and the config
fingerprint, is **accepted** — that is where the change must land, and this
document proposes no orchestrator config change and edits no config.

What is left here is the analysis and the open decision. Once ARM/ENTG/SNDK are
ruled on, the authoritative change is a strategy-104 PR carrying the config diff,
the fingerprint and the retrain evidence; this note should be reduced to a
pointer to it rather than merged as a parallel record.
