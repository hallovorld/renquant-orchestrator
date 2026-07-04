# S-TC: transfer coefficient measurement module

DATE: 2026-07-04

## What

New module `transfer_coefficient.py` that measures TC = corr(w_kelly, w_qp) per
run from the live run DB (read-only). The Grinold-Kahn value equation
IR = TC x IC x sqrt(BR) makes TC a key lever.

## Key finding

TC mean = -0.43 on 18 live runs with QP weights populated. The QP optimizer
is anti-correlated with the Kelly targets. Decomposition: blocking 15.5%,
shrinkage 38%, expansion 46.5%.

## Delivered

- `src/renquant_orchestrator/transfer_coefficient.py` (10 tests passing)
- `doc/progress/2026-07-04-s-tc-transfer-coefficient.md`
