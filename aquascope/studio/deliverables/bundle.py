"""The documents of a study and the zip that carries everything.

:func:`build` adds the report (Markdown, HTML, Word), the workbook, the
notebook, ``study.yaml`` and ``workspace.json`` to the workspace as
artifacts, then the bundle zip with every artifact and a README. Nothing
here touches the filesystem except :func:`export`, which writes the
artifacts into a directory.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from aquascope.studio.deliverables import _common as c
from aquascope.studio.deliverables.notebook import notebook_json
from aquascope.studio.deliverables.report_docx import report_docx_bytes
from aquascope.studio.deliverables.report_md import report_html, report_markdown
from aquascope.studio.deliverables.workbook import workbook_bytes
from aquascope.studio.workspace import MEDIA_TYPES, Artifact, Workspace

logger = logging.getLogger(__name__)

#: The formats :func:`build` knows, in the order they are made. ``zip`` is the bundle of all the others.
FORMATS = ("md", "html", "docx", "xlsx", "ipynb", "yaml", "json", "zip")

_SPEC: dict[str, tuple[str, str, str, str]] = {
    # format: (artifact id, kind, file name, media type key)
    "md": ("report-md", "document", "report.md", "md"),
    "html": ("report-html", "document", "report.html", "html"),
    "docx": ("report-docx", "document", "report.docx", "docx"),
    "xlsx": ("workbook", "workbook", "workbook.xlsx", "xlsx"),
    "ipynb": ("notebook", "notebook", "study.ipynb", "ipynb"),
    "yaml": ("study", "study", "study.yaml", "yaml"),
    "json": ("workspace", "data", "workspace.json", "json"),
    "zip": ("bundle", "bundle", "bundle.zip", "zip"),
}

_CAPTIONS = {
    "md": "The report in Markdown (figures as relative paths).",
    "html": "The report as one self-contained HTML page.",
    "docx": "The report as a Word document.",
    "xlsx": "The workbook: README, inventory, plan, gates, every table, the figure index, the ledger.",
    "ipynb": "The notebook that re-runs the study and redraws the figures.",
    "yaml": "The study file: aquascope run study.yaml replays it with no model.",
    "json": "The workspace without the artifact bytes (resume with aquascope studio --resume).",
    "zip": "Everything above and every figure and table, with a README.",
}


def _artifact(fmt: str, data: bytes) -> Artifact:
    aid, kind, name, media = _SPEC[fmt]
    return Artifact(id=aid, kind=kind, name=name, data=data, media_type=MEDIA_TYPES[media], caption=_CAPTIONS[fmt])


def readme_text(ws: Workspace) -> str:
    """``README.txt`` for the bundle: what is in it and how to reproduce the study."""
    lines = [c.title_of(ws), "=" * min(len(c.title_of(ws)), 78), ""]
    site = c.site_text(ws)
    if site:
        lines.append(f"Site: {site}")
    lines += [f"Date: {c.date_of(ws)}", f"AquaScope {c.version()}", c.model_line(ws), ""]
    answer = c.answer_of(ws)
    if answer:
        lines += ["Answer", "------", answer, ""]
    lines += ["Files", "-----"]
    for a in sorted(ws.artifacts, key=lambda x: (x.kind != "document", x.kind, x.name)):
        if a.kind == "bundle":
            continue
        lines.append(f"{a.name:40s} {a.caption or ''}".rstrip())
    lines += ["", "Reproduce", "---------",
              "pip install aquascope[studio]",
              "aquascope run study.yaml          # replays every step with its gates, no model needed",
              "jupyter notebook study.ipynb      # the same, with the figures redrawn",
              "aquascope studio --resume workspace.json   # picks the conversation up where it stopped",
              "", "Cite", "----", c.citation(), ""]
    return "\n".join(lines)


def bundle_bytes(ws: Workspace) -> bytes:
    """The zip of every artifact except the bundle itself, plus ``README.txt``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme_text(ws))
        seen: set[str] = set()
        for a in ws.artifacts:
            if a.kind == "bundle" or a.id == "bundle" or not a.name or a.name in seen:
                continue
            seen.add(a.name)
            zf.writestr(a.name, a.data)
    return buf.getvalue()


def build(ws: Workspace, *, formats: list[str] | tuple[str, ...] | None = None) -> list[Artifact]:
    """Add the documents (and the bundle) to the workspace; returns the artifacts added, in order.

    ``formats`` picks from :data:`FORMATS` (all by default). The Word report is skipped, with a note event,
    when python-docx is not installed; ``study.yaml`` is skipped when no plan exists.
    """
    wanted = [f for f in (formats or FORMATS) if f in _SPEC]
    added: list[Artifact] = []

    def add(fmt: str, data: bytes | str | None) -> None:
        if data is None:
            return
        raw = data.encode("utf-8") if isinstance(data, str) else data
        art = ws.add_artifact(_artifact(fmt, raw))
        added.append(art)
        ws.event("author", "artifact", f"{art.name} ({art.size:,} bytes)")

    if "md" in wanted:
        add("md", report_markdown(ws))
    if "html" in wanted:
        add("html", report_html(ws))
    if "docx" in wanted:
        add("docx", report_docx_bytes(ws))
    if "xlsx" in wanted:
        add("xlsx", workbook_bytes(ws))
    if "ipynb" in wanted:
        add("ipynb", notebook_json(ws))
    if "yaml" in wanted:
        add("yaml", c.study_yaml(ws) or None)
    if "json" in wanted:
        add("json", ws.to_json(with_artifacts=False, indent=1))
    if "zip" in wanted:
        add("zip", bundle_bytes(ws))
    return added


def export(ws: Workspace, out_dir: str | Path) -> dict[str, str]:
    """Write every artifact under ``out_dir`` (``figures/`` and ``tables/`` as subdirectories); returns
    ``{artifact id: path}``."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for a in ws.artifacts:
        if not a.name:
            continue
        rel = Path(*[p for p in Path(a.name).parts if p not in ("..", "/", "")])
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(a.data)
        paths[a.id] = str(dest)
    return paths


def summary(ws: Workspace) -> dict[str, Any]:
    """What a face shows after a build: the documents by id with their sizes."""
    return {a.id: {"name": a.name, "bytes": a.size, "media_type": a.media_type}
            for a in ws.artifacts if a.kind in ("document", "workbook", "notebook", "study", "bundle", "data")}
