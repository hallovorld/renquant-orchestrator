# Progress: the shadow-attribution guard never ran

STATUS:   delivered. Read-path fix + 9 behavioural tests. No production surface
          touched; the ledger is not rewritten (see SCOPE/LIMITS).

WHAT:     `ops/renquant104/rq104_blend_readout.py`: `_resolve_shadow_name()` and
          `log_skip()` added; `shadow_scores_for()` now REQUIRES identity.
          `tests/test_shadow_identity_fail_closed.py` — 9 tests.

WHY/DIR:  The guard read
            `if "shadow_name" in df.columns and df[...] != SHADOW_NAME: continue`
          so a table with NO `shadow_name` column fell through and was accepted as
          the clf's. Measured `[VERIFIED-now]`: **0 of the 40 newest
          `comparison.json` files carry a `shadow_name` or `run_date` column**, so
          the only model-identity check in this path NEVER EXECUTED.

EVIDENCE: `[VERIFIED-prior — delegated audit, this session]`
          * three shadows write `shadow_score` tables;
          * 2026-07-28: the two NEWEST tables of the day were
            `xgb_alpha158_fund_previous_primary`, not the clf;
          * 2026-07-29 14:08: the clf and PatchTST tables were logged **25.7 ms
            apart with identical 78-row shapes**, so the mtime fallback in this
            function cannot possibly discriminate between them;
          * the ledger's `n_clf_scored: 78` therefore **cannot be attributed to
            the clf from the record**;
          * `append_ledger` is idempotent per `run_date`, so a mis-attribution is
            written once and never corrected.
          Identity WAS available the whole time: MLflow records it as the run tag
          `<run_dir>/tags/shadow_name`, which this function never read.
  prod or exp:    Read-path only. No scoring, sizing, admission or gate logic
                  touched. Nothing written to the ledger by this change.
  existing data:  Yes — mlruns trees already on disk. No compute, no spend.
  best-known?:    Yes, and it is the FIFTH instance on this programme of a guard
                  validating something other than what it appears to validate,
                  after: the raw-clip contract covering 158 of 172 features; the
                  golden config drift guard comparing one stale copy against
                  another; a placebo shuffle that was not a within-date
                  permutation; and an extended-feature clip that turned a
                  divide-by-near-zero into a legitimate-looking ±3.0. Treating it
                  as a recurring shape rather than five unrelated bugs.
  scope:          `renquant-orchestrator` only: one ops module, one test file,
                  this doc. No pin advanced, no config, no artifact.

SCOPE/LIMITS:
          **The existing ledger rows are NOT re-attributed or deleted.** The three
          forward rows currently in it are *consistent* with clf tables, but
          nothing in the old code establishes that they are right — and rewriting
          an append-only audit record on the strength of a reconstruction would
          replace an unverified row with a differently-unverified one. The honest
          state is "these three rows have unestablished provenance", and that
          belongs in the record rather than being silently overwritten.
          The `run_date` mtime fallback is left in place: it is weak, but with
          identity now required it is no longer load-bearing on its own. Removing
          it is a separate change with its own blast radius.
          This fix cannot recover identity for tables whose run directory carries
          no `tags/shadow_name` either — those are now correctly REFUSED, which
          may reduce the number of sessions the ledger can record. Fewer honest
          rows beats more unattributable ones.

VERIFICATION:
          `python3 -m pytest tests/test_shadow_identity_fail_closed.py -q`
          -> 9 passed. Tests build a real MLflow-shaped tree on disk and drive the
          real function, because a test that only checked "a clf table is found"
          would have passed on the broken code — the failure is that a NON-clf
          table is also found. Covered: a table with no identity anywhere is
          REFUSED (the regression); identity from the MLflow tag is accepted; a
          wrong tag is refused and named in the log; the measured 2026-07-28
          scenario where the two newest tables are the previous-primary xgb; two
          tables 25 ms apart disambiguated by identity rather than mtime; a
          payload column still wins when present; a blank tag does NOT count as
          identity; the resolver returns None rather than raising on a bare path
          (fail-closed must not become fail-crash in an ops job); and a regression
          pin scoped to the DEFECTIVE shape — its first version flagged a
          legitimate presence probe in the new helper, a false positive of exactly
          the kind that makes a pin untrustworthy, so it now targets an identity
          comparison fused to a column-presence probe.
          `make test` shows the 12 pre-existing collection errors
          (`No module named 'renquant_execution'` — bare worktree lacks the
          sibling PYTHONPATH), reproduced identically on a clean `origin/main`
          worktree earlier this session.

NEXT:     The three existing forward rows need provenance re-established from the
          MLflow tags directly, as a separate read-only audit, before the forward
          clf arm is used for anything. Also outstanding from the same audit: the
          120-session forward GATE is 2 blocks against a house floor of 10.
