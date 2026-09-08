"""Unit tests for the Colorado DWR/CDSS telemetry collector.

All HTTP calls are mocked; these tests never contact the live CDSS API.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from aquascope.collectors.colorado_cdss import CFS_TO_CMS, ColoradoCDSSCollector
from aquascope.schemas.water_data import DataSource, StreamflowReading

VALID_ROW = {
    "abbrev": "PLAKERCO",
    "parameter": "DISCHRG",
    "measDateTime": "2026-09-03T05:39:01-06:00",
    "measValue": 10.0,
    "measUnit": "cfs",
    "flagA": "",
    "flagB": "Published",
    "modified": "2026-09-03T06:00:00-06:00",
}


class TestColoradoCdssCollectorInit:
    def test_collector_name(self):
        assert ColoradoCDSSCollector(client=MagicMock()).name == "colorado_cdss"


class TestColoradoCDSSCollectorFetchRaw:
    def setup_method(self):
        self.client = MagicMock()
        self.collector = ColoradoCDSSCollector(client=self.client)

    def test_requires_station_abbreviation(self):
        with pytest.raises(ValueError, match="abbrev"):
            self.collector.fetch_raw(abbrev="")

    def test_builds_expected_request(self):
        self.client.get_json.return_value = {
            "PageNumber": 1,
            "PageCount": 1,
            "ResultCount": 1,
            "ResultDateTime": "2026-09-02T12:00:00-06:00",
            "ResultList": [VALID_ROW],
        }

        rows = self.collector.fetch_raw(
            abbrev="PLAKERCO",
            parameter="DISCHRG",
            startDate="09/01/2026",
            endDate="09/02/2026",
        )

        assert rows == [VALID_ROW]
        self.client.get_json.assert_called_once_with(
            "telemetrystations/telemetrytimeseriesraw",
            params={
                "format": "json",
                "abbrev": "PLAKERCO",
                "parameter": "DISCHRG",
                "startDate": "09/01/2026",
                "endDate": "09/02/2026",
            },
        )

    def test_includes_optional_api_key(self):
        client = MagicMock()
        client.get_json.return_value = {"ResultList": []}
        collector = ColoradoCDSSCollector(api_key="secret", client=client)

        collector.fetch_raw(abbrev="PLAKERCO")

        assert client.get_json.call_args.kwargs["params"]["apiKey"] == "secret"

    def test_extracts_rows_from_result_list_envelope(self):
        self.client.get_json.return_value = {
            "PageNumber": 1,
            "PageCount": 1,
            "ResultCount": 1,
            "ResultList": [VALID_ROW],
        }

        assert self.collector.fetch_raw(abbrev="PLAKERCO") == [VALID_ROW]

    def test_missing_result_list_returns_empty(self):
        self.client.get_json.return_value = {
            "PageNumber": 1,
            "PageCount": 0,
            "ResultCount": 0,
        }

        assert self.collector.fetch_raw(abbrev="PLAKERCO") == []

    def test_invalid_result_list_shape_returns_empty(self):
        self.client.get_json.return_value = {"ResultList": "invalid"}

        assert self.collector.fetch_raw(abbrev="PLAKERCO") == []

    def test_non_dictionary_items_are_removed(self):
        self.client.get_json.return_value = {"ResultList": [VALID_ROW, None, "invalid"]}

        assert self.collector.fetch_raw(abbrev="PLAKERCO") == [VALID_ROW]


class TestColoradoCDSSCollectorNormalise:
    def setup_method(self):
        self.collector = ColoradoCDSSCollector(client=MagicMock())

    def test_converts_cfs_to_streamflow_reading(self):
        records = self.collector.normalise([VALID_ROW])

        assert len(records) == 1
        record = records[0]
        assert isinstance(record, StreamflowReading)
        assert record.source == DataSource.COLORADO_CDSS
        assert record.station_id == "PLAKERCO"
        assert record.reading_datetime == datetime.fromisoformat("2026-09-03T05:39:01-06:00")
        assert record.discharge_cms == pytest.approx(10.0 * CFS_TO_CMS)
        assert record.source_type == "in_situ"
        assert record.unit == "m3/s"

    @pytest.mark.parametrize("unit", ["cfs", "CFS", "ft3/s", "ft³/s"])
    def test_accepts_supported_cfs_unit_spellings(self, unit):
        row = {**VALID_ROW, "measUnit": unit}

        assert len(self.collector.normalise([row])) == 1

    @pytest.mark.parametrize(
        "change",
        [
            {"measValue": None},
            {"measValue": "not-a-number"},
            {"measDateTime": "not-a-date"},
            {"measUnit": "m3/s"},
            {"abbrev": ""},
        ],
    )
    def test_skips_invalid_rows(self, change):
        row = {**VALID_ROW, **change}

        assert self.collector.normalise([row]) == []

    def test_skips_rows_with_missing_required_fields(self):
        assert self.collector.normalise([{"abbrev": "PLAKERCO"}]) == []

    def test_preserves_quality_flags_in_remark(self):
        row = {**VALID_ROW, "flagA": "Ice Affected", "flagB": "Provisional"}

        record = self.collector.normalise([row])[0]

        assert record.remark == "flagA=Ice Affected; flagB=Provisional"

    def test_collect_chains_fetch_and_normalise(self):
        client = MagicMock()
        client.get_json.return_value = {"ResultList": [VALID_ROW]}
        collector = ColoradoCDSSCollector(client=client)

        records = collector.collect(abbrev="PLAKERCO")

        assert len(records) == 1
        assert records[0].discharge_cms == pytest.approx(10.0 * CFS_TO_CMS)
