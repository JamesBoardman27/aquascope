"""The method catalogue: every step the Methodologist may put in a plan, described once.

The Methodologist composes a methodology rather than reading one off a
playbook tree, so it needs to know what exists: the Analyst's site and station
tools, the workbench analyses over a table, the reconnaissance, and the table
loader for the user's own data. Each entry says what the step is for, what it
needs (a site, a station, a table from an earlier step), what its payload
yields (a series, a frequency fit, drought indices, donors) so the figure
makers and the workbook know what to draw, which registry method it applies
(so the sufficiency verdict at the site gates it), and which gate checks make
sense on it.

Two forms: :func:`compact` is the JSON the model reads (short, no callables),
:func:`callables` is what the runner executes (the same dict
:func:`aquascope.study.run_study` uses, plus ``load_table``). :func:`validate_step`
is the deterministic check every model-written step passes before a plan is
accepted. Importing this module imports no plotting or document library.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: Analyst tools that are not analysis steps (the model's own loop, listings, the older Solve faces).
_NOT_STEPS = frozenset({
    "run_python", "list_sources", "describe_methods", "list_analyses", "analyse_table",
    "list_playbooks", "describe_playbook", "solve_plan", "solve_run",
})

#: The table loader the Studio runner adds: a user's upload (or a named table) as a step payload,
#: so a workbench step can take it with ``from_step``.
LOAD_TABLE = "load_table"


@dataclass
class Entry:
    """One catalogue entry. ``id`` is the name a study step uses as ``tool``."""

    id: str
    about: str
    #: site (lat, lon) | station (source, station_id) | frame (from_step) | weather (from_step) | recon | table | none
    kind: str
    arguments: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    #: What the payload carries, in the vocabulary the figure makers and the workbook use.
    yields: list[str] = field(default_factory=list)
    #: Registry method ids this step can apply (``aquascope.methods``); the plan names one as ``method``.
    methods: list[str] = field(default_factory=list)
    #: Gate checks (``aquascope.gates.CHECKS``) that make sense on this payload, with the usual path.
    gates: list[dict[str, Any]] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    citation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "about": self.about, "kind": self.kind,
            "arguments": self.arguments, "required": self.required,
            "yields": self.yields, "methods": self.methods, "gates": self.gates,
            "figures": self.figures, "tables": self.tables, "citation": self.citation,
        }

    def compact(self) -> dict[str, Any]:
        """The short form the model reads."""
        return {
            "tool": self.id, "about": self.about[:160], "kind": self.kind,
            "arguments": {k: (v.get("type") or "any") for k, v in self.arguments.items()},
            "required": self.required, "yields": self.yields, "methods": self.methods,
            "gates": [g["check"] for g in self.gates],
        }


# ── what each tool yields, which methods it applies, which gates fit, what gets drawn ──
# Hand-written: this is domain knowledge, not something to introspect.

_ANNOTATIONS: dict[str, dict[str, Any]] = {
    "assess_site": {
        "kind": "recon", "yields": ["recon", "sufficiency", "stations"],
        "tables": ["sufficiency", "stations_within_reach"],
    },
    "describe_catchment": {
        "kind": "site", "yields": ["catchment"], "tables": ["catchment_attributes"], "figures": ["site_map"],
        "gates": [{"check": "not_empty", "path": "sub_basin"}, {"check": "max_area_km2", "path": "area_km2"}],
    },
    "find_stations": {
        "kind": "site", "yields": ["stations"], "tables": ["stations"],
        "gates": [{"check": "not_empty", "path": "stations"}],
    },
    "get_timeseries": {
        "kind": "station", "yields": ["series"], "tables": ["series"], "figures": ["series"],
        "gates": [{"check": "not_empty", "path": "series"}, {"check": "min_years", "path": "years"},
                  {"check": "unit_present", "path": "unit"}],
    },
    "analyze_station": {
        "kind": "station",
        "yields": ["series", "summary", "annual_maxima", "ffa", "fdc", "trend", "low_flow"],
        "methods": ["at_site_flood_frequency", "flow_duration", "trend_mann_kendall", "groundwater_trend",
                    "low_flow_frequency"],
        "tables": ["series", "summary", "annual_maxima", "return_levels", "fdc_percentiles", "trend"],
        "figures": ["series", "annual_maxima", "frequency_curve", "fdc", "trend"],
        "gates": [{"check": "min_years", "path": "years"}, {"check": "not_empty", "path": "trend"},
                  {"check": "unit_present", "path": "unit"},
                  {"check": "max_return_period_factor", "path": "years"}],
    },
    "flood_frequency": {
        "kind": "station", "yields": ["ffa", "annual_maxima"],
        "methods": ["at_site_flood_frequency"],
        "tables": ["return_levels", "annual_maxima", "fit_spread"], "figures": ["frequency_curve", "annual_maxima"],
        "gates": [{"check": "max_return_period_factor", "path": "years"},
                  {"check": "ci_finite", "path": "ffa.fits.gev_bootstrap.ci"},
                  {"check": "spread_within", "path": "ffa.fits.gev_lmoments.q, ffa.fits.lp3.q"}],
    },
    "water_quality_samples": {
        "kind": "station", "yields": ["samples"], "tables": ["samples", "sample_counts"],
        "figures": ["samples_by_parameter"],
        "gates": [{"check": "min_samples", "path": "sample_counts"}],
    },
    "anywhere": {
        "kind": "site", "yields": ["climate", "glofas"], "methods": ["glofas_cross_check", "spei_reanalysis"],
        "tables": ["monthly_climate", "glofas_summary"], "figures": ["monthly_climate", "glofas_series"],
        "gates": [{"check": "not_empty", "path": "climate"}],
    },
    "similar_basins": {
        "kind": "site", "yields": ["donors"], "methods": ["similar_basins"],
        "tables": ["donors"], "figures": ["donors_map"],
        "gates": [{"check": "min_donors", "path": "donors"}],
    },
    "regionalize_signatures": {
        "kind": "site", "yields": ["signatures", "donors"], "methods": ["regionalize_signatures"],
        "tables": ["signatures", "donors"], "figures": ["signatures_band"],
        "gates": [{"check": "min_donors", "path": "donors"}, {"check": "not_empty", "path": "signatures"}],
    },
    "drought_indices": {
        "kind": "site", "yields": ["spi", "spei", "drought_events", "temperature_trend"],
        "methods": ["spi", "spei", "spei_reanalysis"],
        "tables": ["indices_monthly", "drought_events", "index_divergence"], "figures": ["drought_strip"],
        "gates": [{"check": "not_empty", "path": "spi"}, {"check": "min_years", "path": "years"}],
    },
    "drought_propagation": {
        "kind": "station", "yields": ["sgi", "lag"], "methods": ["sgi"],
        "tables": ["sgi_monthly", "propagation_lag"], "figures": ["propagation"],
        "gates": [{"check": "not_empty", "path": "sgi"}],
    },
    "low_flow_context": {
        "kind": "station", "yields": ["low_flow"], "methods": ["low_flow_frequency", "baseflow_separation"],
        "tables": ["low_flow_stats"], "figures": ["fdc"],
        "gates": [{"check": "min_years", "path": "years"}],
    },
    "supply_reliability": {
        "kind": "site", "yields": ["reliability", "fdc"], "methods": ["supply_reliability"],
        "tables": ["reliability", "fdc_percentiles"], "figures": ["reliability_curve"],
        "gates": [{"check": "status_is", "path": "status"}, {"check": "not_empty", "path": "reliability"}],
    },
    "crop_water_demand": {
        "kind": "site", "yields": ["demand", "et0"], "methods": ["crop_water_requirement", "fao56_et0"],
        "tables": ["demand_monthly", "et0_monthly"], "figures": ["demand_monthly"],
        "gates": [{"check": "not_empty", "path": "demand"}],
    },
    # workbench analyses over a table (from_step or a load_table step)
    "eda": {"yields": ["summary"], "tables": ["summary"]},
    "quality": {"yields": ["quality"], "tables": ["quality_issues"]},
    "preprocess": {"yields": ["series"], "tables": ["series"]},
    "insights": {"yields": ["insights"], "tables": ["insights"]},
    "who_screen": {"yields": ["screen"], "tables": ["who_screen"], "figures": ["who_exceedances"]},
    "wqi": {"yields": ["wqi"], "methods": ["water_quality_index"], "tables": ["wqi"], "figures": ["wqi_bars"],
            "gates": [{"check": "not_empty", "path": "ccme"}]},
    "iwqi": {"yields": ["iwqi"], "methods": ["iwqi"], "tables": ["iwqi"]},
    "flow_duration": {"yields": ["fdc"], "methods": ["flow_duration"], "tables": ["fdc_percentiles"],
                      "figures": ["fdc"], "gates": [{"check": "not_empty", "path": "percentiles"}]},
    "baseflow": {"yields": ["baseflow"], "methods": ["baseflow_separation"], "tables": ["baseflow"],
                 "figures": ["baseflow"]},
    "recession": {"yields": ["recession"], "tables": ["recession_segments"]},
    "signatures": {"yields": ["signatures"], "tables": ["signatures"]},
    "return_periods": {"yields": ["ffa"], "methods": ["at_site_flood_frequency"], "tables": ["return_levels"],
                       "figures": ["frequency_curve"]},
    "reference_et": {"yields": ["et0"], "methods": ["fao56_et0"], "tables": ["et0"], "figures": ["et0_monthly"]},
    "irrigation": {"yields": ["demand", "schedule"], "methods": ["crop_water_requirement"],
                   "tables": ["demand", "schedule"], "figures": ["demand_monthly"]},
    "spei": {"yields": ["spi", "spei"], "methods": ["spi", "spei"], "tables": ["indices_monthly"],
             "figures": ["drought_strip"]},
    "sgi_drought": {"yields": ["sgi", "drought_events"], "methods": ["sgi"], "tables": ["sgi_monthly", "events"],
                    "figures": ["drought_strip"]},
    "recharge": {"yields": ["recharge"], "methods": ["recharge_wtf"], "tables": ["recharge_events"],
                 "figures": ["recharge"]},
    "aquifer_drawdown": {"kind": "none", "yields": ["drawdown"], "tables": ["drawdown"]},
    LOAD_TABLE: {
        "kind": "table", "yields": ["series", "samples"], "tables": ["series"], "figures": ["series"],
        "gates": [{"check": "not_empty", "path": "n"}],
    },
}

_CACHE: dict[str, Any] = {}


def _schema_of_function(func: Callable[..., Any], *,
                        skip: tuple[str, ...] = ("df",)) -> tuple[dict[str, Any], list[str]]:
    """Argument names and rough types from a signature (workbench analyses have no JSON schema of their own)."""
    props: dict[str, Any] = {}
    required: list[str] = []
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return props, required
    for name, p in sig.parameters.items():
        if name in skip or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        ann = p.annotation
        t = "any"
        text = str(ann) if ann is not inspect.Parameter.empty else ""
        if "bool" in text:
            t = "boolean"
        elif "int" in text:
            t = "integer"
        elif "float" in text:
            t = "number"
        elif "str" in text:
            t = "string"
        elif "list" in text or "Sequence" in text:
            t = "array"
        elif "dict" in text:
            t = "object"
        entry: dict[str, Any] = {"type": t}
        if p.default is not inspect.Parameter.empty:
            plain = isinstance(p.default, (int, float, str, bool, type(None)))
            entry["default"] = p.default if plain else str(p.default)
        else:
            required.append(name)
        props[name] = entry
    return props, required


def _build() -> dict[str, Entry]:
    from aquascope import workbench
    from aquascope.ai_engine.analyst import _tool_specs
    from aquascope.methods import METHODS

    out: dict[str, Entry] = {}
    for spec in _tool_specs():
        if spec.name in _NOT_STEPS:
            continue
        ann = _ANNOTATIONS.get(spec.name, {})
        props = dict((spec.parameters or {}).get("properties") or {})
        required = list((spec.parameters or {}).get("required") or [])
        kind = ann.get("kind") or ("station" if "station_id" in props else "site" if "lat" in props else "none")
        out[spec.name] = Entry(
            id=spec.name, about=spec.description, kind=kind, arguments=props, required=required,
            yields=list(ann.get("yields") or []), methods=list(ann.get("methods") or []),
            gates=list(ann.get("gates") or []), figures=list(ann.get("figures") or []),
            tables=list(ann.get("tables") or []),
        )
    for name, spec in workbench.TOOLS.items():
        if name in out:
            # The Analyst's tool of the same name wins in the runner (aquascope.study._tools), so the
            # workbench analysis is reachable only through analyse_table; do not list it twice.
            continue
        ann = _ANNOTATIONS.get(name, {})
        props, required = _schema_of_function(spec["func"])
        needs = spec.get("needs")
        if needs in ("frame", "weather"):
            props = {"from_step": {"type": "string", "description": "the id of the step whose payload is the table"},
                     **props}
            required = ["from_step", *required]
        out[name] = Entry(
            id=name, about=spec.get("summary") or name, kind=str(ann.get("kind") or needs or "frame"),
            arguments=props, required=required,
            yields=list(ann.get("yields") or []), methods=list(ann.get("methods") or []),
            gates=list(ann.get("gates") or []), figures=list(ann.get("figures") or []),
            tables=list(ann.get("tables") or []),
        )
    if "assess_site" not in out:
        ann = _ANNOTATIONS["assess_site"]
        out["assess_site"] = Entry(
            id="assess_site", about="What can be answered at a place: the gauges in reach, the catchment, "
            "and the registry's verdict per method.", kind="recon",
            arguments={"lat": {"type": "number"}, "lon": {"type": "number"}, "radius_km": {"type": "number"},
                       "problem": {"type": "string"}, "return_period": {"type": "number"}},
            required=["lat", "lon"], yields=ann["yields"], tables=ann["tables"],
        )
    ann = _ANNOTATIONS[LOAD_TABLE]
    out[LOAD_TABLE] = Entry(
        id=LOAD_TABLE, about="A table the user attached to the study (by its inventory id), as a payload with the "
        "series (datetime, value) or the sample rows, so a workbench step can take it with from_step.",
        kind="table",
        arguments={"table": {"type": "string", "description": "the inventory id of the upload, e.g. upload:flows.csv"},
                   "value_column": {"type": "string"}, "datetime_column": {"type": "string"}},
        required=["table"], yields=ann["yields"], tables=ann["tables"], figures=ann["figures"], gates=ann["gates"],
    )
    # citations from the registry, by the first method an entry applies
    for e in out.values():
        for m in e.methods:
            meth = METHODS.get(m)
            if meth is not None and meth.citation:
                e.citation = meth.citation
                break
    return out


def entries() -> dict[str, Entry]:
    """Every entry by id (built once)."""
    if "entries" not in _CACHE:
        _CACHE["entries"] = _build()
    return _CACHE["entries"]


def get(tool: str) -> Entry | None:
    return entries().get(tool)


def names() -> list[str]:
    return sorted(entries())


def compact(problem: str | None = None) -> list[dict[str, Any]]:
    """The catalogue as the model reads it. With ``problem`` (a registry problem kind such as ``flood_risk``),
    entries whose methods do not serve that problem drop to the end but stay listed: a study may still need them."""
    from aquascope.methods import METHODS

    rows = [e for e in entries().values()]

    def serves(e: Entry) -> bool:
        if not problem:
            return True
        return any(problem in (METHODS[m].problems if m in METHODS else ()) for m in e.methods) or not e.methods

    rows.sort(key=lambda e: (0 if serves(e) else 1, e.id))
    return [e.compact() for e in rows]


def callables(extra: dict[str, Callable[..., Any]] | None = None) -> dict[str, Callable[..., Any]]:
    """The dict of callables the runner executes: the study's own tools plus what the caller adds
    (the Studio binds ``load_table`` to its workspace)."""
    from aquascope.study import _tools

    tools = _tools()
    if extra:
        tools.update(extra)
    return tools


def figure_kinds() -> list[str]:
    """Every figure kind an entry names, so the figure makers can be checked against the catalogue."""
    return sorted({f for e in entries().values() for f in e.figures})


# ── validation of a model-written step ─────────────────────────────────────


def validate_step(step: dict[str, Any], *, known_ids: set[str] | None = None,
                  sufficiency: list[dict[str, Any]] | None = None) -> list[str]:
    """Errors in one plan step, in plain words. Empty means the step is acceptable.

    Checks: the tool exists; the arguments are the tool's (``from_step`` allowed
    for table analyses, ``{{ result.<step>.<path> }}`` references only to known
    ids); required arguments are present; ``depends_on`` names known ids; every
    gate is a check in :data:`aquascope.gates.CHECKS`; a ``method`` is a registry
    id the tool can apply and, when ``sufficiency`` (from the reconnaissance) is
    given, one the registry does not call not defensible here.
    """
    import re

    from aquascope.gates import CHECKS

    errors: list[str] = []
    tool = str(step.get("tool") or "")
    sid = str(step.get("id") or "?")
    entry = get(tool)
    if entry is None:
        errors.append(f"step {sid}: unknown tool {tool!r}")
        return errors
    args = step.get("arguments") or {}
    if not isinstance(args, dict):
        errors.append(f"step {sid}: arguments must be a mapping")
        args = {}
    allowed = set(entry.arguments) | {"from_step"}
    for k in args:
        if k not in allowed:
            errors.append(f"step {sid}: {tool} takes no argument {k!r} (it takes {sorted(entry.arguments)})")
    for k in entry.required:
        if k not in args and not (k == "from_step" and "from_step" in args):
            errors.append(f"step {sid}: {tool} needs argument {k!r}")
    ids = known_ids or set()
    ref = re.compile(r"\{\{\s*result\.([A-Za-z0-9_]+)\.")
    for k, v in args.items():
        if isinstance(v, str):
            for m in ref.finditer(v):
                if m.group(1) not in ids:
                    errors.append(f"step {sid}: argument {k!r} refers to step {m.group(1)!r}, which is not in the plan")
    src = args.get("from_step")
    if src is not None and str(src) not in ids:
        errors.append(f"step {sid}: from_step {src!r} is not an earlier step of the plan")
    for d in step.get("depends_on") or []:
        if str(d) not in ids:
            errors.append(f"step {sid}: depends_on {d!r} is not an earlier step of the plan")
    for g in step.get("expects") or []:
        if not isinstance(g, dict) or g.get("check") not in CHECKS:
            errors.append(f"step {sid}: gate {g!r} is not one of {sorted(CHECKS)}")
    method = step.get("method")
    if method:
        from aquascope.methods import METHODS

        if method not in METHODS:
            errors.append(f"step {sid}: method {method!r} is not in the registry")
        elif entry.methods and method not in entry.methods:
            errors.append(f"step {sid}: {tool} does not apply method {method!r} (it applies {entry.methods})")
        elif sufficiency:
            row = next((r for r in sufficiency if r.get("method") == method), None)
            status = (row or {}).get("status")
            if status in ("not_defensible", "not defensible"):
                errors.append(f"step {sid}: the registry calls {method!r} not defensible here: {row.get('reason')}")
    fb = step.get("fallback")
    if isinstance(fb, dict) and isinstance(fb.get("step"), dict):
        errors += [f"fallback of {e}" for e in validate_step(fb["step"], known_ids=ids, sufficiency=sufficiency)]
    return errors


def validate_plan(steps: list[dict[str, Any]], *, sufficiency: list[dict[str, Any]] | None = None) -> list[str]:
    """Every error over an ordered list of steps (ids must be unique; references may only point backwards)."""
    errors: list[str] = []
    seen: set[str] = set()
    for i, step in enumerate(steps, 1):
        sid = step.get("id")
        if not sid:
            errors.append(f"step {i}: no id")
            sid = f"s{i}"
        elif sid in seen:
            errors.append(f"step {sid}: duplicate id")
        errors += validate_step(step, known_ids=set(seen), sufficiency=sufficiency)
        seen.add(str(sid))
    return errors
