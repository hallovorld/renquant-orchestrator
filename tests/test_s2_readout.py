"""CI-runnable positive controls for the S2 readout's DECISION LOGIC
(mandatory per the frozen prereg; the only runs allowed before session 20).

[codex on orch#783 round 3] The provider loader is injected behind
``run_readout``'s ``momentum_loader`` seam, so the extension verdict,
canonical-run selection, coverage handling, and identity recording are all
executed on hosted CI with a FAKE loader — the REAL ledger/artifact
verification lives in pipeline#262's own suite, and one optional
integration test here exercises the real provider when installed."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))

import s2_readout as s2  # noqa: E402

SESSIONS = [f"2026-09-{d:02d}" for d in range(1, 21)]
CUTOFFS = {s: f"{s}T20:00:00+00:00" for s in SESSIONS}
UNIVERSE = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


def _mk_runs_db(path: Path, per_session_scores: dict[str, dict[str, float]],
                *, decoy_runs: int = 0,
                decoy_scores: "dict[str, float] | None" = None) -> None:
    """decoy_runs adds same-day holding-only runs (the live intraday
    pattern: 21-35 runs/session measured 2026-08-04, exactly one carrying
    candidate rows); decoy_scores adds a candidate-carrying decoy with a
    LOWER run_id which the lexicographically-last rule must ignore."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT)")
    con.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT, rank_score REAL)")
    for i, (session, scores) in enumerate(per_session_scores.items()):
        rid = f"{session}-live-zz{i}"
        con.execute("INSERT INTO pipeline_runs VALUES (?,?)", (rid, session))
        for t, sc in scores.items():
            con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (rid, t, "candidate", sc))
        con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (rid, "HOLD1", "holding", 99.0))
        for d in range(decoy_runs):
            drid = f"{session}-live-aa{d}"
            con.execute("INSERT INTO pipeline_runs VALUES (?,?)", (drid, session))
            con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (drid, "HOLD1", "holding", 42.0))
        if decoy_scores:
            drid = f"{session}-live-mm0"   # sorts BELOW zz -> must be ignored
            con.execute("INSERT INTO pipeline_runs VALUES (?,?)", (drid, session))
            for t, sc in decoy_scores.items():
                con.execute("INSERT INTO candidate_scores VALUES (?,?,?,?)", (drid, t, "candidate", sc))
    con.commit(); con.close()


def _mk_fwd_db(path: Path, per_session_returns: dict[str, dict[str, float]]) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE ticker_forward_returns (as_of_date TEXT, ticker TEXT, fwd_1d REAL)")
    for session, rets in per_session_returns.items():
        for t, r in rets.items():
            con.execute("INSERT INTO ticker_forward_returns VALUES (?,?,?)", (session, t, r))
    con.commit(); con.close()


class _FakeLoader:
    """The injected provider seam: records every (session, cutoff) call and
    serves the configured scores + identity, or None (a coverage miss)."""

    def __init__(self, scores: "dict[str, float] | None",
                 identity: "dict | None" = None,
                 per_session: "dict[str, object] | None" = None):
        self.scores = scores
        self.identity = identity or {"row_index": 0, "row_sha": "sha256:aa",
                                     "artifact_content_sha256": "sha256:bb",
                                     "cutoff_date": "2026-08-28",
                                     "params_version": "v0"}
        self.per_session = per_session or {}
        self.calls: list[tuple] = []

    def __call__(self, ledger_path, *, session_date, session_cutoff_utc):
        self.calls.append((str(ledger_path), session_date, session_cutoff_utc))
        if session_date in self.per_session:
            return self.per_session[session_date]
        if self.scores is None:
            return None
        return dict(self.scores), dict(self.identity)


MOM_SCORES = {"EEE": 9.0, "DDD": 8.0, "CCC": 1.0, "AAA": 0.5, "BBB": 0.2, "FFF": 0.1}


def _standard_world(tmp_path: Path, *, blend_beats_prod: bool = True,
                    decoy_runs: int = 0, decoy_scores=None):
    prod_scores, blend_scores, fwd = {}, {}, {}
    for sess in SESSIONS:
        fwd[sess] = {"AAA": -0.01, "BBB": -0.01, "CCC": 0.0,
                     "DDD": 0.01, "EEE": 0.01, "FFF": 0.0}
        prod_scores[sess] = {"AAA": 6.0, "BBB": 5.0, "CCC": 4.0,
                             "DDD": 3.0, "EEE": 2.0, "FFF": 1.0}
        blend_scores[sess] = ({"DDD": 6.0, "EEE": 5.0, "CCC": 4.0,
                               "AAA": 3.0, "BBB": 2.0, "FFF": 1.0}
                              if blend_beats_prod else dict(prod_scores[sess]))
    prod_db = tmp_path / "prod.db"
    _mk_runs_db(prod_db, prod_scores, decoy_runs=decoy_runs, decoy_scores=decoy_scores)
    blend_db = tmp_path / "blend.db"; _mk_runs_db(blend_db, blend_scores)
    fwd_db = tmp_path / "fwd.db"; _mk_fwd_db(fwd_db, fwd)
    return prod_db, blend_db, tmp_path / "momentum.jsonl", fwd_db


def test_positive_control_promote_interest_and_seam_contract(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    fake = _FakeLoader(MOM_SCORES)
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                         momentum_loader=fake)
    assert rep["verdict"] == "PROMOTE-INTEREST"
    assert rep["coverage_ok"] is True
    assert rep["matched_pairs"]["blend_vs_prod"]["mean_diff"] > 0
    # SEAM CONTRACT: one call per session, exact (session, cutoff) pairs,
    # and the SUPPLIED identity recorded verbatim per session.
    assert [(c[1], c[2]) for c in fake.calls] == [(s_, CUTOFFS[s_]) for s_ in SESSIONS]
    for rec in rep["per_session"]:
        assert rec["momentum_serving_identity"] == fake.identity
    # deterministic top-3 of MOM_SCORES within the prod universe:
    assert rep["per_session"][0]["momentum_basket"] == ["EEE", "DDD", "CCC"]


def test_canonical_run_selection_ignores_decoys(tmp_path):
    """[item 3] holding-only decoys AND a candidate-carrying lower-run_id
    decoy must not perturb the canonical selection."""
    decoy = {"FFF": 99.0, "CCC": 98.0, "AAA": 97.0}
    prod_db, blend_db, ledger, fwd_db = _standard_world(
        tmp_path, decoy_runs=3, decoy_scores=decoy)
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                         momentum_loader=_FakeLoader(MOM_SCORES))
    assert rep["per_session"][0]["prod_basket"] == ["AAA", "BBB", "CCC"]
    assert rep["verdict"] == "PROMOTE-INTEREST"


def test_first_coverage_miss_extends_second_closes(tmp_path):
    """[item 1] first 20-session coverage miss -> EXTEND; with the
    extension used -> INSUFFICIENT; a winning blend never promotes
    through a miss in either phase."""
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    absent = _FakeLoader(None)   # momentum always missing
    rep1 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                          momentum_loader=absent)
    assert rep1["coverage_ok"] is False
    assert rep1["verdict"] == "EXTEND"
    assert rep1["matched_pairs"]["blend_vs_prod"]["mean_diff"] > 0
    rep2 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                          momentum_loader=absent, extension_used=True)
    assert rep2["verdict"] == "INSUFFICIENT RECORD — no promotion interest"


def test_partial_momentum_coverage_below_threshold(tmp_path):
    """Momentum missing on 2/20 sessions -> 18 matched < the 19 floor."""
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    fake = _FakeLoader(MOM_SCORES, per_session={s_: None for s_ in SESSIONS[:2]})
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                         momentum_loader=fake)
    assert rep["matched_pairs"]["blend_vs_momentum"]["n"] == 18
    assert rep["verdict"] == "EXTEND"


def test_placebo_is_deterministic_and_seeded(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    r1 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                        momentum_loader=_FakeLoader(MOM_SCORES))
    r2 = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                        momentum_loader=_FakeLoader(MOM_SCORES))
    b1 = [rec["placebo_basket"] for rec in r1["per_session"]]
    assert b1 == [rec["placebo_basket"] for rec in r2["per_session"]]
    assert len({tuple(b) for b in b1}) > 1


def test_window_size_is_enforced(tmp_path):
    prod_db, blend_db, ledger, fwd_db = _standard_world(tmp_path)
    with pytest.raises(SystemExit, match="exactly 20"):
        s2.run_readout(SESSIONS[:5], prod_db, blend_db, ledger, fwd_db, CUTOFFS,
                       momentum_loader=_FakeLoader(MOM_SCORES))


# ── optional integration: the REAL provider, when installed ─────────────────

def test_real_provider_integration_when_installed(tmp_path):
    """Runs only where the model+pipeline distributions exist (operator
    machine); hosted CI skips THIS TEST ONLY, not the decision suite."""
    mm = pytest.importorskip("renquant_model_momentum")
    pytest.importorskip("renquant_pipeline.kernel.panel_pipeline.momentum_residual_scorer")
    from renquant_model_momentum.ledger import row_sha256_of
    import numpy as np
    import pandas as pd

    class _Readers:
        def __init__(self, universe, asof, seed):
            idx = pd.bdate_range(end=pd.Timestamp(asof), periods=90)
            rng = np.random.default_rng(seed)
            self._r = {t: pd.Series(rng.normal(0.001, 0.02, 90), index=idx)
                       for t in [*universe, "SPY"]}
            self._v = {t: pd.Series(rng.integers(1000, 9999, 90).astype(float), index=idx)
                       for t in universe}
            self._s = {t: ("TECH" if i % 2 else "ENER") for i, t in enumerate(universe)}
        def tr_returns(self, t): return self._r.get(t)
        def volume(self, t): return self._v.get(t)
        def market_tr_returns(self): return self._r["SPY"]
        def sector_of(self): return dict(self._s)
        def read_digests(self): return {"synthetic": "0" * 64}

    params = {"params_version": "v0", "window": 60, "skip": 5, "min_obs": 30,
              "min_features": 2, "names_per_date_floor": 3, "min_side_obs": 5}
    root = tmp_path / "momentum"; root.mkdir()
    artifact = mm.train_momentum_artifact(
        "2026-08-28", UNIVERSE, params, readers=_Readers(UNIVERSE, "2026-08-28", 7))
    dated = root / "2026-08-28" / "momentum_residual_v0.json"
    dated.parent.mkdir(parents=True)
    dated.write_text(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n",
                     encoding="utf-8")
    ledger = root / "momentum_artifact_ledger.jsonl"
    mm.append_to_artifact_ledger(artifact, ledger)
    rows = [json.loads(l) for l in ledger.read_text().strip().splitlines()]
    rows[0]["appended_at_utc"] = "2026-08-28T12:00:00+00:00"
    rows[0]["prev_row_sha"] = None
    rows[0]["row_sha"] = row_sha256_of(rows[0])
    ledger.write_text(json.dumps(rows[0], sort_keys=True, separators=(",", ":")) + "\n",
                      encoding="utf-8")

    prod_db, blend_db, _l, fwd_db = _standard_world(tmp_path)
    rep = s2.run_readout(SESSIONS, prod_db, blend_db, ledger, fwd_db, CUTOFFS)
    first = rep["per_session"][0]
    assert first["momentum_serving_identity"]["row_index"] == 0
    assert first["momentum_serving_identity"]["artifact_content_sha256"] == artifact["content_sha256"]
