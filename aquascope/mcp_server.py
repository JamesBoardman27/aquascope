"""aquascope-mcp: the world's public gauges and aquascope's analyses as MCP tools (#113).

Run it with ``aquascope mcp`` (stdio). Every MCP-speaking assistant (Claude
Desktop, Claude Code, Cursor, ...) can then find stations anywhere on Earth
from the published catalog, pull the observed record through aquascope's
collectors, and get flood frequency, flow duration and trend with citations,
without writing Python.

Design rules:

* Tools read the Archive first (fast, no agency call) and only touch an
  agency API when a series is asked for.
* Responses are bounded: catalog searches are capped, series are resampled
  and truncated, analyses drop the raw arrays. An LLM context is not a
  data lake.
* Everything is plain JSON and comes from the same functions the CLI and the
  Explorer use (``aquascope.registry``, ``aquascope.archive.catalog``,
  ``aquascope.explore``).

Requires the ``mcp`` extra (``pip install "aquascope[mcp]"``). Works with the
official Python SDK 1.x (``FastMCP``) and 2.x (``MCPServer``).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

from aquascope import __version__
from aquascope.registry import SOURCES, redistributable_sources, station_sources
from aquascope.schemas.station import VARIABLES

logger = logging.getLogger(__name__)

SERVER_NAME = "aquascope"
INSTRUCTIONS = (
    "AquaScope gives you the world's public water gauges (USGS, UK EA, Hub'Eau, PEGELONLINE, Ireland OPW, "
    "Taiwan CWA and more) behind one schema. Start with find_stations (no agency call), then get_timeseries or "
    "analyze_station for a specific station. Flood frequency needs at least 10 complete years of daily flow. "
    "Always show the licence/attribution returned with the data."
)

MAX_STATIONS = 200
MAX_POINTS = 2_000


def _server():
    """Return an MCP server instance from whichever SDK generation is installed."""
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer

        return MCPServer(SERVER_NAME, instructions=INSTRUCTIONS, version=__version__)
    except ImportError:
        try:  # mcp 1.x
            from mcp.server.fastmcp import FastMCP

            return FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "The MCP server needs the 'mcp' package. Install it with: pip install 'aquascope[mcp]'"
            ) from exc


# ── tool implementations (plain functions, testable without an MCP client) ──


def list_sources() -> dict[str, Any]:
    """Every data source aquascope knows: agency, country, variables, licence, whether it has a station catalog."""
    out = []
    for key in sorted(SOURCES):
        m = SOURCES[key]
        out.append(
            {
                "key": key,
                "label": m.label,
                "agency": m.agency,
                "country": m.country,
                "region": m.region,
                "variables": list(m.variables),
                "station_catalog": m.supports_station_lookup,
                "supports_bbox": m.supports_bbox,
                "requires_api_key": m.requires_api_key,
                "license": m.license,
                "redistributable": m.redistributable,
                "homepage": m.homepage,
            }
        )
    return {
        "n_sources": len(out),
        "with_station_catalog": station_sources(),
        "redistributable": redistributable_sources(),
        "variables": list(VARIABLES),
        "sources": out,
    }


def find_stations(
    query: str | None = None,
    bbox: list[float] | None = None,
    near: list[float] | None = None,
    variable: str | None = None,
    sources: list[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Search the published station catalog (no agency call).

    query: substring of the station name or id. bbox: [west, south, east, north] in degrees.
    near: [lat, lon]; results are ordered nearest-first. variable: one of the registry vocabulary
    (discharge, water_level, precipitation, groundwater_level, ...). Returns at most ``limit`` (<= 200)
    stations with ids you can pass to get_timeseries / analyze_station.
    """
    from aquascope.archive.catalog import load_stations, search_stations

    if variable and variable not in VARIABLES:
        return {"error": f"unknown variable {variable!r}; allowed: {list(VARIABLES)}"}
    limit = max(1, min(int(limit or 25), MAX_STATIONS))
    rows = load_stations()
    hits = search_stations(
        rows,
        bbox=tuple(bbox) if bbox else None,
        near=tuple(near) if near else None,
        variable=variable,
        sources=sources,
        query=query,
        limit=limit,
    )
    slim = [
        {k: r.get(k) for k in ("source", "station_id", "name", "latitude", "longitude", "variables",
                               "period_start", "period_end", "river", "country", "agency", "license", "url")}
        for r in hits
    ]
    return {"n_catalog": len(rows), "n_returned": len(slim), "limit": limit, "stations": slim}


def get_timeseries(
    source: str,
    station_id: str,
    years: int = 10,
    resample: str = "D",
    max_points: int = 400,
    variable: str | None = None,
) -> dict[str, Any]:
    """Observed record for one station (archive first, then the agency), resampled and bounded.

    resample: 'D' daily, 'W' weekly, 'M' monthly means, 'Y' annual means. Values beyond ``max_points``
    are thinned evenly (never more than 2,000). variable: discharge (default), water_level,
    precipitation or groundwater_level, for stations that have several. Returns unit, variable, stats
    and the points as [date, value] pairs, plus licence and attribution.
    """
    import pandas as pd

    from aquascope.explore import fetch_series

    if source not in SOURCES:
        return {"error": f"unknown source {source!r}"}
    if variable and variable not in VARIABLES:
        return {"error": f"unknown variable {variable!r}; allowed: {list(VARIABLES)}"}
    meta = SOURCES[source]
    fetched = fetch_series(source, station_id, years=int(years), variable=variable)
    s = fetched["series"]
    if s is None or s.empty:
        return {"source": source, "station_id": station_id, "n": 0, "error": "no observations returned",
                "note": fetched["note"]}
    rule = {"D": "D", "W": "W", "M": "MS", "Y": "YS"}.get(str(resample).upper(), "D")
    r = s.resample(rule).mean().dropna()
    max_points = max(10, min(int(max_points or 400), MAX_POINTS))
    step = max(1, -(-len(r) // max_points))
    thinned = r.iloc[::step]
    return {
        "source": source,
        "station_id": station_id,
        "variable": fetched["variable"],
        "unit": fetched["unit"],
        "start": s.index.min().date().isoformat(),
        "end": s.index.max().date().isoformat(),
        "n_observations": int(len(s)),
        "resample": rule,
        "n_points": int(len(thinned)),
        "thinning_step": step,
        "stats": {"mean": float(s.mean()), "min": float(s.min()), "max": float(s.max())},
        "points": [[d.date().isoformat(), None if pd.isna(v) else round(float(v), 4)] for d, v in thinned.items()],
        "note": fetched["note"],
        "license": meta.license,
        "attribution": meta.attribution,
    }


def analyze_station(
    source: str, station_id: str, years: int = 40, bootstrap_ci: bool = False, variable: str | None = None
) -> dict[str, Any]:
    """Fetch and analyse one station: record summary, annual maxima, flood frequency (GEV L-moments and
    Log-Pearson III with 90 % CI; optional bootstrap GEV band), flow-duration percentiles, Mann-Kendall
    trend, and the method citations. Raw daily arrays are omitted; use get_timeseries for those.
    variable picks one of the station's variables (discharge by default; water_level, precipitation,
    groundwater_level where the station has them).
    """
    from aquascope.explore import analyze_station as _analyze
    from aquascope.explore import flood_ci

    if source not in SOURCES:
        return {"error": f"unknown source {source!r}"}
    if variable and variable not in VARIABLES:
        return {"error": f"unknown variable {variable!r}; allowed: {list(VARIABLES)}"}
    store: dict[str, Any] = {}
    res = _analyze(source, station_id, years=int(years), store=store, variable=variable)
    res.pop("series", None)
    if "fdc" in res:
        res["fdc"] = {k: res["fdc"][k] for k in ("q95", "q50", "q10")}
    if bootstrap_ci and res.get("ffa") and store.get("series") is not None:
        try:
            ci = flood_ci(store["series"])
            res["ffa"]["fits"]["gev_bootstrap"] = {k: ci[k] for k in ("q", "ci", "params")}
            res.setdefault("methods", []).append(ci["method"])
        except Exception as exc:  # noqa: BLE001
            res.setdefault("notes", []).append(f"bootstrap CI failed: {exc}")
    return res


def flood_frequency(source: str, station_id: str, years: int = 40, bootstrap_ci: bool = False) -> dict[str, Any]:
    """Return levels for T = 2, 5, 10, 25, 50, 100 years at a station (subset of analyze_station)."""
    res = analyze_station(source, station_id, years=years, bootstrap_ci=bootstrap_ci)
    if "error" in res:
        return res
    keep = {k: res.get(k) for k in ("source", "station_id", "agency", "license", "attribution", "unit",
                                    "start", "end", "years", "n", "ffa", "notes", "methods")}
    if not keep.get("ffa"):
        keep["error"] = "flood frequency not available (see notes)"
    return keep


def describe_methods() -> dict[str, Any]:
    """What each analysis computes and the reference to cite."""
    from aquascope.explore import METHODS, MIN_YEARS_FOR_FFA, RETURN_PERIODS

    return {"return_periods": RETURN_PERIODS, "min_years_for_ffa": MIN_YEARS_FOR_FFA, "methods": METHODS}


def archive_health() -> dict[str, Any]:
    """Status of the last catalog harvest per source (health.json from the Archive)."""
    import httpx

    from aquascope.archive.catalog import catalog_url

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        resp = client.get(catalog_url(filename="health.json"))
        resp.raise_for_status()
        return resp.json()


def _default_years_note() -> str:
    today = date.today()
    return f"Records are requested back to {(today - timedelta(days=int(40 * 365.25))).isoformat()} by default."


# ── server wiring ──────────────────────────────────────────────────────────


def build_server():
    """Create the MCP server with all tools and resources registered."""
    server = _server()
    server.tool()(list_sources)
    server.tool()(find_stations)
    server.tool()(get_timeseries)
    server.tool()(analyze_station)
    server.tool()(flood_frequency)
    server.tool()(describe_methods)
    server.tool()(archive_health)

    @server.resource("aquascope://sources")
    def sources_resource() -> str:
        """The source registry as JSON."""
        return json.dumps(list_sources(), ensure_ascii=False)

    @server.resource("aquascope://methods")
    def methods_resource() -> str:
        """Analysis methods and citations as JSON."""
        return json.dumps(describe_methods(), ensure_ascii=False)

    return server


def main(transport: str = "stdio") -> None:
    """Entry point for ``aquascope mcp``."""
    logging.basicConfig(level=logging.WARNING)
    build_server().run(transport)


if __name__ == "__main__":  # pragma: no cover
    main()
