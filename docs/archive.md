# The Archive: the world's public gauges as one open dataset

AquaScope's collectors already reach national agencies on four continents. The
Archive turns that reach into a data asset anyone can use without Python: a
scheduled harvest writes what the sources answer into cloud-native files and
publishes them to a public Hugging Face dataset,
[`Rekin226/aquascope-gauges`](https://huggingface.co/datasets/Rekin226/aquascope-gauges).

Phase 0 is the **station catalog**. Phase 1 mirrors **daily observations**
for the sources whose terms allow it, filling up week by week. Phase 2 adds
**more variables** (water level, rainfall, groundwater level) and **one
Parquet bundle per variable and source** for whole-source reads. See
[#188](https://github.com/Rekin226/aquascope/issues/188) for the plan.

## What is in it

| file | contents |
| --- | --- |
| `stations.parquet` | GeoParquet 1.0 (WKB point geometry, WGS84). One row per station: `source`, `station_id`, `name`, `latitude`, `longitude`, `variables`, `period_start`, `period_end`, `url`, `river`, `country`, `agency`, `license`, `redistributable`, `extra`. |
| `stations.geojson` | the same rows as GeoJSON, for tools and browsers that don't read parquet |
| `health.json` | per-source status of the last run: station count, seconds, error message if the endpoint failed |
| `README.md` | the dataset card, regenerated on every run, with the per-source licence table |
| `obs/<variable>/<source>/<station_id>.csv.gz` | daily values for one station (`date,value`; discharge m3/s, water and groundwater level m, precipitation mm/day), only for redistributable sources |
| `obs/<variable>/<source>.parquet` | the folder above as one Parquet bundle: `station_id, date, value`, sorted, snappy; `station_id` joins to `stations.parquet` |
| `obs/manifest.json` | every harvested station with period, count, unit, measure note and harvest time, keyed by `source/variable`, plus every bundle; `obs/last_run.json` the last run's per-source tallies |

Sources with a station catalog today: USGS, UK Environment Agency, Hub'Eau
(France), PEGELONLINE (Germany), Ireland OPW, Taiwan CWA. Every source that
gains a `stations()` implementation appears on the next run.

## Query it in place

DuckDB reads the parquet over HTTPS (Hugging Face serves range requests):

```sql
INSTALL httpfs; LOAD httpfs;
SELECT source, count(*) AS n
FROM 'https://huggingface.co/datasets/Rekin226/aquascope-gauges/resolve/main/stations.parquet'
GROUP BY source ORDER BY n DESC;
```

Python, no aquascope needed:

```python
import pandas as pd
stations = pd.read_parquet("hf://datasets/Rekin226/aquascope-gauges/stations.parquet")
```

GeoPandas / QGIS open the parquet directly as a point layer.

## Observations, incrementally

Each weekly run harvests a budget of stations per source and variable and
re-harvests a station once it is older than 30 days, so the archive grows
without ever hammering an agency. What is mirrored:

| source | variables | where the daily value comes from |
| --- | --- | --- |
| `usgs` | discharge, water_level | NWIS daily values, 00060 and 00065 (gage height converted from feet to metres) |
| `uk_ea` | discharge, water_level, precipitation, groundwater_level | Hydrology API daily mean flow; daily max level where no daily mean is published; daily rainfall totals; borehole levels in metres above Ordnance Datum (manual dips or logger) |
| `hubeau_hydrometrie` | discharge | obs_elab QmnJ, the elaborated daily mean discharge |
| `taiwan_cwa` | precipitation | CODIS daily rainfall |

Read one station:

```python
import pandas as pd
s = pd.read_csv("hf://datasets/Rekin226/aquascope-gauges/obs/discharge/usgs/USGS-01646500.csv.gz")
```

a whole source and variable in one go (the bundle):

```python
df = pd.read_parquet("hf://datasets/Rekin226/aquascope-gauges/obs/groundwater_level/uk_ea.parquet")
# or, with aquascope: from aquascope.archive import load_observations; df = load_observations("uk_ea", "groundwater_level")
```

or with DuckDB, joined to the catalog:

```sql
SELECT s.name, o.date, o.value
FROM 'hf://datasets/Rekin226/aquascope-gauges/obs/discharge/uk_ea.parquet' o
JOIN 'hf://datasets/Rekin226/aquascope-gauges/stations.parquet' s USING (station_id)
WHERE s.name ILIKE '%thames%';
```

The Explorer and `aquascope.explore.fetch_series` read a station's file first
(one HTTPS GET, no agency load) and only fall back to the agency when the
archive has no file yet. `fetch_series(..., variable="water_level")` (and the
`variable` argument of the MCP `analyze_station` / `get_timeseries` tools)
picks one variable at stations that have several.

Run it yourself: `aquascope harvest obs --out archive --source uk_ea --variable groundwater_level --max-stations 50`
(add `--sync-from Rekin226/aquascope-gauges` for an incremental run and
`--publish` to upload), then `aquascope harvest bundles --out archive` to roll
the folders into Parquet.

## Catchments: BasinATLAS in the Archive (`basins/`)

Gauges are points; hydrology happens in catchments. The Archive carries the
level-12 sub-basins of HydroATLAS v1.0 / BasinATLAS (Linke et al. 2019,
CC BY 4.0: about a million polygons of ~130 km² with routing and some 280
attributes each) so any point on land can be placed in its catchment and the
catchment described without a GIS:

| file | contents |
| --- | --- |
| `basins/lev12.fgb` | simplified sub-basin polygons as FlatGeobuf with a spatial index: a point-in-polygon lookup over HTTPS reads a few kilobytes |
| `basins/lev12_topology.parquet` | `hybas_id, next_down, next_sink, main_bas, sub_area, up_area, pfaf_id, endo, coast, order, lat, lon` |
| `basins/lev12_attributes.parquet` | every BasinATLAS attribute per sub-basin, including the upstream-aggregated `*_u*` fields, sorted by `hybas_id` |
| `basins/lev12.pmtiles`, `basins/lev06.pmtiles` | vector tiles for the Explorer |

```bash
pip install "aquascope[basins]"
aquascope basins at 48.85 2.35            # the Seine at Paris: sub-basin, upstream area, climate, land cover, soils, dams
aquascope basins at 25.04 121.56 --local  # only the level-12 sub-basin containing the point
aquascope basins upstream 2120018800      # every level-12 sub-basin draining to this one
```

```python
from aquascope.archive import basins
res = basins.describe_catchment(48.85, 2.35)      # dict: sub_basin, upstream, attributes, licence, methods
topo = basins.Topology(basins.load_topology())     # upstream_ids / downstream_ids over the whole graph
```

The MCP tool `describe_catchment(lat, lon)` and the analyst expose the same
function, and the Explorer shows the card and highlights the upstream
sub-basins for any station or clicked point.

### Similar gauged basins (prediction in ungauged basins, the practical half)

The weekly harvest also spatially joins every catalog station to its
sub-basin and publishes `basins/station_catchments.parquet` (station, sub-basin,
upstream area and the catchment attributes above). On that table,

```bash
aquascope basins similar 25.04 121.56 --k 8            # gauges whose catchments most resemble this point's
aquascope basins similar --station usgs/USGS-01646500  # ... or a station's own catchment (itself excluded)
aquascope basins similar 48.85 2.35 --method proximity --source hubeau_hydrometrie
```

ranks the gauged stations by weighted Euclidean distance in standardised
BasinATLAS attribute space (log area, elevation, slope, precipitation,
aridity, temperature, snow, forest, cropland, urban, clay, sand, population
density, regulation), by great-circle distance, or both (`combined`, the
default), and prints the per-feature deltas. That is the donor-selection
step of regionalisation (Bloeschl et al. 2013; Oudin et al. 2008); the MCP
tool `similar_basins` and the analyst use it ("find gauges like this
ungauged site, then analyse the best donors"), and the Explorer lists them
under the catchment card. `aquascope.archive.similar` is the module; #53
tracks the regression / leave-one-out half. Built by
`.github/workflows/basins.yml` (`aquascope basins build` plus `ogr2ogr` and
`tippecanoe`); it downloads BasinATLAS from figshare, so it runs on demand,
not weekly. Why BasinATLAS and not HydroBASINS: the HydroSHEDS core licence
forbids stand-alone redistribution, HydroATLAS is CC BY 4.0.

## Caravan-format export

`aquascope caravan export --source uk_ea --out caravan_gb` turns the archive
(catalog + discharge bundle + BasinATLAS + Open-Meteo forcing) into a Caravan
sub-dataset: per-gauge daily forcing and mm/d streamflow, climate indices and
HydroATLAS-style attributes. See [caravan.md](caravan.md).

## Terms

The station catalog is factual metadata (where a gauge is, what it measures)
and every row links back to the agency page. Observations will only be
mirrored for sources whose licence permits it: the registry entry's
`redistributable` flag is the gate, and it is `False` until someone has read
the terms and recorded the licence id. The current state per source is in the
dataset card and in `aquascope list-sources`.

## Run it yourself

```bash
pip install "aquascope[archive]"
aquascope harvest stations --out archive            # local files only
aquascope harvest stations --out archive --publish you/your-dataset   # needs HF_TOKEN
```

The scheduled run lives in `.github/workflows/harvest.yml` (Mondays 03:17 UTC,
or on demand from the Actions tab). It never fails because one agency is down;
`health.json` and the job summary say which one did.
