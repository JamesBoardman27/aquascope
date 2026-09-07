"""The Explorer worker's Studio face, run in CPython.

The Python between the markers in explorer/worker.js is plain functions over
dicts (the ``js`` module is only touched by the thin call site), so it can run
here against the Studio test fixtures: no network, fake tools, the deliverables
as installed (the figures and the bundle when matplotlib is there, a note when
it is not, exactly as in the worker). What is checked is the contract the page
relies on: the reply shape, the workspace without bytes, the worker's own copy
with them, the figures posted as they are drawn, ``file`` and ``export`` by id,
the device brief, the catchment tool and the reconnaissance context, an
unknown op.
"""

from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

import aquascope.explore
from aquascope.studio.workspace import Artifact
from tests.test_studio.conftest import PROBLEM, RECON, fake_tools

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "explorer" / "worker.js"

try:
    import matplotlib  # noqa: F401

    HAS_PLOTTING = True
except ImportError:  # pragma: no cover - depends on the extras installed
    HAS_PLOTTING = False


def _face() -> dict:
    """The Python block of worker.js, executed in a namespace with the worker's globals."""
    text = WORKER.read_text(encoding="utf-8")
    m = re.search(r"# --- studio face \(explorer\) ---(.*?)# --- end studio face ---", text, re.S)
    assert m, "the studio face block is missing from worker.js"
    ns: dict = {"_STORE": {}}
    exec(m.group(1), ns)  # noqa: S102 - the worker's own code, under test
    return ns


@pytest.fixture
def face():
    return _face()


def _run(face: dict, args: dict, *, tools: dict, events: list | None = None, artifacts: list | None = None) -> dict:
    with patch.object(aquascope.explore, "assess_site", create=True, return_value=RECON), \
         patch("aquascope.study._tools", return_value=tools):
        return face["studio_call"](args, on_event=(events.append if events is not None else None),
                                   on_artifact=(artifacts.append if artifacts is not None else None),
                                   store=face["_STORE"])


def test_start_approve_file_and_export_round_trip(face) -> None:
    calls: list = []
    tools = fake_tools(calls)
    events: list = []
    out = _run(face, {"op": "start", "lat": 51.415, "lon": -0.308, "text": PROBLEM, "tables": {}}, tools=tools,
               events=events)
    assert set(out) == {"reply", "workspace", "status"}
    assert out["reply"]["kind"] == "plan" and out["status"] == "review"
    ws = out["workspace"]
    assert ws["status"] == "review" and ws["site"] == {"lat": 51.415, "lon": -0.308}
    assert calls == [], "nothing runs before the approval"
    assert [e["detail"] for e in events if e["event"] == "status"] == ["scouting", "planning", "review"]
    assert json.dumps(out)  # the whole reply is JSON for the page

    # the page holds the workspace without bytes; the worker keeps its own copy by id
    assert ws["id"] in face["_STUDIO"]
    artifacts: list = []
    out2 = _run(face, {"op": "approve", "workspace": ws}, tools=tools, events=events, artifacts=artifacts)
    assert out2["reply"]["kind"] == "report" and out2["status"] == "done"
    assert [c[0] for c in calls] == ["describe_catchment", "analyze_station", "flood_frequency"]
    ws2 = out2["workspace"]
    assert all("data" not in a for a in ws2["artifacts"]), "no bytes cross to the page"
    if HAS_PLOTTING:
        # the figures are posted as they are drawn, with their bytes, and the report lists them
        pngs = [a for a in artifacts if a.media_type == "image/png"]
        assert pngs and all(a.data[:8] == b"\x89PNG\r\n\x1a\n" for a in pngs)
        assert {a["id"] for a in ws2["artifacts"] if a["media_type"] == "image/png"} == {a.id for a in pngs}
        assert {a["id"] for a in ws2["artifacts"]} >= {"report-md", "report-html", "workbook", "notebook", "study",
                                                        "workspace", "bundle"}
    else:
        assert any(e["event"] in ("figures_skipped", "deliverables_unavailable") for e in events)

    # an artifact by id comes back as base64, from the worker's copy
    kept = face["_STUDIO"][ws["id"]]
    kept.ws.add_artifact(Artifact(id="fig-test", kind="figure", name="figures/test.png",
                                  data=b"\x89PNGfake", media_type="image/png", caption="The curve", step="s3"))
    got = _run(face, {"op": "file", "workspace": ws2, "artifact_id": "fig-test"}, tools=tools)
    assert got["name"] == "figures/test.png" and got["media_type"] == "image/png"
    assert base64.b64decode(got["data"]) == b"\x89PNGfake"
    missing = _run(face, {"op": "file", "workspace": ws2, "artifact_id": "nope"}, tools=tools)
    assert "error" in missing

    # the bundle is the zip of every artifact the worker holds, plus the README
    bundle = _run(face, {"op": "export", "workspace": ws2}, tools=tools)
    assert bundle["name"] == "bundle.zip" and bundle["media_type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(bundle["data"]))) as zf:
        names = zf.namelist()
    assert "README.txt" in names and "figures/test.png" in names
    if HAS_PLOTTING:
        expected = {"report.md", "report.html", "workbook.xlsx", "study.ipynb", "study.yaml", "workspace.json"}
        assert expected <= set(names)

    # a follow-up question is answered from the workspace, on the same copy
    out3 = _run(face, {"op": "follow_up", "workspace": ws2, "text": "how sure can we be?"}, tools=tools)
    assert out3["reply"]["kind"] == "answer" and out3["status"] == "done"
    assert out3["workspace"]["messages"][-1]["role"] == "consultant"


def test_the_page_workspace_is_enough_when_the_worker_has_no_copy(face) -> None:
    calls: list = []
    tools = fake_tools(calls)
    out = _run(face, {"op": "start", "lat": 51.415, "lon": -0.308, "text": PROBLEM}, tools=tools)
    ws = out["workspace"]
    face["_STUDIO"].clear()  # the worker was restarted between the plan and the approval
    out2 = _run(face, {"op": "approve", "workspace": ws}, tools=tools)
    assert out2["reply"]["kind"] == "report" and out2["workspace"]["id"] == ws["id"]


def test_questions_say_and_the_device_brief(face) -> None:
    tools = fake_tools([])
    out = _run(face, {"op": "start", "lat": 51.415, "lon": -0.308,
                      "text": "Can the river supply the town with 3 ML/day reliably?",
                      "brief": {"decision": "renew the abstraction licence", "quantities": ["the reliability"]}},
               tools=tools)
    assert out["reply"]["kind"] == "questions" and out["status"] == "intake"
    ws = out["workspace"]
    assert ws["brief"]["decision"] == "renew the abstraction licence"
    assert ws["brief"]["quantities"] == ["the reliability"]
    assert ws["brief"]["source"] == "device"
    out2 = _run(face, {"op": "say", "workspace": ws, "text": "just go"}, tools=tools)
    assert out2["reply"]["kind"] == "plan" and out2["status"] == "review"


def test_the_intake_from_the_device_skips_the_question_it_answers(face) -> None:
    tools = fake_tools([])
    out = _run(face, {"op": "start", "lat": 51.415, "lon": -0.308, "text": "Design flow for a road crossing",
                      "intake": {"return_period": 200}}, tools=tools)
    assert out["workspace"]["brief"]["intake"]["return_period"] == 200


def test_uploads_travel_as_csv_text_and_my_data_is_attached_on_request(face) -> None:
    import pandas as pd

    tools = fake_tools([])
    face["_STORE"]["frame"] = pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "discharge": [3.2, 3.4]})
    out = _run(face, {"op": "start", "lat": 51.415, "lon": -0.308, "text": PROBLEM,
                      "tables": {"flows.csv": "date,flow\n2020-01-01,1\n"}, "use_frame": True,
                      "frame_label": "Kingston"}, tools=tools)
    tables = out["workspace"]["tables"]
    assert set(tables) == {"upload:flows.csv", "upload:Kingston"}
    assert tables["upload:Kingston"].startswith("date,discharge")


def test_the_catchment_row_and_the_recon_context_reach_the_engine(face) -> None:
    seen: dict = {}
    calls: list = []

    def assess(lat, lon, **kw):
        seen.update(kw)
        return RECON

    tools = fake_tools(calls)
    with patch.object(aquascope.explore, "assess_site", create=True, side_effect=assess), \
         patch("aquascope.study._tools", return_value=tools):
        out = face["studio_call"]({"op": "start", "lat": 51.415, "lon": -0.308, "text": PROBLEM,
                                   "area_km2": 9948.0, "donors": 10}, store=face["_STORE"])
    assert seen["area_km2"] == 9948.0 and seen["donors"] == 10
    catchment = {"sub_basin": {"hybas_id": 2120000010, "up_area": 9948.0}, "row": None, "n_upstream": 3}
    described: list = []

    def fake_row(lat, lon, sub_basin, row, n_upstream=None):
        described.append((sub_basin["hybas_id"], n_upstream))
        return {"area_km2": 9948.0, "source": "BasinATLAS", "sub_basin": "2120000010"}

    with patch("aquascope.archive.basins.describe_catchment_from_row", side_effect=fake_row, create=True):
        out2 = _run(face, {"op": "approve", "workspace": out["workspace"], "catchment": catchment}, tools=tools)
    assert out2["status"] == "done"
    assert described == [(2120000010, 3)], "describe_catchment ran from the page's row, not the archive"


def test_unknown_ops_are_errors_not_exceptions(face) -> None:
    tools = fake_tools([])
    out = _run(face, {"op": "start", "lat": 51.415, "lon": -0.308, "text": PROBLEM}, tools=tools)
    bad = _run(face, {"op": "dance", "workspace": out["workspace"]}, tools=tools)
    assert bad == {"error": "unknown op 'dance'"}
