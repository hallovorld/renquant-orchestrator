"""Scheduled-job wrapper for native live account snapshots."""
from __future__ import annotations

from .native_live_snapshots import account_main as main


__all__ = ["main"]
