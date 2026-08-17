# The Explorer: click any gauge on Earth, nothing to install

**Live:** [rekin226-aquascope-explorer.static.hf.space](https://rekin226-aquascope-explorer.static.hf.space/)
(also under [/explorer/](https://rekin226.github.io/aquascope/explorer/) on this docs site).

A static page, no server. It reads the station catalog from the
[Archive](archive.md) with DuckDB-WASM, shows every station on a MapLibre map,
and when you click one it fetches the observed record from the agency and runs
aquascope in your browser (Pyodide) to compute:

- the hydrograph and annual maxima,
- flood frequency: GEV by L-moments and Log-Pearson III with analytical 90 %
  confidence limits, plus an optional bootstrap GEV band (1,000 refits, on
  demand),
- the flow-duration curve with Q95 / Q10,
- a Mann-Kendall trend with Sen's slope on the annual means,
- and a "Methods and citations" panel naming exactly what was computed and the
  references, so the numbers are defensible in a report.

Every result has a permalink (`#s=<source>/<station_id>`), a CSV download, and
a link to the agency page. Data licence and attribution are shown per source.

Click anywhere that is not a gauge and you get the **hydrology of that point**
(`#p=<lat>,<lon>`): ERA5 rainfall and temperature, FAO-56 reference
evapotranspiration and the aridity class, a monthly climate chart, GloFAS
modelled discharge with an indicative return-period table (clearly labelled
as a model, not a gauge), and the nearest gauges to click next. All from
Open-Meteo, keyless.

Stations already mirrored in the [Archive](archive.md) load from it (one small
file) instead of from the agency, so they are faster and do not add load
upstream.

## What works today (Phase 0 of [#189](https://github.com/Rekin226/aquascope/issues/189))

| source | record you get | analyses |
| --- | --- | --- |
| USGS | daily mean discharge (or gage height), full period requested (40 years) | all of the above |
| UK Environment Agency | daily mean flow (falls back to level, rainfall, groundwater), full period | all of the above |
| Hub'Eau (France) | daily mean discharge (obs_elab `QmnJ`, multi-decade where computed), else last 30 days real-time | all of the above when the daily series exists |
| PEGELONLINE (Germany) | last 31 days of W / Q | hydrograph |
| Ireland OPW | last month of 15-minute levels | hydrograph |
| Taiwan CWA | daily rainfall, last 10 years (one request per year at the source, a few seconds each) | hydrograph, annual maxima, trend |

Flood frequency needs at least 10 complete years of daily flow; the page says
so when a record is shorter.

## How it is built

`explorer/` in the repository, no build step:

- `index.html`, `style.css`, `app.js`: map (MapLibre + CARTO raster basemap),
  catalog (DuckDB-WASM over the archive's GeoParquet, GeoJSON fallback), search,
  panel and Plotly charts.
- `worker.js`: a Web Worker that loads Pyodide, numpy / scipy / pandas, and the
  aquascope wheel, then calls `aquascope.explore`.
- `aquascope.explore` (in the package): the Python half, the same
  `(source, station) -> answer` entry point the CLI and the MCP server use.
  It runs unchanged in CPython, which is how it is tested (`tests/test_explore.py`).
- `build.py`: assembles the site (wheel + `wheels.json` + cache-busting token).
  `.github/workflows/explorer.yml` publishes it to the Hugging Face static Space
  on every push to `main`; `docs.yml` adds it under `/explorer/` here.

First analysis in a session loads about 15 MB of Python once; the catalog
itself arrives in a few seconds. Sources that don't allow browser fetches
(CORS) will come through the Archive as it grows.

## Run it locally

```bash
pip install build
python explorer/build.py --out dist-explorer
cd dist-explorer && python -m http.server 8000   # then open http://localhost:8000/
```
