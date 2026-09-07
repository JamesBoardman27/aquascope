"""`aquascope studio`: --yes writes the bundle, no terminal saves the workspace, --resume continues, the
interactive path answers, edits and follows up through input()."""

from __future__ import annotations

import json
import sys

import pytest

from aquascope import cli
from tests.test_studio.conftest import PROBLEM, patched


def _argv(monkeypatch, *extra: str) -> None:
    monkeypatch.setattr(sys, "argv", ["aquascope", "studio", PROBLEM, "--lat", "51.415", "--lon", "-0.308", *extra])


def test_yes_runs_to_the_bundle(monkeypatch, capsys, tmp_path, no_deliverables):
    out = tmp_path / "bundle"
    _argv(monkeypatch, "--yes", "-q", "--out", str(out), "--intake", "return_period=50")
    with patched():
        cli.main()
    printed = capsys.readouterr().out
    assert "Plan (playbook, playbook flood_risk, branch at_site, 3 step(s))" in printed
    assert "The record at Kingston" in printed and "Bundle written to" in printed
    names = {p.name for p in out.iterdir()}
    assert {"report.md", "study.yaml", "report.json", "workspace.json"} <= names
    assert "T = 50 years" in (out / "report.md").read_text()
    ws = json.loads((out / "workspace.json").read_text())
    assert ws["status"] == "done" and ws["brief"]["intake"]["return_period"] == 50
    # the study re-runs with no model
    monkeypatch.setattr(sys, "argv", ["aquascope", "run", str(out / "study.yaml"), "-q"])
    with patched():
        cli.main()
    assert "No model was involved" in capsys.readouterr().out


def test_without_a_terminal_the_plan_waits_and_the_workspace_resumes(monkeypatch, capsys, tmp_path, no_deliverables):
    out = tmp_path / "b"
    _argv(monkeypatch, "-q", "--out", str(out))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with patched():
        cli.main()
    captured = capsys.readouterr()
    assert "pass --yes" in captured.err and (out / "workspace.json").exists()
    assert json.loads((out / "workspace.json").read_text())["status"] == "review"
    monkeypatch.setattr(sys, "argv", ["aquascope", "studio", "--resume", str(out / "workspace.json"), "--yes", "-q",
                                      "--out", str(out)])
    with patched():
        cli.main()
    printed = capsys.readouterr().out
    assert "Bundle written to" in printed and json.loads((out / "workspace.json").read_text())["status"] == "done"


def test_interactive_answers_edits_and_follows_up(monkeypatch, capsys, tmp_path, no_deliverables):
    out = tmp_path / "c"
    monkeypatch.setattr(sys, "argv", ["aquascope", "studio", "Can the river supply the town reliably?", "--lat",
                                      "51.415", "--lon", "-0.308", "-q", "--out", str(out)])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter(["2 m3/s", "e", "s2.years=20", "how reliable is it?", "done"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    with patched():
        cli.main()
    printed = capsys.readouterr().out
    assert "1. Demand" in printed and "Plan (playbook, playbook supply_reliability" in printed
    assert "Bundle written to" in printed
    ws = json.loads((out / "workspace.json").read_text())
    assert ws["status"] == "done" and ws["brief"]["intake"]["demand_m3s"] == 2.0
    assert next(s for s in ws["study"]["steps"] if s["id"] == "s2")["arguments"]["years"] == 20
    assert ws["follow_ups"][0]["kind"] == "question"


def test_bad_arguments_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["aquascope", "studio", "x", "--lat", "1"])
    with pytest.raises(SystemExit):
        cli.main()
    monkeypatch.setattr(sys, "argv", ["aquascope", "studio", "x", "--lat", "1", "--lon", "2", "--intake", "broken"])
    with pytest.raises(SystemExit):
        cli.main()
    monkeypatch.setattr(sys, "argv", ["aquascope", "studio", "--resume", str(tmp_path / "missing.json")])
    with pytest.raises(SystemExit):
        cli.main()
    assert cli._parse_edits("s3.return_period=200, s2.k=8") == {"s3": {"arguments": {"return_period": 200}},
                                                                 "s2": {"arguments": {"k": 8}}}
    with pytest.raises(ValueError):
        cli._parse_edits("nodot=1")


def test_data_files_become_uploads(monkeypatch, capsys, tmp_path, no_deliverables):
    from tests.test_studio.conftest import SERIES_CSV

    csv = tmp_path / "flows.csv"
    csv.write_text(SERIES_CSV)
    out = tmp_path / "d"
    _argv(monkeypatch, "--yes", "-q", "--out", str(out), "--data", str(csv))
    with patched():
        cli.main()
    ws = json.loads((out / "workspace.json").read_text())
    assert "upload:flows.csv" in ws["tables"]
    assert any(d["id"] == "upload:flows.csv" and d["variable"] == "discharge" for d in ws["inventory"]["datasets"])
