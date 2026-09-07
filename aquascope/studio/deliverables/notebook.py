"""The notebook that re-runs a study and redraws its figures, written as plain nbformat-4 JSON.

No nbformat dependency: the structure is small and fixed (``nbformat`` 4,
``nbformat_minor`` 5, metadata, cells with an id, a type, a source and
metadata, code cells with outputs and an execution count).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from aquascope.studio.deliverables import _common as c
from aquascope.studio.deliverables.figures import kinds_of
from aquascope.studio.workspace import Workspace


def _cell(kind: str, source: str) -> dict[str, Any]:
    cell: dict[str, Any] = {"id": uuid.uuid4().hex[:8], "cell_type": kind, "metadata": {}, "source": source}
    if kind == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    return cell


def _site_literal(ws: Workspace) -> str:
    site = ws.site or (ws.inventory.site if ws.inventory else None) or {}
    lat, lon = site.get("lat", site.get("latitude")), site.get("lon", site.get("longitude"))
    try:
        return json.dumps({"lat": float(lat), "lon": float(lon)})
    except (TypeError, ValueError):
        return "None"


def notebook_cells(ws: Workspace) -> list[dict[str, Any]]:
    """The cells: a title, the run, one per step (summary, gates, figures), the workbook."""
    title = c.title_of(ws)
    answer = c.answer_of(ws)
    lines = [f"# {title}", ""]
    site = c.site_text(ws)
    if site:
        lines.append(f"**Site:** {site}  ")
    lines.append(f"**Date:** {c.date_of(ws)}  ")
    lines.append(f"**AquaScope:** {c.version()}  ")
    if answer:
        lines += ["", answer]
    lines += ["", "This notebook re-runs the study from `study.yaml` with no model, prints what each step "
              "returned and how its gates fared, and redraws the figures with the same makers the report used. "
              "It needs `study.yaml` and `workspace.json` from the bundle next to it, and "
              "`pip install aquascope[studio]`."]
    cells = [_cell("markdown", "\n".join(lines))]
    cells.append(_cell("code", "\n".join([
        "from pathlib import Path",
        "",
        "import matplotlib.pyplot as plt",
        "",
        "from aquascope.study import load, run_study",
        "from aquascope.studio.deliverables.figures import draw",
        "",
        'study = load("study.yaml")',
        "run = run_study(study)",
        'results = {r["id"]: r for r in run.results}',
        f"site = {_site_literal(ws)}",
        'print("ok:", run.ok, "| steps run:", len(run.results), "| stopped at:", run.stopped_at,',
        '      run.stop_reason or "")',
    ])))
    for i, step in enumerate(c.steps_of(ws), 1):
        sid = str(step.get("id") or f"s{i}")
        tool = str(step.get("tool") or "")
        rationale = step.get("rationale") or step.get("note") or ""
        md = [f"## Step {sid}: `{tool}`"]
        if rationale:
            md += ["", str(rationale)]
        if step.get("method"):
            md += ["", f"Method: `{step['method']}`"]
        cells.append(_cell("markdown", "\n".join(md)))
        kinds = kinds_of(tool)
        cells.append(_cell("code", "\n".join([
            f"rec = results.get({sid!r})",
            "if rec is None:",
            f"    print({sid!r}, 'did not run')",
            "else:",
            "    print(rec['tool'], 'ok' if rec['ok'] else f\"failed: {rec.get('error')}\")",
            "    for g in rec.get('gates') or []:",
            "        print('  gate', g['check'], 'passed' if g['passed'] else 'FAILED', '|', g.get('detail', ''))",
            "    payload = rec.get('result') or {}",
            "    for key in ('unit', 'years', 'start', 'end', 'n', 'status', 'verdict', 'text'):",
            "        if key in payload:",
            "            print('  ', key, '=', payload[key])",
            f"    for kind in {kinds!r}:",
            "        fig = draw(kind, payload, site=site)",
            "        if fig is not None:",
            "            plt.show()",
        ])))
    cells.append(_cell("markdown", "## Rebuild the workbook\n\nThe same figures and tables, from this run, into "
                                   "`workbook.xlsx` (and a fresh `workspace.json`)."))
    cells.append(_cell("code", "\n".join([
        "from aquascope.studio.deliverables import figures_for, tables_for",
        "from aquascope.studio.deliverables.workbook import workbook_bytes",
        "from aquascope.studio.workspace import Workspace",
        "",
        'ws = Workspace.from_json(Path("workspace.json").read_text(encoding="utf-8"))',
        'ws.run = {"ok": run.ok, "results": run.results, "stopped_at": run.stopped_at, "stop_reason": run.stop_reason,',
        '          "started": run.started, "finished": run.finished}',
        "for rec in run.results:",
        "    if rec['ok']:",
        "        for a in figures_for(rec['id'], rec['tool'], rec['result'], site=site) + "
        "tables_for(rec['id'], rec['tool'], rec['result']):",
        "            ws.add_artifact(a)",
        'Path("workbook.xlsx").write_bytes(workbook_bytes(ws))',
        'Path("workspace.json").write_text(ws.to_json(indent=1), encoding="utf-8")',
        'print("workbook.xlsx and workspace.json rewritten;", len(ws.artifacts), "artifacts")',
    ])))
    return cells


def notebook_dict(ws: Workspace) -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "aquascope": {"version": c.version(), "workspace": ws.id, "title": c.title_of(ws)},
        },
        "cells": notebook_cells(ws),
    }


def notebook_json(ws: Workspace) -> str:
    """``study.ipynb`` as text: a valid nbformat-4 notebook."""
    return json.dumps(notebook_dict(ws), ensure_ascii=False, indent=1) + "\n"
