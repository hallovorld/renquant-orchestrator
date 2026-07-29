# Progress: a rebuild that touches a file is not one that advanced the data

STATUS:   delivered (checker + 16 tests). Its FIRST revision reported two false
          positives; both are now HEALTHY and both are pinned as regressions.
          Not installed as a job — that is a machine landing needing a grant.

WHAT:     `ops/data_frontier_check.py`. For each watched data artifact it reads
          the newest date from the DATA COLUMN — never the file mtime — and
          classifies any staleness into TRANSIENT / NOT_ADVANCING /
          UPSTREAM_EMPTY, with a retry budget per class. mtime is used only to
          tell "ran and produced nothing" apart from "did not run".

WHY/DIR:  Operator: base-data problems need check-and-retry. The gap is real
          and precise. `scripts/retrain_alpha158_linear.sh` checks success with

              ARTIFACT_AGE=$(date -r "$ARTIFACT" "+%Y-%m-%d %H:%M:%S")

          which reads MTIME. Touching the file satisfies it, so a rebuild that
          advances nothing reports success.

          Retry is deliberately NOT uniform. Three causes need three
          reactions, and conflating them is how "add a retry" produces a job
          that fails forever quietly instead of once loudly:
            TRANSIENT      3 retries — missing/unreadable, or the job never ran
            NOT_ADVANCING  1 retry   — ran within cadence, frontier did not move
            UPSTREAM_EMPTY 0 retries — ran, and upstream had nothing newer.
                                       A retry cannot change that; escalate.

THE FALSE POSITIVES I SHIPPED IN REVISION 1, AND THE FIX:
          Revision 1 applied a FLAT age bound and reported both training panels
          as UPSTREAM_EMPTY:
            alpha158-fund-panel   data 2026-05-01, age 89d
            transformer-panel     data 2026-04-28, age 92d
          Both carry `fwd_60d_excess`. A 60-TRADING-day forward label cannot
          exist until ~84 CALENDAR days after its feature date, so both panels
          were as fresh as they can physically be. They are structurally
          lagged, not stale.

          This is the same single-axis error that renquant-pipeline#220 — the
          two-axis shadow-freshness rule I wrote this morning — exists to fix. I
          walked into it the same day, in a new tool. The bound is now
          `structural_floor(label_horizon) + slack`, derived per artifact and
          PRINTED in the finding so a future false positive is self-diagnosing:
            "within 112d — structural floor 84d (60 trading days) + 28d slack"

EVIDENCE: artifact: `ops/data_frontier_check.py`,
                    `tests/test_data_frontier_check.py`; live files
                    `RenQuant/data/{sec_fundamentals_daily,alpha158_291_fundamental_dataset,transformer_v4_wl200_clean}.parquet`
                    and `scripts/retrain_alpha158_linear.sh`, all READ-ONLY.
  prod or exp:      PROD ops tooling, READ-ONLY. Reads parquet columns; writes
                    nothing, retries nothing itself, installs nothing.
  existing data:    Yes, measured this session:
                    sec_fundamentals_daily  last 2026-07-24, age 5d  `[VERIFIED]`
                    alpha158-fund-panel     last 2026-05-01, age 89d `[VERIFIED]`
                    transformer-panel       last 2026-04-28, age 92d `[VERIFIED]`
                    structural floor for a 60-trading-day label = 84 calendar
                    days `[DERIVED — ceil(60*7/5)]`; both panels therefore sit
                    INSIDE floor+slack and are HEALTHY.
                    Live run after the fix: 3/3 artifacts advancing `[VERIFIED]`.
  best-known?:      Yes for the mtime-vs-data distinction and for the two-axis
                    bound. NOT claimed: that today's live TRADING uses stale
                    features — it does not. The live path builds features from
                    real-time bars (`build_runtime_feature_cache(ohlcv=...)`);
                    these two parquets are TRAINING panels.
  scope:            `renquant-orchestrator` ops + tests. No pin advanced, no
                    config edited, no job installed, no live surface touched.

CORRECTION TO MY OWN EARLIER CLAIM:
          I said "a retrain today would train on data ending 2026-05-01" as
          though that were a defect. For a 60-day-label model it is correct and
          unavoidable. The real constraint on retraining today is different and
          unchanged: the 9 requested new tickers have ZERO rows in the panel.

REVISION 2 (review MED, and it was right):
          The module's docstring defines UPSTREAM_EMPTY as a frontier unmoved
          "across repeated observations", but read_frontier() assigned it from
          ONE stale snapshot plus a recent mtime. That mislabels a transient
          upstream failure as futile and forces ZERO retries — the exact
          opposite of the check-and-retry behaviour this was built for, and an
          internal contradiction between my own docstring and my own code.

          UPSTREAM_EMPTY now requires a `prior_frontier` argument EQUAL to the
          current frontier — proof that an earlier observation saw the same
          newest date. Without that proof, touched-but-stale is NOT_ADVANCING
          with ONE retry. The checker stays stateless by design (it writes
          nothing), so persisting the last reading is the scheduled caller's
          job, and that boundary is now explicit rather than papered over.

          Live re-run after the fix: 3/3 HEALTHY, unchanged. 19 tests (3 added:
          one-observation is not futile, a prior observation of the same
          frontier IS, and a prior observation that ADVANCED is not).

NEXT:     Per-TICKER completeness is a separate and still-open P0: the live run
          logs `Feature cache built: 148/149`, `Loaded models for 122/145
          symbols`, and `sentiment hit=51 miss=94` and reports success anyway.
          That check must distinguish structural absence (PEAD out-of-window
          for names with no earnings in the window is CORRECT) from a real gap,
          or it will produce exactly the false positives this doc records.
