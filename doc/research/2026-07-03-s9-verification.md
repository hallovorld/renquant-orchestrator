# S9 verification — independent adversarial recomputation of the Track A NULL

STATUS: verification evidence (read-only), ADVERSARIAL INDEPENDENT RE-COMPUTATION.
Target under review: PR #262 (`doc/research/2026-07-03-s9-track-a-conditional.md`
+ `scripts/s9_track_a_conditional.py` + evidence JSONs). The mandate was to try
to OVERTURN the NULL — find an implementation bug, spec deviation, or fragile
choice that flips NULL → GO. Their script was NOT rerun; every load-bearing
number was recomputed with independent code from the same primary inputs.
DATE: 2026-07-03
SCRIPT: `scripts/s9_independent_verification.py` (own join with duplicate-validated
`m:1` merge; own IRLS logistic instead of sklearn; C3 recomputed directly from
within-date score medians, not via the S9 margin construction; own bootstrap,
different seed, 4,000 resamples; plus fragility variants).
EVIDENCE: `doc/research/evidence/2026-07-03-s9-verification/verification.json`.

## Verdict on the verdict

**UPHELD.** Every load-bearing number reproduces exactly (deterministic
quantities) or within Monte-Carlo noise (bootstrap CIs). The one material
deviation from the literal §4 text — the raw-unit label substitution — is
disclosed prominently in their memo, is required for spec coherence, and was
independently re-proven here (including a semantics check their script never
did). Three adversarial fragility variants (floor split, strict-median C3,
literal standardized-units label) all leave the verdict NULL. The binding kill
on the only (a)–(d)-passing candidate (C3, gate (e) at 42.9% winners dropped)
is not a tolerance-level miss: passing would require a conditioned hit-rate of
66.5% vs the actual 57.0%.

## Reproduction table (theirs vs mine)

Deterministic quantities are exact matches unless noted. Bootstrap CIs use an
independent RNG (seed 71, 4,000 resamples vs their 20260703/2,000), so CI
endpoints carry MC noise; all gate decisions agree.

| # | Quantity | Theirs (#262) | Mine (independent) | Match |
|---|---|---|---|---|
| 1 | Top-decile rows | 15,109 | 15,109 | exact |
| 1 | Table label per-date mean / std | ≈0 / ≈1 | max abs mean 6.5e-17 / max std dev-from-1 8.9e-12 | confirmed standardized |
| 1 | Raw-label join: missing / max z-diff | 0 / 0.0 | 0 / 0.0; **plus** 0 duplicate (date,ticker) panel keys, `m:1`-validated, row count stable, 0 NaN raw labels in the whole 715,629-row panel | exact, no silent inflation/deflation |
| 1 | Raw-label semantics (new check) | asserted "return units" | **proven**: label − own 60-trading-session fwd return (from `data/ohlcv/<T>/1d.parquet`) is a per-date constant, residual spread **0.0** across 72 probes on 6 dates | 60-session horizon + return units + common per-date benchmark confirmed |
| 2 | Split | 305 / 60 / 143 dates; train 2024-02-02→2025-04-22; embargo 2025-04-23→2025-07-18; test 2025-07-21→2026-02-11 | identical | exact |
| 2 | Embargo leak | claimed none | last train label window ends **2025-07-18** < test start **2025-07-21**; 1 session of slack; pick grid verified daily-trading (max gap 4 calendar days) | no leak (tight but clean) |
| 3 | C3 test book lift (gate a) | +1158.3 bps/yr [+631.7, +1713.0] | **+1158.3** [+598.0, +1698.9] | point exact; CI within MC noise; gate (a) ✓ both |
| 3 | C3 test per-pick lift (b) | +550.4 bps [+300.8, +814.3] | +550.4 [+284.7, +805.8] | point exact |
| 3 | C3 test hit lift (c) | +6.99 pp [+3.41, +10.47] | +6.99 pp [+3.37, +10.44] | point exact |
| 3 | **C3 winners dropped (e — the kill)** | **42.9% (891/2,078)** | **42.88% (891/2,078)** | **exact** |
| 3 | C3 turnover multiple (e2) | 0.54× | 0.5399× | exact |
| 3 | C3 train hit lift ("not selectable ex ante") | −0.30 pp | −0.30 pp [−2.52, +1.91] | exact |
| 3 | C3 train book lift | +103 bps/yr [−141, +358] | +103.0 [−138, +359] | exact |
| 4 | Test-window BEAR dates (C2/(d)) | 1 (30 picks) | 1 (30 picks); regime verified constant within date | exact |
| 4 | C2 test active exposure / winner drop | 0.7% / 99.2% | 0.70% / 99.18% (2,061/2,078) | exact |
| 5 | C1 τ (train-median P) | 0.5107 | 0.51066 (own IRLS, not sklearn) | match across optimizers |
| 5 | C1 test book lift | −635.6 bps/yr [−1351.9, +63.6] | −637.6 [−1315.8, +87.5] | ~2-pick mask diff near τ (2,356 vs 2,358 kept); all C1 gate decisions identical |
| 5 | C1 test winner drop | 44.0% (915) | 44.08% (916) | 1-pick optimizer diff, immaterial |
| — | C2 whitelist + train regime hit-rates | {BEAR}; BEAR 0.6895 / BULL_CALM 0.5024 / CHOPPY 0.4889 / BULL_VOLATILE 0.4485 | identical | exact |
| — | Substrate transport hash | `0cdadd9e34e164fe…` | independent `shasum -a 256` = `0cdadd9e34e164fe…` = sidecar `output_parquet_sha256`; counts 508/292/147,066 | exact |
| — | Verdict | NULL | **NULL** | UPHELD |

## Check 1 — units + join (attempted overturn: silent y-label corruption)

Recomputed from scratch, own merge path. The table's `fwd_60d_excess` is
per-date standardized (max per-date |mean| 6.5e-17, max |std−1| 8.9e-12), so
§4's bps-denominated gates are non-evaluable on it — their raw-unit
substitution is *necessary*, not cosmetic. The join has no failure mode left
to hide in: the rawlabel panel has **zero** duplicate (date, ticker) keys
(no silent row inflation), **zero** NaN `fwd_60d_excess_raw` anywhere in the
panel (no silent y=0 coercion via `NaN > 0.0011 → False`), all 15,109 picks
joined, and the panel's standardized column reproduces the table's with max
|Δ| = 0.0 — same construction, provably.

New check their script never did: for 72 probed (date, name) picks across 6
random dates, `fwd_60d_excess_raw` minus the name's own 60-trading-session
forward close-to-close return (recomputed from the durable bars panel) is a
per-date constant with spread **exactly 0.0** — the label is a 60-session
forward return in return units net of a common per-date benchmark. The 11 bps
threshold and the bps gates are therefore denominated correctly. **No
overturn.**

## Check 2 — split + embargo (attempted overturn: off-by-one / leakage)

Recomputed from the table's own dates: 508 total; `round(0.6·508)` = 305 train
(2024-02-02 → 2025-04-22), 60 embargo (2025-04-23 → 2025-07-18), 143 test
(2025-07-21 → 2026-02-11); 305+60+143 = 508, no date lost or double-counted;
matches §4's "≈2025-08 → 2026-02" test window. The pick grid is verified to be
consecutive trading days (max calendar gap 4 days), so 60 grid dates = 60
trading days = the label horizon. Leak test on the panel's own grid: the last
train date's label window ends 2025-07-18, one session before test start —
**no overlap between any train label window and the test window**, with
exactly 1 session of slack.

Off-by-one variant (floor: train = 304, test = 144 starting 2025-07-18):
recomputed in full — C3 winner drop 42.89%, identical gate pattern, C2 active
0.69%. **No overturn.**

## Check 3 — criterion (a) and the binding (e) kill on C3

Gate (a): my independent bootstrap reproduces +1158.3 bps/yr point-exactly and
the CI within MC noise (LB +598.0 vs their +631.7 — both decisively > 0). Gate
(a) genuinely passes for C3; their memo says so too.

Gate (e) — the kill the verdict hangs on: recomputed via within-date score
medians (mathematically equivalent to their margin construction because the
decile cutoff is a per-date constant — equivalence relied on, path
independent): conditioned set 2,084 picks, kept winners 1,187, dropped **891
of 2,078 = 42.88%**, exactly their number. Kill distance: passing (e) needs
dropped ≤ 692, i.e. kept ≥ 1,386, i.e. a conditioned hit-rate ≥ 66.5% vs the
actual 57.0% — a 9.5 pp shortfall at fixed retention. Adversarial variants:
strict `>` median → 43.07% (worse); floor split → 42.89%; literal
standardized-units label → 42.50%. Every path stays above the 1/3 cap. **No
overturn.** Their two disclosed non-rescue arguments also reproduce: C3's
train hit lift is −0.30 pp (sign-unstable across train/test) and the
champion-by-train protocol selects C1, not C3.

## Check 4 — (d) on C2: one BEAR test date; is (d) evaluable?

Recomputed from the table's regime column (verified constant within date):
the 143-date test window has exactly **1** BEAR date carrying 30 picks →
active exposure 0.70% vs the 25% floor. On spec-faithfulness: §4's (d) is a
mechanical count of active test dates — it **is evaluable** on this window,
and the spec itself pre-registered both the chronological split and the
thin-slice warning ("report per-regime cell counts so thin slices … are
visible and not over-read"). There is no §4 provision to extend, re-weight, or
backfill the window when a regime fails to occur; arguing that C2 "would work
in the next BEAR" is a re-design, which §4's STOP clause explicitly forecloses
("we do not then go fishing"). C2's (d) FAIL is spec-faithful. **No
overturn.**

## Check 5 — frozen-spec faithfulness diff (implemented vs literal §4)

| Item | Literal §4 | Implemented | Disclosed? | Verdict-relevant? |
|---|---|---|---|---|
| Label | "realized `fwd_60d_excess` > 0 net of 11 bps" on the regenerated table | `fwd_60d_excess_raw > 0.0011` joined from the rawlabel panel | YES (memo, prominent) | Required for coherence: table column is standardized; §4 itself names the rawlabel panel as the label input and denominates every gate in return units. Literal-z variant checked: C3 (e) still fails (42.5%) and (a)/(b) become non-evaluable. NO flip |
| "First 60%" | ambiguous 304.8 | `round` → 305 | not stated | floor variant recomputed — identical gates. Immaterial |
| Conditioning candidates | not enumerated (spec defines variables + gates, not candidate rules) | 3 ex-ante-structured candidates; GO iff ANY passes | YES (multiplicity note) | Any-pass is the GENEROUS direction; NULL under it is decision-grade |
| Capital fraction | "active days × names filtered ÷ baseline names" | pick-count ratio n_cond/n_base | YES (formula in JSON) | Equivalent readings; for C2 both give 0.7%. Immaterial |
| Gate (c) "CI excluding 0" | two-sided exclusion | CI lower bound > 0 | code-visible | Equivalent under the ≥ +3 pp point gate. Immaterial |
| Var 4 drop | drop if not PIT-clean, no substitution | dropped | YES | Independently confirmed: `earnings_291.parquet` has NO `acceptedDate` column (columns: symbol/date/eps*/revenue*/lastUpdated/ticker/fetched_at/source). Correct application |
| Var 5 | trailing 60d vol + ADV, PIT-safe | rolling window inclusive of pick-date close; ffill onto pick dates | YES (inclusive noted) | My exact-date (no-ffill) recomputation reproduces C1 to within 2 picks. Immaterial |
| Gate constants | (a) 50 bps/yr, (b) 5 bps, (c) 3 pp, (d) 25%, (e) 1/3 + 2×, cost 11 bps, block 13, embargo 60, ×≈4 | identical, frozen at top of script | YES | Faithfully transcribed |

No undisclosed deviation that could flip the verdict was found.

## Material caveats (verdict stands; these should be on the record)

1. **C2's gate-(c) CI is conditional-on-active.** With one BEAR date in 143,
   ~34% of bootstrap resamples (mine: 1,355/4,000) contain zero conditioned
   picks and are dropped from the CI. The +6.7 pp [+3.1, +9.1] hit-lift CI is
   therefore conditional on the lone BEAR block being drawn — it overstates
   the unconditional evidence for C2's (c) ✓. Not verdict-relevant (C2 fails
   (d) and (e) decisively), but the memo presents the CI without this caveat.
2. **The embargo has exactly one session of slack.** Correct as executed, but
   zero margin: any future variant with a longer label horizon or a shifted
   grid must re-derive it rather than reuse "60 dates is enough".
3. **`round` vs floor on the 60% split is an undisclosed micro-choice** —
   verified immaterial (variant recomputed end-to-end), but frozen-spec
   executions should pin such choices explicitly.
4. **C1's numbers are optimizer-dependent at the margin** (sklearn lbfgs vs
   my IRLS: 2 picks differ near τ; book lift −635.6 vs −637.6 bps/yr). All
   gate decisions identical; C1 fails (a)(b)(c)(e) decisively either way.

## Scope

Same scope limits as the target memo: survivorship-biased 292-name panel,
difference-test reading only. This verification re-establishes internal
correctness and spec fidelity; it does not (and cannot) upgrade the
substrate's external validity.

## Reproduce

```bash
python3 scripts/s9_independent_verification.py \
    --umbrella /Users/renhao/git/github/RenQuant \
    --out-dir doc/research/evidence/2026-07-03-s9-verification
```

All inputs read-only; no git operation anywhere; deterministic (seed 71,
4,000 resamples).
