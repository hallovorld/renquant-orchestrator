"""Tests for SEC EDGAR XBRL harvester (scripts/sec_edgar_harvester.py)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import from scripts — add parent to path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from sec_edgar_harvester import (
    FIELDS,
    extract_facts,
    harvest,
    load_completed_tickers,
    parse_ticker_cik_map,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TICKER_CIK_JSON = {
    "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": "789019", "ticker": "MSFT", "title": "Microsoft Corporation"},
    "2": {"cik_str": "1018724", "ticker": "AMZN", "title": "Amazon.com Inc."},
}

SAMPLE_COMPANY_FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 94836000000,
                            "accn": "0000320193-22-000007",
                            "fy": 2022,
                            "fp": "Q1",
                            "form": "10-Q",
                            "filed": "2022-01-28",
                            "end": "2021-12-25",
                            "start": "2021-09-26",
                        },
                        {
                            "val": 365817000000,
                            "accn": "0000320193-21-000105",
                            "fy": 2021,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2021-10-29",
                            "end": "2021-09-25",
                            "start": "2020-09-27",
                        },
                        {
                            "val": 123456000000,
                            "accn": "0000320193-22-000099",
                            "fy": 2022,
                            "fp": "Q2",
                            "form": "8-K",
                            "filed": "2022-04-28",
                            "end": "2022-03-26",
                        },
                    ]
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income (Loss)",
                "units": {
                    "USD": [
                        {
                            "val": 34630000000,
                            "accn": "0000320193-22-000007",
                            "fy": 2022,
                            "fp": "Q1",
                            "form": "10-Q",
                            "filed": "2022-01-28",
                            "end": "2021-12-25",
                            "start": "2021-09-26",
                        },
                    ]
                },
            },
            "EarningsPerShareDiluted": {
                "label": "Earnings Per Share, Diluted",
                "units": {
                    "USD/shares": [
                        {
                            "val": 2.10,
                            "accn": "0000320193-22-000007",
                            "fy": 2022,
                            "fp": "Q1",
                            "form": "10-Q",
                            "filed": "2022-01-28",
                            "end": "2021-12-25",
                            "start": "2021-09-26",
                        },
                    ]
                },
            },
            "Assets": {
                "label": "Assets",
                "units": {
                    "USD": [
                        {
                            "val": 381191000000,
                            "accn": "0000320193-22-000007",
                            "fy": 2022,
                            "fp": "Q1",
                            "form": "10-Q",
                            "filed": "2022-01-28",
                            "end": "2021-12-25",
                        },
                    ]
                },
            },
        }
    },
}


# ---------------------------------------------------------------------------
# Tests: CIK mapping
# ---------------------------------------------------------------------------


class TestTickerCikMap:
    def test_parse_basic(self):
        result = parse_ticker_cik_map(SAMPLE_TICKER_CIK_JSON)
        assert result["AAPL"] == 320193
        assert result["MSFT"] == 789019
        assert result["AMZN"] == 1018724

    def test_parse_uppercases(self):
        data = {"0": {"cik_str": "123", "ticker": "grmn", "title": "Garmin"}}
        result = parse_ticker_cik_map(data)
        assert "GRMN" in result

    def test_parse_skips_missing_fields(self):
        data = {
            "0": {"cik_str": "123", "ticker": "AAPL", "title": "Apple"},
            "1": {"cik_str": "456", "title": "No Ticker"},
            "2": {"ticker": "NOCE", "title": "No CIK"},
        }
        result = parse_ticker_cik_map(data)
        assert len(result) == 1
        assert "AAPL" in result

    def test_parse_empty(self):
        assert parse_ticker_cik_map({}) == {}


# ---------------------------------------------------------------------------
# Tests: fact extraction
# ---------------------------------------------------------------------------


class TestExtractFacts:
    def test_extracts_all_fields(self):
        records = extract_facts("AAPL", SAMPLE_COMPANY_FACTS)
        fields = {r["field"] for r in records}
        assert "revenue" in fields
        assert "net_income" in fields
        assert "eps_diluted" in fields
        assert "total_assets" in fields

    def test_preserves_filed_date(self):
        records = extract_facts("AAPL", SAMPLE_COMPANY_FACTS)
        revenue_q1 = [
            r for r in records if r["field"] == "revenue" and r["fiscal_period"] == "Q1"
        ]
        assert len(revenue_q1) == 1
        assert revenue_q1[0]["filed_date"] == "2022-01-28"

    def test_filters_10k_10q_only(self):
        records = extract_facts("AAPL", SAMPLE_COMPANY_FACTS)
        forms = {r["form"] for r in records}
        assert forms <= {"10-K", "10-Q"}
        assert "8-K" not in forms

    def test_revenue_count(self):
        records = extract_facts("AAPL", SAMPLE_COMPANY_FACTS)
        revenues = [r for r in records if r["field"] == "revenue"]
        assert len(revenues) == 2  # Q1 (10-Q) + FY (10-K); 8-K filtered out

    def test_eps_uses_usd_per_shares(self):
        records = extract_facts("AAPL", SAMPLE_COMPANY_FACTS)
        eps = [r for r in records if r["field"] == "eps_diluted"]
        assert len(eps) == 1
        assert eps[0]["value"] == 2.10

    def test_record_structure(self):
        records = extract_facts("AAPL", SAMPLE_COMPANY_FACTS)
        rec = records[0]
        required_keys = {
            "ticker", "field", "xbrl_tag", "value", "filed_date",
            "period_end", "fiscal_year", "fiscal_period", "form",
            "accession_number", "source",
        }
        assert required_keys <= set(rec.keys())
        assert rec["source"] == "sec_edgar_xbrl"
        assert rec["ticker"] == "AAPL"

    def test_empty_facts(self):
        empty = {"facts": {"us-gaap": {}}}
        records = extract_facts("XYZ", empty)
        assert records == []

    def test_missing_us_gaap(self):
        no_gaap = {"facts": {}}
        records = extract_facts("XYZ", no_gaap)
        assert records == []


# ---------------------------------------------------------------------------
# Tests: resumability
# ---------------------------------------------------------------------------


class TestResumability:
    def test_load_completed_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.touch()
        assert load_completed_tickers(p) == set()

    def test_load_completed_nonexistent(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        assert load_completed_tickers(p) == set()

    def test_load_completed_with_data(self, tmp_path):
        p = tmp_path / "out.jsonl"
        p.write_text(
            json.dumps({"ticker": "AAPL", "field": "revenue"}) + "\n"
            + json.dumps({"ticker": "AAPL", "field": "net_income"}) + "\n"
            + json.dumps({"ticker": "GRMN", "field": "revenue"}) + "\n"
        )
        result = load_completed_tickers(p)
        assert result == {"AAPL", "GRMN"}

    def test_load_completed_handles_bad_json(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text('{"ticker": "AAPL"}\nnot json\n{"ticker": "MU"}\n')
        result = load_completed_tickers(p)
        assert result == {"AAPL", "MU"}


# ---------------------------------------------------------------------------
# Tests: harvest integration (mocked HTTP)
# ---------------------------------------------------------------------------


class TestHarvest:
    def _mock_session(self):
        session = MagicMock()

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "companyfacts" in url:
                resp.status_code = 200
                resp.json.return_value = SAMPLE_COMPANY_FACTS
            else:
                resp.status_code = 200
                resp.json.return_value = SAMPLE_TICKER_CIK_JSON
            resp.raise_for_status = MagicMock()
            return resp

        session.get.side_effect = get_side_effect
        return session

    @patch("sec_edgar_harvester.time.sleep")
    def test_harvest_basic(self, mock_sleep):
        session = self._mock_session()
        cik_map = {"AAPL": 320193}
        records = harvest(["AAPL"], session=session, ticker_cik_map=cik_map)
        assert len(records) > 0
        assert all(r["ticker"] == "AAPL" for r in records)

    @patch("sec_edgar_harvester.time.sleep")
    def test_harvest_writes_jsonl(self, mock_sleep, tmp_path):
        session = self._mock_session()
        cik_map = {"AAPL": 320193}
        output = tmp_path / "out.jsonl"
        harvest(["AAPL"], output, session=session, ticker_cik_map=cik_map)
        lines = output.read_text().strip().splitlines()
        assert len(lines) > 0
        for line in lines:
            rec = json.loads(line)
            assert "ticker" in rec
            assert "filed_date" in rec

    @patch("sec_edgar_harvester.time.sleep")
    def test_harvest_skips_completed(self, mock_sleep, tmp_path):
        session = self._mock_session()
        cik_map = {"AAPL": 320193, "GRMN": 1121788}
        output = tmp_path / "out.jsonl"
        output.write_text(json.dumps({"ticker": "AAPL", "field": "revenue"}) + "\n")
        records = harvest(
            ["AAPL", "GRMN"], output, session=session, ticker_cik_map=cik_map
        )
        assert all(r["ticker"] == "GRMN" for r in records)

    @patch("sec_edgar_harvester.time.sleep")
    def test_harvest_missing_cik(self, mock_sleep):
        session = self._mock_session()
        cik_map = {}
        records = harvest(["ZZZZZ"], session=session, ticker_cik_map=cik_map)
        assert records == []

    @patch("sec_edgar_harvester.time.sleep")
    def test_harvest_404_graceful(self, mock_sleep):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 404
        session.get.return_value = resp
        cik_map = {"AAPL": 320193}
        records = harvest(["AAPL"], session=session, ticker_cik_map=cik_map)
        assert records == []


# ---------------------------------------------------------------------------
# Tests: output format
# ---------------------------------------------------------------------------


class TestOutputFormat:
    def test_jsonl_roundtrip(self, tmp_path):
        records = extract_facts("AAPL", SAMPLE_COMPANY_FACTS)
        output = tmp_path / "test.jsonl"
        with open(output, "w") as f:
            for rec in records:
                f.write(json.dumps(rec, sort_keys=True) + "\n")

        loaded = []
        with open(output) as f:
            for line in f:
                loaded.append(json.loads(line))

        assert len(loaded) == len(records)
        for orig, read in zip(records, loaded):
            assert orig["ticker"] == read["ticker"]
            assert orig["filed_date"] == read["filed_date"]
            assert orig["value"] == read["value"]
