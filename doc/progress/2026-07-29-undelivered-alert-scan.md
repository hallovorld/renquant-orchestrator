# Progress: an alarm raised and never delivered is now a finding, not a log line

STATUS:   delivered (scan + 15 tests, run against the real fleet logs).
          NOT installed as a job — that is a machine landing and needs an
          operator grant. Runnable by hand today.

WHAT:     `ops/undelivered_alert_scan.py` — reads the fleet log tree for the
          sender's `ntfy send failed` marker, deduplicates by (title, class),
          and classifies each into PERMANENT (an encoding defect that will
          drop every future alarm from that call site) or transient (a network
          timeout). Exit 1 on any finding. Its own alert title is ASCII-only
          by construction, with a test pinning that: an alarm ABOUT
          undeliverable alarms must not be undeliverable for the same reason.

WHY/DIR:  Every sentinel in this fleet terminates in
          `renquant_common.notify.send`, which is deliberately built never to
          raise into a monitor — it swallows, counts, logs, returns False.
          Every caller ignores the return value, and `send_failure_count()`
          has NO consumer anywhere in the fleet. So a raised-but-undelivered
          alarm left evidence only in a log line nobody reads.

          What that cost, measured this session: the rq105 liveness alarm
          hard-codes a leading `🚨` in its title
          (`ops/renquant105/rq105_liveness_check.py:493`). HTTP header values
          go out as latin-1, so the request is unbuildable and the WHOLE
          notification is discarded. **That alarm could never have delivered a
          single notification in its life** — while its own output log shows
          collector issues on seven distinct July dates against three clean
          days, and today's run exited 1.

EVIDENCE: artifact: `ops/undelivered_alert_scan.py` +
                    `tests/test_undelivered_alert_scan.py`, this branch on
                    `renquant-orchestrator` @ origin/main.
  prod or exp:      PROD ops tooling, READ-ONLY. Reads log files; writes
                    nothing, installs nothing, sends nothing in `--dry-run`.
  existing data:    Yes — measured this session against the live log tree, not
                    recalled. **7 dropped alerts across 5 files**, in two
                    classes:
                      PERMANENT (3) — `rq105 DOWN` x2 (07-27, 07-28) and the
                        `rq104 blend` readout, all `'latin-1' codec can't
                        encode`;
                      transient (4) — `RUN-SURFACE DRIFT: 1 issue(s)` x2,
                        `RQ104 dawn preflight`, `RenQuant 104 WATCH`, all SSL
                        handshake/read timeouts.
                    Note the drift alarm itself is among the losses. rq105
                    liveness: `runs = 5`, `last exit code = 1`.
  best-known?:      Yes for what the logs record. NOT claimed: that these are
                    the only losses ever — the failure lines carry no
                    timestamp, so the scan bounds recency by file mtime and
                    can only see logs that still exist.
  scope:            `renquant-orchestrator` ops + tests. No pin advanced, no
                    umbrella change, no live surface mutated, no job installed.

SCOPE/LIMITS:
          This detects; it does not fix transport. The encoding half is fixed
          separately in `renquant-common#37` (RFC 2047 header encoding) — and
          that fix is MERGED-NOT-DEPLOYED until pins sync, so this scan stays
          useful in the interim and afterwards for the transient class, which
          #37 does not address (`send` still does a single POST with no retry).

VERIFICATION:
          `python3 ops/undelivered_alert_scan.py --dry-run` against the real
          log tree returns the 7 findings above, permanent first. 15 tests
          pass, built on verbatim lines from the live logs.

NEXT:     1. `send` has no retry; four of the seven losses were one unlucky
             handshake each. A bounded retry belongs in `renquant-common`
             beside #37, not here.
          2. Installing this as a scheduled job is a machine landing and needs
             an operator grant; until then it is a hand-run tool.
          3. The rq105 collector issues the lost alarms were reporting are a
             separate open question — they were never triaged because nobody
             was told.
