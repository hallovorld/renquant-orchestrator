# PIT estimate-snapshot scheduling (N2 landing package) — ops PR

STATUS:   ops scaffolding for review (repo files only — nothing installed/executed by this PR;
          installation is the landing step per the direction-loop charter).
REVISION: r1.
WHAT:     `ops/pit/` — daily wrapper for the merged base-data #27 forward snapshotter
          (`fmp_estimate_revisions`, writes only the dedicated `data/estimate_snapshots/<date>/`
          path), a liveness check (ntfy on weekday miss — a missed day is UNRECOVERABLE under
          the PIT no-backfill invariant), two launchd plists (14:30 / 15:00 PT weekdays), and a
          README (install / dry-run smoke / N2 AC). Pinned run checkouts only.
WHY/DIR:  #231 N2 is the time-irreversible NOW item: the revision signal (the G106 stack's
          cross-family leg, POC-D) is un-buildable until an as-of history accrues forward;
          base-data #27 built the collector but nothing schedules it — the same
          built-but-dark pathology as N1. Scheduling ownership is orchestrator's per the #27
          docstring and #210's ownership split.
EVIDENCE: base-data #27 MERGED (`fmp_estimate_revisions.py`, 693 lines + tests; PIT hard
          invariant documented in its docstring); FMP `stable` analyst-estimates endpoint
          returns data on the existing key (probed 2026-07-02 — the v3 endpoint is
          legacy-deprecated); `--min-coverage` will surface plan-lock gaps, with the authorized
          N3 Starter upgrade as the remedy.
NEXT:     Codex review; lander runs the README install; N2 AC clock starts at first successful
          dated snapshot; N3 coverage verdict falls out of the first real run's
          `--min-coverage` report.
