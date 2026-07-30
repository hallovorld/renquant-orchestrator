# Phase 3 of the 9-ticker atomic batch: sector_map / sector_etf_map

**Status:** **proposal, pending operator decision.** No operator decision on
ARM's bucket is attributable to any citable source — a prior revision's "decided
by the operator's proxy" claim cited none and is **withdrawn** (§8). §8 keeps
Options A/B/C open for an explicit operator ruling. Per LONG ledger row 7
("design docs are not merged while under discussion"), this stays out of the
merge queue — manual-hold — until that ruling is recorded here with its source,
or the strategy-104 atomic PR ratifies the whole batch (ARM, ENTG, SNDK) in one
review.

**No config changed by this PR, and none may be.** The `sector_map` /
`sector_etf_map` **edit** is strategy-owned and lands in `renquant-strategy-104`,
reviewed atomically with the retrain and the config fingerprint (§8). This
document is the orchestrator's cross-repo sequencing + measurement record for
that change, not a parallel copy of it. These entries are part of the atomic
batch (watchlist + sector maps + retrained artifacts land together); landing any
piece alone hard-fails buys for all 154 names.

> **Correction in this revision — the concentration numbers were understated.**
> A prior revision reported `ai_chip` **17 → 23 (+35.3%)**. That applied the
> watchlist-relative correction to the *before* count but not to the *after*
> count. NXPI has a `sector_map` bucket already but is **not on the watchlist**
> `[VERIFIED — sector_map/watchlist membership, PINNED config, this session]`,
> and the batch adds it to the watchlist, so on the cap-visible axis NXPI is a
> **new** member. The corrected figure is **17 → 24 (+41.2%)** and `ai_chip`
> becomes the **largest** watchlist-relative bucket outright, not "within one of
> the largest" (§4). The error made the concentration case look milder than it
> is; it was found by re-measuring in-session, not raised in review.

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
| ARM | `ai_chip` | QCOM, AVGO, NVDA | **low** — §8, pending operator ruling |
| STX | `datacenter_hw` | WDC (direct HDD competitor) | high |
| SNDK | `datacenter_hw` | WDC (spin-off parent), DELL, SMCI | **medium** — see §3 |

All 9 tickers are currently **absent from the watchlist**, and only NXPI already
has a `sector_map` entry `[VERIFIED — membership check on the PINNED config,
this session]`. So the batch adds 9 watchlist members and 8 `sector_map`
entries.

**No new `sector_etf_map` entries are required** — both buckets already map to
XLK `[VERIFIED — strategy_config.json:649-650]`.

## 3. The calls that rest on judgment rather than measurement

**ARM (low) — pending operator ruling, §8.** Pure IP/royalty licensing: no fab,
no COGS, no unit sales. Every current `ai_chip` incumbent actually manufactures
or sells physical silicon or equipment `[VERIFIED — bucket membership read, this
session]`. `ai_chip` is the best AVAILABLE fit — same sector news-flow, tariff
and export-control exposure — but it remains a genuine qualitative stretch. The
alternative was a new `chip_ip_licensing` bucket; it would need its own
`sector_etf_map` entry, and with no clean ETF for a licensing-only sub-industry
it would also map to XLK, so it differs from `ai_chip` **only** in exempting ARM
from the 6-slot cap. That is the risk-policy question §8 puts to the operator:
inside the cap (Option A) or exempt from it (Option B).

**ENTG (medium).** Materials and filtration consumables, versus capital-equipment
sellers (AMAT/LRCX/KLAC). Recurring-revenue business against a capex cycle. Not
severe enough to block, but the second-loosest call here.

**SNDK (medium).** Defensible either way — `datacenter_hw` on storage-media and
literal spin-off lineage, or `ai_chip` on the memory-chip comp with MU. Chose
`datacenter_hw`. A judgment call, not a clean-cut case.

## 4. Concentration — the counts, and an open measurement question

Three corrections to the first version's counts: one raised in review, two found
by re-measuring.

**(i) `ai_chip` was counted wrong by me.** The first version used 19 =
sector_map ENTRY count. Only **17** of those 19 are on the watchlist
(`NVTS` and `NXPI` are the two mapped-but-unwatched names)
`[VERIFIED — sector_map entries whose ticker is in watchlist, this session]`.
`max_positions_per_sector` caps HELD positions among watchlist names, so the
watchlist-relative figure is the one a cap can ever see. Entry count overstates
it.

**(ii) `datacenter_hw` differs between the two configs, and both readings are
correct.** The review reproduced **13**; I read **14**. Neither is a counting
error — the two files have genuinely diverged.

Measured precisely this session, the drift is **3 tickers**, all present in the
pinned config and all absent from the umbrella copy
`[VERIFIED — §7 repro, set difference on `sector_map` / `watchlist` between the two config paths]`:

| ticker | bucket | affects the counts below? |
|---|---|---|
| **CRWV** | `datacenter_hw` | **yes** — this one ticker is the entire 14-vs-13 gap |
| RKLB | `industrial` | no |
| SPCX | `industrial` | no |

The drift is one-directional: **0** tickers are in the umbrella copy but missing
from the pinned one `[VERIFIED — §7 repro, reverse set difference is empty]`.
Pinned `sector_map` = 159 entries / `watchlist` = 145; umbrella = 156 / 142
`[VERIFIED — §7 repro, `len()` of both fields on both paths]`.

The live runner loads the pinned config (`daily_104.sh:113`, via
`renquant_strategy_config "$SUBREPO_ROOT"`); the trainer loads the umbrella copy
(`train_104.py:193`, `REPO_ROOT / "backtesting" / args.strategy`)
`[VERIFIED — `daily_104.sh:113` and `train_104.py:193`, both read this session]`.
That divergence is filed as
`hallovorld/RenQuant#544` (OPEN, and it cites these same two loader lines)
`[VERIFIED — `gh issue view hallovorld/RenQuant#544`]`.

**(iii) …and the correction was only half-applied — the growth figure was too
small.** Having established that the cap-visible axis is watchlist-relative, the
prior revision then computed `net new` on the *sector_map* axis: it excluded NXPI
as "already mapped". NXPI is indeed already mapped, so the batch adds no
`sector_map` entry for it — but NXPI is **not on the watchlist**
`[VERIFIED — membership check, PINNED config, this session]`, and the batch adds
all 9 tickers to the watchlist. On the axis that governs the cap, NXPI is
therefore a **new** member. Seven of the nine land in `ai_chip`
(NXPI, GFS, SWKS, QRVO, TER, ENTG, ARM), so:

* `net new` on the cap-visible axis = **7**, not 6.
* `after` = **24**, not 23. `growth` = **+41.2%**, not +35.3%
  `[DERIVED — 7/17]`.

The error understated the concentration this document exists to flag, so it is
corrected rather than footnoted.

| bucket | now (watchlist-relative) | net new | after | growth |
|---|---:|---:|---:|---:|
| `ai_chip` | **17** | +7 | **24** | **+41.2%** |
| `datacenter_hw` (PINNED, runner) | **14** | +2 | **16** | +14.3% |
| `datacenter_hw` (umbrella, trainer) | **13** | +2 | **15** | +15.4% |

`datacenter_hw` is unaffected by correction (iii): all 14 of its entries are
already on the watchlist and both of its additions (STX, SNDK) are new to both
surfaces `[VERIFIED — membership check, this session]`.

Both `datacenter_hw` rows are stated on purpose: until #544 is resolved there is
no single answer, and picking one silently would hide the divergence.

`now` `[VERIFIED — sector_map entries per bucket RESTRICTED to watchlist
members, this session]` — see correction (i); the earlier version used
unrestricted entry count. `net new` `[VERIFIED — §2 proposal rows per bucket,
counting every ticker the batch newly adds to the WATCHLIST, i.e. including
NXPI]` — see correction (iii). `after` `[DERIVED — now + net new]`. `growth`
`[DERIVED — net new / now]`.

**Where that puts `ai_chip` — corrected, and on one consistent axis.** The prior
revision compared `ai_chip`'s watchlist-relative count against `software`'s
*entry* count (26), which mixes the two axes. Held on the watchlist-relative axis
throughout `[VERIFIED — per-bucket counts restricted to watchlist members, PINNED
config, this session]`:

| rank | bucket | watchlist-relative, now |
|---:|---|---:|
| 1 | `industrial` | 21 |
| 2 | `software` | 19 |
| 3 | `finance` | 18 |
| 4 | **`ai_chip`** | **17** |

So `ai_chip` is currently **fourth**, not third; and after the batch it is
**24 — the largest bucket outright**, ahead of `industrial`'s 21. It also becomes
by far the largest semiconductor-cycle-correlated bucket. **24** watchlist names
would compete for the same 6 held slots. This is a stronger concentration
statement than the prior revision made, and it is the one the measurement
supports.

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

- Not that these buckets are optimal. ARM's bucket assignment is a risk-policy
  call, not a measurement, and remains **undecided** pending an operator ruling
  (§8). ENTG and SNDK remain judgment calls.
- Not that the 6-slot cap does or does not bind today, and not that
  concentration is safe at a higher admission rate — §4 defers both to a
  canonical strategy-side measurement this PR does not perform.
- Not that the correlation guard handles WDC/SNDK correctly. I did not test it.

## 7. Provenance

### The repro (`§7 repro`, cited by the tags above)

Every count in §2 and §4 comes from this, run READ-ONLY this session. `PIN` is the
config the runner loads, `UMB` the one the trainer loads, `CAN` strategy-104 `main`:

```python
import json, collections
PIN = "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json"
UMB = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.json"
CAN = "/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json"
for name, p in (("PINNED", PIN), ("UMBRELLA", UMB), ("CANONICAL", CAN)):
    c = json.load(open(p)); sm, wl = c["sector_map"], set(c["watchlist"])
    wrel = collections.Counter(b for t, b in sm.items() if t in wl)
    print(name, len(sm), len(wl), dict(wrel))
```

What it returned `[VERIFIED — the block above, this session]`:

| surface | `sector_map` | `watchlist` | `ai_chip` w-rel | `datacenter_hw` w-rel |
|---|---:|---:|---:|---:|
| PINNED (runner) | 159 | 145 | 17 | **14** |
| UMBRELLA (trainer) | 156 | 142 | 17 | **13** |
| CANONICAL strategy-104 `main` | 159 | 145 | 17 | 14 |

`PINNED == CANONICAL` on both `sector_map` and `watchlist`; `PINNED != UMBRELLA`,
with the set difference being exactly `{CRWV: datacenter_hw, RKLB: industrial,
SPCX: industrial}` and the reverse difference **empty**
`[VERIFIED — the block above, this session]`.

### Sources

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

`[VERIFIED — `ls -la` on that absolute path, this session]`. It is also the file
RenQuant#544 names as
the live runner's config, so asserting its absence contradicted this doc's own
cited issue.

Both surfaces were therefore re-read this session, and for the fields that matter
here they agree exactly: `sector_map` and `watchlist` are **identical** between
the pinned mirror and `renquant-strategy-104` `main`
`[VERIFIED — §7 repro, dict equality on both fields]`. So every count below is
unchanged by which of the two is cited; the pinned mirror is the authoritative
one for what the runner loads, and it is quoted as such.

All cited line numbers re-verified against
`renquant-strategy-104/configs/strategy_config.json` on `main` — 210
(`correlation_guard_threshold: 0.7`), 427 (`require_sector_map_for_buys: true`),
511 (`NXPI: ai_chip`), 513 (`WDC: datacenter_hw`), 649-650 (both buckets → XLK),
665 (`max_positions_per_sector: 6`), 829 (`qp_correlation_cap_enabled: true`),
1338-1341 (the LITE + COHR `_activation_log` entry) — **8 of 8 reproduce exactly
as stated** `[VERIFIED — each cited line printed from the PINNED config, §7 repro]`.

The count divergence (13 vs 14 `datacenter_hw`) is §4(ii)'s pinned-vs-umbrella
finding, not a provenance error.

## 8. The decision the operator needs to make — and where the rest happen

**ARM → `ai_chip`. NOT DECIDED.** A prior revision of this document asserted
this was "decided by the operator's proxy," citing no source. That framing is
**withdrawn**: there is no attributable operator decision, issue, or accepted
strategy-104 PR to ground it, and the PR's own review history shows the
opposite sequence — reviewers repeatedly flagged the operator decision as
missing, and it was never subsequently supplied. This is a risk-policy call
between Option A and Option B below, and it stays **open** until the operator
rules on it here (with a citable source) or the strategy-104 PR that lands the
config edit records the ruling itself.

Recommendation, not a decision: Option A (`ai_chip`) is the conservative
choice — it puts ARM inside the concentration cap rather than exempt from it,
and §4 measures `ai_chip` becoming the largest bucket in the book (24 names,
6 slots), which makes cap membership matter more, not less. That is a
recommendation for the operator to weigh, not a ruling already made.

### ARM — the options awaiting an operator ruling

**What is not in dispute** `[VERIFIED — §7 repro, ARM membership test]`: ARM is absent from
`sector_map` and from `watchlist`, so P-SECTOR-MAP would hard-fail buy mode for
the whole watchlist the moment ARM is added to the watchlist without a bucket.
Some bucket must be chosen; "leave it out" is only viable if ARM is also dropped
from the batch.

**Option A — `ai_chip`. Recommended, not yet decided.**
- Shares the sector's news-flow, tariff and export-control exposure, which is
  what a sector bucket is used for downstream: relative-strength grouping and the
  6-slot concentration cap.
- No new `sector_etf_map` entry needed — `ai_chip` → XLK already exists
  `[VERIFIED — strategy_config.json:649]`.
- Against it: every one of the 19 current `ai_chip` incumbents sells physical
  silicon or the equipment to make it
  `[VERIFIED — §7 repro, `ai_chip` bucket membership listing]`.
  ARM sells IP licences and collects royalties — no fab, no unit COGS. On the
  business model it is the odd one out.
- Cost if wrong: ARM occupies one of `ai_chip`'s 6 held slots and is treated as
  correlated with NVDA/AVGO/TSM. Given ARM's royalty revenue does track
  industry unit volumes, that correlation is directionally defensible.

**Option B — a new `chip_ip_licensing` bucket.**
- Taxonomically precise, and the taxonomy is explicitly finer than GICS.
- Against it: it needs its own `sector_etf_map` entry, and there is no clean ETF
  for a licensing-only sub-industry, so it would map to **XLK** anyway — the same
  ETF `ai_chip` uses `[VERIFIED — strategy_config.json:649]`. Since the ETF is the only thing
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

**Why this needs a ruling rather than an analysis.** A and B differ only in
whether ARM is subject to `ai_chip`'s 6-slot cap. That is a **risk-policy
question, not a taxonomy question**, so no measurement can settle it — which is
why it is escalated rather than decided in this document. It has **not** yet
been ruled on. Recommendation: **A**, for the reasons above.

### ENTG and SNDK — ratified where the edit lands, not here

Both remain **medium**-confidence agent recommendations (ENTG → `ai_chip`,
SNDK → `datacenter_hw`), both are defensible either way, and neither is an
orchestrator decision to make:
- **ENTG** — consumables/filtration versus the capital-equipment sellers it would
  sit beside. Recurring revenue against a capex cycle.
- **SNDK** — `datacenter_hw` on storage lineage, or `ai_chip` on the MU memory
  comp. `datacenter_hw` is recommended; if taken, §5's WDC/SNDK same-lineage
  cluster is the live concern and is **untested**.

Unlike ARM, neither turns on a policy question that only the operator can answer:
each is a taxonomy call whose consequence is visible in the config diff itself.
They are therefore **ratified in the strategy-104 PR that makes the edit**, on the
same review where the fingerprint and retrain evidence are checked — not held open
against this record. Nothing downstream can act on them before that PR exists.

### On repo ownership (the standing review objection)

The objection that the `sector_map` / `sector_etf_map` **edit** belongs in
`renquant-strategy-104`, reviewed atomically with the retrain and the config
fingerprint, is **accepted without reservation**: that is where the change must
land, this document edits no config, and no orchestrator config change is
proposed.

What this document is, and why it is here rather than only there: the
orchestrator owns cross-repo **sequencing** and the run record. The measurements
in §1 and §4 are about pipeline enforcement paths (`preflight_pipeline`,
`task_selection`, `portfolio_qp`) and the pinned-vs-umbrella config divergence
(RenQuant#544) — orchestration-level facts that no single strategy PR owns, and
that the strategy PR will *cite* rather than reproduce. Deleting this record
would not move those facts to strategy-104; it would lose them.

The authoritative change remains a strategy-104 PR carrying the config diff, the
fingerprint and the retrain evidence. When it exists, §2's table should be
reduced to a pointer at it so the buckets are stated in exactly one place.
