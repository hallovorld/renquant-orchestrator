# S-REL: Experiment Reliability Program — SHORT-tier P0

STATUS: design RFC (docs only — no code, no config, no production behavior change). Companion
deliverable: `doc/research/VERDICTS.md` (the seeded standing-verdict ledger, same PR).
DATE: 2026-07-03
TIER: **SHORT (July), P0** — operator directive 2026-07-03: "试验可靠性优先级很高！放在短期p0，
着重处理" (experiment reliability is high priority — SHORT-tier P0, handle it as a focus), after
the operator challenged whether our rejected-direction experiments are 100% scientific.
MASTER-PLAN INTEGRATION: this program slots into the unified master plan
(`doc/design/2026-07-02-unified-107-master-plan.md`) SHORT tier as P0; the plan itself is
amended only through its own §4 dated-addendum mechanism — the next addendum should reference
this doc. This doc is the S-REL source of truth.

---

## 0. Why this program exists (the proven precedent, not a hypothetical)

**The founding precedent — a NULL that was wrong, caught, and overturned.** The A-1 λ
dose-response study's round 1 (revision history of merged PR #240,
`doc/research/2026-07-02-a1-lambda-sweep-null.md`) swept `cash_drag_lambda` but never passed
`min_invested_pct`. The solver only activates the cash-drag objective when **both** are > 0
(`qp_solver.py:468`), so the wrapper default (`0.0`) silently disabled the entire mechanism —
identical solutions at every λ were **guaranteed by construction**. Round 1 reported that as a
"NULL". Codex's adversarial review caught it; the NULL was retracted; round 3 re-ran with the
mechanism genuinely armed **and a positive control** (a scenario proving the harness can detect
a λ effect when the mechanism is active), and produced a different, correct finding.

The lesson is structural, not personal: **a negative result from a harness that cannot detect
the effect it is testing for is not evidence — and nothing in our process, until now, forced
that distinction.** Several of our highest-consequence standing verdicts are negatives (S9
NULL, M8 NO-GO, M3 AC-FAIL, phase −1 NO-GO). Each one closed a direction or feeds a D-gate.
If any of them has a λ-round-1-class defect, we are steering the program on a wrong number.

The near-misses that were caught confirm the failure class is live, not rare:

- **C3**: the mechanical MISS was computed on a substrate whose regime labels and universe
  membership were not point-in-time — caught in Codex round-2 review, downgraded to
  UNADJUDICATED (`doc/research/2026-07-02-c3-residual-momentum.md`).
- **S9**: the pick table's `fwd_60d_excess` turned out to be the cross-sectionally
  *standardized* label while every §4 gate is denominated in return units — caught during
  execution, fixed by a proven-faithful raw-label join (15,109/15,109 rows, max |Δ| = 0.0 on
  the standardized reproduction).
- **RS-5 round 2**: `prereg_contract.json` had no test proving it agreed with the prose it was
  supposed to freeze — caught in review.

Every one of these was caught by an *ad-hoc* adversarial pass. S-REL makes that pass a
contract instead of a favor.

**Design constraint (standing lesson, operator 2026-06-28): no validation cathedral.** S-REL
is four rules, one audit queue, one ledger, one JSON convention. CI-enforced memo compliance
and any heavier machinery are explicitly deferred (§3.3, §4).

---

## 1. The reliability contract for verdicts (the operator's four rules, made precise)

These rules bind from the merge of this design forward. They apply to **verdict-producing
research** (a memo whose output is GO/NO-GO/NULL/PASS/FAIL/REJECTED against a frozen rule).
Ordinary engineering PRs, ops records, and exploratory scans that do not claim a verdict are
out of scope.

### 1.1 Rule R1 — D-gate-feeding and direction-closing verdicts are PROVISIONAL until adversarially verified

**Scope.** A verdict is in R1 scope iff it (i) feeds a master-plan decision gate (§1.5 of the
unified plan: D1, S9/Track-A, M2 canary, D3/L1, L6, M10/L7, M-SIG kill branch) — i.e. its
number appears in a gate's synthesis inputs; or (ii) **closes a direction** — removes a path
from the plan (S9 NULL ⇒ Track B only; M8 NO-GO ⇒ waves stop; phase −1 ⇒ intraday directional
alpha dead; M3 AC-FAIL ⇒ haircut not shipped). Low-load exploratory NULLs are NOT in scope
(§4).

**States.** Every in-scope verdict is **PROVISIONAL** at publication and stays PROVISIONAL
until an independent adversarial re-verification returns **UPHELD**. The other outcomes:

- **UPHELD** — every load-bearing number reproduced within its stated tolerance from the
  committed inputs, AND no mechanism-off / contamination / arm-parity finding. Verdict becomes
  standing evidence at full weight.
- **OVERTURNED** — a load-bearing number is wrong and the corrected number flips the verdict
  through the frozen decision rule. The verdict is retracted (λ-round-1 style): memo revised
  or superseded, ledger row updated, every downstream consumer notified in the same PR.
- **WEAKENED** — real errors or fragilities found that do NOT flip the verdict, but narrow the
  evidence boundary (e.g. a sub-window result doesn't hold, a sensitivity was mislabeled). The
  verdict stands with an amended evidence-boundary block; the ledger row records the weakening.

**The verification protocol (what "independent adversarial re-verification" means).**

1. **Different implementation** — the verifier writes fresh code from the frozen spec and the
   committed inputs. Re-running the author's script proves only determinism; it would not have
   caught λ-round-1 (the bug reproduced perfectly).
2. **Different party** — not the author agent/session. Codex-adversarial review per the
   standing agent control-plane is the default verifier.
3. **Recompute the load-bearing numbers** — all of them (defined below), from the committed
   evidence inputs, and check the verdict re-derives through the frozen rule.
4. **Try-to-OVERTURN framing** — the verifier's explicit brief is to break the verdict, not to
   confirm it. Checklist derived from our actual failure modes:
   - Is the mechanism under test actually ARMED in the harness (λ-round-1 class)? Prove it,
     don't assume it — ideally by the positive control (R2).
   - Units / scale / label mapping (S9's standardized-vs-raw label class).
   - Substrate PIT-ness: regime labels, universe membership, availability timestamps (C3
     class; the M-SIG r4 period-date-fallback lookahead class).
   - Join fidelity and dedup rules (M3's canonical-run dedup, weekend date mapping).
   - Arm parity in paired designs (M8: identical cuts/featurization/params across arms;
     coverage-boundary NaN behavior).
   - Sign conventions and the direction of every inequality in the frozen rule.
5. **One pass suffices** — no verification-of-verifications (§4). Only an OVERTURNED outcome
   triggers a second look, and that look reviews the *correction*, not a third opinion.

**Definition: load-bearing number.** A quantity is load-bearing for a verdict iff a plausible
error in it — sign flip, magnitude error beyond its own stated CI, or a wrong unit / substrate
/ join mapping — **changes the verdict under the frozen decision rule, holding everything else
fixed**. Diagnostics that are reported but do not gate (e.g. M8's per-regime cuts, C3's
per-regime breakdown) are not load-bearing. From this design forward, every in-scope verdict
memo MUST name its own load-bearing numbers in a short list (the audit queue in §2 does this
retroactively for the standing verdicts).

**What PROVISIONAL means operationally** (not a freeze of all downstream work):

- The verdict is recorded, cited, and downstream *engineering* may proceed.
- Any D-gate synthesis consuming it must label it PROVISIONAL explicitly.
- **No irreversible plan action** — deleting a direction from the plan's non-goals, a
  watchlist change, a config flip, capital movement — rests solely on a PROVISIONAL verdict.
- The pre-registered consequence of a verdict (e.g. "waves stop") executes immediately — the
  conservative direction never waits on verification; only the *irreversible* consumption of
  the verdict does.

### 1.2 Rule R2 — positive controls mandatory in every negative-result harness

**Mechanical requirement.** Any harness whose output can be a NULL / NO-GO / FAIL verdict MUST
include at least one **positive-control fixture**: an input in which the mechanism or effect
under test is deliberately PLANTED — a synthetic injection of a known-size effect, or a
configuration in which the mechanism is provably active — and the harness's detection path
MUST fire on it. The control is **committed as a test** (pytest, runs with the repo suite)
alongside the harness script — not a one-off note in the memo.

- **Sensitivity at decision scale.** The planted effect must be at or near the frozen decision
  threshold, not 10× it. For an M8-style gate at −0.010, plant a ~0.02 IC degradation and show
  the paired WF detects it; for an S9-style expectancy gate at +5 bps/60d, plant an
  enrichment of that order. A harness that only detects huge effects has not demonstrated the
  sensitivity the gate assumes.
- **Admissibility rule.** A negative verdict from a harness with no passing positive control
  is **inadmissible as a verdict** — it may be reported only as "harness ran; sensitivity
  unproven", and it cannot close a direction or feed a D-gate.
- **Negative controls (placebo) are unchanged** — the placebo-clean-differences house rule
  stands; R2 adds the symmetric requirement that was missing.
- **Precedents already in the corpus** (this is codification, not invention): λ-sweep round
  3's scenario 3 (non-binding turnover + mechanism armed → λ effect detected); the master
  plan's S1–S3 AC "fixture: passes known-clean, fails known-leaked".

**Applies to:** every NEW harness from this design forward, plus the retrospective queue's
verification reruns (§2). NOT a mass retrofit of merged low-load NULLs (§4).

### 1.3 Rule R3 — evidence-boundary block mandatory in every verdict memo

Every verdict memo MUST contain a literal `## Evidence boundary` section using this template
(one line per field; "n/a" must be argued, not assumed):

```markdown
## Evidence boundary
- Window: <start → end; n decision dates>
- Cells: <n per regime/era cell; NAME every thin (<30 obs) or empty cell>
- Outcome era: <which scorer/config era produced the resolved outcomes; retired or current;
  n resolved per era>
- Cost model: <none | proxy (state the value) | measured>
- Substrate: <PIT status of every input; survivorship status; known contamination>
- Multiplicity: <k candidates/looks; correction applied>
- Not covered: <one line: the strongest true statement about what this verdict does NOT say>
```

The existing S9/M8/M3/C3 memos already carry most of this in prose (cell-count tables, era
caveats, cost-proxy statements) — R3 makes it uniform, mandatory, and greppable. The point is
that a verdict's *scope* travels with its *number*: "M3 AC-FAIL" must never be quotable without
"on retired-era mu streams, fwd_20d proxy, BULL_CALM only" attached.

### 1.4 Rule R4 — reopening conditions mandatory (the E34 → M8 pattern, generalized)

E34 (umbrella failed-experiments log) recorded a **resume condition** with its failure
("cluster-based similarity admission instead of blind expansion"); M8 operationalized exactly
that condition, measured it, and recorded the outcome — the resume condition was consumed, not
re-argued. Generalize this to every direction-closing verdict:

- **(i)** State the specific future fact — new data, substrate fix, mechanism change, regime
  of the world — that would justify reopening. "Someone wants to retry" is not a condition.
- **(ii)** Reopening executes as a **NEW frozen prereg** (new spec, new gates frozen before
  measurement) — never a rerun of the same test with tweaks, and never threshold motion.
- **(iii)** Absent the stated condition, re-pitching is barred (this codifies the standing
  "don't re-pitch" notes into the verdict format itself).

Well-formed examples already in the corpus: M3 ("revisit after S5 accrues panel-era fwd_60d
outcomes AND a persisted per-name uncertainty exists"); M8 ("any revisit routes through D3");
S9 ("a genuinely NEW hypothesis needs its own separate frozen prereg, never a revival"); C3
("a genuinely point-in-time rerun or an accepted substitute substrate").

---

## 2. The retrospective audit queue

Standing verdicts, ordered by **load** = (feeds a D-gate or closed a direction) × (substrate
fragility). Each item lists the load-bearing numbers the verifier must recompute and what
would flip the verdict. Verification results land as
`doc/research/<date>-<id>-verification.md` + a ledger-row update (§3.2).

| # | ID | Verdict under audit | Priority | Status |
|---|---|---|---|---|
| V1 | S9 Track A conditional (#262) | NULL | P0 | verification **IN FLIGHT** |
| V2 | M8 cluster wave-1 (#261) | NO-GO | P0 | verification **IN FLIGHT** |
| V3 | M3 haircut replay (merged) | AC FAIL | P1 | **NEXT** — first S-REL dispatch |
| V4 | C3 adjudication status | UNADJUDICATED vs "MISS" | P1 | queued (reconciliation, not recompute) |
| V5 | M4 intercept finding (pipeline #162) | FINDING (M4-b's premise) | P1 | queued |
| V6 | Phase −1 intraday alpha (PR #199) | NO-GO (soft) | P2 | queued — **durability first** |
| V7 | Low-load NULL batch (trend-scan, fundmom, analyst/minute/PEAD scans, price-trend) | NULL/REJECTED ×n | P3 | NOT dispatched — verify-on-reopen only |

### V1 — S9 Track A conditional NULL (P0, in flight)

Closed a direction (Track A dead; Track B only remaining directional path for renquant105) and
feeds D3. Doc: `doc/research/2026-07-03-s9-track-a-conditional.md`.

**Load-bearing numbers to recompute:**
- The **raw-label join**: 15,109/15,109 pick rows joined to `fwd_60d_excess_raw`; the
  standardized column reproduced with max |Δ| = 0.0; frozen label `y = 1` iff raw > 0.0011.
  An error here invalidates every gate simultaneously.
- **Gate (e) winner-drop for C3-candidate**: 42.9% (891/2,078) vs the ≤ 1/3 cap — the ONLY
  gate C3-candidate fails on test. This is the single highest-leverage number in the memo.
- **C1 train→test flip**: +592 bps/yr train → −636 bps/yr test (the overfit read).
- **C2 active exposure**: 0.7% (1 BEAR date in 143) vs the ≥25% floor.
- **Split integrity**: 305 train / 60d embargo (2025-04-23 → 2025-07-18) / 143 test dates —
  verify no leak across the embargo; verify the bootstrap (block 13, 2,000 resamples) is
  built on date blocks, not row blocks.

**What would flip it:** if C3-candidate's true winner-drop is ≤ 1/3 under a corrected winner
definition (cost proxy, excess join, or the 2,078 winner denominator), C3-candidate passes all
of (a)–(e) → the verdict becomes GO and a meta-label filter direction reopens. A units/join
error invalidates (not flips) everything. Note the memo's own honest flag: even then, C3 was
not selectable ex ante (train sign disagrees) — the verifier must rule on the frozen §4 "any
conditioning clears all gates" wording, which is the GENEROUS direction.

### V2 — M8 cluster wave-1 NO-GO (P0, in flight)

Closed a direction (waves stop; Term BR now rides on D3 down-cap alone). Doc:
`doc/research/2026-07-03-m8-cluster-wave1.md`.

**Load-bearing numbers to recompute:**
- **Mean paired ΔIC over qualifying cuts = −0.0477** vs the frozen −0.010 band (per-cut:
  −0.0764 / +0.0159 / −0.0825 on cuts 5/6/7).
- **Qualifying-cut rule application**: cuts 5–7 qualify (≥50% wave coverage) — verify the rule
  was applied as frozen, since it selects which cuts the gate reads.
- **Arm parity** (the paired design's Achilles' heel): identical cuts, featurization, and
  `PANEL_LTR_PARAMS` in both arms; specifically whether the 512/683 candidates with the
  2021-05-03 fetch-window start inject NaN/short-history rows into the augmented arm's
  TRAINING in a way the baseline arm never faces — a handicapped augmented arm would
  manufacture exactly this degradation.
- **The incumbent-subset diagnostic** (augmented model scored only on the 133 incumbents:
  0.1398→0.0663, 0.0054→0.0250, 0.1276→0.0615) — this is the mechanism claim ("training
  dilution hits the incumbent book"), and it is also the natural parity check: it compares
  the two arms on an identical scoring universe.
- **Placebo-clean paired Δ = −0.0328** (the not-an-embargo-artifact claim).

**What would flip it:** corrected mean Δ ≥ −0.010 on qualifying cuts → PASS → wave-2 reopens
and Term BR regains its second path. The most plausible route to that is an arm-parity bug;
the survivorship direction is already argued conservative in the memo (bias favors the wave).

### V3 — M3 haircut replay AC-FAIL (P1, next — the first new S-REL dispatch)

Feeds Term TC (killed the haircut config change; routed to observe-only alert). Doc:
`doc/research/2026-07-02-m3-haircut-replay.md`. **Why it is the queue's most fragile item**
(the memo says so itself, honestly):

- **Retired-era outcomes**: every resolved outcome comes from the pre-tournament and
  legacy-tournament mu streams (May–early June); the CURRENT scorer (panel_ltr_xgboost, since
  06-22) has zero resolved fwd_10d/20d outcomes. The verdict is about historical mu streams.
- **SE proxy**: cross-run dispersion (stability), not a sampling SE; defined for only 301/430
  floor-clearing rows; undefined on its own motivating fixtures (OXY/GRMN fresh entrants).
- **fwd_20d substitution**: the AC is denominated at fwd_60d, which is unresolvable for the
  entire live window — fwd_20d is a proxy, and the memo's own fwd_5d row shows the W/L
  direction *reverses* at short horizons (15W/25L at k=0.5).
- Degenerate block-13 bootstrap (8–13 usable dates); BULL_CALM-only; 26 canonical dates.

**Load-bearing numbers to recompute:**
- **Winners/losers removed: 18W/15L (k=0.5), 28W/22L (k=1.0) at fwd_20d** — the AC verdict is
  literally these four integers. They depend on: the 11 bps cost-proxy winner definition, the
  SPY-excess join, weekend→prior-trading-day mapping, and the one-canonical-run-per-date dedup
  rule. Small errors move single counts; the margins are 3 and 6.
- **Δ expectancy −0.51 pp at k=1.0** (block-5 CI [−0.89, −0.01] — the "actively harmful" read;
  note block-1 spans 0, so significance is already self-labeled weak).
- **Thin-margin share 39.5% → 23.7%/20.0%** (the second AC leg, "nowhere near ~0").

**What would flip it:** corrected counts showing losers ≥ winners removed at the primary
horizon with a positive expectancy delta → the AC is MET → the haircut config-PR route
reopens. Independently: fwd_60d outcomes aging in via S5 could legitimately reverse the
fwd_20d read — that is V3's *reopening condition* (already recorded in the memo), not a
verification finding.

### V4 — C3 adjudication status: UNADJUDICATED vs "MISS" (P1 — reconciliation, not recompute)

The numbers were already recomputed twice under Codex review (rounds 1–2); a third recompute
is exactly the verification-of-verifications regress §4 bars. The open reliability problem is
**which adjudication is recorded where** — and G106's composition depends on it:

- The governing memo (`doc/research/2026-07-02-c3-residual-momentum.md`) rules
  **UNADJUDICATED**: the mechanical MISS was computed on substrate with future contamination
  (non-PIT regime labels + universe membership); C3's formal vote was NOT cast; a PIT-clean
  rerun remains open future work.
- The plan addendum (`doc/progress/2026-07-02-plan-addendum.md`) recorded "**C3 MISS** ⇒ G106
  2-of-3 ≈ 0.35–0.45" — treating C3 as settled-negative and shrinking the M-SIG stack.
- These disagree. If C3 is MISS, G106 rides on C2/C4 (2-of-3 becomes 2-of-2-remaining); if
  UNADJUDICATED, C3 still holds a vote pending an admissible substrate, and the G106 prior is
  different. The M-SIG spec's Bonferroni k=3 family also reads differently in the two cases.

**Deliverable:** a one-page reconciliation memo ruling which status governs (the memo is the
evidence source of truth; the addendum is a consumer — the presumption is UNADJUDICATED
governs and the addendum's G106 delta needs a dated correction via the plan's §4 mechanism),
plus an explicit decision on whether a PIT-clean C3 rerun is worth scoping — stated honestly
as a materially larger data-engineering task (walk-forward regime model + PIT universe), per
the memo's own §6/§8 search results, not a quick fix.

**Load-bearing numbers** (context for the reconciliation, no recompute): conditioned
placebo-clean −0.0040 vs the +0.015 bar; conditioned-minus-unconditioned +0.0086 with every CI
spanning zero; 98.33% one-sided LBs ≈ −0.055 on all seeds.

### V5 — M4 intercept finding, pipeline #162 (P1)

Not a closure — a live FINDING that is the entire premise of the M4-b redesign (orchestrator
PR #260) and of the "floor must become relative" route. If it is wrong, M4-b is redesigning
around an artifact. Source: pipeline #162 PR body + `shadow_replay_bl1_recenter.py` evidence.

**Load-bearing numbers to recompute (independent implementation against the stored
`score_distribution.raw_panel` + the live calibrator JSON):**
- **ER=0 neutral at raw = −0.2902** (the anchor; live log line) — and the consequence that
  raw ∈ (−0.2902, 0) maps to μ of the opposite sign.
- **Sign-laundered counts 44 (07-01) / 45 (07-02) → 0 post-recentering** on all six replayed
  runs.
- **Replay fidelity max |Δ| = 0.0** on 07-01/02 (the before-path reproduces stored prod μ
  exactly — this is the claim that makes the replay trustworthy at all; earlier days ≤0.0035
  attributed to calibrator vintage drift — verify that attribution).
- **Admitted at mu_floor 0.03: 22→1, 17→1, 18→1, 18→0** on the drifted June cross-sections
  (the "near-sell-only" honest warning that M4-b exists to solve), vs 5→6, 3→3 on 06-24/25
  where center ≈ anchor.

**What would flip it:** if the fidelity claim or the per-bar median-center convention is wrong
(e.g. the calibrator's own training-time centering makes the median shift double-count), then
"recentering zeroes laundering" and/or "the floor admits ~0–1" collapse — weakening or
voiding M4-b's premise and reinstating the +2–3% intercept as the open question.

### V6 — Phase −1 intraday directional alpha NO-GO (P2 — durability FIRST, then verify)

Killed a direction (intraday directional alpha), and merged plans actively rely on it: the H2
roadmap's non-goals, the unified plan's L3 row ("phase −1 NO-GO not re-litigated"), and the
104/105 design-review amendment A4.2 (Stage-2 estimand pinned to the timing residual because
of it). **But the verdict's evidence is not durable: PR #199 is CLOSED unmerged — the memo
(`2026-06-27-renquant105-phase-minus-1-results.md`), the harness script, and its tests are not
on main.** A verdict that merged documents rely on has no committed evidence. This is itself
S-REL's first concrete infrastructure finding.

**Step 1 (durability):** recommit the phase −1 memo + script + evidence from PR #199's branch
as a docs/evidence PR (no re-litigation — archival), so the verdict has a citable substrate.
**Step 2 (verification, after durability):**

- **Load-bearing numbers:** σ(open→close) ≈ 152 bps (std, 114-name robust); net edge
  **−6.4 bps @ IC 0.03 / −3.4 bps @ IC 0.05**; breakeven cost bar 220–367 bps.
- **What would flip it:** a cost-model error or a σ_oc measurement error large enough to push
  net edge positive at a plausible IC — given the gap (needs ~an order of magnitude), P2 not
  P0. The honest reopening condition: a measured cost below breakeven or an evidenced IC claim
  far above the 0.03–0.05 band — either is a NEW prereg per R4.

### V7 — Low-load NULL batch (P3 — no dispatch, verify-on-reopen only)

Trend-scan label evidence (now superseded as M-SIG C4's frozen candidate with its retrospective
status honestly labeled), fundamental momentum REJECTED (#177 — successor test is M-SIG C2 on
N3 data), the renquant105 exploratory scans (trend baseline / fundamentals / minute-feature IC
/ PEAD — 4 NULLs on free-tier data), canonical price-trend multi-day edge NULL. These closed
exploratory lanes, not plan gates; several already have successor tests frozen in the M-SIG
spec. Per §4 scope discipline: **no mass retrofit** — they get a ledger row (visibility) and a
verification only if and when their R4 reopening condition fires.

---

## 3. Auditability infrastructure (lightweight by design)

### 3.1 Evidence-JSON convention, hardened

**Measured current state** (why this is needed): `evidence/2026-07-03-m8/m8_verdict.json`
stamps `generated_utc` but no input hashes, no code SHA, no environment;
`evidence/2026-07-03-s9/s9_results.json` stamps the frozen spec and constants but not the
generating code's revision. S9's substrate content hash (`ba964b407ec1e0a5…`) WAS verified —
but in-memo, via the #59 contract, not stamped in the evidence files themselves. A verifier
today cannot prove *which inputs and which code* produced a given evidence file without
forensic reconstruction.

**The hardened convention** — every evidence directory gains (or every evidence JSON embeds) a
`manifest` with exactly these fields:

```json
{
  "generated_utc": "<ISO-8601>",
  "inputs": [
    {"path": "<repo-or-umbrella-relative path>", "sha256": "<content hash>"}
  ],
  "code": {
    "repo": "<repo name>",
    "git_sha": "<commit of the generating script's tree>",
    "dirty": false,
    "script": "scripts/<name>.py",
    "argv": ["--as-run"]
  },
  "env": {
    "python": "<x.y.z>",
    "lock_sha256": "<sha256 of the venv lockfile, or of `pip freeze` output>"
  },
  "seeds": [42]
}
```

Rules: content hashes of INPUTS (not just paths — paths mutate); the code stamp must include
the `dirty` flag (a dirty-tree run is admissible for exploration, inadmissible for a verdict);
`env.lock_sha256` pins the dependency surface (an xgboost minor-version change moves ICs).
**Adoption boundary:** all NEW harnesses and all §2 verification runs. **No retro-editing of
merged evidence files** — history stays honest; the queue's verification memos stamp their own
manifests.

### 3.2 The standing-verdict ledger: `doc/research/VERDICTS.md`

One line per standing verdict: **date · ID · verdict · evidence boundary (one phrase) ·
verification status · reopening condition.** Seeded in this PR with the current standing
verdicts (see the file). Update discipline:

- A row changes ONLY via a PR that carries the evidence for the change (a verification memo, a
  new prereg, a dated plan addendum) — the ledger is an index, never the evidence itself.
- Every new verdict memo adds its row in the same PR (cheap, reviewable, no tooling).
- Verification statuses: `PROVISIONAL` / `IN FLIGHT` / `UPHELD` / `WEAKENED` / `OVERTURNED` /
  `SETTLED-BY-REVIEW` (adjudication resolved in documented review rather than a separate
  verification pass) / `NOT QUEUED (low load)`.

### 3.3 Explicitly deferred (the no-cathedral clause)

CI-checkable memo-template compliance (a linter for R3 blocks and ledger rows), automated
manifest generation helpers, and any evidence-database tooling are **FUTURE niceties — not
now**. The program must prove its value on the queue in §2 with zero new tooling beyond the
JSON convention and one markdown file. Revisit only after the P0/P1 queue items resolve.

---

## 4. Scope discipline — what S-REL does NOT do

1. **No re-litigating verdicts without new evidence.** The audit RECOMPUTES load-bearing
   numbers from committed inputs; it does not re-argue judgment calls, thresholds, or frozen
   specs. Disagreement with a frozen gate's *level* is a design conversation under R4's
   reopening rules, never an audit finding.
2. **No verification-of-verifications regress.** One adversarial pass suffices. Only an
   OVERTURNED outcome gets a second look, and that look reviews the correction. UPHELD is
   terminal; WEAKENED is terminal with an amended boundary.
3. **Positive controls: new harnesses + the retrospective queue only.** No mass retrofit of
   merged low-load NULLs (V7 stays un-dispatched absent a reopening trigger).
4. **No production surface.** S-REL changes no config, no gate, no pipeline behavior — docs,
   research scripts, and evidence conventions only. Anything a verification OVERTURNS routes
   through the normal design-via-PR path for consequences.
5. **No blocking the NOW lane.** Verification runs parallel to N1/N2/N3 data accrual and the
   SHORT engineering tier; a PROVISIONAL tag defers *irreversible* consumption only (§1.1).
6. **No absolute-IC re-adjudication.** The ~+0.04 embargo-leakage floor and the
   differences-only house rule stand; a verifier reproducing absolute ICs is reproducing the
   floor, not validating alpha.

---

## 5. Acceptance criteria (for S-REL itself, honest and checkable)

- **AC1**: `VERDICTS.md` merged and seeded; the next master-plan dated addendum references
  S-REL and the ledger.
- **AC2**: V1 (S9) and V2 (M8) verification memos recorded with an
  UPHELD/WEAKENED/OVERTURNED outcome within the SHORT tier; ledger rows updated.
- **AC3**: V3 (M3) and V5 (#162) verifications dispatched with frozen verification briefs
  (this doc's load-bearing-number lists ARE those briefs); V4 reconciliation memo recorded;
  V6 step-1 durability PR opened.
- **AC4**: every NEW negative-result harness merged after this design carries a committed,
  passing positive control — enforced at PR review (checkable in the diff: the fixture test
  exists and asserts detection).
- **AC5**: every NEW verdict memo carries the R3 evidence-boundary block and an R4 reopening
  condition — enforced at PR review.
- **Program failure mode, stated**: if the P0/P1 verifications all return UPHELD with zero
  WEAKENED findings, S-REL's marginal value was low and the program shrinks to rules R1–R4 at
  PR-review time (no standing audit activity) — that outcome is recorded, not hidden.
