# A4-T1 orchestrator-owned consumption — v2 (identify → consume → stamp)   (PR #1110)

STATUS:    delivered — v2 of the orchestrator side of RFC#210 A4-T1, paired
           with renquant-backtesting#128 (v13); supersedes orch#1107 (v1).
           This PR's CI is RED until bt#128 merges — by design (see TESTS).
WHAT:      committed authorization record
           `ops/governance/a4t1/20260831T141820Z.authorization.json`;
           `a4t1_governance.promote_candidate(prod, staging, as_of)` as the ONLY
           producer of consumption proofs (identify → `decide()` → atomic
           `O_CREAT|O_EXCL` marker under `<data_root>/logs/weekly_wf_promote/
           a4t1_ledger/` → `stamp()` → marker `stamped: true`); the
           `renquant_orchestrator a4t1-promote` CLI subcommand and the
           `ops/renquant104/a4t1_promote_staged.sh` wrapper; strategy snapshot
           refreshed.
WHY/DIR:   closes the three codex #1107 blockers (no production entry point;
           free-form `consume()` bypassable; host-local `~/.renquant` + red CI).
           Direction: governance state is orchestrator-owned and auditable in
           git plus the backed-up data root; backtesting only identifies the
           candidate and validates the proof it is handed.
EVIDENCE:  `tests/test_a4t1_governance.py` 22 passed + `tests/test_doc_alignment.py`
           2 passed with bt#128 (885d3ce) on the path [VERIFIED — pytest
           2026-09-03 at e966e43c, the last code-touching commit]; full suite in
           the PR worktree 7223 passed / 4 failed / 15 skipped, the 4 being the
           known pre-existing set on main plus one detached-worktree path artifact
           [VERIFIED — prior work, PR #1110 comment 2026-09-03T14:38Z]. No
           model-quality claim is made.
           artifact:      `ops/governance/a4t1/20260831T141820Z.authorization.json` (this PR), binding the live staging artifact `backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.weekly_20260831T141820Z.staging.json` (umbrella live tree)
           prod or exp:   prod (governs the production pair promotion of exactly one candidate)
           existing data: record `artifact_digest` == bt `_A4T1_CANDIDATE_DIGEST` == canonical-JSON SHA-256 recomputed from the live artifact (`760912ec…4af1e`) [VERIFIED — python hashlib + record read, 2026-09-03]
           best-known?:   no — the authorized candidate is a zero-trade artifact the standing A4 policy refuses; this PR governs the operator-authorized exception, not the candidate's quality
           scope:         "this is the orchestrator consumption record for the 20260831T141820Z staging artifact, prod, vs the served 2026-08-02 model — one-shot governance, no signal claim"
NEXT:      bt#128 merges → CI here turns green → this PR merges; then the
           umbrella PR (pins + `weekly_wf_promote.sh` rewiring + `make snapshot`)
           → live-tree ff-only + `.subrepo_runtime` sync →
           `weekly_wf_promote.sh --promote-staged 20260831T141820Z` → daily full
           (see §Operator sequence after merge).

## Problem (codex on #1107, three blockers)

1. The v1 ledger helper was not wired into any production promotion entry
   point; the "sequence" was manual Python calls; no e2e test across the
   actual caller.
2. `consume()` accepted arbitrary run IDs / digests / staging paths and
   issued a proof without validating the authorized exception or the
   backtesting verdict; with bt#127 accepting any non-empty proof dict the
   boundary was bypassable.
3. CI red (`test_doc_alignment::test_snapshot_not_stale` — a new module
   without a snapshot refresh); and `~/.renquant/governance` is host-local,
   not the auditable system of record.

## What changed

**Authorization record — committed, reviewed.**
`ops/governance/a4t1/20260831T141820Z.authorization.json` (schema
`a4t1_authorization.v1`): exception id, run id, full-artifact digest
`760912ec…4af1e`, authority string, the five authorized bypass classes,
floor override 0.001, temporal bounds [2026-08-31, 2026-09-07], both
operator authorizations (structural 08-31, candidate/regime_sanity_ic
09-02 — session 428feb92). `load_authorization()` cross-checks run id,
digest and authority against the constants backtesting pins; a record and
a pin that disagree → `authorization_record_mismatch`. bt's
`_A4T1_CANDIDATE_AUTHORITY` now names this file; bt's local JSON is a
pointer only.

**The narrow operation.** `a4t1_governance.promote_candidate(prod,
staging, as_of)` is the ONLY producer of consumption proofs:
identify (filename run id + independently recomputed digest ==
record) → `freshness_fallback.decide()` must return FALLBACK_PROMOTE AND
carry the candidate keys equal to the record → build the v1 proof
(`receipt_id` = sha256 of the canonical JSON of the 8 bound fields) and
validate it BEFORE consuming → atomic `O_CREAT|O_EXCL` marker
`<ledger>/a4t1_20260831T141820Z.consumed.json` (`stamped: false`) →
`freshness_fallback.stamp(..., a4t1_consumption_proof=proof)` → marker
atomically flipped to `stamped: true`. No free-form `consume()`; no
`--ledger` / `--authorization` / `--data-root` flags; no caller-constructed
proof path. Refusal vocabulary (`refused_on`): `run_id_format`,
`authorization_record_missing`, `authorization_record_unreadable`,
`authorization_record_schema`, `authorization_record_mismatch`,
`temporal_bounds`, `run_id_mismatch`, `staging_unreadable`,
`artifact_digest_mismatch`, `verdict_refused`,
`verdict_not_candidate_exception`, `already_consumed`, `stamp_failed`.
Every refusal leaves the artifact byte-identical; `stamp_failed` leaves the
marker (consumed, `stamped: false`) — that state is the operator's to
inspect, never retried by accident.

**Ledger location / host ownership.** `<data_root>/logs/weekly_wf_promote/
a4t1_ledger/`, next to the promote verdicts the umbrella already writes.
`data_root` = `runtime_paths.default_data_root()` (`RENQUANT_DATA_ROOT`
or the umbrella runtime root) — the durable operator state root every other
orchestrator job writes to and that `com.renquant.backup` backs up. This is
a single-host deployment; host ownership IS the data root. `~/.renquant` is
gone. The orchestrator creates its own ledger dir (the v11 "decide()
refuses before stamp() can create the dir" deadlock cannot recur); the
marker itself stays O_EXCL.

**Production entry points.**
- `renquant_orchestrator a4t1-promote --prod P --staging S [--as-of D]`
  (`cli.py`): exit 0 iff PROMOTED, JSON verdict on stdout.
- `ops/renquant104/a4t1_promote_staged.sh <RUN_ID> <ACTIVE_ART>
  <STAGING_ART>`: validates the run-id format and that the staging file
  carries it, runs the subcommand under `$PYTHON` (default the production
  venv), tees the JSON to `$LOG_DIR/<RUN_ID>.a4t1_promote.json`, exits with
  the subcommand's code.
- **Umbrella wiring is a separate PR** (repo boundary): in
  `RenQuant/scripts/weekly_wf_promote.sh` the `--promote-staged` branch's
  call `"$PYTHON" -m renquant_backtesting.wf_gate.freshness_fallback --prod
  "$ACTIVE_ART" --staging "$STAGING_ART" --stamp > "$PS_VERDICT"`
  (lines 357-358 at umbrella `d7007e76`) is replaced by
  `"$SUBREPO_ROOT/repos/renquant-orchestrator/ops/renquant104/a4t1_promote_staged.sh"
  "$PS_RUN_ID" "$ACTIVE_ART" "$STAGING_ART"`, and `renquant-orchestrator`
  is added to the `renquant_subrepo_pythonpath` list at line 228. Until
  that lands the existing call is fail-closed on the candidate: since
  bt#128 the direct CLI exits 1 with `stamp_refused`.

**Snapshot.** `data/strategy_snapshot.json` regenerated
(`scripts/generate_strategy_snapshot.py --update`): `a4t1_governance` in
`source_modules`, `a4t1-promote` in the CLI inventory.

## Tests — `tests/test_a4t1_governance.py`, 22 passed [VERIFIED — 2026-09-03]

Module top FAILS (not skips) when the backtesting on the path lacks
`A4T1_PROOF_SCHEMA` — so this PR's CI is red until bt#128 merges, and a
pre-v13 pin can never turn it green vacuously.

- committed record cross-checks clean against the backtesting pin (no
  monkeypatching — this pins the two repos together in CI)
- record missing / disagreeing with the pin on authority, run id, digest
  (parametrized) / wrong schema → refused, no marker, artifact untouched
- valid promotion: marker `stamped: true`, artifact carries
  `promotion_basis` + the proof, `validate_a4t1_proof` passes,
  `is_consumed`
- fabricated digest (artifact edited after the record) / wrong run id in
  the filename / outside temporal bounds / backtesting REFUSE (fresh prod)
  / standing-path promotion without candidate keys → refused, no marker
- replay across directories → `already_consumed` carrying the first
  receipt id; corrupt marker → `already_consumed`
- stamp failure → `stamp_failed`, marker `stamped: false`, retry →
  `already_consumed`
- 8 racing threads (barrier-started), one shared ledger → exactly one
  PROMOTED, seven `already_consumed`, exactly one artifact stamped
- CLI subcommand promotes then refuses the replay (exit 0 / 1)
- cross-process replay via a runner around the real CLI main → exit 0
  then exit 1 `already_consumed`; 4 concurrent processes → exactly one
  exit 0
- bash wrapper: `bash -n`; bad run id / wrong arity refused before Python;
  end-to-end through the wrapper with `$PYTHON` = the runner: PROMOTED
  recorded in `$LOG_DIR`, replay exit 1 with the refusal recorded, run id
  not matching the file refused by the wrapper
- default ledger path resolves under `RENQUANT_DATA_ROOT`

Full suite in this worktree: see PR body for the count and the known
pre-existing failures (4 on main, unrelated).

## What this enforces / what it cannot

Every production path (umbrella script → wrapper → CLI → `promote_candidate`)
consumes the exception exactly once per host data root, and backtesting
refuses any proof not shaped and bound exactly like the one this module
builds. A Python caller that imports backtesting directly and reconstructs a
valid proof is not stopped by code — it is visible: the stamped artifact
carries a `receipt_id` that the ledger does not, and the ledger dir is the
audit surface. Replication beyond this host is not claimed.

## Operator sequence after merge

1. bt#128 merges → this PR's CI turns green → this PR merges.
2. Umbrella PR: `subrepos.lock.json` pins (backtesting → bt#128 merge sha,
   orchestrator → this merge sha) + the `weekly_wf_promote.sh` wiring above
   + `make snapshot`. Codex review; merge.
3. Live tree: `git pull --ff-only` (preflight + durable record), then
   `scripts/promote_pin.py` / `subrepo_assemble.py --sync` materialises
   `.subrepo_runtime`; `-run` checkout ff-only to main.
4. `scripts/weekly_wf_promote.sh --promote-staged 20260831T141820Z` →
   PROMOTED → pair promote → `FALLBACK-PROMOTED` ntfy.
5. Daily full rerun.

## Literal revert

- Code: `git revert` this PR's merge commit.
- Consumption state (only if the operator decides the exception must be
  re-armed — a governance decision, not a fix): delete
  `<data_root>/logs/weekly_wf_promote/a4t1_ledger/a4t1_20260831T141820Z.consumed.json`
  and record why in the LONG ledger.

## Iteration history

- v1 (orch#1107): free-form `consume()` + `~/.renquant/governance`. Codex:
  the three blockers above.
- v2 (this PR): committed record; narrow `promote_candidate`; data-root
  ledger; CLI + wrapper; 22 integration tests incl. cross-process and
  concurrent consumption; snapshot refreshed.
