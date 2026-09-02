# A4-T1 orchestrator-side consumption governance

STATUS: paired with renquant-backtesting#127 (v12)

## Problem

Codex rejected backtesting's v11 (#126) because:
- Hardcoded `~/.renquant/governance/` in backtesting is host-local
- `decide()` refuses before `stamp()` can create the governance dir (deadlock)
- Backtesting should not own governance state — the orchestrator should

## Solution

Split concerns:
- **Backtesting** (bt#127): identifies A4-T1 candidates (run-ID + digest match),
  `stamp()` requires `a4t1_consumption_proof` from the caller
- **Orchestrator** (this PR): owns consumption governance — atomic O_CREAT|O_EXCL
  marker file, returns proof dict to pass to backtesting's `stamp()`

### Module: `a4t1_governance.py`

- `consume(run_id, artifact_digest, staging_path, *, governance_dir)` — atomic
  file marker, returns proof dict. Raises `FileExistsError` on replay,
  `FileNotFoundError` if governance dir missing (fail-closed).
- `is_consumed(run_id, *, governance_dir)` — check-only, fail-closed on corrupt.

### Promotion flow

1. `freshness_fallback.decide()` identifies the candidate → verdict with
   `a4t1_candidate_run_id` + `a4t1_candidate_artifact_digest`
2. Orchestrator calls `a4t1_governance.consume()` → proof dict
3. Orchestrator calls `freshness_fallback.stamp(path, verdict,
   a4t1_consumption_proof=proof)` → artifact stamped with proof

## Tests

7 tests:
- Creates marker and returns proof
- Replay raises FileExistsError
- No governance dir raises FileNotFoundError
- is_consumed false before, true after
- Corrupt marker = consumed (fail-closed)
- Cross-directory replay blocked (shared governance dir)
- Different run-IDs are independent

## Operator instructions

After both PRs merge, the promotion sequence:
1. Umbrella bt pin advance → `make snapshot` → umbrella PR → merge
2. Live-tree ff-only → runtime bt sync
3. `mkdir -p ~/.renquant/governance` (one-time)
4. Python: `from renquant_orchestrator.a4t1_governance import consume`
   `proof = consume("20260831T141820Z", "<digest>", staging_path)`
5. Python: `from renquant_backtesting.wf_gate.freshness_fallback import stamp`
   `stamp(staging_path, verdict, a4t1_consumption_proof=proof)`
6. Daily full rerun
