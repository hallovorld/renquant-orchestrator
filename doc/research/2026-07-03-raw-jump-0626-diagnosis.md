# The 2026-06-26 raw-score jump: a silent scorer rollback, not the feed rebuild

S-REL follow-up to V5 (`doc/research/2026-07-03-v5-m4-verification.md`, check 5),
which found the live panel scorer's raw-score cross-sectional median jumped
from −0.297 to −0.047 (+0.25) between the 2026-06-25 and 2026-06-26 daily runs
and flagged root cause as out of scope. Mandate here: attribute the jump from
prod-persisted evidence. All inputs read-only; no git anywhere near the live
tree; evidence pinned by content hash in
`doc/research/evidence/2026-07-03-raw-jump-0626/diagnosis.json`
(tool: `scripts/diagnose_raw_jump_0626.py`).

## Verdict

**The jump is a prod model swap, not input sensitivity.** Between the 06-25 and
06-26 daily runs the prod panel artifact
(`backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`)
silently reverted from the **2026-06-21-trained** XGB (booster `a9b1a075…`,
oos_mean_ic 0.0533 — the model the operator re-promoted on 06-22) to the
**2026-05-18-trained** XGB (booster `a6f5a22f…`, oos_mean_ic 0.0447 — the
pre-promotion prod model). The mechanism is the **2026-06-25 live-tree
recovery** (`git checkout -B main origin/main` after the sub-agent
`git reset --hard` near-miss): the 06-22 promotion lived only in the working
tree (promote flow is uncommitted by design), the committed blob at
origin/main is the 05-18 model, so the recovery checkout restored it. The
revert WAS noticed at the time but misread as a stale config-fingerprint
stamp; the fingerprint was re-stamped over the wrong (05-18) booster, a
readonly daily-full then passed P-CONFIG-FP, and the restamped 05-18 model was
committed as prod "for durability" (#413). Prod has been running the rolled-back
scorer since 06-26.

Two task premises are **refuted** by the run bundles:

1. *"scorer artifact's trained_date unchanged (2026-05-18)"* — false. The 06-25
   run's bundle stamps `panel_contract.trained_date = 2026-06-21`
   (panel sha256 `04d7a381…`); the 06-26 run stamps `2026-05-18`
   (`5ce63326…`). V5 read the trained_date off the *current* file only.
2. *"the jump coincides with the fund-freshness feed rebuild"* — false on
   timing. The #26 serving-axis fix deployed and the feed rebuilt on
   **2026-06-29** (feed axis 2026-03-31 → 2026-06-26), three sessions *after*
   the jump. Measured across that rebuild (same model, 06-26 → 06-29 runs) the
   raw cross-section moved **+0.007 mean / 0.077 std / Spearman 0.88** — an
   order of magnitude smaller than the boundary and barely above weekend
   feature drift.

## 1. The jump, precisely

Per-run cross-sectional stats of `raw_panel` (candidates only, prod
`score_distribution`, DB `mode=ro`):

| run | n | median | mean | panel artifact (bundle) | trained |
|---|---|---|---|---|---|
| 2026-06-22-live-c26c0042 | 81 | −0.293 | −0.222 | `04d7a381…` | 2026-06-21 |
| 2026-06-24-live-710e3805 | 73 | −0.282 | −0.235 | `04d7a381…` | 2026-06-21 |
| 2026-06-25-live-6c3aa3fa | 76 | **−0.297** | −0.241 | `04d7a381…` | 2026-06-21 |
| 2026-06-26-live-3d74ce5c | 79 | **−0.047** | −0.057 | `5ce63326…` | 2026-05-18 |
| 2026-06-30-live-b616357c | 83 | −0.046 | −0.075 | `5ce63326…` | 2026-05-18 |
| 2026-07-02-live-85496d1c | 83 | −0.036 | −0.067 | `5ce63326…` | 2026-05-18 |

Boundary Δmedian = **+0.250**, exactly at the run whose bundle swaps the panel
sha. The 06-25 run (created 21:07 UTC = the 14:06 local daily-full) still ran
the 06-21 model; the incident + recovery happened after it; the next daily run
picked up the reverted file.

## 2. Attribution — the artifact swap, with alternates ruled out

**Artifact archaeology (booster content hashes, not file hashes).** Hashing
`booster_raw_json` across all prod/staging/rollback copies collapses the file
zoo into exactly **two** models: every 06-22/06-23 promote-window copy carries
booster `a9b1a075…` (trained 06-21), and prod-now, prod-pre-06-22, and every
weekly_rollback backup from 06-27 on carry booster `a6f5a22f…` (trained 05-18).
File-sha differences within a family are fingerprint re-stamps only. No weekly
promote attempt exists between 06-23 and 06-27 (no staging/rollback files) —
the 06-25/26 swap happened **outside the promote mechanism**.

**Mechanism.** The committed blob for the prod artifact at the umbrella
origin/main is sha256 `5a1e4e14…`, trained_date 2026-05-18 (fetched via the
GitHub API — `gh api repos/hallovorld/RenQuant/contents/...` — never local git;
last commit touching the path: 2026-05-30). `git checkout -B main origin/main`
on 06-25 therefore reverts the working-tree artifact to the 05-18 model. The
06-25 incident memory records the gotcha in real time: the checkout "also
reverted the prod XGB artifact fingerprint (…f8fb2259→stale 14586756)" — read
then as a stamp revert, fixed by re-stamping the fingerprint and committing.
The booster underneath had reverted too; `trained_date: 2026-05-18` on disk
looked normal because the model "was old anyway". The run bundles' umbrella
`commit_sha` flips b2f511e → a4f2c79 at the same boundary — the checkout
moving HEAD.

**Alternates ruled out** (all from the two boundary bundles):

- *Watchlist*: identical hash `cc388cb8…`, size 145, both runs.
- *OHLCV/price plane*: `data_max_dates` advance exactly one session
  (06-25 → 06-26) for all 145 symbols; same-model day-over-day control pairs
  bound normal price-drift at Δmedian ≈ ±0.004, per-ticker Δ std 0.035–0.039,
  Spearman 0.965–0.976.
- *Fundamentals feed*: unchanged at the boundary — the serving feed was still
  the stale (as-of 2026-03-31) feed on BOTH sides; the #26 rebuild landed 06-29
  (measured effect above).
- *Calibrator*: also swapped at the boundary (`b9925b7c…` → `9edfa148…`, the
  06-05-era calibrator — same checkout, same reason) but cannot affect
  `raw_panel`, which is upstream of it. V5's ≤0.0035 vintage-drift bound covers
  the μ side.
- *Code/config*: pipeline runtime assembles from `.subrepo_runtime`, which the
  reset/recovery never touched (pins 42d6205/a15a64b before and after);
  `config_hash` churns run-to-run all month (daily-varying content) and is not
  boundary-specific.

## 3. Sensitivity decomposition

Per-ticker Δraw across run pairs (all scored rows, common tickers):

| pair | what it isolates | Δ mean | Δ std | Spearman |
|---|---|---|---|---|
| 06-24 → 06-25 | same model A, 1 day of data | −0.002 | 0.039 | 0.976 |
| **06-25 → 06-26** | **model swap A→B (+1 day of data)** | **+0.158** | **0.219** | **0.185** |
| 06-26 → 06-29 | same model B, weekend + **fund-feed rebuild (#26)** | +0.007 | 0.077 | 0.880 |
| 06-26 → 06-30 | same model B, 2 sessions + feed rebuild | +0.009 | 0.091 | 0.822 |
| 06-30 → 07-01 | same model B, 1 day of data | −0.001 | 0.035 | 0.965 |

The boundary is not a level shift with ranks preserved: rank correlation
collapses to 0.185 (day-over-day norm ≥0.96). ~20 of 80 names moved *down*
while the median moved up 0.25. This is a different model, not a shifted one.

**Two-model, identical-rows test.** Scoring the same feature rows (last 15
dates of the prebuilt alpha158+fund panel, 292 tickers) under both boosters:
the models disagree in level (per-row A−B = +0.133 ± 0.124) and in ranking
(mean cross-sectional Spearman 0.765). Note the offline level offset has the
*opposite sign* to the live one (+0.25 toward B live, +0.13 toward A on the
prebuilt panel): the live path z-scores every feature with the artifact's own
training-window means/stds (`transform_feature_frame(source_space="raw")`),
while the prebuilt panel path does not — the raw-score *level* depends on the
normalization vintage as much as on the booster. That is the general lesson:
**`rank:pairwise` LTR raw scores are only rank-identified; the cross-sectional
level is an arbitrary byproduct of training window + normalization constants
and can move by O(0.1–0.3) on ANY retrain/rollback with no input change at
all.**

**Why an 88-day fundamentals refresh moved raw by only ~0.01:** despite the
booster assigning ~61–65% of total split gain to the 13 fundamental/event/
sentiment features, those features are slow-moving (quarterly filings,
`book_to_price` drift); un-freezing them re-ranks moderately (Spearman 0.88 vs
0.97 baseline) but shifts the center almost not at all. Score-anchored
consumers survive feed rebuilds fine; they do not survive scorer-identity
changes.

## 4. Implications

**(i) Which regime is the anomaly?** Not the one the question assumed. Both
raw regimes ran the SAME stale fundamentals until 06-29, so neither is a
"fundamentals-freshness" regime; they are **model identities**. In governance
terms the *post*-06-26 state is the anomaly: an operator promotion (06-22,
fresh 06-21 model, higher oos_ic) was silently undone by incident recovery,
and prod has since run a model trained 2026-05-18 — **45 days old at 07-02,
violating the 2026-06-30 model-freshness directive (28-day cap)** — with its
identity additionally laundered by the fingerprint re-stamp + durability
commit. The 06-21 model's exact promoted bytes still exist on disk
(`…weekly_rollback_2026-06-23.json`, sha256 `04d7a381…`).

For M4/M4-b (pipeline PR #162), this *reframes but does not weaken* the
verified finding: the +2% intercept is real on 06-26+, but it is a
**scorer/calibrator pairing artifact** — the live calibrator's ER curve is
anchored at neutral_raw ≈ −0.290, i.e. at the 06-21 model's cross-section
center (V5's "anchor-adjacent" days 06-24/25 are exactly the days that model
was live), while the scorer producing today's raw scores is the rolled-back
05-18 model centered at −0.05. Every μ, the 0.03 floor geometry, and the 44/45
sign-laundering counts are currently computed through a transfer curve fit to
a different scorer's scale. Consequences: (a) M4-b's per-bar recentering is
the right *shape* of fix precisely because it removes sensitivity to this
class of event; (b) the "current drifted regime" evidence window is not a
market regime — it can end abruptly whenever the scorer/calibrator pairing is
next touched (re-promotion of the 06-21 model would put the floor back to a
near-no-op); (c) any re-fit of the calibrator should be explicitly bound to
the booster content hash it was fit against.

**(ii) Monitoring.** A raw-distribution drift alarm **exists and fired**:
`score_drift_audits` (PSI vs a ~1,600-row baseline, pipeline
`kernel/score_audit.py`) jumped 0.46 → 2.66 at the boundary, and the alert
lifecycle minted a fresh incident (`CRITICAL:psi~2.7`, first_seen 06-26,
1 notification). It carried no signal because the monitor is **saturated**:
every one of its 247 rows since birth (06-22) is CRITICAL, and PSI-bucket
cause-hashing minted 8 near-identical incidents in 10 days, so a genuine
scorer-identity event was indistinguishable from daily wobble. The gap is not
a missing alarm but baseline/identity management: the PSI baseline is not
re-anchored per scorer vintage, and no check compares the **booster content
hash** (or `panel_contract.trained_date`) of consecutive runs — a one-line
"prod scorer identity changed without a promote event" alarm would have
caught both the 06-22 promotion and the 06-26 silent revert, with zero false
positives. (Also note V5 finding #1 pattern repeats: identity fields exist in
bundles but nothing diffs them run-over-run.)

**(iii) No design changes here.** Findings fed to M4-b (pipeline PR #162) as a
comment; the freshness-policy violation and the recoverable 06-21 artifact are
flagged to the operator via this memo. Restoring the 06-21 model, re-pairing
the calibrator, or re-anchoring the PSI baseline are separate,
operator-visible actions with their own gates — deliberately not done here.

## 5. Reproduce

```bash
/Users/renhao/git/github/RenQuant/.venv/bin/python \
  scripts/diagnose_raw_jump_0626.py \
  --json-out doc/research/evidence/2026-07-03-raw-jump-0626/diagnosis.json
```

Everything except the committed-blob check (GitHub API, §2) is offline and
read-only. Input identities are pinned in the evidence JSON: runs DB sha256
`0630ffb5…` (byte-identical to the DB V5 verified), artifact A `04d7a381…`,
artifact B `5ce63326…`, the 792 MB panel parquet `f89c1738…`, and the
script's own sha256.
