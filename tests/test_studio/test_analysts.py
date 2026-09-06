"""The Analysts: the table loader, the run with gates, figures when the makers exist, the bounded replan."""

from __future__ import annotations

import json
import sys
import types

from aquascope.studio.model import Model
from aquascope.studio.roles import analysts, methodologist, scout
from aquascope.studio.workspace import Artifact, Workspace
from tests.test_studio.conftest import (
    FLOW,
    PROBLEM,
    RECON,
    SAMPLES_CSV,
    SERIES_CSV,
    FakeModel,
    fake_tools,
    patched,
)


def _ws(**tables) -> Workspace:
    ws = Workspace()
    ws.site = {"lat": 51.415, "lon": -0.308}
    ws.brief.problem, ws.brief.playbook, ws.brief.kind = PROBLEM, "flood_risk", "flood_risk"
    ws.brief.intake = {"return_period": 100}
    for k, v in tables.items():
        ws.add_table(k, v)
    with patched(RECON):
        scout.scout(ws)
        methodologist.plan(ws, None)
    return ws


def test_load_table_serves_a_series_or_sample_rows():
    ws = Workspace()
    ws.add_table("upload:flows.csv", SERIES_CSV)
    ws.add_table("upload:samples.csv", SAMPLES_CSV)
    out = analysts.load_table(ws, "upload:flows.csv")
    assert out["n"] > 1000 and out["years"] > 10 and out["unit"] == "m3/s" and out["variable"] == "discharge"
    assert out["columns"] == ["date", "flow_m3s"] and len(out["series"]["t"]) == out["n"]
    assert out["series"]["t"][0].startswith("2010-01-01") and isinstance(out["series"]["v"][0], float)
    assert out["stats"]["mean"] > 0 and out["qa"]["coverage_pct"] > 0
    assert analysts.load_table(ws, "flows.csv")["n"] == out["n"], "a bare file name finds the upload"
    samples = analysts.load_table(ws, "upload:samples.csv")
    assert samples["n"] == 3 and samples["samples"][0] == {"station": "A", "parameter": "nitrate", "value": "3.1",
                                                          "unit": "mg/L"}
    assert "error" in analysts.load_table(ws, "upload:nope.csv")
    assert "error" in analysts.load_table(ws, "upload:flows.csv", value_column="nope")
    assert analysts.load_table(ws, "upload:flows.csv", value_column="flow_m3s", datetime_column="date")["n"] == out["n"]


def test_the_run_writes_results_gates_and_the_study_and_skips_figures_without_the_makers(no_deliverables):
    ws = _ws()
    calls: list = []
    with patched(RECON, tools=fake_tools(calls)):
        run = analysts.run(ws, None)
    assert run.ok and ws.run["ok"] and ws.run["stopped_at"] is None and ws.run["replans"] == 0
    assert [r["id"] for r in ws.run["results"]] == ["s1", "s2", "s3"] and len(ws.run["gates"]) == 7
    assert ws.run["failed_gates"] == [] and ws.study["results"]["s3"]["ok"]
    assert [c[0] for c in calls] == ["describe_catchment", "analyze_station", "flood_frequency"]
    kinds = [(e["role"], e["event"]) for e in ws.events]
    assert ("analyst", "figures_skipped") in kinds and ("runner", "done") in kinds and ("reviewer", "gate") in kinds
    assert ("analyst", "gates") in kinds and ws.artifacts == []


def test_figures_and_tables_are_made_per_step_when_the_makers_exist(monkeypatch):
    made: list = []

    def figures_for(step_id, tool, payload, *, unit=None, site=None):
        made.append(("fig", step_id, tool, unit, site))
        if tool == "flood_frequency":
            raise RuntimeError("no matplotlib here")
        return [Artifact(id=f"{step_id}_series", kind="figure", name=f"figures/{step_id}_series.png", data=b"png",
                         media_type="image/png", caption="the series")]

    def tables_for(step_id, tool, payload):
        made.append(("tab", step_id, tool))
        return [{"id": f"{step_id}_table", "kind": "table", "name": f"tables/{step_id}.csv", "data": "YWJj",
                 "media_type": "text/csv"}]

    pkg = types.ModuleType("aquascope.studio.deliverables")
    figs = types.ModuleType("aquascope.studio.deliverables.figures")
    tabs = types.ModuleType("aquascope.studio.deliverables.tables")
    figs.figures_for, tabs.tables_for = figures_for, tables_for
    monkeypatch.setitem(sys.modules, "aquascope.studio.deliverables", pkg)
    monkeypatch.setitem(sys.modules, "aquascope.studio.deliverables.figures", figs)
    monkeypatch.setitem(sys.modules, "aquascope.studio.deliverables.tables", tabs)
    ws = _ws()
    streamed: list = []
    with patched(RECON):
        analysts.run(ws, None, on_artifact=streamed.append)
    assert [m[1] for m in made if m[0] == "fig"] == ["s1", "s2", "s3"] and made[2][3] == "m3/s"
    assert made[2][4] == {"lat": 51.415, "lon": -0.308}
    ids = sorted(a.id for a in ws.artifacts)
    assert ids == ["s1_series", "s1_table", "s2_series", "s2_table", "s3_table"], "a maker's error skips one figure"
    assert [a.id for a in streamed] == [a.id for a in ws.artifacts]
    assert ws.artifact("s1_table").data == b"abc" and ws.artifact("s2_series").step == "s2"
    assert any(e["event"] == "figures_skipped" and e["step"] == "s3" and "matplotlib" in e["detail"]
               for e in ws.events)
    assert ws.figures("s1")[0].kind == "figure"


def test_a_failed_gate_runs_the_playbooks_fallback_then_the_specialists_proposal(no_deliverables):
    wide = json.loads(json.dumps(FLOW))
    wide["ffa"]["fits"]["lp3"]["q"][5] = 900
    calls: list = []
    tools = fake_tools(calls, flood_frequency=wide, analyze_station=wide,
                       similar_basins={"k": 1, "method": "combined",
                                       "stations": [{"source": "usgs", "station_id": "1"}]})
    ws = _ws()
    with patched(RECON, tools=tools):
        run = analysts.run(ws, None)
    assert run.stop_reason and "spread_within" in run.stop_reason and ws.run["stopped_at"] == "s3"
    assert ws.run["results"][2]["fallback_used"] and ws.run["results"][2]["fallback"]["tool"] == "similar_basins"
    assert ws.run["replans"] == 0, "keyless: no specialist"

    proposal = {"tool": "anywhere", "arguments": {"lat": 51.415, "lon": -0.308, "years": 20},
                "rationale": "GloFAS as an independent cross-check",
                "expects": [{"check": "not_empty", "path": "glofas"}]}
    ws2 = _ws()
    client = FakeModel({"analyst": [proposal]})
    model = Model.resolve(ws2, client=client, model="fake", provider="custom")
    calls2: list = []
    with patched(RECON, tools=fake_tools(calls2, flood_frequency=wide, analyze_station=wide,
                                         similar_basins={"k": 1, "stations": []})):
        run2 = analysts.run(ws2, model)
    assert run2.ok and run2.stop_reason is None and ws2.run["replans"] == 1
    assert ws2.study["plan"]["replans"][0]["fallback"]["tool"] == "anywhere"
    assert ws2.study["steps"][2]["fallback"]["step"]["tool"] == "anywhere"
    r3 = ws2.run["results"][2]
    assert r3["fallback"]["tool"] == "anywhere" and r3["fallback"]["ok"] and r3["fallback"]["gates_passed"]
    assert [c[0] for c in calls2] == ["describe_catchment", "analyze_station", "flood_frequency", "similar_basins",
                                      "flood_frequency", "anywhere"], "passed steps are reused"
    assert ws2.ledger["analyst"]["calls"] == 1 and client.requests[0]["context"]["failed_step"]["id"] == "s3"
    assert any(e["event"] == "replan" and e["role"] == "analyst" for e in ws2.events)


def test_a_proposal_that_fails_the_validator_is_refused(no_deliverables):
    wide = json.loads(json.dumps(FLOW))
    wide["ffa"]["fits"]["lp3"]["q"][5] = 900
    ws = _ws()
    client = FakeModel({"analyst": [{"tool": "anywhere", "arguments": {"lat": 1, "lon": 2, "bogus": 3},
                                     "rationale": "x"}]})
    model = Model.resolve(ws, client=client, model="fake", provider="custom")
    with patched(RECON, tools=fake_tools([], flood_frequency=wide, analyze_station=wide,
                                         similar_basins={"k": 1, "stations": []})):
        run = analysts.run(ws, model)
    assert run.stop_reason and ws.run["replans"] == 0, "a refused proposal is not a replan"
    assert any(e["event"] == "no_fallback" and "bogus" in e["detail"] for e in ws.events)


def test_a_branch_fallback_replans_through_the_playbook(no_deliverables):
    wide = json.loads(json.dumps(FLOW))
    wide["ffa"]["fits"]["lp3"]["q"][5] = 900
    ws = _ws()
    study = ws.study
    study["steps"][2]["fallback"] = {"branch": "regional"}
    ws.study = study
    calls: list = []
    with patched(RECON, tools=fake_tools(calls, flood_frequency=wide, analyze_station=wide)):
        run = analysts.run(ws, None)
    assert ws.study["plan"]["branch"] == "regional" and ws.study["plan"]["replanned_from"]["step"] == "s3"
    assert ws.study["version"] == 3 and ws.study["plan"]["objective"], "the plan block carries over"
    assert [s["tool"] for s in ws.study["steps"]] == ["describe_catchment", "similar_basins",
                                                      "regionalize_signatures", "anywhere"]
    assert run.ok and ws.run["replans"] == 1
    assert calls[0][0] == "describe_catchment" and "describe_catchment" not in [c[0] for c in calls[1:]], "reused"


def test_prior_results_are_reused_unless_the_gates_changed(no_deliverables):
    ws = _ws()
    calls: list = []
    with patched(RECON, tools=fake_tools(calls)):
        analysts.run(ws, None)
        prior = analysts.prior_run(ws)
        assert prior is not None and len(prior.results) == 3
        methodologist.change(ws, None, "T = 50", intake={"return_period": 50})
        analysts.run(ws, None, prior=prior)
    assert [c[0] for c in calls] == ["describe_catchment", "analyze_station", "flood_frequency", "flood_frequency"]
    gate = next(g for g in ws.run["gates"] if g["check"] == "max_return_period_factor")
    assert "T = 50 years" in gate["detail"]
