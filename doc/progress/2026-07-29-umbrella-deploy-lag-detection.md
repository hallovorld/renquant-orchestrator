# Progress: the drift scan checked the branch NAME but not whether the tree IS main

STATUS:   delivered. Detection only — no live-tree mutation, no sync performed.

WHAT:     `ops/run_surface_drift_check.py`: new `check_umbrella_deploy_lag()`
          plus `_resolve_ref()` and `STALE_FETCH_DAYS`, wired into `main()`.
          `tests/test_umbrella_deploy_lag.py` — 10 behavioural tests.

WHY/DIR:  `check_umbrella_branch()` verifies the umbrella live tree is on
          `main`. That is not sufficient. The daily run consumes local sibling
          checkouts by PATH, so a tree sitting ON main at an OLD commit runs old
          code while every dashboard reports the fix as merged. This is the
          "merged is not deployed" class, and it was live TODAY.

EVIDENCE: measured against the real live tree, READ-ONLY `[VERIFIED-now]`:
            old branch-name check       -> CLEAN (misses it entirely)
            new deploy-lag check        -> FIRES
            refs/heads/main             = 36a8c459
            refs/remotes/origin/main    = 3f4e3d6b
            live tree behind origin/main by 9 commits
          Concrete consequence, also measured: `grep -c -- '--panel'
          RenQuant/scripts/train_production_model.py` on the LIVE tree returns
          **0**, although umbrella#543 ("feat(train): --panel, so a rebuilt panel
          can be trained without overwriting production") is MERGED to
          origin/main. A delegated retrain today failed on exactly that: the
          flag it was told to use did not exist on the machine, and it had to
          work around the hardcoded relative panel path with an isolated `data/`
          directory of symlinks.
  prod or exp:    Detection only. This scan does NOT and MUST NOT sync the live
                  tree: syncing is a machine-landing action requiring operator
                  authorization, and a `checkout -- .` / `reset --hard` in that
                  tree has previously clobbered uncommitted operational fixes
                  (18 FAILs, 2026-06-25). The alarm text says so explicitly and
                  names `pull --ff-only` after a read-only preflight instead.
  existing data:  Yes — git ref files already on disk. No fetch, no network.
  best-known?:    Yes. Two signals rather than one, because the first can lie:
                  (a) `refs/heads/main != refs/remotes/origin/main`; and
                  (b) the fetched remote ref being stale, since `origin/main`
                  inside that tree is only as fresh as the last fetch INTO it
                  and this scan will not fetch. Without (b) the check would
                  report "in sync" against a month-old remote and read as a pass.
  scope:          `renquant-orchestrator` only: one ops module + one test file +
                  this doc. No pin advanced, no umbrella change, no config.

SCOPE/LIMITS:
          Reports drift as a BOOLEAN plus both shas, not a commit count. Counting
          the distance needs graph traversal, i.e. invoking git in the live tree,
          which this module deliberately does not do — it reads git metadata as
          FILES, loose refs then `packed-refs`. A read-only-looking git
          invocation is one typo from a writing one, and a sub-agent's
          `git reset --hard` in this shared checkout is why that rule exists.
          A test enforces the property by making `subprocess.run` raise.
          Because signal (a) compares against the ref as last fetched INTO the
          live tree, upstream commits that were never fetched there are NOT
          visible; signal (b) exists to make that unmeasurability loud rather
          than silent. STALE_FETCH_DAYS=7 is a judgement, not a measurement.
          The 9-commit figure above came from a git invocation in the primary
          orchestrator checkout (not the live tree) and is reported here as
          context; the shipped check does not compute it.

VERIFICATION:
          `python3 -m pytest tests/test_umbrella_deploy_lag.py -q` -> 10 passed.
          Tests drive the real function against real on-disk ref layouts, since
          a test that greps for the word "behind" would also pass on a check
          that compares nothing. Covered: in-sync clean; the exact 2026-07-29
          condition (branch-name check CLEAN while the sha check fires, asserted
          in one test so the regression is pinned to the actual gap); packed-refs
          resolution for a gc'd repo with no loose refs; missing local ref and
          missing remote ref each reported rather than crashing; a stale fetch
          flagged even when the shas MATCH; a fresh fetch not flagged; injectable
          `now` so the staleness test is not clock-dependent; and no subprocess
          invoked at all.
          `make test` shows 12 pre-existing collection errors
          (`ModuleNotFoundError: No module named 'renquant_execution'` — the bare
          worktree lacks the sibling PYTHONPATH). Reproduced IDENTICALLY on a
          clean `origin/main` worktree, so they are environmental and not from
          this change; stated rather than presented as a pass.

NEXT:     The alarm now fires every 07:00 scan until the live umbrella tree is
          synced. Syncing needs operator authorization; the lift is
          `git -C <umbrella> pull --ff-only` after a read-only preflight, and it
          should be treated as its own action with its own record, not folded
          into this PR.
