# Twin-parity re-pin: readonly_broker after umbrella #538   (PR #587)

STATUS:    delivered

WHAT:      Re-pins the `readonly_broker` diverged-twin hash in
           `data/twin_parity_manifest.json` (one line, umbrella-side sha256
           `ee4b634c...` -> `75373e85...`) via
           `scripts/check_twin_parity.py --write-manifest`. No behavior
           change — this is the deliberate review act that acknowledges an
           already-landed umbrella-side edit.

WHY/DIR:   `make test` on the deploy machine failed
           `test_live_twin_parity_manifest_current` with
           `diverged_pin:readonly_broker`: umbrella's
           `live/broker_readonly.py` changed in the reviewed+merged
           umbrella #538 (`edc6d61` — shadow_blend rail, parameterized
           readonly tag) and the orchestrator's pinned divergence hash was
           not updated alongside. This is the R0 twin-parity tripwire
           (`doc/design/2026-07-10-architecture-compliance-registry.md`
           T3/R0) doing its job — it makes the drift visible instead of
           silently passing.

EVIDENCE:  artifact:      data/twin_parity_manifest.json
                          (diverged_twins.readonly_broker.umbrella_sha256),
                          scripts/check_twin_parity.py,
                          tests/test_twin_parity.py.
           prod or exp:   prod — this manifest is the live pin `make test`
                          enforces on the deploy machine (not CI-only; see
                          check_twin_parity.py's "CI green does NOT certify
                          umbrella-twin parity" note).
           existing data: before this PR, the pinned umbrella_sha256 was
                          `ee4b634cacdcd766674f659f3537e441f84c7e77721f7ffb194978b57e191f06`,
                          computed against umbrella `live/broker_readonly.py`
                          pre-#538. `git log --oneline -1 -- live/broker_readonly.py`
                          on the umbrella checkout shows `edc6d61` (#538) is
                          the only commit that touched the file since that
                          pin — confirmed via `git show edc6d61 --stat`
                          (parameterized readonly tag + ALLOWED_BROKERS
                          entry, no other unrelated edits).
           best-known?:   n/a (not a model variant) — this is a mechanical
                          hash re-pin, not a scored artifact.
           scope:         "this is data/twin_parity_manifest.json, prod, a
                          1-line re-pin restoring the manifest to match the
                          umbrella file that is actually deployed; verified
                          `shasum -a 256 live/broker_readonly.py` on the
                          umbrella checkout == the new pinned value
                          `75373e85f627d3b5523a16041fc440d0c2c7fe59a79d5d678930bf51a0568121`."

           Test evidence: `RENQUANT_SIBLINGS_ROOT=/Users/renhao/git/github
           python3 scripts/check_twin_parity.py` -> 14 pass, 0 fail, 0 skip.
           `pytest tests/test_twin_parity.py -v` -> 23 passed, including
           `test_live_twin_parity_manifest_current`. Full suite
           `pytest tests/ --tb=short -q` (real `GH_TOKEN` /
           `RENQUANT_{CLAUDE,CODEX}_GH_TOKEN` scrubbed from the shell to
           avoid an unrelated env-pollution false failure in
           `test_resolve_token_env_precedence`, confirmed pre-existing and
           unrelated to this diff by reproducing it in isolation with and
           without those vars set) -> 4294 passed, 2 skipped, 0 failed.

NEXT:      none — this PR only restores the pin to match already-merged
           umbrella state. Codex review round 1 (commit
           `7eeec2d`) flagged the progress doc's missing C5 fields; this
           rewrite (literal `STATUS:`/`WHAT:`/`WHY/DIR:`/`EVIDENCE:`/`NEXT:`
           fields per `doc/AGENT-RETROSPECTIVE.md` §4(c)) is the fix.
