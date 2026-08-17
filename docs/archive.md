# The Archive: the world's public gauges as one open dataset

AquaScope's collectors already reach national agencies on four continents. The
Archive turns that reach into a data asset anyone can use without Python: a
scheduled harvest writes what the sources answer into cloud-native files and
publishes them to a public Hugging Face dataset,
[`Rekin226/aquascope-gauges`](https://huggingface.co/datasets/Rekin226/aquascope-gauges).

Phase 0 is the **station catalog**. Phase 1 (also shipped, filling up week by
week) mirrors **daily observations** for the sources whose terms allow it. See
[#188](https://github.com/Rekin226/aquascope/issues/188) for the plan.

## What is in it

| file | contents |
| --- | --- |
| `stations.parquet` | GeoParquet 1.0 (WKB point geometry, WGS84). One row per station: `source`, `station_id`, `name`, `latitude`, `longitude`, `variables`, `period_start`, `period_end`, `url`, `river`, `country`, `agency`, `license`, `redistributable`, `extra`. |
| `stations.geojson` | the same rows as GeoJSON, for tools and browsers that don't read parquet |
| `health.json` | per-source status of the last run: station count, seconds, error message if the endpoint failed |
| `README.md` | the dataset card, regenerated on every run, with the per-source licence table |
| `obs/<variable>/<source>/<station_id>.csv.gz` | daily means for one station (`date,value`, SI units), only for redistributable sources; today USGS, UK EA, Hub'Eau discharge and Taiwan CWA rainfall |
| `obs/manifest.json` | every harvested station with period, count, unit and harvest time; `obs/last_run.json` the last run's per-source tallies |

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

Each weekly run harvests a budget of stations per source (150 for USGS, UK EA
and Hub'Eau, 15 for CWA) and re-harvests a station once it is older than 30
days, so the archive grows without ever hammering an agency. Read one station:

```python
import pandas as pd
s = pd.read_csv("hf://datasets/Rekin226/aquascope-gauges/obs/discharge/usgs/USGS-01646500.csv.gz")
```

or a whole source with DuckDB:

```sql
SELECT * FROM read_csv('hf://datasets/Rekin226/aquascope-gauges/obs/discharge/hubeau_hydrometrie/*.csv.gz');
```

The Explorer and `aquascope.explore.fetch_series` read a station's file first
(one HTTPS GET, no agency load) and only fall back to the agency when the
archive has no file yet.

Run it yourself: `aquascope harvest obs --out archive --source usgs --max-stations 50`
(add `--sync-from Rekin226/aquascope-gauges` for an incremental run and
`--publish` to upload).

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
