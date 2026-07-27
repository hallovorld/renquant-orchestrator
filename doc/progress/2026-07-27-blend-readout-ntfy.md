# Blend readout: daily picks ntfy (operator visibility)

## STATUS
delivered

## WHAT
After appending each session's ledger row, the readout job sends one INFO
ntfy: the day's hypothetical blend top-10, prod's top-10, the divergence
(+adds/-drops), and clf coverage — explicitly labeled 陪跑/假想/不下单.
Best-effort (a notify failure never fails the ledger job); idempotent-skip
paths never re-notify.

## WHY/DIR
2026-07-27 operator: the shadow's picks were invisible outside a JSONL
only scripts read. This is the day-1 stopgap; the full PatchTST-parity
shadow lane (composite blend scorer driving the whole funnel minus order
submission, own runs DB, sized-order ntfy) is the follow-up build.

## EVIDENCE
Offline smoke: hook intercepts alert() with the exact formatted body;
syntax + import-path verified from the ops/ layout (liveness_common lives
one directory up).

## NEXT
Full-funnel shadow_blend lane: pipeline composite scorer kind -> strategy
shadow_blend profile -> orch daily shadow run + sized-order ntfy.
