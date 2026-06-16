"""Scheduled-job wrapper for native live market snapshots."""
from __future__ import annotations

from .native_live_snapshots import market_main as main


__all__ = ["main"]
