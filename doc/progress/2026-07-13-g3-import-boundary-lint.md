# 2026-07-13 G3 import boundary lint (V-018 remediation)

Ported the renquant-model import boundary test pattern to renquant-orchestrator.
The existing test checked broker/torch/xgboost prefixes; this PR adds
`renquant_pipeline.kernel` to the forbidden list (V-018) and adds parametrized
tests for the three known V-005 violation modules (`native_context_hydration`,
`live_bridge`, `train_gbdt`) that verify their kernel imports remain deferred
(not eagerly loaded at module import time).

## Update: codex CHANGES_REQUESTED fix (same day)

Codex flagged that the `sys.modules` before/after diff was unsound in a
shared pytest process: several other suites (`test_d6_freeze_record.py`,
`test_native_context_hydration.py`, `test_live_bridge.py`,
`test_train_gbdt.py`) import real `renquant_pipeline.kernel` submodules
directly inside test bodies. Whichever runs first (`test_d6_freeze_record.py`
sorts before this file and does run first under `make test`) leaves kernel
cached in `sys.modules` for the rest of the session, so a later diff sees no
*new* kernel modules even when a target eagerly imports it — reproduced
empirically. Codex also noted the `ImportError -> skip` fallback lets a
known V-005 module go entirely unguarded.

Fix: every import check now runs in a fresh subprocess (immune to
same-process module caching regardless of test order), and the ImportError
fallback only skips when the full multirepo environment is genuinely absent
(probed via `renquant_common`) — otherwise it fails loudly, since this is
the only CI job (`ci.yml`'s "Full multirepo test") that ever collects this
file. Added three regression tests proving the harness actually has teeth:
it flags an eager top-level kernel import, ignores a deferred one, and is
not fooled even when the parent process's `sys.modules` is deliberately
poisoned with a stand-in kernel package first (the exact bug reported).
