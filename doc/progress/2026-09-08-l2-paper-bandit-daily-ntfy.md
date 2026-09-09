# The MoE L2 lane says what it did: daily ntfy on both outcomes   (PR #TBD)

STATUS:    delivered — G-A/G-D: the lane has run daily since 2026-09-03 with
           NO alert path of any kind.
WHAT:      `l2_paper_bandit.py` gains `format_notification(status, …)` (pure,
           returns `(title, body, priority)`) and posts it through the
           canonical `renquant_common.notify.send` to topic `renquant`:
           * SYNCED → `RenQuant MoE L2 paper-bandit <asof>`, priority 3:
             rows appended, every arm with its Hedge weight and 1-day return
             (weight-sorted), the mixture value against the champion with the
             signed difference and the best fixed arm, and one line stating
             these are PAPER books — regret, not a profitability claim, and
             no order is placed from this lane.
           * REFUSED → `RenQuant MoE L2 REFUSED`, priority 4: the refusal
             reason plus the fact that the self-verifying log appended
             NOTHING and will refuse every run until the divergence is
             explained.
           Default is production-only: a run with an explicit `--log-dir`
           (the documented pre-14:30 dry run into scratch) stays silent;
           `--notify` / `--no-notify` override either way, `--topic`
           redirects. stdout stays ONE parseable JSON object — the alert
           text rides inside it as `notification{title,body,sent}`, so the
           launchd log and the operator see the same words and the existing
           CLI contract (and its test) is unchanged. No plist edit: the
           installed job already invokes the module with no `--log-dir`, so
           it starts notifying on the first run after the `-run` sync.
WHY/DIR:   `com.renquant.l2-paper-bandit` has fired every weekday at 15:45
           since 2026-09-03 and its only outputs were two JSONL files and a
           launchd stdout log nobody reads. The operator asked repeatedly to
           see the MoE messages and there were none to see — the
           deployed-but-dark class: a lane whose whole value is the evidence
           trail, invisible. The REFUSED half matters more: the engine
           replays the full history every run and refuses forever once any
           existing row diverges, so a silent refusal freezes the lane
           indefinitely with no signal — exactly the fail-closed-in-silence
           shape this repo keeps paying for.
EVIDENCE:  artifact:      installed plist `ProgramArguments = [python, -m, renquant_orchestrator.l2_paper_bandit]` — no notify flag; `grep -n "notify\|ntfy" l2_paper_bandit.py` at 0474af18 → no match [VERIFIED — read 2026-09-08 ~22:35 PDT]
           prod or exp:   prod ops surface (one new daily operator alert; the lane places no orders, and no scoring/log/serving behaviour changes)
           existing data: `tests/test_l2_paper_bandit_notify.py` (11 cases: both message shapes, priority ordering, unmarked arm named not dropped, partial mixture safe, production-default notifies, scratch dry run silent, both flag overrides, refusal pages at priority 4, stdout stays one JSON object) + the existing `tests/test_l2_paper_bandit.py` = 22 passed [VERIFIED — 2026-09-08 between 22:40 and 22:55 PDT]; read-only run of the patched module against the REAL arm books into a scratch log dir: `status SYNCED | appended 98 | SENT: False` and the body it would post is byte-for-byte the message the operator received by hand at 22:33 (`mixture 1.045261 vs champion 1.079581 (-0.03432)`) [VERIFIED — same window, nothing posted]
           best-known?:   n/a — reporting only; no model or allocation claim. The mixture has trailed the champion since inception (−0.034 on 98 rows); the alert states that rather than hiding it
           scope:         "this adds an alert to one shadow lane; it does not change the Hedge update, the arm registry, the logs' contents, or any serving path"
NEXT:      after merge + `-run` sync the 15:45 run posts the first automatic
           MoE message. Follow-up (not here): the arms have been marked from
           sell-only sessions since 2026-09-04, so the daily returns are
           position-drift only — the message will start carrying decision
           information again once the 104 buy path reopens.
