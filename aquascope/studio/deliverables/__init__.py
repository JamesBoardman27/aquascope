"""The deliverables of a study: figures, tables, the workbook, the reports, the notebook and the bundle.

Pure Python so it runs in the Pyodide worker: matplotlib, openpyxl and
python-docx are imported inside the functions that need them, never here.
Nothing writes to the filesystem except :func:`export`; everything else
returns bytes on :class:`aquascope.studio.workspace.Artifact` rows.
"""

from __future__ import annotations

from aquascope.studio.deliverables.bundle import build, bundle_bytes, export
from aquascope.studio.deliverables.figures import figures_for
from aquascope.studio.deliverables.tables import tables_for

__all__ = ["build", "bundle_bytes", "export", "figures_for", "tables_for"]
