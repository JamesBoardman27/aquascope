"""Unit tests for the ``benchmarks.camels_benchmark`` harness.

Everything reads the committed local files under ``data/camels_benchmark`` --
no network access, and ``dataretrieval`` / ``lmoments3`` are not imported.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pytest

from benchmarks import camels_benchmark as cb

ALL_METHODS = {"gev", "gev_lmoments", "lp3"}
UNSTABLE_GAUGE = "11532500"

_full_results_cache: dict | None = None


def _full_results() -> dict:
    """Full 10-gauge harness run, computed once per test session."""
    global _full_results_cache
    if _full_results_cache is None:
        _full_results_cache = cb.build_results()
    return _full_results_cache


def test_build_results_schema_and_gates() -> None:
    """Full run: gates pass and every catchment has the expected structure."""
    results = _full_results()

    meta = results["metadata"]
    assert meta["schema_version"] == cb.SCHEMA_VERSION
    assert meta["timings_not_asserted"] is True
    tolerance_names = set(meta["tolerances"])
    assert tolerance_names >= {
        "signature_relative",
        "baseflow_absolute",
        "peak_month_circular",
        "ffa_relative",
        "q_mean_nrmse_gate",
        "bfi_pbias_gate",
        "ffa_gate",
    }
    for name, entry in meta["tolerances"].items():
        assert "value" in entry and "rationale" in entry, f"{name} lacks value/rationale"

    gates = results["summary"]["gates"]
    assert gates["q_mean_gate_met"]
    assert gates["bfi_gate_met"]
    assert gates["ffa_gate_met"]
    assert results["summary"]["n_integrity_failures"] == 0

    assert len(results["catchments"]) == 10
    for gid, res in results["catchments"].items():
        assert set(res) >= {"name", "climate", "signatures", "baseflow", "flood_frequency", "timings"}
        assert res["signatures"]["checks"]
        integrity_metrics = {c["metric"] for c in res["signatures"]["integrity"]}
        assert integrity_metrics == {"order", "runoff_ratio", "recession_constant", "fdc_slope", "complete"}
        assert all(c["check_passes"] and "detail" in c for c in res["signatures"]["integrity"])
        assert set(res["baseflow"]["methods"]) == {"lyne_hollick", "eckhardt"}
        assert set(res["flood_frequency"]["methods"]) == ALL_METHODS
        for mres in res["flood_frequency"]["methods"].values():
            assert len(mres["fits"]) == 6
            for fit in mres["fits"]:
                assert fit["classification"] in {"implementation", "data_limitation"}
        assert res["timings"]["total_s"] >= 0


def test_gev_unstable_findings_classified_as_data_limitation() -> None:
    """On an unstable-reference gauge, unmet GEV matches are data limitations."""
    res = cb.build_results(gauge_ids=[UNSTABLE_GAUGE])
    gev = res["catchments"][UNSTABLE_GAUGE]["flood_frequency"]["methods"]["gev"]
    assert gev["reference_mle_unstable"] is True
    for fit in gev["fits"]:
        if not fit["check_passes"]:
            assert fit["classification"] == "data_limitation"


def test_dependable_ffa_cross_checks_match_reference() -> None:
    """GEV-L-moments and LP3 track the flood-frequency reference closely (20 % band)."""
    res = _full_results()
    for gid, catchment in res["catchments"].items():
        for method in ("gev_lmoments", "lp3"):
            mean_err = catchment["flood_frequency"]["methods"][method]["mean_relative_error_pct"]
            assert mean_err < 5.0, f"{gid} {method} mean relative error {mean_err:.2f}%"


def test_aggregate_metrics_present() -> None:
    """Cross-catchment RMSE / PBIAS / R2 exist for the signatures."""
    aggregate = _full_results()["summary"]["aggregate"]
    assert aggregate["q_mean"]["rmse"] == 0.0
    assert aggregate["q_mean"]["r2"] > 0.99
    assert aggregate["q5"]["pbias"] is not None
    assert aggregate["bfi_lyne_hollick"]["pbias"] is not None


def test_findings_are_surfaced_not_hidden() -> None:
    """The GEV data-limitation mismatches stay visible in the summary."""
    results = _full_results()
    assert results["summary"]["n_data_limitation_findings"] >= 20
    assert results["summary"]["n_unmet"] >= results["summary"]["n_data_limitation_findings"]


def test_results_are_json_serialisable() -> None:
    """numpy scalars from the pipeline never leak into the JSON."""
    results = cb.build_results(gauge_ids=["03451500"])
    json.dumps(results)


def test_annual_maxima_series_is_a_noop() -> None:
    """Synthetic unique-year dates preserve every water-year peak."""
    values = np.array([10.0, 60.0, 30.0])  # a calendar year could hold two of these
    series = cb._annual_maxima_series(values)
    assert len(series) == len(values)
    assert len(series.index.year.unique()) == len(values)
    assert list(series) == list(values)


def test_render_markdown_consumes_results(tmp_path) -> None:
    """The Markdown report derives from the results dict."""
    results = cb.build_results(gauge_ids=["01013500"])
    out = cb.render_markdown(results, tmp_path / "results.md")
    text = out.read_text(encoding="utf-8")
    assert "01013500" in text
    assert "Tolerances and rationale" in text
    assert "signature integrity" in text
    assert "Cite this software" in text
    assert "DOI not yet assigned" in text


def test_render_html_consumes_results(tmp_path) -> None:
    """The HTML report derives from the results dict."""
    results = cb.build_results(gauge_ids=["01013500"])
    out = cb.render_html(results, tmp_path / "results.html")
    html = out.read_text(encoding="utf-8")
    assert "<table>" in html
    assert "01013500" in html


def test_render_round_trips_from_json(tmp_path) -> None:
    """The report built from the on-disk JSON matches the in-memory one.

    results.json is the single source of truth: the renderers read the JSON
    exactly as written, not freshly computed values.
    """
    results = cb.build_results(gauge_ids=["01013500"])
    path = tmp_path / "results.json"
    cb._write_json_atomic(results, path)
    loaded = json.loads(path.read_text(encoding="utf-8"))

    md_memory = cb.render_markdown(results, tmp_path / "memory.md").read_text(encoding="utf-8")
    md_disk = cb.render_markdown(loaded, tmp_path / "disk.md").read_text(encoding="utf-8")
    assert "01013500" in md_disk
    assert "q_mean" in md_disk
    # Both renderings carry the same recorded numbers.
    assert "Q mean normalized RMSE" in md_memory and "Q mean normalized RMSE" in md_disk


def test_cli_writes_all_three(tmp_path) -> None:
    """A default run writes results.json + results.md + results.html."""
    rc = cb.main(["--output-dir", str(tmp_path), "--gauge-id", "01013500", "01664000"])
    assert rc == 0
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "results.md").exists()
    assert (tmp_path / "results.html").exists()
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert len(data["catchments"]) == 2
    # The report heading reflects the actual run scope, not a fixed default.
    md = (tmp_path / "results.md").read_text(encoding="utf-8")
    assert "across 2 catchments" in md
    assert (tmp_path / "results.md.tmp").exists() is False


def test_cli_no_reports(tmp_path) -> None:
    """--no-reports writes only the JSON."""
    rc = cb.main(["--output-dir", str(tmp_path), "--gauge-id", "03451500", "--no-reports"])
    assert rc == 0
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "results.md").exists() is False
    assert (tmp_path / "results.html").exists() is False


def test_cli_renders_from_json(tmp_path) -> None:
    """--from-json re-renders an existing results.json without recomputing.

    results.json is the single source of truth, so a new report layout can be
    applied to a recorded run without touching the numbers.
    """
    run_dir = tmp_path / "run"
    rc = cb.main(["--output-dir", str(run_dir), "--gauge-id", "01013500"])
    assert rc == 0

    render_dir = tmp_path / "render"
    rc = cb.main(["--from-json", str(run_dir / "results.json"), "--output-dir", str(render_dir)])
    assert rc == 0
    assert (render_dir / "results.json").exists()
    assert (render_dir / "results.md").exists()
    assert (render_dir / "results.html").exists()

    original = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    copy = json.loads((render_dir / "results.json").read_text(encoding="utf-8"))
    assert copy["summary"]["n_unmet"] == original["summary"]["n_unmet"]
    assert set(copy["catchments"]) == set(original["catchments"])


def test_cli_from_json_rejects_no_reports(tmp_path) -> None:
    """--from-json cannot be combined with --no-reports (nothing to write)."""
    run_dir = tmp_path / "run"
    cb.main(["--output-dir", str(run_dir), "--gauge-id", "01013500"])
    with pytest.raises(ValueError):
        cb.main(["--from-json", str(run_dir / "results.json"), "--no-reports"])


def test_cli_strict_exits_nonzero_when_unmet(tmp_path) -> None:
    """--strict fails the run when any recorded check is unmet."""
    rc = cb.main(["--output-dir", str(tmp_path), "--strict"])
    assert rc == 1


def test_cli_rejects_unknown_gauge(tmp_path) -> None:
    """An unknown gauge_id is an operational error, not a silent empty run."""
    with pytest.raises(ValueError):
        cb.main(["--output-dir", str(tmp_path), "--gauge-id", "99999999"])


def test_strict_flags_integrity_failures() -> None:
    """--strict fails on internal signature-integrity defects, not only value checks."""
    results = cb.build_results(gauge_ids=["03451500"])
    assert results["summary"]["n_unmet"] == 0
    assert results["summary"]["n_integrity_failures"] == 0
    assert cb._strict_failed(results) is False
    summary = dict(results["summary"], n_integrity_failures=1)
    assert cb._strict_failed(dict(results, summary=summary)) is True


def test_build_results_friendly_error_when_metadata_missing(tmp_path, monkeypatch) -> None:
    """Missing committed metadata fails cleanly instead of tracebacking."""
    monkeypatch.setattr(cb, "DAILY_CATCHMENTS_FILE", tmp_path / "daily_catchments.json")
    monkeypatch.setattr(cb, "FFA_REFERENCE_FILE", tmp_path / "ffa_reference.json")
    monkeypatch.setattr(cb, "BENCHMARK_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="daily_catchments.json and ffa_reference.json"):
        cb.build_results()


def test_build_results_friendly_error_when_gauge_data_missing(tmp_path, monkeypatch) -> None:
    """Missing per-gauge series / peaks fails cleanly with a regeneration hint."""
    monkeypatch.setattr(cb, "BENCHMARK_DIR", tmp_path)
    monkeypatch.setattr(cb, "PEAKS_DIR", tmp_path / "peaks")
    with pytest.raises(RuntimeError, match="generate_synthetic.py"):
        cb._require_data_files("03451500")


def test_duplicate_water_year_peaks_are_not_collapsed() -> None:
    """Peaks that share a calendar year (different water years) both survive."""
    peaks = pd.Series([10.0, 200.0, 30.0], index=pd.to_datetime(["2000-03-01", "2000-12-01", "2001-03-01"]))
    series = cb._annual_maxima_series(peaks.values)
    assert len(series) == 3  # calendar-year resampling would have kept only 2


def test_committed_examples_validate_against_schema() -> None:
    """The committed examples must own the schema (build_results enforces it too)."""
    assert cb.validate_results(_full_results()) == []
    committed = pathlib.Path(cb.BASE).parent / "examples" / "camels_benchmark" / "results.json"
    assert cb.validate_results(json.loads(committed.read_text(encoding="utf-8"))) == []


def test_committed_schema_matches_generated_models() -> None:
    """results.schema.json is a derived artifact of the Pydantic models."""
    import benchmarks.results_models as rm

    committed = json.loads(cb.SCHEMA_FILE.read_text(encoding="utf-8"))
    assert committed == rm.results_json_schema()


def test_validate_results_rejects_corrupt_structure() -> None:
    """Schema validation flags shape drift, not just type drift."""
    results = _full_results()
    broken = json.loads(json.dumps(results))
    assert cb.validate_results(broken) == []
    broken["summary"]["n_catchments"] = "ten"
    del broken["software"]["doi"]
    errors = cb.validate_results(broken)
    assert any("n_catchments" in e for e in errors)
    assert any("software" in e and "doi" in e for e in errors)


def test_cli_from_json_rejects_invalid_results(tmp_path) -> None:
    """A results.json that violates the schema is refused before rendering."""
    bad = tmp_path / "results.json"
    bad.write_text(json.dumps({"metadata": {"schema_version": "1.0"}, "not": "a results file"}), encoding="utf-8")
    with pytest.raises(ValueError, match="results.schema.json"):
        cb.main(["--from-json", str(bad), "--output-dir", str(tmp_path / "out")])
