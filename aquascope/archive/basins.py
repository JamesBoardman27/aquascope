"""Catchments for the whole world: BasinATLAS (HydroATLAS v1.0, CC BY 4.0) in the Archive.

HydroBASINS level-12 sub-basins (about 1.0 million polygons, ~130 km² each)
carry, in BasinATLAS, some 280 hydro-environmental attributes each: climate,
runoff, land cover, soils, population, dams. Caravan's static attributes are
exactly these. HydroATLAS is CC BY 4.0 (Linke et al. 2019), unlike the bare
HydroBASINS core product whose licence forbids stand-alone redistribution, so
BasinATLAS is what the Archive mirrors, under ``basins/``:

``basins/lev12.fgb``
    every level-12 sub-basin polygon (simplified) as FlatGeobuf, spatially
    indexed, so a point-in-polygon lookup over HTTPS reads a few kilobytes
``basins/lev12_topology.parquet``
    ``hybas_id, next_down, next_sink, main_bas, sub_area, up_area, pfaf_id,
    endo, coast, order, lat, lon``: the routing graph and centroids (small)
``basins/lev12_attributes.parquet``
    every BasinATLAS attribute per sub-basin, sorted by ``hybas_id`` so a
    row-group lookup is cheap
``basins/lev12.pmtiles``, ``basins/lev06.pmtiles``
    vector tiles for the Explorer (attributes limited to the routing keys)

Two jobs live here: :func:`build_basins` turns the BasinATLAS FileGDB into
those files (run by ``.github/workflows/basins.yml``), and the read side
(:func:`sub_basin_at`, :func:`upstream_ids`, :func:`catchment_attributes`,
:func:`describe_catchment`) answers "which catchment is this point in, what
is upstream, and what does the catchment look like" from the published files.

Attribution required by the licence (also embedded in every file's metadata):
Linke, S., Lehner, B., Ouellet Dallaire, C., et al. (2019). Global
hydro-environmental sub-basin and river reach characteristics at high spatial
resolution. Scientific Data 6: 283. https://doi.org/10.1038/s41597-019-0300-6
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_REPO_ID = "Rekin226/aquascope-gauges"
LEVEL = 12
LAYER = f"BasinATLAS_v10_lev{LEVEL:02d}"
COARSE_LEVEL = 6

ATTRIBUTION = (
    "HydroATLAS v1.0 (BasinATLAS), CC BY 4.0. Linke, S., Lehner, B., Ouellet Dallaire, C., et al. (2019). "
    "Global hydro-environmental sub-basin and river reach characteristics at high spatial resolution. "
    "Scientific Data 6: 283. https://doi.org/10.1038/s41597-019-0300-6"
)
LICENSE = "CC-BY-4.0"

TOPOLOGY_COLUMNS = ("HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "SUB_AREA", "UP_AREA", "PFAF_ID", "ENDO",
                    "COAST", "ORDER")

# The attributes a hydrologist asks about first, with the BasinATLAS field name
# (suffix: s = sub-basin, u = upstream; av = average, se = spatial extent %,
# yr = annual, mn/mx = min/max month) and how to aggregate over an upstream set.
# "area" = area-weighted mean over sub-basins, "sum" = total, "outlet" = value
# of the outlet sub-basin's upstream ("u") field, "max" = maximum.
ATTRIBUTE_GUIDE: dict[str, tuple[str, str, str, str]] = {
    # key: (field, unit, aggregation, label)
    "elevation_m": ("ele_mt_sav", "m", "area", "mean elevation"),
    "slope_deg": ("slp_dg_sav", "degrees", "area", "mean slope"),
    "precipitation_mm_yr": ("pre_mm_syr", "mm/yr", "area", "annual precipitation (WorldClim)"),
    "pet_mm_yr": ("pet_mm_syr", "mm/yr", "area", "annual potential evapotranspiration"),
    "aet_mm_yr": ("aet_mm_syr", "mm/yr", "area", "annual actual evapotranspiration"),
    "aridity_index": ("ari_ix_sav", "P/PET x 100", "area", "aridity index (x100)"),
    "temperature_c": ("tmp_dc_syr", "°C", "area", "mean annual air temperature (stored x10)"),
    "snow_cover_pct": ("snw_pc_syr", "%", "area", "annual snow cover extent"),
    "runoff_mm_yr": ("run_mm_syr", "mm/yr", "area", "annual land-surface runoff"),
    "discharge_m3s": ("dis_m3_pyr", "m3/s", "outlet", "mean annual natural discharge at the outlet"),
    "forest_pct": ("for_pc_sse", "%", "area", "forest cover"),
    "cropland_pct": ("crp_pc_sse", "%", "area", "cropland"),
    "pasture_pct": ("pst_pc_sse", "%", "area", "pasture"),
    "urban_pct": ("urb_pc_sse", "%", "area", "urban extent"),
    "irrigated_pct": ("ire_pc_sse", "%", "area", "irrigated area"),
    "glacier_pct": ("gla_pc_sse", "%", "area", "glacier extent"),
    "wetland_pct": ("wet_pc_sg1", "%", "area", "wetlands (all classes)"),
    "lake_pct": ("lka_pc_sse", "%", "area", "lake area"),
    "karst_pct": ("kar_pc_sse", "%", "area", "karst extent"),
    "clay_pct": ("cly_pc_sav", "%", "area", "clay fraction in soil"),
    "silt_pct": ("slt_pc_sav", "%", "area", "silt fraction in soil"),
    "sand_pct": ("snd_pc_sav", "%", "area", "sand fraction in soil"),
    "soil_water_pct": ("swc_pc_syr", "%", "area", "annual soil water content"),
    "groundwater_table_cm": ("gwt_cm_sav", "cm", "area", "groundwater table depth"),
    "population_density": ("ppd_pk_sav", "people/km2", "area", "population density"),
    "population": ("pop_ct_ssu", "people", "sum", "population count"),
    "degree_of_regulation_pct": ("dor_pc_pva", "%", "outlet", "degree of regulation by reservoirs"),
    "human_footprint_2009": ("hft_ix_s09", "index 0-100", "area", "human footprint (2009)"),
    "reservoir_volume_mcm": ("rev_mc_usu", "million m3", "outlet", "reservoir volume upstream"),
}


@dataclass
class BasinsBuildReport:
    built_at: str
    n_basins: int
    files: dict[str, int]
    seconds: float
    attribution: str = ATTRIBUTION
    license: str = LICENSE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def basins_url(filename: str, repo_id: str = DEFAULT_REPO_ID) -> str:
    return f"https://huggingface.co/datasets/{repo_id}/resolve/main/basins/{filename}"


# ── build (workflow) ────────────────────────────────────────────────────────


def _require_pyogrio():
    from aquascope.utils.imports import require

    return require("pyogrio", feature="basins build", group="basins")


def build_basins(
    gdb_path: str | Path,
    out_dir: str | Path,
    *,
    simplify_deg: float = 0.0005,
    batch: int = 50_000,
    max_features: int | None = None,
    write_fgb: bool = False,
) -> BasinsBuildReport:
    """Turn the BasinATLAS FileGDB into the Archive's ``basins/`` parquet files.

    Reads the level-12 layer in batches (about 1 M polygons) and streams the
    full attribute table into ``lev12_attributes.parquet`` (one row group per
    batch; the source is ordered by ``HYBAS_ID`` so row-group statistics prune
    lookups) while collecting the routing columns and a representative point
    per sub-basin into ``lev12_topology.parquet``. ``write_fgb`` also writes
    the simplified polygons as an indexed FlatGeobuf from Python (fine for
    tests and small extracts; the workflow streams it with ``ogr2ogr``
    instead, which needs no memory). ``max_features`` limits the read.
    """
    pyogrio = _require_pyogrio()
    from aquascope.utils.imports import require

    pa = require("pyarrow", feature="basins build", group="basins")
    pq = require("pyarrow.parquet", feature="basins build", group="basins")

    t0 = time.perf_counter()
    out = Path(out_dir) / "basins"
    out.mkdir(parents=True, exist_ok=True)
    info = pyogrio.read_info(str(gdb_path), layer=LAYER)
    total = int(info["features"]) if max_features is None else min(int(info["features"]), max_features)
    logger.info("BasinATLAS %s: %d features, %d fields", LAYER, total, len(info["fields"]))
    meta = {b"aquascope": json.dumps({"source": "BasinATLAS v1.0", "layer": LAYER, "license": LICENSE,
                                       "attribution": ATTRIBUTION}).encode()}

    topo_frames: list[pd.DataFrame] = []
    fgb_frames: list[Any] = []
    attr_path = out / f"lev{LEVEL:02d}_attributes.parquet"
    writer = None
    n_done = 0
    for start in range(0, total, batch):
        n = min(batch, total - start)
        gdf = pyogrio.read_dataframe(str(gdb_path), layer=LAYER, skip_features=start, max_features=n)
        gdf.columns = [c.lower() if c.upper() in TOPOLOGY_COLUMNS else c for c in gdf.columns]
        cent = gdf.geometry.representative_point()
        topo = pd.DataFrame({c.lower(): gdf[c.lower()] for c in TOPOLOGY_COLUMNS if c.lower() in gdf.columns})
        topo["lat"] = cent.y.round(5).to_numpy()
        topo["lon"] = cent.x.round(5).to_numpy()
        topo_frames.append(topo)
        attrs = pd.DataFrame(gdf.drop(columns=[gdf.geometry.name])).sort_values("hybas_id")
        table = pa.Table.from_pandas(attrs, preserve_index=False)
        if writer is None:
            schema = table.schema.with_metadata({**(table.schema.metadata or {}), **meta})
            writer = pq.ParquetWriter(attr_path, schema, compression="zstd")
        writer.write_table(table.cast(writer.schema), row_group_size=20_000)
        if write_fgb:
            keep = [c for c in ("hybas_id", "next_down", "main_bas", "sub_area", "up_area", "pfaf_id")
                    if c in gdf.columns]
            slim = gdf[keep + [gdf.geometry.name]].copy()
            if simplify_deg:
                slim[gdf.geometry.name] = slim.geometry.simplify(simplify_deg, preserve_topology=True)
            fgb_frames.append(slim)
        n_done += n
        logger.info("  %d / %d", n_done, total)
    if writer is not None:
        writer.close()
    files: dict[str, int] = {attr_path.name: attr_path.stat().st_size} if attr_path.exists() else {}

    topo_df = pd.concat(topo_frames, ignore_index=True).sort_values("hybas_id").reset_index(drop=True)
    topo_table = pa.Table.from_pandas(topo_df, preserve_index=False)
    topo_table = topo_table.replace_schema_metadata({**(topo_table.schema.metadata or {}), **meta})
    p = out / f"lev{LEVEL:02d}_topology.parquet"
    pq.write_table(topo_table, p, compression="zstd", row_group_size=200_000)
    files[p.name] = p.stat().st_size

    if write_fgb and fgb_frames:
        import geopandas as gpd

        fgb_path = out / f"lev{LEVEL:02d}.fgb"
        all_fgb = gpd.GeoDataFrame(pd.concat(fgb_frames, ignore_index=True), crs=fgb_frames[0].crs)
        pyogrio.write_dataframe(all_fgb, str(fgb_path), driver="FlatGeobuf", layer_options={"SPATIAL_INDEX": "YES"})
        files[fgb_path.name] = fgb_path.stat().st_size

    report = BasinsBuildReport(
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), n_basins=int(len(topo_df)),
        files=files, seconds=round(time.perf_counter() - t0, 1),
    )
    (out / "build.json").write_text(json.dumps(report.to_dict(), indent=1), encoding="utf-8")
    logger.info("basins built: %d sub-basins in %.0fs", report.n_basins, report.seconds)
    return report


# ── read side ───────────────────────────────────────────────────────────────


def _cache_path(name: str, repo_id: str) -> Path:
    from aquascope.archive.catalog import cache_dir

    return cache_dir() / f"{repo_id.replace('/', '__')}__basins__{name}"


def load_topology(
    *, repo_id: str = DEFAULT_REPO_ID, refresh: bool = False, path: str | Path | None = None
) -> pd.DataFrame:
    """The level-12 routing table (about 1 M rows), downloaded once a day into the cache."""
    from aquascope.archive.catalog import _download

    if path is None:
        path = _download(basins_url(f"lev{LEVEL:02d}_topology.parquet", repo_id),
                         _cache_path(f"lev{LEVEL:02d}_topology.parquet", repo_id), refresh)
    return pd.read_parquet(path)


class Topology:
    """Upstream/downstream navigation over the level-12 graph, built once from the topology frame."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.set_index("hybas_id", drop=False)
        self.children: dict[int, list[int]] = defaultdict(list)
        for hid, nd in zip(df["hybas_id"].to_numpy(), df["next_down"].to_numpy()):
            if nd:
                self.children[int(nd)].append(int(hid))

    def upstream_ids(self, hybas_id: int, *, include_self: bool = True, limit: int = 200_000) -> list[int]:
        seen = {int(hybas_id)}
        order = [int(hybas_id)] if include_self else []
        q = deque([int(hybas_id)])
        while q and len(seen) < limit:
            for c in self.children.get(q.popleft(), ()):
                if c not in seen:
                    seen.add(c)
                    order.append(c)
                    q.append(c)
        return order

    def downstream_ids(self, hybas_id: int, *, limit: int = 5_000) -> list[int]:
        out: list[int] = []
        cur = int(hybas_id)
        while len(out) < limit:
            nd = int(self.df.at[cur, "next_down"]) if cur in self.df.index else 0
            if not nd:
                break
            out.append(nd)
            cur = nd
        return out


def sub_basin_at(
    lat: float, lon: float, *, repo_id: str = DEFAULT_REPO_ID, fgb_path: str | Path | None = None
) -> dict[str, Any] | None:
    """The level-12 sub-basin containing the point, from the indexed FlatGeobuf (one small range read).

    Returns ``{"hybas_id", "next_down", "main_bas", "sub_area", "up_area", "pfaf_id"}`` or None.
    Needs pyogrio and shapely (``basins`` extra).
    """
    pyogrio = _require_pyogrio()
    from shapely.geometry import Point

    src = str(fgb_path) if fgb_path else f"/vsicurl/{basins_url(f'lev{LEVEL:02d}.fgb', repo_id)}"
    d = 0.02
    gdf = pyogrio.read_dataframe(src, bbox=(lon - d, lat - d, lon + d, lat + d))
    if gdf.empty:
        return None
    pt = Point(lon, lat)
    hit = gdf[gdf.contains(pt)]
    if hit.empty:
        hit = gdf.iloc[[gdf.distance(pt).argmin()]]
    row = hit.iloc[0]
    return {k: (int(row[k]) if k in ("hybas_id", "next_down", "main_bas", "pfaf_id") else float(row[k]))
            for k in ("hybas_id", "next_down", "main_bas", "sub_area", "up_area", "pfaf_id") if k in hit.columns}


def load_attributes(
    hybas_ids: list[int],
    *,
    repo_id: str = DEFAULT_REPO_ID,
    path: str | Path | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """BasinATLAS attribute rows for the given sub-basins (row groups pruned by hybas_id min/max)."""
    from aquascope.utils.imports import require

    pq = require("pyarrow.parquet", feature="basins", group="archive")
    ds = require("pyarrow.dataset", feature="basins", group="archive")
    pc = require("pyarrow.compute", feature="basins", group="archive")

    if path is None:
        from aquascope.archive.catalog import _download

        path = _download(basins_url(f"lev{LEVEL:02d}_attributes.parquet", repo_id),
                         _cache_path(f"lev{LEVEL:02d}_attributes.parquet", repo_id), False)
    dataset = ds.dataset(str(path), format="parquet")
    ids = [int(x) for x in hybas_ids]
    table = dataset.to_table(filter=pc.field("hybas_id").isin(ids), columns=columns)
    _ = pq
    return table.to_pandas()


def catchment_attributes(ids: list[int], attrs: pd.DataFrame, outlet: int | None = None) -> dict[str, Any]:
    """Aggregate BasinATLAS attributes over a set of sub-basins per :data:`ATTRIBUTE_GUIDE`."""
    if attrs.empty:
        return {}
    df = attrs.set_index("hybas_id")
    df = df[df.index.isin(ids)]
    if df.empty:
        return {}
    w = df["sub_area"].astype(float).clip(lower=0) if "sub_area" in df.columns else pd.Series(1.0, index=df.index)
    wsum = float(w.sum()) or 1.0
    if outlet is None:
        outlet = int(df["up_area"].astype(float).idxmax()) if "up_area" in df.columns else int(df.index[0])
    outlet = int(outlet)
    out: dict[str, Any] = {
        "n_sub_basins": int(len(df)),
        "area_km2": round(float(w.sum()), 1),
        "outlet_hybas_id": outlet,
    }
    if "up_area" in df.columns and outlet in df.index:
        out["upstream_area_km2"] = round(float(df.at[outlet, "up_area"]), 1)
    for key, (field, unit, how, label) in ATTRIBUTE_GUIDE.items():
        if field not in df.columns:
            continue
        col = pd.to_numeric(df[field], errors="coerce")
        if col.isna().all():
            continue
        if how == "area":
            val = float((col.fillna(0) * w).sum() / wsum)
        elif how == "sum":
            val = float(col.fillna(0).sum())
        elif how == "max":
            val = float(col.max())
        else:  # outlet
            val = float(col.get(outlet, col.iloc[0]))
        if field == "tmp_dc_syr":
            val, unit = val / 10.0, "°C"
        if field == "ari_ix_sav":
            val, unit = val / 100.0, "P/PET"
        out[key] = {"value": round(val, 2), "unit": unit, "label": label, "field": field, "aggregation": how}
    return out


def describe_catchment(
    lat: float, lon: float, *, repo_id: str = DEFAULT_REPO_ID, upstream: bool = True, max_sub_basins: int = 20_000
) -> dict[str, Any]:
    """Which sub-basin a point sits in, what drains to it, and the catchment's HydroATLAS attributes.

    Runs entirely on the Archive's ``basins/`` files. ``upstream=False`` describes the local
    level-12 sub-basin only. Returns a JSON-safe dict with ``sub_basin``, ``upstream``
    (ids count and area) and ``attributes`` (see :data:`ATTRIBUTE_GUIDE`), plus licence
    and attribution.
    """
    sb = sub_basin_at(lat, lon, repo_id=repo_id)
    if sb is None:
        return {"latitude": lat, "longitude": lon,
                "error": "no BasinATLAS sub-basin contains this point (ocean, or outside coverage)"}
    ids = [sb["hybas_id"]]
    note = "local level-12 sub-basin only"
    if upstream:
        topo = Topology(load_topology(repo_id=repo_id))
        ids = topo.upstream_ids(sb["hybas_id"], limit=max_sub_basins)
        note = f"catchment upstream of the sub-basin containing the point ({len(ids)} level-12 sub-basins)"
        if len(ids) >= max_sub_basins:
            note += "; truncated at the sub-basin cap, attributes cover the nearest part of the basin"
    attrs = load_attributes(ids, repo_id=repo_id)
    return {
        "latitude": lat,
        "longitude": lon,
        "sub_basin": sb,
        "upstream": {"n_sub_basins": len(ids), "note": note},
        "attributes": catchment_attributes(ids, attrs, outlet=sb["hybas_id"]),
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "methods": [{
            "name": "Catchment attributes from BasinATLAS (HydroATLAS v1.0)",
            "text": "Level-12 HydroBASINS sub-basins traced upstream through the NEXT_DOWN routing field; "
                    "attributes aggregated as area-weighted means (or outlet / total values where the field is "
                    "already an upstream aggregate).",
            "citation": ATTRIBUTION,
        }],
    }


__all__ = [
    "ATTRIBUTE_GUIDE", "ATTRIBUTION", "LICENSE", "Topology", "basins_url", "build_basins", "catchment_attributes",
    "describe_catchment", "load_attributes", "load_topology", "sub_basin_at",
]
