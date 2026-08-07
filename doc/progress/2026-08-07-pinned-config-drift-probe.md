# Pinned-config drift probe — ask what the run READS, not how far the pin trails

STATUS:    Probe added and registered in `ops_audit.MEMBERS`; 16 unit tests green.
           The incident that motivated it (orch#895) was separately remediated
           under an explicit operator grant — recorded below with revert steps.

WHAT:      `ops/pinned_config_drift_probe.py` compares the PINNED
           `strategy_config.json` — the file the live run actually reads — against
           `origin/main`'s, key by key, and reports any behavioural difference.
           Registered as `pinned-config-drift` so the daily ops-audit runs it and
           `agent_inbox.py` surfaces it.

WHY/DIR:   2026-08-07 (orch#895): `strategy-104` merged `feat(risk): per-name cap
           12% -> 30% (#94)` under an operator directive. The runtime checkout was
           advanced to it and `subrepos.lock.json` was NEVER updated, so the next
           pin-restoring run checked the old sha back out. For days `origin/main`
           said `BULL_CALM.max_position_pct = 0.3` while the config sizing new
           entries said `0.12`. Nothing alarmed.

           `ops/subrepo_pin_lag_check.py` DID see it — `strategy-104 pin=c8bba9c9
           behind=1` — and structurally could not report it. Its alarm is
           per-subrepo `behind > --max-lag`, default 50, and today's real exit of 1
           is driven entirely by `renquant-orchestrator behind=307`.

           The defect is the unit of measurement: **lag counted in COMMITS cannot
           distinguish "1 behind because of a typo fix" from "1 behind because the
           operator's P0 risk-cap change is stranded".** Dropping the threshold to
           0 is not the fix — a pin legitimately trails main most of the time, so
           that is pure noise. The question worth asking is about CONTENT.

           Two design choices follow from prior fleet defects:

           * **The default is inverted.** An enumerated list of "keys that matter"
             leaves every unanticipated key on the silent-pass side. Every
             difference is a finding; the sole exemption is `_`-prefixed
             documentation keys, which this config uses for provenance prose.
           * **A stale mirror must not read as clean.** `origin/main` here is
             whatever the local sibling clone last fetched, so the probe reports
             the main sha AND its commit date it compared against, and refuses
             (exit 2) when the mirror has no `origin/main`.

EVIDENCE:  artifact:      ops/pinned_config_drift_probe.py (registered in
                          `ops_audit.MEMBERS` as `pinned-config-drift`)
           prod or exp:   prod — reads the live pinned `strategy_config.json` and
                          was used to remediate a live production drift below
           existing data: `ops/subrepo_pin_lag_check.py` already alarms on this
                          class of drift but only in commit count
                          (`strategy-104 pin=c8bba9c9 behind=1`) and could not
                          say whether the 1 commit changed anything a running
                          strategy reads
           best-known?:   yes — first content-aware pin-drift check in this repo;
                          supersedes commit-count lag as the detector that would
                          have caught orch#895
           scope:         this is ops/pinned_config_drift_probe.py, prod
                          (ops_audit.MEMBERS member), vs existing best
                          subrepo_pin_lag_check.py, which cannot distinguish a
                          behavioural config change from routine drift

           probe, live, after remediation:
             `python3 ops/pinned_config_drift_probe.py` ->
             `OK renquant-strategy-104/configs/strategy_config.json:
              pinned=e00d9356 main=e00d9356 (committed 2026-08-06T16:24:18-07:00),
              716 keys compared`, exit 0
             `[VERIFIED — command stdout, 2026-08-07]`

           reverse check that the guard is not vacuous — the historical case is
           reconstructed from fixtures and DETECTED:
             `test_the_stranded_cap_change_is_a_FINDING` asserts the sole diff is
             `regime_params.BULL_CALM.max_position_pct` pinned=0.12 main=0.3
           and the complementary case is deliberately silent:
             `test_a_differing_sha_with_an_identical_config_is_NOT_a_finding`
             (asserts `pinned_sha != main_sha` as a premise before asserting no
             diffs — so it cannot pass by accident if the fixture stops differing)

           suite: `tests/test_pinned_config_drift_probe.py` 16 passed
             `[VERIFIED — pytest, 2026-08-07]`
           full orchestrator suite: 6152 passed, 2 skipped, 3 failed
             `[VERIFIED — pytest, 2026-08-07]`
           All three failures pre-date this change and none touches
           `ops_audit.MEMBERS`:
             * `test_the_RECORD_names_the_revision_that_was_actually_measured`
               and `test_the_LIVE_audit_is_what_the_record_describes` reproduce on
               a clean `origin/main` worktree.
             * `test_live_twin_parity_manifest_current` is orch#886 — the
               `live/alerts.py` vs `renquant-execution` divergence. NOTE: this one
               PASSES in an `origin/main` worktree, and that pass is VACUOUS: the
               sibling repos resolve relative to the checkout, so under
               `/private/tmp/.../wt-orch` there is nothing to compare. The failing
               run in the real tree is the trustworthy one.

           REMEDIATION OF THE UNDERLYING INCIDENT (operator grant, 2026-08-07,
           market closed, no run in flight — both verified before mutating):
             preflight: the `c8bba9c -> e00d935` diff is exactly
               `max_position_pct` and `max_concentration` 0.12 -> 0.3 across 8
               config files, plus a progress doc and a test update. Nothing else.
               `max_concentration` sits under `ranking.kelly_sizing` with
               `enabled=false` and is inert.
             `subrepos.lock.json`: `renquant-strategy-104.commit`
               `c8bba9c9b30c960f85daa2529ee422a0997ad607` ->
               `e00d9356ac620426df031e0c08ce66301c50c22e`
               (single-value string replace after asserting the old sha appears
               EXACTLY once in the file, so formatting is untouched)
             runtime checkout advanced to `e00d935` after asserting
               `git status --porcelain` was empty — an unclean tree would have
               aborted rather than clobbering an uncommitted hotfix.
             post-state `[VERIFIED — command stdout]`:
               `BULL_CALM.max_position_pct = 0.3`,
               `BEAR.entry_mode = blocked` (unchanged)

           LITERAL REVERT STEPS, if this needs to come back out:
             1. `python3 -c "p='/Users/renhao/git/github/RenQuant/subrepos.lock.json';
                t=open(p).read();
                open(p,'w').write(t.replace('e00d9356ac620426df031e0c08ce66301c50c22e',
                'c8bba9c9b30c960f85daa2529ee422a0997ad607'))"`
             2. `git -C /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104
                checkout c8bba9c9b30c960f85daa2529ee422a0997ad607`
             A pre-change copy of the lock file is in the session scratchpad at
             `subrepos.lock.json.bak`.

NEXT:      1. The deployment ceiling changed but the book has not re-sized: 7/8
              positions, 53.3% cash `[VERIFIED — Alpaca, 2026-08-07]`. The next
              daily-full is the first run that can size a new entry at 0.30, and
              `book_beta` (last measured 145.4% CRITICAL) must be re-measured
              after any buy it places.
           2. `WATCHED` currently holds one file. The six shadow-lane configs
              moved in the same commit and are equally capable of stranding;
              adding them is a deliberate widening and should be its own PR with
              its own evidence, not a silent tuple edit here.
           3. NOT DONE, and NOT this probe's job: `subrepo_pin_lag_check.py` is
              still unregistered in `ops_audit.MEMBERS`. Registering it is
              orthogonal — it answers "how far behind", which remains worth
              knowing — but on today's numbers it would fire on
              `renquant-orchestrator behind=307` (orch#881) and say nothing about
              the class this probe covers.
