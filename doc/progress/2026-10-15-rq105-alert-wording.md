# 2026-10-15 — rq105 alert wording: the skip title and the stall page said the wrong cause

STATUS:   delivered, awaiting review — zero reviews at head.
WHAT:     Two notification strings only. `run_batch_scores_export.sh`: the exit-3 title
          "prior session buy-gated by design" -> "SKIPPED by design — prior session admitted no
          buy candidate" (exit 3 now also covers the sell-only zero-candidate shape, #1131).
          `run_quote_logger.sh`: "tick feed frozen (collector hung)" -> "(stalled or source
          failing)", body names the RemoteDisconnected case and that the watchdog restarts it.
WHY/DIR:  both titles asserted a cause the code no longer (or never) established. On 2026-10-15
          the two 🚨 pages were Alpaca data-API disconnects (every batch raised
          RemoteDisconnected), not a hung process; the watchdog recovered it as designed.
EVIDENCE: see below.
  artifact:      ops/renquant105/run_batch_scores_export.sh, ops/renquant105/run_quote_logger.sh.
  prod or exp:   exp — notification text; no behaviour, exit codes or thresholds change.
  existing data: logs/rq105/quote_logger_2026-10-15.log tail = repeated "quote batch failed (RemoteDisconnected)"; quote_logger_crash_2026-10-15.log shows the watchdog kill/restart at 15:16Z and 16:38Z [VERIFIED 2026-10-15]; Alpaca data and GitHub reachable again at 15:56 PDT.
  best-known?:   n/a — wording.
  scope:         two shell files; 152 rq105 wrapper/export/liveness tests pass.
NEXT:     merge + -run sync.
