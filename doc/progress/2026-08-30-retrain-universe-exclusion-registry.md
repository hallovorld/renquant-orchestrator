# Retrain universe exclusions are explicit and reviewed: a committed registry removes AVB/IAC from the universe AND the panel build; a stale name outside it still vetoes, and the veto says what to do   (PR #1096, r2)

STATUS:    delivered (code + registry + tests; NOT deployed — the orchestrator pin
           advance / `-run` sync is the deploy step, see "Deploy"). Revision 2:
           the r1 heuristic ("stale AND not served ⇒ presumed delisted ⇒ skip")
           is REMOVED per the codex BLOCKER; nothing is skipped by inference.
WHAT:      (1) `config/retrain_universe_exclusions.json` — a reviewed registry
           (kind/schema_version + one entry per ticker: `reason` ∈ {delisted,
           merged, symbol_change, data_outage_confirmed}, ISO `effective_date`,
           http(s) `evidence_url`, `added_by_pr`, optional `notes`), seeded with
           IAC and AVB. (2) `retrain_alpha158_fund.py` loads it FAIL-CLOSED
           (`load_exclusion_registry`: absent / invalid ⇒ `ExclusionRegistryError`,
           run refuses), removes its names in `_resolve_panel_universe` (unioned
           with the inventory's delisted keys and `--exclude-tickers`) — so they
           are skipped by the OHLCV refresh and the guard — and the guard writes
           an EFFECTIVE inventory (`_write_effective_inventory`: the inventory
           copied with excluded names removed from BOTH tier lists,
           `delisted_tickers` + an `effective_universe` provenance block naming
           each excluded ticker and its reason) that `BuildAlpha158PanelTask`
           hands base-data's panel build via `--inventory`; a real run without
           that file is REFUSED. (3) The strict rule is unchanged for every name
           that remains; the PANEL-FREEZE veto now names each stale ticker with
           its lag AND last bar and ends with the remedy: add a REVIEWED entry to
           `config/retrain_universe_exclusions.json` (path of the registry in
           use) with evidence, or fix ingestion. (4) An informational ntfy
           `STALE-NON-WATCHLIST` alert names stale non-served names + the
           registry path (labels only; never changes the verdict). (5) The
           persisted freshness report (dated + latest) stays and now lists
           `excluded_names` / `registry_excluded` (with reasons) / `cli_excluded`
           / `stale_detail` / `stale_not_served` / `effective_inventory` /
           `remedy`. (6) `--exclusion-registry` CLI override; the r1 flags
           `--presumed-delisted-after-sessions`, `--presumed-delisted-max-fraction`,
           `--served-watchlist-file` are gone.
WHY/DIR:   codex on r1 (verbatim): "`not in the served watchlist` plus more than
           three missing exchange sessions is not sufficient evidence that a
           symbol is delisted … the 2% cap only catches mass outages … the
           presumed-delisted name remains in the panel build with stale
           historical rows … Use an authoritative delisting/corporate-action
           signal, or require an explicit reviewed inventory/exclusion entry, and
           ensure excluded names are removed from the actual panel universe."
           r2 does the second thing exactly: an exclusion exists only as a
           reviewed, evidenced, PR-attributed registry entry, and it reaches the
           panel build. The trigger is unchanged: the 2026-08-29/30 weekly promote
           failed `PANEL-FREEZE 1/293 stale … Worst: AVB(-4s)` (AVB: Equity
           Residential merger closed 2026-08-17, last bar 2026-08-24, in tier_A of
           an inventory with no `delisted_tickers` channel, not served) — the IAC
           pattern from July. Boundary, stated honestly: base-data's
           `alpha158_qlib_panel.LoadUniverseJob` re-reads tier_A/tier_B from the
           inventory file it is given, has no exclude argument and ignores
           `delisted_tickers`; the orchestrator therefore passes a FILTERED COPY
           (`--inventory`, an existing base-data CLI flag) written next to the
           freshness report — never into `data/`. Regenerating the inventory
           (base-data) remains the versioned fix; the registry is the reviewed
           bridge until then and the shipped IAC entry is honest about its
           evidence (`data_outage_confirmed`: a vendor outage confirmed across
           three months, no corporate-action record located).
EVIDENCE:  see §4(b) below; full `make test` on this branch: 6 failed / 7099
           passed / 10 skipped — the SAME 6 pre-existing failures as clean
           `origin/main` (6 failed / 7066 passed / 10 skipped, r1 baseline at
           b76a5b25; +33 = the new tests net of the removed r1 tests and of
           origin/main's advance to 06ceb310): `test_cli::test_parking_sleeve_cli_
           computes_allocation`, 2× `test_g2v3_stage_i2_binding`,
           `test_goal3_public_export_resolution`, 2× `test_shadow_serving_skips_
           leave_evidence` — all read paths/records on the operator's disk
           `[VERIFIED — scratchpad r2_branch_test.log, umbrella venv + absolute
           sibling src, 2026-08-30]`.
NEXT:      codex re-review → merge → orchestrator pin advance + `-run` sync
           (operator landing action). Until then the live promote still vetoes on
           AVB: the interim bridge is umbrella PR #625 (`RETRAIN_EXCLUDE_TICKERS`
           default `IAC,AVB`), to be dropped in the batch that pins this. A future
           delisting = one reviewed registry PR (the veto text says so).

## Bottom line

- `[VERIFIED — logs/daily_retrain_alpha158_fund/2026-08-30.log, read-only grep]`
  `$AVB: possibly delisted; no price data found (1d 2026-08-25 -> 2026-08-30)`
  … `returning stale cache (last=2026-08-24)` … `freshness guard TRIPPED: 1/293
  panel tickers stale (0.3% > 0.0%; missing=0 future=0); bars lag expected NYSE
  session 2026-08-28 by >1 sessions. Worst: AVB(-4s). FAILING retrain.`
- AVB is in `tier_A_tickers` (nA=258, nB=36, inventory generated 2026-05-05;
  keys carry no `delisted_tickers`) and NOT in the served watchlist (n=145)
  `[VERIFIED — python json read of the umbrella inventory and
  renquant-strategy-104/configs/strategy_config.json, 2026-08-30]`.
- IAC: bars ceased 2026-05-12; vendor "possibly delisted; no price data found"
  on 2026-07-09 and 2026-07-17; bridged since by the umbrella's
  `RETRAIN_EXCLUDE_TICKERS=IAC` `[VERIFIED — prior work,
  doc/progress/2026-07-09-retrain-delisted-ticker-resilience.md and umbrella
  doc/progress/2026-07-17-retrain-exclude-iac.md]`.
- Delisting evidence for AVB: SEC 8-K / Form 25,
  https://www.sec.gov/Archives/edgar/data/0000915912/000110465926097833/tm2623381d1_8k.htm
  `[VERIFIED — prior work, the r1 investigation]`.

## r1 → r2 (what changed and why)

| r1 (rejected) | r2 |
|---|---|
| stale >3 sessions AND not served ⇒ `presumed_delisted`, excluded from the freshness accounting, run proceeds | REMOVED. No inference. A name leaves the universe only through a reviewed registry entry (or the inventory's own delisted keys / the `--exclude-tickers` bridge). |
| 2% mass-outage cap | REMOVED (nothing to cap). |
| excluded only from freshness accounting; panel still built on the raw inventory | excluded from the refresh, the guard AND the panel build (effective inventory via `--inventory`); a real run without it is refused. |
| stale served name vetoes; stale non-served name skipped | every stale name vetoes; the veto names ticker / lag / last bar and the remedy. |
| `PRESUMED-DELISTED` alert | `STALE-NON-WATCHLIST` informational alert naming the registry path; verdict unchanged. |
| served watchlist gates the skip | served watchlist only labels the alert; unavailable ⇒ the label is skipped (WARNING) and the strict verdict covers every name. |
| `--presumed-delisted-*`, `--served-watchlist-file` | gone; `--exclusion-registry` added. |

## What changed (files)

- `config/retrain_universe_exclusions.json` (NEW, committed): the registry.
  IAC (`data_outage_confirmed`, 2026-05-12, evidence = the umbrella July record)
  and AVB (`merged`, 2026-08-17, evidence = the SEC filing), both
  `added_by_pr: hallovorld/renquant-orchestrator#1096`.
- `src/renquant_orchestrator/retrain_alpha158_fund.py`:
  `DEFAULT_EXCLUSION_REGISTRY_PATH` (= `<orchestrator>/config/…`, resolved from
  the module's own location, a source checkout as `runtime_paths` already
  assumes), `EXCLUSION_REASONS`, `ExclusionRegistryError`, `UniverseExclusion`,
  `_validate_exclusion_entry`, `load_exclusion_registry` (strict schema:
  kind, schema_version, required keys, no unknown keys, reason enum, ISO date,
  http(s) evidence, duplicates rejected; empty list valid),
  `_resolve_panel_universe` (registry applied in BOTH the inventory and the
  explicit-list branch; provenance gains `registry_excluded` with reasons,
  `inventory_delisted_excluded`, `exclusion_registry`), `_write_effective_inventory`
  (+ `_atomic_write_json`, `_freshness_report_dir`), `_stale_remedy`,
  `_resolve_served_watchlist` (labels only), `PanelUniverseFreshnessGuardTask`
  (effective inventory written before the verdict; report + alert + veto text
  as above), `BuildAlpha158PanelTask` (`--inventory`; refuses a real run
  without it), CLI. Explicit `--panel-universe-file <list>` now also drives the
  panel build (previously only refresh + guard) — the effective inventory is
  the list; recorded here as a deliberate behaviour change.
- `tests/test_retrain_ohlcv_coverage.py`: r1 section replaced; `_ctx` pins an
  EMPTY tmp registry (the committed one really lists IAC/AVB) and an empty
  served watchlist so no guard test measures the operator's disk.
- `doc/memory/mid-term/serving-reliability.md`: addendum rewritten for r2.

## §4(b) evidence

- Registry validation tests: valid entries parse (records, fingerprint, n);
  empty valid; ticker uppercased; unknown reason rejected; missing / empty /
  non-http evidence rejected; bad date, bad symbol, empty `added_by_pr`, unknown
  key, non-string notes, non-object entry rejected; duplicate ticker rejected;
  wrong kind / schema_version / non-list rejected; absent / corrupt / non-object
  file fails closed; the COMMITTED registry parses and lists IAC + AVB with the
  expected reasons, dates and SEC URL.
- AVB in the registry ⇒ removed from the universe (n_universe 3 of 4 declared),
  never stale, no alert, run proceeds; the effective inventory on disk has
  `tier_A == [AAPL, MSFT]`, `tier_B == [XYZ]`, `delisted_tickers == [AVB]`,
  reason in `effective_universe`, every other inventory key preserved; the
  panel build command ends `--inventory <that file>`; the refresh skips AVB.
- Panel build refuses a real run without the effective inventory; dry-run
  previews the plain command.
- Stale name NOT in the registry ⇒ RuntimeError whose text contains
  `AVB(-4s, last 2026-06-26)`, `add a REVIEWED entry to
  config/retrain_universe_exclusions.json`, the registry path in use, `otherwise
  fix ingestion`; alerts = `STALE-NON-WATCHLIST` (names the registry, "NOT
  excluded") then `PANEL-FREEZE`; report carries `stale_detail`,
  `stale_not_served`, `remedy`, persisted on disk. Stale SERVED name ⇒ only
  `PANEL-FREEZE`. Watchlist unavailable ⇒ label skipped, still vetoes with the
  remedy. Watchlist read from the strategy config (served stale name not
  labelled).
- IAC + AVB excluded via the COMMITTED registry with no `--exclude-tickers`;
  registry ∪ `--exclude-tickers` ∪ inventory `delisted_tickers` (each source
  reported on its own, a name in two sources excluded once, union in the
  effective `delisted_tickers`); registry applies to an explicit universe (all
  names excluded ⇒ fail-closed); invalid registry fails closed in the guard AND
  the refresh; report persisted dated + latest (also on a veto), `--freshness-
  report-out` as `.json` / directory; non-default registry path recorded as an
  override; CLI: `--exclusion-registry` parses, the three r1 flags are rejected.
- Targeted run: `tests/test_retrain_ohlcv_coverage.py tests/test_retrain_alpha158_fund.py
  tests/test_retrain_alpha158_linear.py tests/test_market_calendar_repoint.py
  tests/test_retrain_sigma_head_rawlabel.py tests/test_scheduled_jobs.py` ⇒
  **180 passed** `[VERIFIED — pytest, umbrella venv, 2026-08-30]`.
- Full `make test`: see EVIDENCE above. `ruff check` on the two changed
  Python files reports the SAME 2 pre-existing unused-import findings as
  `origin/main` (`functools`, `model_content_sha256_from_path`); none
  introduced `[VERIFIED — ruff on both versions, 2026-08-30]`.

## Deploy

- Nothing here touches a live path. The registry is read from the orchestrator
  checkout that runs the retrainer (`-run`), so the deploy step is the
  orchestrator pin advance + `-run` sync (operator landing action). Until then
  the live weekly promote still vetoes on AVB; the interim bridge is umbrella
  PR #625 (`RETRAIN_EXCLUDE_TICKERS` default `IAC,AVB` — freshness accounting
  only, as codex noted). Drop that default in the batch that pins this.
- `weekly_wf_promote.sh` needs no other change: the registry is the default and
  `--exclude-tickers` keeps unioning.

## Memory tier

MID `doc/memory/mid-term/serving-reliability.md`: the 2026-08-30 defect #6
addendum rewritten for r2 (registry, not heuristic; panel build included).
