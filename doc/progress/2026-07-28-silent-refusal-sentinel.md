# Progress: silent-refusal sentinel (GOAL-5 AC5)

STATUS:   delivered (code + 18 tests). Not yet installed as a launchd job — that is a
          machine landing and needs an operator grant; the manifest entry and plist
          land in a follow-up PR so installation is one reviewed step.
          Fix (codex HIGH): `inaction_streak()` silently skipped `undecided` runs
          while still calling the resulting run "consecutive" — e.g.
          newest=undecided, refused, failed, refused could alarm "3 consecutive"
          when the current streak is actually unknown. Fixed: `inaction_streak` now
          returns the non-acting runs AND the skipped-undecided runs separately;
          `check()` drops the word "consecutive" and names the gap when one exists
          (2 new regression tests: gap at the top, gap in the middle).

WHAT:     Adds `ops/renquant104/rq104_silent_refusal_sentinel.py` and its tests. It
          reads dated job logs read-only, classifies each run as acted / refused /
          failed / undecided, and alarms when a job has not ACTED for N consecutive
          runs (default 3). Registry-driven: a job belongs when "it ran successfully"
          and "it did its job" are different statements.

WHY/DIR:  GOAL-5 AC5, and the one serving-reliability AC with no PR yet. The
          motivating incident: `com.renquant.weekly-retrain-patchtst` trained a fresh
          fold every Saturday, refused at the freshness gate, printed `finished rc=0`,
          and kept the old pin — for months, while the served artifact reached 622
          days stale and every liveness checker reported the job healthy. Liveness
          asks "did it run"; the degradation sentinel (`rq104_degradation_sentinel.py`)
          watches the live buy path; nothing asked "did it keep declining".

EVIDENCE: artifact:      `ops/renquant104/rq104_silent_refusal_sentinel.py` +
          `tests/test_rq104_silent_refusal_sentinel.py`, dry-run output against the
          real job logs `[VERIFIED — direct read, 2026-07-28]`.
           prod or exp:   experiment/code-only. Read-only dry-run against existing
          logs on this machine; no state, config, or artifact written; not installed
          as a launchd job by this PR.
           existing data: `logs/weekly_retrain_patchtst/*.log`
          `[VERIFIED — logs/weekly_retrain_patchtst/*.log, read 2026-07-28]`: the real
          recent cycles are a MIX, which is what forced the design past a
          refusals-only rule — 07-03 `CorpusRefreshError` **and** `promote: refused`
          **and** `finished rc=0`; 07-11 `CorpusRefreshError` (no rc line); 07-18
          `CorpusRefreshError`; 07-25 `promote: refused`, rc=0. Every crash carries
          the same cause: `rebuilt rawlabel sidecar rejected (kept prior sidecar):
          staged corpus dropped columns (recipe/schema drift): ['mean_sentiment',
          'n_articles_...']`. A refusals-only streak scores that history as 2 and
          stays silent; counting non-action (refused OR failed) scores it as 4, and
          the dry-run against the real logs reports exactly that: "has not acted on 4
          consecutive runs (2026-07-25:refused, 2026-07-18:failed, 2026-07-11:failed,
          2026-07-03:failed; 3 of them CRASHED)" `[VERIFIED — dry-run output]`. Suite
          18/18 `[VERIFIED — pytest run this session]`.
           best-known?:   n/a — this is a monitoring/alerting utility, not a model or
          statistic; no IC/Sharpe claim is made.
           scope:         code-only delivery landing a read-only sentinel; no
          production surface (launchd manifest, live config, live state) is touched
          by this PR — the §4(b) sanity triad does not apply.

          This also CORRECTS a claim made earlier the same day in RenQuant#541, which
          said the panel "is advancing, not frozen" on the strength of a recent mtime.
          The mtime reflects a write ATTEMPT; the rebuild is rejected and the prior
          sidecar is kept. The #541 gate fix remains correct on its own terms — the
          28d SLA is unsatisfiable for a fwd60 source — but it is not the whole root
          cause, and the upstream schema drift is now a separate open item (see NEXT).

NEXT:     (1) install as a launchd job (operator grant + manifest entry, one reviewed
          step, tracked separately from this PR per the containment-protocol rule
          that reviewed-surface changes land in their own reviewed batch); (2) chase
          the schema drift itself — why the rebuilt sidecar drops `mean_sentiment` /
          `n_articles_*`, plausibly related to the base-data#48 single-writer
          amendment that made those columns canonical; (3) extend the registry to
          the other jobs that can exit 0 without acting.
