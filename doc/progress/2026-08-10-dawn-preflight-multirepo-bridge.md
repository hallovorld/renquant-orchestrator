# dawn preflight probe → multirepo bridge (stop the umbrella-kernel false refuse)

STATUS:    reviewed ops-script change; readonly monitoring probe only; NO
           change to the order path, live state, or any trading behaviour.
           Deploy = a separate operator-gated pin sync to the -run checkout.

WHAT:      ops/renquant104/dawn_funnel_preflight.sh — the dawn readonly
           funnel probe now runs through `-m renquant_orchestrator
           daily-bridge --repo-dir "$REPO_DIR"` (the SAME multirepo bridge
           the real order run uses, daily_104.sh:410) instead of `-m
           live.runner` directly. One-line rollback: restore the
           `-m live.runner` prefix.

WHY/DIR:   Root-caused 2026-08-10: the direct `-m live.runner` invocation
           resolves the top-level `kernel` package to the umbrella-VENDORED
           June-vintage kernel (`RenQuant/backtesting/renquant_104/kernel/`,
           preflight.py mtime 2026-06-12) which PREDATES RFC#210 (added
           2026-08-04) and has no `rfc210_license.py`. So the probe hard-
           refused P-WF-GATE on the served `passed=False`
           freshness_fallback_rfc210 artifact (trained 2026-08-02, 8d ≤ 28d
           SLA), emitting a daily HARD-refuse the actual order path does NOT
           produce. The order path (daily_104.sh / intraday_104) routes
           kernel.* through the PINNED subrepos ("[multirepo] routed 57
           lifted modules through sibling subrepos") and honors RFC#210.
           A preview probe is only faithful if it evaluates the gate the
           order run will actually run. This aligns with the sanctioned
           migration (`renquant_orchestrator scheduled-jobs
           --fail-on-umbrella-bridge`) to move scheduled jobs off umbrella
           code.

           SCOPE NOTE (visible correction): this does NOT resume buys. The
           live buy-halt is a DELIBERATE sell-only containment
           ("diagnostic-only scorer deployment pending", daily104 launchd
           stdout 2026-08-07 13:55, exit 0) — orthogonal to this probe. This
           change only removes a false alarm on the monitoring surface.

EVIDENCE:  artifact:      ops/renquant104/dawn_funnel_preflight.sh (1 invocation
                          line + its rationale comment) [VERIFIED — mirrors the
                          working daily_104.sh:410 daily-bridge pattern; the
                          pinned kernel returns served=True on the served
                          artifact, measured 2026-08-10]
           prod or exp:   readonly monitoring probe; no order/state/DB/notify
                          side effects (the probe's own fail-closed attestation
                          enforces this); no deploy in this PR
           existing data: daily_104.sh:410/435 (the order path already uses this
                          exact bridge); the umbrella vendored kernel lacks rfc210
           best-known?:   yes — makes the probe faithful to the order path; the
                          alternative (leave umbrella) keeps a daily false refuse
           scope:         one ops script + this doc

RISKS (for review — validate before deploy):
  - daily-bridge vs live-bridge: daily-bridge chosen to match the ORDER path
    exactly (daily_104.sh); it forwards trailing runner args as REMAINDER.
    Confirm `--strategy-config-path` + `--preflight` forward cleanly through
    the bridge (daily_104.sh forwards --strategy/--broker/--once/--sell-only).
  - the bridge prepends "[multirepo] routed N lifted modules…" stdout lines;
    confirm dawn_preflight_attest.py + dawn_funnel_analyze.py still locate the
    `preflight_attestation:` line and the gate lines (they scan for specific
    tokens, so prefix lines should be inert — verify on a scratch run).
  - PRE-DEPLOY: a real scratch preflight run through the bridge, output to a
    scratch path (NOT the dated log — the wrapper truncates it) with MLflow
    disabled, asserting attestation persisted:false/notified:false/
    reached_decision:true AND P-WF-GATE previews the pinned gate's verdict.

TESTS:     `renquant_orchestrator scheduled-jobs --fail-on-umbrella-bridge`
           should no longer flag the dawn preflight job after deploy.

NEXT:      codex review; then operator-gated pin sync of the -run checkout.
