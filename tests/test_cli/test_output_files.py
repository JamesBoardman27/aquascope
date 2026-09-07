"""CLI coverage for structured analysis output files."""

from __future__ import annotations

import json
import sys

import pandas as pd

from aquascope import cli


def test_recommend_writes_json(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "recommendations.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aquascope",
            "recommend",
            "--parameters",
            "discharge,precipitation",
            "--goal",
            "flood frequency",
            "-o",
            str(output_path),
        ],
    )

    cli.main()

    recommendations = json.loads(output_path.read_text(encoding="utf-8"))
    assert recommendations
    assert {"methodology", "score", "rationale"} <= recommendations[0].keys()


def test_hydro_baseflow_writes_json(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "discharge.csv"
    output_path = tmp_path / "baseflow.json"
    pd.DataFrame(
        {"discharge": [12.0, 10.0, 11.0, 8.0, 7.0, 9.0]},
        index=pd.date_range("2026-01-01", periods=6, freq="D"),
    ).to_csv(input_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aquascope",
            "hydro",
            "--analysis",
            "baseflow",
            "--file",
            str(input_path),
            "--method",
            "eckhardt",
            "-o",
            str(output_path),
        ],
    )

    cli.main()

    rows = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(rows) == 6
    assert {"index", "total", "baseflow", "quickflow", "method", "bfi"} <= rows[0].keys()
