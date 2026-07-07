"""Modal app definition for remote sweep execution."""
from __future__ import annotations

import modal

VOLUME_NAME = "renquant-sweep-data"
APP_NAME = "renquant-sweep"

app = modal.App(APP_NAME)
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def build_image(bundle_dir: str) -> modal.Image:
    """Build a Modal image from a local bundle directory."""
    return (
        modal.Image.debian_slim(python_version="3.10")
        .pip_install(
            "pandas>=2.0",
            "numpy>=1.24",
            "scipy>=1.10",
            "scikit-learn>=1.2",
            "torch>=2.0",
            "xgboost>=1.7",
            "pyarrow>=12.0",
            "joblib>=1.2",
            "pyyaml>=6.0",
        )
        .copy_local_dir(bundle_dir, "/app")
        .env({
            "PYTHONPATH": (
                "/app/subrepos/renquant-common/src:"
                "/app/subrepos/renquant-base-data/src:"
                "/app/subrepos/renquant-artifacts/src:"
                "/app/subrepos/renquant-model/src:"
                "/app/subrepos/renquant-pipeline/src:"
                "/app/subrepos/renquant-execution/src:"
                "/app/subrepos/renquant-strategy-104/src:"
                "/app/subrepos/renquant-backtesting/src:"
                "/app/subrepos/renquant-orchestrator/src:"
                "/app/kernel:/app/sim:/app/scripts"
            ),
        })
    )
