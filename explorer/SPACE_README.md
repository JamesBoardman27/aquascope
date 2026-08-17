---
title: AquaScope Explorer
emoji: 🌊
colorFrom: blue
colorTo: green
sdk: static
pinned: true
license: mit
short_description: Click any public water gauge on Earth, nothing to install
---

# 🌊 AquaScope Explorer

Every public water gauge [AquaScope](https://github.com/Rekin226/aquascope) can
reach, on one map. Click a station and get the observed record straight from
the agency, plus flood frequency (GEV, Log-Pearson III with confidence limits),
flow duration and trend, computed **in your browser** by aquascope running on
Pyodide. Nothing to install, no server, no account.

- Station catalog: [`Rekin226/aquascope-gauges`](https://huggingface.co/datasets/Rekin226/aquascope-gauges)
  (GeoParquet, harvested weekly), read in place with DuckDB-WASM.
- Sources with a catalog today: USGS, UK Environment Agency, Hub'Eau (France),
  PEGELONLINE (Germany), Ireland OPW, Taiwan CWA.
- Full daily records: USGS and UK EA. Real-time feeds (last month): Hub'Eau,
  PEGELONLINE, OPW. Daily rainfall: Taiwan CWA.

Source and issues: https://github.com/Rekin226/aquascope (Explorer epic #189, Archive epic #188).
