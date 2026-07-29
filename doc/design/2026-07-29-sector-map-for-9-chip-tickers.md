# Phase 3 of the 9-ticker atomic batch: proposed sector_map / sector_etf_map

**Status:** proposal for review. **No config changed.** These entries are part of
the atomic batch (watchlist + sector maps + retrained artifacts land together);
landing any piece alone hard-fails buys for all 154 names.

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
correct.** The review reproduced **13**; I read **14**. The difference is
exactly **CRWV**, present in `datacenter_hw` in the PINNED config and absent
from the umbrella copy `[VERIFIED — both files read this session]`. The live
runner loads the pinned one (`daily_104.sh:113`); the trainer loads the umbrella
one (`train_104.py:193`). That divergence is filed as
`hallovorld/RenQuant#544` — it is not a counting error on either side.

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
this PR.** #610 reports a `mu >= 0.03` admission rate of 2-6 names per session
across the whole cross-section, but #610 is itself open and under review, not
a canonical, reproduced strategy-side measurement, and it proposes no
admission change of its own. This doc does not use that number to conclude the
cap "cannot bind today," and does not predict what #223/#608/#610 "would
cause." That conclusion is deferred to a canonical, reproducible strategy-side
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

All figures read READ-ONLY from
`.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
(sector_map lines 485-645, sector_etf_map 646-664, cap 665, require flag 427)
and the pipeline enforcement paths cited in §1. Admission figures from
orchestrator#610. Nothing written; no config changed.
