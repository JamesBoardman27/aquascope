"""Archive Phase 1 (#188): budgeted, incremental per-station daily observations."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from aquascope.archive import observations as obs

CATALOG = [
    {"source": "hubeau_hydrometrie", "station_id": "A1", "variables": ["discharge", "water_level"]},
    {"source": "hubeau_hydrometrie", "station_id": "A2", "variables": ["discharge", "water_level"]},
    {"source": "hubeau_hydrometrie", "station_id": "A3", "variables": ["discharge", "water_level"]},
    {"source": "uk_ea", "station_id": "B1", "variables": ["water_level"]},  # no discharge: skipped
    {"source": "pegelonline", "station_id": "P1", "variables": ["discharge"]},  # not harvestable
]


def _series(n=800, start="2020-01-01"):
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.Series(np.linspace(1, 2, n), index=idx)


def test_csv_gz_roundtrip():
    s = _series(10)
    payload = obs.series_to_csv_gz(s)
    assert gzip.decompress(payload).decode().startswith("date,value\n2020-01-01,1\n")
    back = obs.read_csv_gz(payload)
    assert len(back) == 10 and back.iloc[-1] == pytest.approx(2.0)
    # sub-daily input is averaged to daily
    sub = pd.Series([1.0, 3.0], index=pd.to_datetime(["2020-01-01 06:00", "2020-01-01 18:00"]))
    assert obs.read_csv_gz(obs.series_to_csv_gz(sub)).iloc[0] == 2.0


def test_harvest_writes_files_manifest_and_report(tmp_path):
    calls = []

    def fake_fetch(source, sid, *, years, prefer_archive):
        calls.append((source, sid, prefer_archive))
        if sid == "A2":
            return {"series": None, "variable": "", "unit": "", "note": ""}
        return {"series": _series(), "variable": "discharge", "unit": "m3/s", "note": "fake"}

    with patch("aquascope.explore.fetch_series", side_effect=fake_fetch):
        report = obs.harvest_observations(tmp_path, sources=["hubeau_hydrometrie"], catalog=CATALOG, max_stations=10)

    assert [c[2] for c in calls] == [False, False, False]  # harvest never reads the archive back
    h = report.sources[0]
    assert (h.attempted, h.harvested, h.empty, h.failed) == (3, 2, 1, 0)
    f = tmp_path / "obs" / "discharge" / "hubeau_hydrometrie" / "A1.csv.gz"
    assert f.exists() and obs.read_csv_gz(f.read_bytes()).shape[0] == 800
    manifest = json.loads((tmp_path / "obs" / "manifest.json").read_text())
    entry = manifest["sources"]["hubeau_hydrometrie"]
    assert entry["variable"] == "discharge" and entry["license"] == "etalab-2.0" and entry["n_stations"] == 2
    assert entry["stations"]["A1"]["n"] == 800 and entry["stations"]["A1"]["file"].endswith("A1.csv.gz")
    assert entry["stations"]["A2"]["empty"] is True
    assert (tmp_path / "obs" / "last_run.json").exists()


def test_harvest_is_incremental_and_budgeted(tmp_path):
    def fake_fetch(source, sid, *, years, prefer_archive):
        return {"series": _series(), "variable": "discharge", "unit": "m3/s", "note": "fake"}

    with patch("aquascope.explore.fetch_series", side_effect=fake_fetch) as fake:
        r1 = obs.harvest_observations(tmp_path, sources=["hubeau_hydrometrie"], catalog=CATALOG, max_stations=2)
        assert r1.sources[0].attempted == 2 and fake.call_count == 2
        r2 = obs.harvest_observations(tmp_path, sources=["hubeau_hydrometrie"], catalog=CATALOG, max_stations=2)
        assert r2.sources[0].attempted == 1 and fake.call_count == 3  # only the remaining station
        r3 = obs.harvest_observations(tmp_path, sources=["hubeau_hydrometrie"], catalog=CATALOG, max_stations=2)
        assert r3.sources[0].attempted == 0  # everything fresh, nothing to do

    # make one station stale: it gets picked again
    manifest = obs.load_manifest(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(timespec="seconds")
    manifest["sources"]["hubeau_hydrometrie"]["stations"]["A1"]["harvested_at"] = old
    obs.save_manifest(tmp_path, manifest)
    with patch("aquascope.explore.fetch_series", side_effect=fake_fetch) as fake:
        r4 = obs.harvest_observations(tmp_path, sources=["hubeau_hydrometrie"], catalog=CATALOG, max_stations=5)
    assert r4.sources[0].attempted == 1 and fake.call_args.args[1] == "A1"


def test_failures_are_recorded_not_raised(tmp_path):
    def boom(source, sid, *, years, prefer_archive):
        raise RuntimeError("503 from agency")

    with patch("aquascope.explore.fetch_series", side_effect=boom):
        report = obs.harvest_observations(tmp_path, sources=["hubeau_hydrometrie"], catalog=CATALOG, max_stations=2)
    h = report.sources[0]
    assert h.failed == 2 and h.harvested == 0 and "503" in h.errors[0]


def test_refuses_non_harvestable_and_non_redistributable(tmp_path):
    with pytest.raises(ValueError):
        obs.harvest_observations(tmp_path, sources=["pegelonline"], catalog=CATALOG)
    with patch.dict(obs.HARVESTABLE, {"grdc": "discharge"}):
        with pytest.raises(ValueError, match="redistributable"):
            obs.harvest_observations(tmp_path, sources=["grdc"], catalog=CATALOG)


def test_fetch_archived_series_404_and_hit(monkeypatch):
    import urllib.error

    class Resp:
        def __init__(self, data):
            self._d = data

        def read(self):
            return self._d

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    payload = obs.series_to_csv_gz(_series(5))

    def urlopen(url, timeout=30):
        if "A404" in url:
            raise urllib.error.HTTPError(url, 404, "nf", None, None)
        return Resp(payload)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert obs.fetch_archived_series("hubeau_hydrometrie", "A404", "discharge") is None
    s = obs.fetch_archived_series("hubeau_hydrometrie", "A1", "discharge")
    assert len(s) == 5
    assert obs.archive_series_url("usgs", "USGS-1", "discharge").endswith("/obs/discharge/usgs/USGS-1.csv.gz")


def test_explore_prefers_archive(monkeypatch):
    from aquascope import explore

    hit = _series(30)
    with patch("aquascope.archive.observations.fetch_archived_series", return_value=hit):
        out = explore.fetch_series("usgs", "USGS-1", years=40)
    assert out["variable"] == "discharge" and out["unit"] == "m3/s" and "archive" in out["note"]
    assert out["series"].equals(hit[hit.index >= out["series"].index.min()])
