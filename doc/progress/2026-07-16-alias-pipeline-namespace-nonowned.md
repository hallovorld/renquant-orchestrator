# Fix: alias non-owned kernel stems under the pipeline namespace too

STATUS: delivered
WHAT: `bootstrap_multirepo` force-aliased non-owned stems only as
`kernel.<stem>`; the pinned pipeline's own modules import them under the
PIPELINE namespace (`pp_inference` lazily imports
`renquant_pipeline.kernel.meta_label.task_meta_label_veto`, which exists
only in the authoritative renquant-backtesting copy — the pipeline's
physical meta_label is a declared-non-authoritative partial lift shipping
only triple_barrier). The first full daily after the F-8 pin sync
(2026-07-16) died mid-run with ModuleNotFoundError at MetaLabelVetoTask.
Fix: also `_force_alias(f"renquant_pipeline.kernel.{stem}", target)` in
the same loop.
WHY/DIR: 07-16 incident recovery — last blocker between the governed
diagnostic-only override (deployed) and a completed qualifying daily run.
EVIDENCE: reproduced the failing import in the live env pre-fix; post-fix
it resolves from
`.subrepo_runtime/repos/renquant-backtesting/.../task_meta_label_veto.py`.
`tests/test_live_bridge.py` regression asserts both namespaces are
aliased. Full suite 3961 passed.
NEXT: none (pin bump + live rerun handled operationally).
