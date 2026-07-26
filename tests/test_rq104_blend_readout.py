"""Tests for the blend-readout ledger job (pipeline#213 piece 3/3)."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

_P = Path(__file__).resolve().parents[1] / "ops" / "renquant104" / "rq104_blend_readout.py"
spec = importlib.util.spec_from_file_location("bro", _P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_zsum_blend_matches_frozen_construction():
    prod = pd.Series({"A": 2.0, "B": 1.0, "C": 0.0})
    clf = pd.Series({"A": 0.1, "B": 0.9, "C": 0.5})
    b = mod.zsum_blend(prod, clf)
    zp = (prod - prod.mean()) / prod.std()
    zc = (clf - clf.mean()) / clf.std()
    assert np.allclose(b.values, (zp + zc).values)
    # missing clf ticker -> clf term 0, prod term kept
    b2 = mod.zsum_blend(prod, clf.drop("C"))
    assert b2["C"] == ((prod - prod.mean()) / prod.std())["C"]


def test_top_n_deterministic_tiebreak():
    s = pd.Series({"B": 1.0, "A": 1.0, "C": 0.5})
    assert mod.top_n(s, 2) == ["A", "B"]  # tie -> ticker asc


def test_ledger_append_idempotent(tmp_path):
    led = tmp_path / "ledger.jsonl"
    row = {"run_date": "2026-07-27", "picks_prod": ["A"], "picks_blend": ["B"],
           "realized": False}
    assert mod.append_ledger(led, row) is True
    assert mod.append_ledger(led, row) is False
    assert len(led.read_text().splitlines()) == 1


def test_mature_fill_only_when_all_returns_present(tmp_path):
    led = tmp_path / "ledger.jsonl"
    row = {"run_date": "2026-06-01", "picks_prod": ["A", "B"],
           "picks_blend": ["B", "C"], "realized": False}
    led.write_text(json.dumps(row) + "\n")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE ticker_forward_returns (ticker TEXT, as_of_date TEXT, fwd_20d REAL)")
    db.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,?)",
                   [("A", "2026-06-01", 0.10), ("B", "2026-06-01", 0.02)])
    assert mod.mature_fill(led, db) == 0          # C missing -> not filled
    db.execute("INSERT INTO ticker_forward_returns VALUES ('C','2026-06-01',-0.04)")
    assert mod.mature_fill(led, db) == 1
    out = json.loads(led.read_text().splitlines()[0])
    assert out["realized"] and abs(out["spread_prod"] - 0.06) < 1e-9
    assert abs(out["spread_blend"] - (-0.01)) < 1e-9
