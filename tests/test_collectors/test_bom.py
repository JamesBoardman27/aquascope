"""Tests for the Australian Bureau of Meteorology (BOM) water data collector.

Station reference data:

- 410001 "M/BIDGEE R @ WAGGA" (Murrumbidgee River at Wagga Wagga) -- station
  number and live station_name confirmed against the real BOM Water Data
  Online API. Coordinates used below are an approximate town-centre
  location, not the verified exact gauge position.
- 410730 "Cotter R. at Gingera" (ACT) -- station number, name, and
  coordinates all confirmed against the live API and the BOM Hydrologic
  Reference Stations dataset:
  http://www.bom.gov.au/water/hrs/content/data/410730/410730_monthly_total_01.csv
"""

from __future__ import annotations

from unittest.mock import MagicMock

from aquascope.collectors.bom import (
    LEVEL_PARAMETERS,
    PARAMETER_UNITS,
    BOMCollector,
)
from aquascope.schemas.water_data import DataSource, WaterLevelReading, WaterQualitySample

STATION_LIST_RESPONSE = [
    ["station_name", "station_no", "station_latitude", "station_longitude"],
    ["M/BIDGEE R @ WAGGA", "410001", "-35.1082", "147.3598"],
]

STATION_LIST_NO_MATCH = ["No matches."]

# NOTE: getTimeseriesList intentionally receives no `returnfields` (BOM's
# KiWIS instance returns HTTP 500 for any returnfields value on this
# request type), so these fixtures use the server's *default* response
# columns -- notably no parametertype_unitname, which forces the
# PARAMETER_UNITS fallback in fetch_raw/normalise.
TS_LIST_RESPONSE = [
    ["station_name", "station_no", "station_id", "ts_id", "ts_name", "parametertype_id", "parametertype_name"],
    [
        "M/BIDGEE R @ WAGGA",
        "410001",
        "410123",
        "149310",
        "DMQaQc.Merged.DailyMean.24HR",
        "11762",
        "Water Course Discharge",
    ],
]

TS_LIST_LEVEL_RESPONSE = [
    ["station_name", "station_no", "station_id", "ts_id", "ts_name", "parametertype_id", "parametertype_name"],
    [
        "M/BIDGEE R @ WAGGA",
        "410001",
        "410123",
        "149355",
        "DMQaQc.Merged.DailyMean.24HR",
        "11763",
        "Water Course Level",
    ],
]

TS_LIST_NO_MATCH = ["No matches."]

TS_VALUES_RESPONSE = [
    {
        "ts_id": "149310",
        "columns": "Timestamp,Value,Quality Code",
        "data": [
            ["2023-07-15T00:00:00.000+10:00", "1234.5", "10"],
            ["2023-07-16T00:00:00.000+10:00", "1201.2", "10"],
            ["2023-07-17T00:00:00.000+10:00", "", "255"],
        ],
    }
]

SAMPLE_RAW = [
    {
        "station_no": "410001",
        "station_name": "M/BIDGEE R @ WAGGA",
        "parameter_type": "Water Course Discharge",
        "unit": "",  # not returned by default getTimeseriesList columns
        "latitude": -35.1082,
        "longitude": 147.3598,
        "timestamp": "2023-07-15T00:00:00.000+10:00",
        "value": "1234.5",
        "quality_code": "10",
    },
    {
        "station_no": "410001",
        "station_name": "M/BIDGEE R @ WAGGA",
        "parameter_type": "Water Course Level",
        "unit": "",
        "latitude": -35.1082,
        "longitude": 147.3598,
        "timestamp": "2023-07-15T00:00:00.000+10:00",
        "value": "2.31",
        "quality_code": "10",
    },
]


class TestBOMInit:
    def test_collector_name(self):
        assert BOMCollector().name == "bom"


class TestBOMFetchRaw:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.collector = BOMCollector(client=self.mock_client)

    def test_fetch_raw_requires_station_id(self):
        try:
            self.collector.fetch_raw(station_id="")
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "station_id" in str(exc)

    def test_fetch_raw_returns_merged_rows(self):
        self.mock_client.get_json.side_effect = [STATION_LIST_RESPONSE, TS_LIST_RESPONSE, TS_VALUES_RESPONSE]
        rows = self.collector.fetch_raw(station_id="410001", days=30)
        # The empty-value row (quality code 255) is passed through by fetch_raw;
        # filtering of missing values happens in normalise().
        assert len(rows) == 3
        assert rows[0]["station_no"] == "410001"
        assert rows[0]["station_name"] == "M/BIDGEE R @ WAGGA"
        # No parametertype_unitname in the default getTimeseriesList columns,
        # so fetch_raw falls back to the PARAMETER_UNITS table.
        assert rows[0]["unit"] == "m^3/s"
        assert rows[0]["latitude"] == -35.1082

    def test_fetch_raw_calls_station_list_then_timeseries_list_then_values(self):
        self.mock_client.get_json.side_effect = [STATION_LIST_RESPONSE, TS_LIST_RESPONSE, TS_VALUES_RESPONSE]
        self.collector.fetch_raw(station_id="410001", parameter_type="Water Course Discharge")
        calls = self.mock_client.get_json.call_args_list
        assert calls[0][1]["params"]["request"] == "getStationList"
        assert calls[1][1]["params"]["request"] == "getTimeseriesList"
        assert calls[2][1]["params"]["request"] == "getTimeseriesValues"

    def test_fetch_raw_omits_returnfields_from_timeseries_list(self):
        # Regression test: BOM's KiWIS instance returns HTTP 500 for *any*
        # returnfields value on getTimeseriesList (confirmed against the
        # live API -- not specific to lat/lon fields). getStationList is
        # unaffected and keeps its returnfields param.
        self.mock_client.get_json.side_effect = [STATION_LIST_RESPONSE, TS_LIST_RESPONSE, TS_VALUES_RESPONSE]
        self.collector.fetch_raw(station_id="410001")
        ts_list_params = self.mock_client.get_json.call_args_list[1][1]["params"]
        assert "returnfields" not in ts_list_params

    def test_fetch_raw_station_list_still_uses_returnfields(self):
        self.mock_client.get_json.side_effect = [STATION_LIST_RESPONSE, TS_LIST_RESPONSE, TS_VALUES_RESPONSE]
        self.collector.fetch_raw(station_id="410001")
        station_list_params = self.mock_client.get_json.call_args_list[0][1]["params"]
        assert "returnfields" in station_list_params
        assert "station_latitude" in station_list_params["returnfields"]

    def test_fetch_raw_builds_timeseries_list_params(self):
        self.mock_client.get_json.side_effect = [STATION_LIST_RESPONSE, TS_LIST_RESPONSE, TS_VALUES_RESPONSE]
        self.collector.fetch_raw(station_id="410001", parameter_type="Water Course Discharge")
        ts_list_params = self.mock_client.get_json.call_args_list[1][1]["params"]
        assert ts_list_params["request"] == "getTimeseriesList"
        assert ts_list_params["station_no"] == "410001"
        assert ts_list_params["parametertype_name"] == "Water Course Discharge"

    def test_fetch_raw_no_matches_returns_empty(self):
        self.mock_client.get_json.side_effect = [STATION_LIST_NO_MATCH, TS_LIST_NO_MATCH]
        rows = self.collector.fetch_raw(station_id="999999")
        assert rows == []

    def test_fetch_raw_handles_request_failure(self):
        self.mock_client.get_json.side_effect = ConnectionError("boom")
        rows = self.collector.fetch_raw(station_id="410001")
        assert rows == []

    def test_fetch_raw_passes_explicit_dates(self):
        self.mock_client.get_json.side_effect = [STATION_LIST_RESPONSE, TS_LIST_RESPONSE, TS_VALUES_RESPONSE]
        self.collector.fetch_raw(station_id="410001", start_date="2023-01-01", end_date="2023-01-31")
        values_params = self.mock_client.get_json.call_args_list[2][1]["params"]
        assert values_params["from"] == "2023-01-01"
        assert values_params["to"] == "2023-01-31"

    def test_fetch_raw_water_course_level_resolves_correct_ts(self):
        self.mock_client.get_json.side_effect = [STATION_LIST_RESPONSE, TS_LIST_LEVEL_RESPONSE, TS_VALUES_RESPONSE]
        rows = self.collector.fetch_raw(station_id="410001", parameter_type="Water Course Level")
        assert rows[0]["unit"] == "m"
        assert rows[0]["parameter_type"] == "Water Course Level"


class TestBOMNormalise:
    def setup_method(self):
        self.collector = BOMCollector()

    def test_normalise_produces_water_quality_sample(self):
        records = self.collector.normalise([SAMPLE_RAW[0]])
        assert len(records) == 1
        assert isinstance(records[0], WaterQualitySample)
        assert records[0].source == DataSource.BOM
        assert records[0].parameter == "Water Course Discharge"
        assert records[0].value == 1234.5
        assert records[0].unit == "m^3/s"  # falls back to PARAMETER_UNITS

    def test_normalise_produces_water_level_reading_for_level_parameter(self):
        records = self.collector.normalise([SAMPLE_RAW[1]])
        assert len(records) == 1
        assert isinstance(records[0], WaterLevelReading)
        assert records[0].water_level == 2.31

    def test_normalise_parses_location(self):
        records = self.collector.normalise([SAMPLE_RAW[0]])
        assert records[0].location is not None
        assert abs(records[0].location.latitude - (-35.1082)) < 0.001
        assert abs(records[0].location.longitude - 147.3598) < 0.001

    def test_normalise_skips_missing_values(self):
        raw = [
            {
                "station_no": "410001",
                "parameter_type": "Water Course Discharge",
                "unit": "",
                "timestamp": "2023-07-17T00:00:00.000+10:00",
                "value": "",
                "quality_code": "255",
            }
        ]
        records = self.collector.normalise(raw)
        assert records == []

    def test_normalise_empty_input(self):
        assert self.collector.normalise([]) == []

    def test_normalise_falls_back_to_default_unit(self):
        raw = [
            {
                "station_no": "410001",
                "parameter_type": "Water Course Discharge",
                "unit": "",
                "timestamp": "2023-07-15T00:00:00.000+10:00",
                "value": "10.0",
            }
        ]
        records = self.collector.normalise(raw)
        assert records[0].unit == PARAMETER_UNITS["Water Course Discharge"]


class TestBOMConstants:
    def test_level_parameters_include_storage_and_groundwater(self):
        assert "Storage Level" in LEVEL_PARAMETERS
        assert "Ground Water Level" in LEVEL_PARAMETERS
        assert "Water Course Discharge" not in LEVEL_PARAMETERS

    def test_parameter_units_cover_discharge(self):
        assert PARAMETER_UNITS["Water Course Discharge"] == "m^3/s"
