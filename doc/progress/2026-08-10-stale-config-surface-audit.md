# Stale config surface audit — umbrella strategy_config.json vs pinned running config

STATUS:    read-only research; no config touched; remediation PROPOSED only
           (any umbrella config change is production-adjacent and needs its
           own reviewed RenQuant PR).

WHAT:      doc/research/2026-08-10-stale-config-surface-audit.md — full
           flattened diff of the umbrella
           RenQuant/backtesting/renquant_104/strategy_config.json against the
           pinned renquant-strategy-104/configs/strategy_config.golden.json:
           147 differing leaf keys (103 substantive + 44 comment), risk-
           classified (a) actively misleading = 43, (b) inert-but-confusing
           = 56, (c) benign = 4. Most misleading key:
           ranking.panel_scoring.kind = "hf_patchtst" (retired 2026-08-02,
           orch#741) vs the running "blend". Consumption chain proven
           file:line — daily/intraday/promote all inject the PINNED active
           config (daily_104.sh:113 + live_bridge.py:93-113,410 +
           live/runner.py:406,413); pinned active ≡ golden on every
           non-comment key except walkforward.manifest_path.

WHY/DIR:   The umbrella file already misled forensics once (assumed-tree ≠
           running-tree class). The audit found it is NOT a dead surface:
           the weekly tournament retrain READS it
           (weekly_tournament_retrain.sh:97 → train_104.py:194-201) and
           recalibrate WRITES blend_updated/blend_n_symbols back into it
           (recalibrate_scores.py:281-288; observed written 2026-08-09).
           One divergence is OPERATIVE, not just forensic: the umbrella
           watchlist lacks CRWV/RKLB/SPCX (142 vs 145), so those names
           never enter the weekly per-ticker tournament. The daily drift
           guard compares umbrella-vs-umbrella-golden — two stale copies —
           and can never catch this (daily_104.sh:127-129 says so verbatim).
           Remediation options A-E proposed with tradeoffs; recommended
           sequence: banner keys (A) → drift-guard re-target (E) →
           watchlist re-mirror with its own validation (B); section
           deletion (C) rejected pending a train_104 caller inventory.

EVIDENCE:  artifact:      the research note itself; every number carries
                          [VERIFIED — file:line] read this session
           prod or exp:   read-only over RenQuant f85a639 (dirty umbrella
                          config, mtime 2026-08-09 06:27) +
                          renquant-strategy-104 aa77593 (configs/ clean) +
                          orchestrator origin/main f521408e
           existing data: entirely — configs, runner/bridge/scripts source,
                          launchd plists, git log/status
           best-known?:   yes for the consumption chain (fail-closed since
                          RenQuant#546); the (b) call on the QP admission
                          subtree carries an explicit re-verify caveat
                          (consumers outside the QP solver not inventoried)
           scope:         diff is umbrella-vs-golden as tasked; umbrella-vs-
                          active differs by exactly one row
                          (walkforward.manifest_path, golden-side gap)

TESTS:     none (docs-only PR); the flatten-diff procedure is described in
           the note and re-runnable read-only against the three configs.

NEXT:      remediation is out of scope here. If picked up: Option A banner
           PR in RenQuant (umbrella active + umbrella golden in one commit,
           drift-guard ignore-path included), then Option E guard re-target,
           then Option B watchlist re-mirror as a validated retrain-scope
           change.
