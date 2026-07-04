"""expkit plugins: experiments expressed as FrozenSpec + callbacks.

Each plugin module exposes a `build_*_plugin(...)` factory returning an
`ExperimentPlugin`; import the module directly (kept lazy — no eager imports
here, so `python -m renquant_orchestrator.expkit.plugins.<name>` runs clean
and heavy substrate deps never load on package import).

Residents:
- `c2_quality` — the migration proof: the merged C2 quality-composite
  measurement (#275) re-expressed on the library, with a regression fixture
  proving its committed evidence values reproduce
  (tests/test_expkit_c2_regression.py).
"""
