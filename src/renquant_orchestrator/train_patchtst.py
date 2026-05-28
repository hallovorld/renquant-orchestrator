#!/usr/bin/env python
"""PatchTST training, orchestrated through the pinned subrepos.

Runs the lifted HF PatchTST trainer (``renquant_model_patchtst.hf_trainer``, pin)
with its data-side ``kernel.*`` deps resolved from the umbrella via
``RENQUANT_STRATEGY_DIR`` — same model-in-subrepo / data-from-baseline split as
the GBDT driver.

PatchTST weights are NOT byte-reproducible (torch on Apple MPS is not
bit-deterministic even with a fixed seed), so parity is structural/procedural
(same lifted code + config contract + valid checkpoint), unlike the GBDT engine
which is byte-identical.

Usage (passes all args through to the trainer's CLI):
    python -m renquant_orchestrator.train_patchtst --cut cut1_covid --epochs 1 --device mps
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

GITHUB = Path(__file__).resolve().parents[3]          # …/github
UMBRELLA = GITHUB / "RenQuant"
STRATEGY_DIR = UMBRELLA / "backtesting" / "renquant_104"
_PIN_SRCS = ["renquant-common", "renquant-base-data", "renquant-artifacts", "renquant-model"]


def _bootstrap() -> None:
    for name in _PIN_SRCS:
        src = GITHUB / name / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
    os.environ.setdefault("RENQUANT_STRATEGY_DIR", str(STRATEGY_DIR))
    for p in (str(STRATEGY_DIR), str(UMBRELLA)):
        if p not in sys.path:
            sys.path.insert(0, p)


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    trainer = importlib.import_module("renquant_model_patchtst.hf_trainer")
    sys.stderr.write(
        f"[orchestrator.train_patchtst] trainer={trainer.__file__} (pin); "
        f"kernel.* data deps from {STRATEGY_DIR} (umbrella)\n"
    )
    sys.argv = [trainer.__file__] + (list(argv) if argv is not None else sys.argv[1:])
    trainer.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
