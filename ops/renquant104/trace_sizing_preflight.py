#!/usr/bin/env python3
"""Run the dawn preflight with every sizing call traced. Places NO orders.

WHY (P0 orch#851): on 2026-07-28 the live book took two buys at ~23 % of
equity each, against a 12 % cap. Four rounds of static analysis could not
reproduce them: every value recorded on the trade rows — `max_pct`, conviction,
sigma_mult, portfolio value, cash — is internally consistent and yields **zero
shares** through the deployed `compute_position_size`.

The decisive evidence turned out to be sitting in `logs/rq104/`: the
**dawn preflight**, a scheduled dry run whose attestation is
`{"ordered": false, "persisted": false, "notified": false}`, reproduces the
same oversized decisions on 07-27, 07-28, 08-03 and 08-04 `[VERIFIED]`. So the
defect is observable **without touching money**, and this is the harness that
observes it.

WHAT IT SHOWS. Every call to `compute_position_size` with its full argument
list and return value, so the effective `max_pct` at the emit site is visible
rather than inferred. The trade row already records a `max_pct`, and it is
**correct** — that is precisely why static reconstruction failed.

WHAT IT DOES NOT DO. Place orders, persist state, notify, or promote anything:
it runs `live.runner --preflight --broker readonly-alpaca` against the PINNED
strategy config, exactly as `dawn_funnel_preflight.sh` does. The only writes are
this trace's own stdout.

CAVEAT, and it is why this is a harness rather than an answer: sizing is only
reached when the funnel has an **open slot**. On a day when the book is full
(as 2026-08-05 was), the run reaches its decision without calling the sizer at
all and the trace is legitimately empty. That is not a failure of the harness —
but it does mean the answer arrives on the next day with an open slot, not on
demand.

Usage (must run under the daily wrapper's PYTHONPATH — see
`ops/renquant104/dawn_funnel_preflight.sh` for the exact environment):
    python ops/renquant104/trace_sizing_preflight.py [--config PATH]
"""
from __future__ import annotations

import argparse
import runpy
import sys

DEFAULT_CONFIG = ("/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/"
                  "renquant-strategy-104/configs/strategy_config.json")

TRACE_PREFIX = "TRACE_SIZE"


def install_trace(out=sys.stdout) -> None:
    """Wrap `compute_position_size` in the module that defines it.

    VERIFIED before relying on it: `SizeAndEmitTask` imports the symbol
    **inside `run()`** (`task_selection.py:215`, a function-local import), not
    at module scope. So the name is resolved from the defining module on every
    invocation, and patching that module IS sufficient — there is no import-time
    binding to chase.

    I first wrote this the other way round, patching a module attribute that
    does not exist, and the test caught it. A tracer that silently traces
    nothing is the same failure as a guard that silently passes, so the
    installation announces itself and a test asserts the call site resolves
    through the patched module.
    """
    import renquant_pipeline.kernel.sizing as SZ

    original = SZ.compute_position_size

    def traced(pv, cash, max_pct, reserve_pct, price, override_pct=None, **kw):
        result = original(pv, cash, max_pct, reserve_pct, price,
                          override_pct=override_pct, **kw)
        print(f"{TRACE_PREFIX} pv={pv:.2f} cash={cash:.2f} max_pct={max_pct:.8f} "
              f"reserve={reserve_pct} price={price:.2f} override={override_pct} "
              f"kw={kw} -> {result}", file=out, flush=True)
        return result

    SZ.compute_position_size = traced
    print(f"{TRACE_PREFIX} installed on renquant_pipeline.kernel.sizing "
          f"(task_selection imports it per-call, so this covers the call site)",
          file=out, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args(argv)
    install_trace()
    sys.argv = ["live.runner", "--strategy", "renquant_104",
                "--broker", "readonly-alpaca",
                "--strategy-config-path", args.config,
                "--preflight"]
    runpy.run_module("live.runner", run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
