# CI fix: gate-stamp-parity ack census renewal (48/16/0/32)

STATUS:   delivered. 1 pre-existing test failure fixed by renewing the
          gate-stamp-parity ack with current census numbers.
WHY/DIR:  the ack was filed 2026-08-29 with census 46/16/0/30. Two new
          canonical-only artifacts appeared (census now 48/16/0/32), which
          flipped the ack to ACKED_BUT_CHANGED — the test expected ACKED.
          The parity situation is identical: 16 both-copy, 0 served, 32
          canonical-only (was 30). The 2 new artifacts each carry ONE gate
          stamp and cannot disagree with themselves.
EVIDENCE:
  artifact:      ops/ops_audit_acks.json: numbers_when_acked updated,
                 acked_at advanced to 2026-08-31, expires_at 2026-09-14.
  prod or exp:   exp — read-only detector run confirmed 48/16/0/32
                 [VERIFIED — gate_stamp_parity.py run 2026-08-31].
  scope:        1 ops contract file. No code change.
REVIEW:    codex (haorensjtu-dev).
