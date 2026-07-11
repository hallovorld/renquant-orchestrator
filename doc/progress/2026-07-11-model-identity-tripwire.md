# model-identity regression tripwire — #484 fix C

STATUS:   done (new module, DARK by default; wire-ready, no scheduled job invokes it).
          Round 2a after Codex CHANGES_REQUESTED on #485 (see REVIEW below); round 2b
          adds the chain-adjacency supporting check (see ROUND 2b below) — Codex's
          "prove the chain, not just the endpoint" point wasn't yet closed by 2a.
WHAT:     `model_identity_tripwire` (sibling of the #480 outage monitor, same headline
          vocabulary) compares the latest run bundle's `artifact_hashes.panel` against
          (a) the previous session's bundle and (b) the AUTHORIZED identity binding —
          a new `expected-model-identity.json` record in the neutral R-PIN state root
          (sibling of `expected-generation.json`; FORWARD-ONLY, atomic write, refuses
          generation decreases and same-generation re-binds; identical re-record is
          idempotent). The deploy/promote flow records the panel sha it deploys via
          `--record-expected` (or `record_expected_identity()`); an optional
          promotions ledger is the second binding source. The #477 deployment manifest
          supplies DIAGNOSTIC metadata only (generation, deployed_at, plus a
          generation-vs-durable-record check that adds a DEGRADED note on
          stale/replayed/torn state). CLI:
          `renquant-orchestrator identity-tripwire --bundle-dir … [--offline]
          [--record-expected]`.
CONTRACT: | case | verdict | page |
          |---|---|---|
          | same sha as prev session, binding matches/absent | `identity_unchanged` | none (INFO) |
          | changed + binding names the NEW sha | `explained_pin_advance` | none (INFO)* |
          | changed + sha in promotions ledger | `explained_promotion` | none (INFO)* |
          | serving sha contradicts the binding (changed or not) | `identity_binding_mismatch` | OUTAGE, prio 5, exit 2 |
          | changed + no binding + no promotion (06-25 shape) | `unexplained_identity_change` | OUTAGE, prio 5, exit 2 |
          | comparison impossible (no latest identity / no prev bundle) | `coverage_lost` | DEGRADED exit 1 by default; quiet note under `--offline` |

          Absent/unreadable binding record or manifest = lost verification coverage:
          DEGRADED contribution by default, quiet under `--offline`; a DEGRADED
          contribution never downgrades an OUTAGE (worst tag wins).
          \* round 2b: a `pin_advance`/`promotion` verdict is the endpoint proof only —
          see ROUND 2b for the chain-adjacency contribution that can still add a
          DEGRADED (coverage gap) or OUTAGE (proven non-monotonic chain) tag on top.
WHY/DIR:  orchestrator#484 (ZM/NFLX forensics) found the prod panel artifact silently
          regressed 06-21 → 05-18 between the 06-25/06-26 sessions and served a
          39-45-day-old model for 5 sessions, unalerted — nothing existing noticed a
          DIFFERENT model was serving. This closes that detection gap the same way #480
          closed the funnel/data-availability alerting gap.
REVIEW:   Codex round 1 (CHANGES_REQUESTED) — three points, addressed across 2a/2b:
          (1) the original `deployed_at >= prev session` predicate was UNSOUND (a
          timestamp proves capture, not authorization) → replaced by the verifiable
          identity binding; manifest timestamps demoted to diagnostics; a change the
          manifest cannot explain is OUTAGE/DEGRADED, never INFO. [2a]
          (2) missing-input posture inverted: lost coverage pages DEGRADED by default;
          `--offline` is the explicit local-forensics quiet mode (`--require-inputs`
          dropped). [2a]
          (3) expected state lives under the neutral R-PIN state root with atomic
          forward-only generation semantics; torn (same-generation re-bind), rollback
          (generation decrease) and same-day-re-run (idempotent) transitions tested.
          Note: `data/strategy_snapshot.json` was never tripwire state — it is the
          repo's CLI-subcommand doc-alignment snapshot (test_doc_alignment), untouched
          by the tripwire at runtime. [2a]
          (4) "classification must prove... that the prior bundle belongs to the
          immediately preceding authorized generation" — 2a's `expected-model-
          identity.json` is a single, forward-only SLOT (proves the LATEST identity
          only; no history), so this point was still open after 2a. Closed in 2b. [2b]

ROUND 2b: chain-adjacency supporting check (this round). The single-slot binding
          record cannot say whether the PRIOR identity was itself authorized at an
          earlier generation. Added:
          - `load_promotion_ledger(path) -> {sha: generation}` (was
            `load_promotion_shas(path) -> set[str]`, presence-only). NOT silently
            backward compatible for chain-anchoring purposes: a legacy bare-sha entry
            (no `generation` key) is still parsed fail-soft, and can still explain a
            LATEST-identity change via the unchanged presence-only
            `explained_promotion` gate in `classify_transition`, but it CANNOT anchor
            the chain-adjacency check below (excluded from the returned map) — a
            one-time migration (add `"generation": N` to each entry, the manifest
            generation active when that promotion happened) is needed to get the full
            round-2b proof for pre-existing ledger files.
          - `build_tripwire_report` supporting check (same pattern as the existing
            manifest `generation_status` check — contributes a note + tag, never
            overrides `classify_transition`'s verdict): when the transition is
            `explained_pin_advance`/`explained_promotion`, resolve the ACTIVE
            generation (the binding record's, falling back to the manifest's), then
            require the PRIOR identity's own ledger-recorded generation to be
            STRICTLY OLDER. Three outcomes: no active generation resolvable at all ->
            DEGRADED coverage-gap note (quiet under `--offline`); generation 1 (the
            epoch floor) -> skipped, informational-only note (nothing older exists);
            prior identity unbound in the ledger -> DEGRADED coverage-gap note (quiet
            under `--offline`); prior identity bound to a generation that is NOT
            older (non-monotonic/rollback shape) -> OUTAGE, a PROVEN contradiction,
            **never suppressed by `--offline`**; prior identity bound to a strictly
            older generation -> clean "chain verified" note, no tag change.
          - `--promotions-ledger` CLI help text updated to describe the
            `{sha, generation}` format and the migration note.
EVIDENCE: `tests/test_model_identity_tripwire.py` — 41/41 passed `[VERIFIED]` (was 34
          after 2a; +7 net new for 2b: generation-bound ledger load + legacy-entry
          exclusion + bad-generation-value rejection; chain verified / coverage-gap
          (default DEGRADED, quiet under `--offline`) / broken-non-monotonic (OUTAGE,
          never suppressed) / generation-1-floor). Two pre-existing 2a tests
          (`test_recorded_pin_advance_passes_with_info`,
          `test_main_exit_codes_for_the_three_cases` case 2) were updated to also
          supply the prior identity's ledger binding, since a "fully clean" pass now
          legitimately needs BOTH endpoints proven — this is the intended new
          behavior, not a broken assertion. Full repo suite (via the umbrella-relative
          `PYTHONPATH`, matching the Makefile's sibling-repo wiring): 3638 passed, 16
          failed, 5 skipped — the 16 failures are byte-identical on the pristine round-1
          tip (`d4e6e1f3`) in this SAME isolated-worktree location (relative
          sibling-repo `git rev-parse` / fixture paths that only resolve from the
          normal dev-checkout location, not a `/private/tmp` worktree) — confirmed
          zero regressions via direct comparison before/after 2b.
NEXT:     (i) wiring into a scheduled job is a separate, ask-first machine landing
          (same posture as #480); (ii) the deploy/promote flow should call
          `--record-expected` after its verify step so the binding stays current —
          same landing; (iii) migrate any existing promotions-ledger file to the
          `{sha, generation}` format to get 2b's full chain-adjacency proof (bare-sha
          entries still work for the endpoint check, just not the chain-anchor).
          Fix D (fill-truth in the runs DB, pipeline-owned) ships as renquant-pipeline
          PR #190.
BOUNDARIES: read-only in check mode — consumes run-bundle JSONs + state-root records;
          never touches broker, live state, or production paths; the only write path
          is the explicit `--record-expected` maintenance mode, confined to the
          neutral state root.
