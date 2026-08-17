// AquaScope Explorer, main thread: catalog -> map -> click -> worker (Pyodide) -> charts.
// No build step. Everything static; the only server is a CDN and the agencies' own APIs.

import { CONFIG } from "./config.js?v=__BUILD__";

const SOURCE_STYLE = {
  usgs: { label: "USGS (US)", color: "#1565c0" },
  uk_ea: { label: "Environment Agency (UK)", color: "#2e7d32" },
  hubeau_hydrometrie: { label: "Hub'Eau (FR)", color: "#c62828" },
  pegelonline: { label: "PEGELONLINE (DE)", color: "#ef6c00" },
  ireland_opw: { label: "OPW (IE)", color: "#6a1b9a" },
  taiwan_cwa: { label: "CWA (TW)", color: "#00838f" },
};
const FALLBACK_COLOR = "#546e7a";
const VAR_LABEL = {
  discharge: "discharge", water_level: "water level", precipitation: "rainfall",
  groundwater_level: "groundwater", climate: "climate", water_quality: "water quality",
};

const $ = (id) => document.getElementById(id);
// Debug hooks (harmless in production): window.__aq.state, window.__aq.log
const dbg = (window.__aq = { log: [], state: null });
const trace = (msg) => { dbg.log.push(`${new Date().toISOString().slice(11, 19)} ${msg}`); };
const state = { stations: [], byKey: new Map(), hidden: new Set(), selected: null, result: null, workerReady: false, pending: new Map(), reqId: 0, mapOk: false, marker: null, point: null };
dbg.state = state;

// ── catalog ─────────────────────────────────────────────────────────────────

async function loadCatalogDuckDB() {
  trace("duckdb: import");
  const duckdb = await import(CONFIG.duckdbModule);
  const bundles = duckdb.getJsDelivrBundles();
  const bundle = await duckdb.selectBundle(bundles);
  trace(`duckdb: bundle ${bundle.mainModule}`);
  const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }));
  const worker = new Worker(workerUrl);
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  trace("duckdb: instantiated");
  URL.revokeObjectURL(workerUrl);
  const conn = await db.connect();
  const sql = `SELECT source, station_id, name, latitude, longitude, variables,
                      CAST(period_start AS VARCHAR) AS period_start, CAST(period_end AS VARCHAR) AS period_end, url
               FROM read_parquet('${CONFIG.stationsParquet}')`;
  const table = await conn.query(sql);
  trace(`duckdb: query returned ${table.numRows} rows`);
  const rows = table.toArray().map((r) => r.toJSON());
  await conn.close();
  await db.terminate();
  return rows.map((r) => ({
    source: r.source, station_id: r.station_id, name: r.name ?? null,
    lat: Number(r.latitude), lon: Number(r.longitude),
    variables: Array.isArray(r.variables) ? r.variables : (r.variables?.toArray?.() ?? []),
    period_start: r.period_start ? String(r.period_start).slice(0, 10) : null,
    period_end: r.period_end ? String(r.period_end).slice(0, 10) : null,
    url: r.url ?? null,
  }));
}

async function loadCatalogGeoJSON() {
  const res = await fetch(CONFIG.stationsGeoJSON);
  if (!res.ok) throw new Error(`GeoJSON ${res.status}`);
  const gj = await res.json();
  return gj.features.map((f) => ({
    source: f.properties.source, station_id: f.properties.station_id, name: f.properties.name ?? null,
    lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1],
    variables: f.properties.variables ?? [], period_start: f.properties.period_start ?? null,
    period_end: f.properties.period_end ?? null, url: f.properties.url ?? null,
  }));
}

async function loadCatalog() {
  $("count").textContent = "loading catalog…";
  let rows;
  try {
    rows = await loadCatalogDuckDB();
    console.info(`catalog via DuckDB-WASM: ${rows.length} stations`);
  } catch (err) {
    console.warn("DuckDB-WASM path failed, falling back to GeoJSON:", err);
    trace(`duckdb failed: ${err && err.message}; geojson fallback`);
    rows = await loadCatalogGeoJSON();
    console.info(`catalog via GeoJSON: ${rows.length} stations`);
  }
  state.stations = rows;
  state.byKey = new Map(rows.map((r) => [`${r.source}/${r.station_id}`, r]));
  return rows;
}

function toFeatureCollection(rows) {
  return {
    type: "FeatureCollection",
    features: rows.filter((r) => !state.hidden.has(r.source)).map((r) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [r.lon, r.lat] },
      properties: { key: `${r.source}/${r.station_id}`, source: r.source, name: r.name ?? "", color: (SOURCE_STYLE[r.source] || {}).color || FALLBACK_COLOR },
    })),
  };
}

// ── map ─────────────────────────────────────────────────────────────────────

let map;
function initMap() {
  try {
    return initMapUnsafe();
  } catch (err) {
    console.warn("map unavailable:", err && err.message);
    map = null;
    return Promise.resolve(false);
  }
}

function initMapUnsafe() {
  map = dbg.map = new maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      sources: {
        carto: {
          type: "raster", tileSize: 256,
          tiles: ["https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png", "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png"],
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
        },
      },
      layers: [{ id: "carto", type: "raster", source: "carto" }],
    },
    center: [0, 30], zoom: 1.6, attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  map.addControl(new maplibregl.ScaleControl(), "bottom-left");
  // Resolve true when the style loaded, false if WebGL is missing or the map
  // errors out / stalls: the catalog, search and analysis panel still work.
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 12000);
    map.once("load", () => { clearTimeout(timer); resolve(true); });
    map.once("error", (e) => { console.warn("map error", e && e.error); clearTimeout(timer); resolve(false); });
  });
}

function addStationLayers(fc) {
  map.addSource("stations", { type: "geojson", data: fc, cluster: true, clusterMaxZoom: 9, clusterRadius: 38 });
  map.addLayer({
    id: "clusters", type: "circle", source: "stations", filter: ["has", "point_count"],
    paint: {
      "circle-color": "#1565c0", "circle-opacity": 0.75, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5,
      "circle-radius": ["step", ["get", "point_count"], 14, 50, 18, 250, 24, 1000, 30],
    },
  });
  map.addLayer({
    id: "cluster-count", type: "symbol", source: "stations", filter: ["has", "point_count"],
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 11, "text-font": ["Open Sans Semibold"] },
    paint: { "text-color": "#fff" },
  });
  map.addLayer({
    id: "points", type: "circle", source: "stations", filter: ["!", ["has", "point_count"]],
    paint: { "circle-color": ["get", "color"], "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 3, 10, 6, 14, 9], "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
  });
  map.addLayer({
    id: "selected", type: "circle", source: "stations", filter: ["==", ["get", "key"], "__none__"],
    paint: { "circle-color": "#ffd600", "circle-radius": 11, "circle-stroke-color": "#212121", "circle-stroke-width": 2 },
  });

  map.on("click", "clusters", async (e) => {
    const f = map.queryRenderedFeatures(e.point, { layers: ["clusters"] })[0];
    const zoom = await map.getSource("stations").getClusterExpansionZoom(f.properties.cluster_id);
    map.easeTo({ center: f.geometry.coordinates, zoom });
  });
  map.on("click", "points", (e) => {
    const f = e.features[0];
    selectStation(f.properties.key, { fly: false });
  });
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
  map.on("mouseenter", "points", (e) => {
    map.getCanvas().style.cursor = "pointer";
    const p = e.features[0].properties;
    popup.setLngLat(e.features[0].geometry.coordinates).setHTML(`<strong>${escapeHtml(p.name || p.key.split("/")[1])}</strong><br><span class="muted">${(SOURCE_STYLE[p.source] || {}).label || p.source}</span>`).addTo(map);
  });
  map.on("mouseleave", "points", () => { map.getCanvas().style.cursor = ""; popup.remove(); });
  map.on("click", (e) => {
    const hit = map.queryRenderedFeatures(e.point, { layers: ["points", "clusters"] });
    if (hit.length) return; // handled by the layer handlers
    selectPoint(e.lngLat.lat, e.lngLat.lng);
  });
  map.on("mouseenter", "clusters", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "clusters", () => (map.getCanvas().style.cursor = ""));
}

function refreshMapData() {
  if (state.mapOk) map.getSource("stations").setData(toFeatureCollection(state.stations));
  const visible = state.stations.filter((r) => !state.hidden.has(r.source)).length;
  $("count").textContent = `${visible.toLocaleString()} stations${state.mapOk ? "" : " (map unavailable here: WebGL is off; search still works)"}`;
}

// ── legend / search ─────────────────────────────────────────────────────────

function buildLegend() {
  const counts = {};
  for (const r of state.stations) counts[r.source] = (counts[r.source] || 0) + 1;
  const el = $("legend");
  el.innerHTML = "";
  for (const src of Object.keys(counts).sort((a, b) => counts[b] - counts[a])) {
    const st = SOURCE_STYLE[src] || { label: src, color: FALLBACK_COLOR };
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.innerHTML = `<i style="background:${st.color}"></i>${escapeHtml(st.label)} <em>${counts[src].toLocaleString()}</em>`;
    chip.title = `Toggle ${st.label}`;
    chip.addEventListener("click", () => {
      if (state.hidden.has(src)) state.hidden.delete(src); else state.hidden.add(src);
      chip.classList.toggle("off", state.hidden.has(src));
      refreshMapData();
    });
    el.appendChild(chip);
  }
}

function initSearch() {
  const input = $("search"), box = $("search-results");
  let t;
  input.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = input.value.trim().toLowerCase();
      if (q.length < 2) { box.hidden = true; return; }
      const hits = [];
      for (const r of state.stations) {
        if (state.hidden.has(r.source)) continue;
        if ((r.name && r.name.toLowerCase().includes(q)) || r.station_id.toLowerCase().includes(q)) {
          hits.push(r);
          if (hits.length >= 25) break;
        }
      }
      box.innerHTML = hits.length ? "" : `<div class="hit muted">no match</div>`;
      for (const r of hits) {
        const d = document.createElement("div");
        d.className = "hit";
        d.innerHTML = `<i style="background:${(SOURCE_STYLE[r.source] || {}).color || FALLBACK_COLOR}"></i>${escapeHtml(r.name || r.station_id)} <span class="muted">${escapeHtml(r.station_id)}</span>`;
        d.addEventListener("click", () => { box.hidden = true; input.value = ""; selectStation(`${r.source}/${r.station_id}`, { fly: true }); });
        box.appendChild(d);
      }
      box.hidden = false;
    }, 120);
  });
  document.addEventListener("click", (e) => { if (!box.contains(e.target) && e.target !== input) box.hidden = true; });
}

// ── selection + panel ───────────────────────────────────────────────────────

function selectStation(key, { fly } = { fly: false }) {
  const r = state.byKey.get(key);
  if (!r) return;
  state.selected = r;
  state.result = null;
  if (state.mapOk) {
    map.setFilter("selected", ["==", ["get", "key"], key]);
    if (fly) map.flyTo({ center: [r.lon, r.lat], zoom: Math.max(map.getZoom(), 9) });
  }
  history.replaceState(null, "", `#s=${encodeURIComponent(key)}`);

  $("panel-empty").hidden = true;
  $("panel-point").hidden = true;
  $("panel-station").hidden = false;
  if (state.marker) { state.marker.remove(); state.marker = null; }
  const st = SOURCE_STYLE[r.source] || { label: r.source, color: FALLBACK_COLOR };
  const badge = $("st-source");
  badge.textContent = st.label; badge.style.background = st.color;
  $("st-name").textContent = r.name || r.station_id;
  $("st-id").textContent = r.station_id;
  $("st-vars").textContent = (r.variables || []).map((v) => VAR_LABEL[v] || v).join(", ") || "—";
  $("st-period").textContent = r.period_start ? ` · ${r.period_start} → ${r.period_end || "present"}` : "";
  const agency = $("st-agency");
  if (r.url) { agency.href = r.url; agency.hidden = false; } else agency.hidden = true;
  $("btn-csv").disabled = true;
  $("btn-ci").disabled = false;
  for (const id of ["sec-summary", "sec-hydro", "sec-ffa", "sec-fdc", "sec-trend", "sec-notes", "sec-methods"]) $(id).hidden = true;
  $("panel").scrollTop = 0;
  requestAnalysis(r);
}

function setStatus(text, kind = "info") {
  const el = $("status");
  el.textContent = text;
  el.className = `status ${kind}`;
  el.hidden = !text;
}

// ── click anywhere ──────────────────────────────────────────────────────────

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371, d2r = Math.PI / 180;
  const dLat = (lat2 - lat1) * d2r, dLon = (lon2 - lon1) * d2r;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * d2r) * Math.cos(lat2 * d2r) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function nearestStations(lat, lon, n = 6) {
  const out = [];
  for (const r of state.stations) {
    if (state.hidden.has(r.source)) continue;
    const d = haversineKm(lat, lon, r.lat, r.lon);
    if (out.length < n) { out.push([d, r]); out.sort((a, b) => a[0] - b[0]); }
    else if (d < out[n - 1][0]) { out[n - 1] = [d, r]; out.sort((a, b) => a[0] - b[0]); }
  }
  return out;
}

async function selectPoint(lat, lon) {
  lat = Math.round(lat * 1e4) / 1e4; lon = Math.round(lon * 1e4) / 1e4;
  state.selected = null; state.result = null; state.point = { lat, lon };
  if (state.mapOk) {
    map.setFilter("selected", ["==", ["get", "key"], "__none__"]);
    if (state.marker) state.marker.remove();
    state.marker = new maplibregl.Marker({ color: "#455a64" }).setLngLat([lon, lat]).addTo(map);
  }
  history.replaceState(null, "", `#p=${lat},${lon}`);
  $("panel-empty").hidden = true; $("panel-station").hidden = true; $("panel-point").hidden = false;
  $("pt-title").textContent = `${lat.toFixed(3)}°, ${lon.toFixed(3)}°`;
  $("pt-coords").textContent = `lat ${lat}, lon ${lon}`;
  for (const id of ["pt-sec-climate", "pt-sec-glofas", "pt-sec-notes", "pt-sec-methods"]) $(id).hidden = true;
  const near = nearestStations(lat, lon);
  $("pt-nearest").innerHTML = near.map(([d, r]) => `<li data-key="${escapeHtml(`${r.source}/${r.station_id}`)}"><i style="background:${(SOURCE_STYLE[r.source] || {}).color || FALLBACK_COLOR}"></i>${escapeHtml(r.name || r.station_id)} <span class="muted">${escapeHtml((SOURCE_STYLE[r.source] || {}).label || r.source)}</span><span class="dist">${d < 10 ? d.toFixed(1) : Math.round(d)} km</span></li>`).join("") || `<li class="muted">no gauges in the catalog</li>`;
  for (const li of $("pt-nearest").querySelectorAll("li[data-key]")) li.addEventListener("click", () => selectStation(li.dataset.key, { fly: true }));
  $("panel").scrollTop = 0;
  const statusEl = $("pt-status");
  const setPt = (t, k = "info") => { statusEl.textContent = t; statusEl.className = `status ${k}`; statusEl.hidden = !t; };
  setPt(state.workerReady ? "Asking Open-Meteo about this point…" : "Loading Python in your browser (once, ~15 MB)…");
  try {
    const res = await call("anywhere", { lat, lon, years: 10 });
    if (!state.point || state.point.lat !== lat || state.point.lon !== lon) return;
    setPt("");
    renderPoint(res);
  } catch (err) {
    setPt(`Could not describe this point: ${err.message}`, "error");
  }
}

function renderPoint(res) {
  const c = res.climate;
  if (c) {
    $("pt-sec-climate").hidden = false;
    $("pt-kpis").innerHTML = [
      ["rainfall", `${fmt(c.precipitation_mm_per_year, 0)} mm/yr`, "ERA5, 10-yr mean"],
      ["reference ET0", `${fmt(c.et0_mm_per_year, 0)} mm/yr`, "FAO-56"],
      ["aridity", `${fmt(c.aridity_index, 2)}`, c.aridity_class || "P / ET0"],
      ["temperature", `${fmt(c.temperature_mean_c, 1)} °C`, `wettest day ${fmt(c.wettest_day_mm, 0)} mm`],
    ].map(([l, v, s]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");
    const months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
    Plotly.react("plot-climate", [
      { x: months, y: c.monthly_precipitation_mm, type: "bar", name: "rain (mm)", marker: { color: "#1565c0" } },
      { x: months, y: c.monthly_et0_mm, type: "scatter", mode: "lines+markers", name: "ET0 (mm)", line: { color: "#ef6c00" } },
    ], { ...PLOT_LAYOUT, height: 220, yaxis: { title: { text: "mm / month" } }, legend: { orientation: "h", y: 1.15 }, barmode: "group" }, PLOT_CONFIG);
  }
  const g = res.glofas;
  if (g && g.n) {
    $("pt-sec-glofas").hidden = false;
    $("pt-glofas-kpis").innerHTML = [
      ["mean", `${fmt(g.stats.mean)} m³/s`, `${g.start} → ${g.end}`],
      ["max", `${fmt(g.stats.max)} m³/s`, "modelled daily"],
    ].map(([l, v, s]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");
    if (g.ffa && g.ffa.fits) {
      const rps = g.ffa.return_periods, gv = g.ffa.fits.gev_lmoments || {}, lp = g.ffa.fits.lp3 || {};
      $("pt-ffa-table").innerHTML = `<thead><tr><th>T (yr)</th><th>GEV L-moments</th><th>LP3 (90 % CI)</th></tr></thead><tbody>` +
        rps.map((rp, i) => `<tr><td>${rp}</td><td>${gv.q ? fmt(gv.q[i]) : "—"}</td><td>${lp.q ? `${fmt(lp.q[i])} <span class="ci">[${fmt(lp.ci[i][0])}, ${fmt(lp.ci[i][1])}]</span>` : "—"}</td></tr>`).join("") +
        `</tbody><tfoot><tr><td colspan="3" class="muted">Indicative only: GloFAS grid-cell discharge in m³/s, ${g.ffa.n_years} modelled years.</td></tr></tfoot>`;
    } else {
      $("pt-ffa-table").innerHTML = "";
    }
  }
  const notes = res.notes || [];
  $("pt-notes").innerHTML = notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("");
  $("pt-sec-notes").hidden = notes.length === 0;
  const ms = res.methods || [];
  $("pt-methods").innerHTML = ms.map((m) => `<li><strong>${escapeHtml(m.name)}.</strong> ${escapeHtml(m.text)}<br><span class="cite">${escapeHtml(m.citation)}</span></li>`).join("");
  $("pt-attribution").textContent = res.attribution ? `Data: ${res.attribution}` : "";
  $("pt-sec-methods").hidden = ms.length === 0;
}

// ── worker (Pyodide) ────────────────────────────────────────────────────────

let worker;
function ensureWorker() {
  if (worker) return worker;
  worker = new Worker(`./worker.js?v=${CONFIG.build}`);
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === "progress") { if (state.selected && !state.result) setStatus(m.text, "info"); return; }
    if (m.type === "ready") { state.workerReady = true; return; }
    const pending = state.pending.get(m.id);
    if (!pending) return;
    state.pending.delete(m.id);
    if (m.type === "error") pending.reject(new Error(m.message)); else pending.resolve(m.result);
  };
  worker.onerror = (e) => { console.error(e); setStatus(`Worker error: ${e.message}`, "error"); };
  worker.postMessage({ type: "init", pyodideIndexURL: CONFIG.pyodideIndexURL, wheelsJson: new URL(CONFIG.wheelsJson, location.href).href, build: CONFIG.build });
  return worker;
}

function call(type, payload) {
  ensureWorker();
  const id = ++state.reqId;
  return new Promise((resolve, reject) => {
    state.pending.set(id, { resolve, reject });
    worker.postMessage({ type, id, ...payload });
  });
}

async function requestAnalysis(r) {
  const key = `${r.source}/${r.station_id}`;
  setStatus(state.workerReady ? "Fetching the record from the agency…" : "Loading Python in your browser (once, ~15 MB)…", "info");
  try {
    const result = await call("analyze", { source: r.source, station_id: r.station_id, years: CONFIG.years });
    if (!state.selected || `${state.selected.source}/${state.selected.station_id}` !== key) return; // user moved on
    state.result = result;
    render(result, r);
  } catch (err) {
    if (!state.selected || `${state.selected.source}/${state.selected.station_id}` !== key) return;
    setStatus(`Could not analyse this station: ${err.message}`, "error");
  }
}

// ── rendering ───────────────────────────────────────────────────────────────

const PLOT_LAYOUT = { margin: { l: 48, r: 12, t: 8, b: 36 }, height: 240, font: { family: "system-ui, sans-serif", size: 11 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)" };
const PLOT_CONFIG = { displayModeBar: false, responsive: true };

function fmt(x, digits = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const ax = Math.abs(x);
  if (ax >= 1000) return x.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (ax >= 10) return x.toLocaleString(undefined, { maximumFractionDigits: digits });
  return x.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function render(res, r) {
  const st = SOURCE_STYLE[r.source] || { color: FALLBACK_COLOR };
  if (res.error || !res.n) {
    setStatus(res.error || "No observations returned.", "warn");
    renderNotes(res); renderMethods(res);
    return;
  }
  setStatus("", "info");
  $("btn-csv").disabled = false;
  const unit = res.unit || "";
  const varLabel = VAR_LABEL[res.variable] || res.variable;

  // KPIs
  const k = res.stats || {};
  $("kpis").innerHTML = [
    ["record", `${res.start} → ${res.end}`, `${res.years} yr · ${res.n.toLocaleString()} obs`],
    ["mean", `${fmt(k.mean)} ${unit}`, varLabel],
    ["max", `${fmt(k.max)} ${unit}`, "observed"],
    ["min", `${fmt(k.min)} ${unit}`, "observed"],
  ].map(([l, v, s]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");
  $("sec-summary").hidden = false;

  // hydrograph
  $("sec-hydro").hidden = false;
  const traces = [{ x: res.series.t, y: res.series.v, mode: "lines", line: { width: 1, color: st.color }, name: varLabel, hovertemplate: "%{x}<br>%{y:.3~f} " + unit + "<extra></extra>" }];
  if (res.annual_max && res.annual_max.year.length > 1) {
    traces.push({ x: res.annual_max.year.map((y) => `${y}-07-01`), y: res.annual_max.v, mode: "markers", marker: { color: "#e53935", size: 6 }, name: "annual max", hovertemplate: "%{x|%Y} annual max<br>%{y:.3~f} " + unit + "<extra></extra>" });
  }
  Plotly.react("plot-hydro", traces, { ...PLOT_LAYOUT, yaxis: { title: { text: unit }, rangemode: "tozero" }, showlegend: false }, PLOT_CONFIG);

  // FFA
  if (res.ffa && res.ffa.fits) {
    $("sec-ffa").hidden = false;
    $("ffa-years").textContent = `(${res.ffa.n_years} annual maxima)`;
    renderFfaTable(res.ffa, unit);
    renderFfaPlot(res.ffa, unit, st.color);
  }

  // FDC
  if (res.fdc) {
    $("sec-fdc").hidden = false;
    Plotly.react("plot-fdc", [{ x: res.fdc.exceedance, y: res.fdc.q, mode: "lines", line: { color: st.color, width: 2 }, hovertemplate: "%{x:.1f} % exceedance<br>%{y:.3~f} " + unit + "<extra></extra>" }],
      { ...PLOT_LAYOUT, xaxis: { title: { text: "% of time exceeded" }, range: [0, 100] }, yaxis: { title: { text: unit }, type: "log" }, showlegend: false,
        annotations: [{ x: 95, y: Math.log10(res.fdc.q95 || 1), text: `Q95 ${fmt(res.fdc.q95)}`, showarrow: true, arrowhead: 2, ax: -40, ay: -30 }, { x: 10, y: Math.log10(res.fdc.q10 || 1), text: `Q10 ${fmt(res.fdc.q10)}`, showarrow: true, arrowhead: 2, ax: 40, ay: -30 }] }, PLOT_CONFIG);
  }

  // trend
  if (res.trend) {
    $("sec-trend").hidden = false;
    const t = res.trend;
    const dir = t.trend === "no trend" ? "no significant trend" : `a ${t.trend} trend`;
    $("trend-text").innerHTML = `Mann-Kendall on ${t.n_years} annual means: <strong>${dir}</strong> (p = ${fmt(t.p_value, 3)}, τ = ${fmt(t.tau, 2)}). Sen's slope ${fmt(t.sens_slope_per_year, 3)} ${unit}/yr.`;
  }

  renderNotes(res); renderMethods(res);
}

function renderNotes(res) {
  const notes = [...(res.notes || [])];
  if (res.fetch_note) notes.unshift(res.fetch_note);
  $("notes").innerHTML = notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("");
  $("sec-notes").hidden = notes.length === 0;
}

function renderMethods(res) {
  const ms = res.methods || [];
  $("methods").innerHTML = ms.map((m) => `<li><strong>${escapeHtml(m.name)}.</strong> ${escapeHtml(m.text)}<br><span class="cite">${escapeHtml(m.citation)}</span></li>`).join("");
  $("attribution").textContent = res.attribution ? `Data: ${res.attribution}. Licence: ${res.license}. Computed with aquascope in your browser.` : "";
  $("sec-methods").hidden = ms.length === 0 && !res.attribution;
}

function renderFfaTable(ffa, unit) {
  const rps = ffa.return_periods;
  const g = ffa.fits.gev_lmoments || {}, l = ffa.fits.lp3 || {}, b = ffa.fits.gev_bootstrap;
  const head = `<tr><th>T (yr)</th><th>GEV L-moments</th><th>LP3 (90 % CI)</th>${b ? "<th>GEV bootstrap (90 % CI)</th>" : ""}</tr>`;
  const rows = rps.map((rp, i) => {
    const gq = g.q ? fmt(g.q[i]) : (g.error ? "n/a" : "—");
    const lq = l.q ? `${fmt(l.q[i])} <span class="ci">${l.ci && l.ci[i] ? `[${fmt(l.ci[i][0])}, ${fmt(l.ci[i][1])}]` : ""}</span>` : (l.error ? "n/a" : "—");
    const bq = b ? `${fmt(b.q[i])} <span class="ci">${b.ci && b.ci[i] ? `[${fmt(b.ci[i][0])}, ${fmt(b.ci[i][1])}]` : ""}</span>` : "";
    return `<tr><td>${rp}</td><td>${gq}</td><td>${lq}</td>${b ? `<td>${bq}</td>` : ""}</tr>`;
  }).join("");
  $("ffa-table").innerHTML = `<thead>${head}</thead><tbody>${rows}</tbody><tfoot><tr><td colspan="${b ? 4 : 3}" class="muted">Return levels in ${unit}. T = return period.</td></tr></tfoot>`;
}

function renderFfaPlot(ffa, unit, color) {
  const rps = ffa.return_periods;
  const traces = [];
  if (ffa.fits.gev_lmoments && ffa.fits.gev_lmoments.q) traces.push({ x: rps, y: ffa.fits.gev_lmoments.q, mode: "lines+markers", name: "GEV (L-moments)", line: { color } });
  if (ffa.fits.lp3 && ffa.fits.lp3.q) {
    traces.push({ x: rps, y: ffa.fits.lp3.q, mode: "lines+markers", name: "LP3", line: { color: "#8e24aa" } });
    if (ffa.fits.lp3.ci) {
      traces.push({ x: [...rps, ...rps.slice().reverse()], y: [...ffa.fits.lp3.ci.map((c) => c[1]), ...ffa.fits.lp3.ci.map((c) => c[0]).reverse()], fill: "toself", fillcolor: "rgba(142,36,170,0.12)", line: { color: "transparent" }, name: "LP3 90 % CI", hoverinfo: "skip" });
    }
  }
  if (ffa.fits.gev_bootstrap) {
    const b = ffa.fits.gev_bootstrap;
    traces.push({ x: rps, y: b.q, mode: "lines+markers", name: "GEV (MLE)", line: { color: "#f57c00", dash: "dot" } });
    traces.push({ x: [...rps, ...rps.slice().reverse()], y: [...b.ci.map((c) => c[1]), ...b.ci.map((c) => c[0]).reverse()], fill: "toself", fillcolor: "rgba(245,124,0,0.12)", line: { color: "transparent" }, name: "GEV 90 % CI", hoverinfo: "skip" });
  }
  Plotly.react("plot-ffa", traces, { ...PLOT_LAYOUT, height: 260, xaxis: { title: { text: "return period (years)" }, type: "log" }, yaxis: { title: { text: unit } }, legend: { orientation: "h", y: 1.15 } }, PLOT_CONFIG);
}

// ── buttons ─────────────────────────────────────────────────────────────────

function initButtons() {
  $("btn-share-pt").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(location.href); $("btn-share-pt").textContent = "Copied!"; setTimeout(() => ($("btn-share-pt").textContent = "Copy link"), 1500); }
    catch { prompt("Copy this link", location.href); }
  });
  $("btn-share").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(location.href); $("btn-share").textContent = "Copied!"; setTimeout(() => ($("btn-share").textContent = "Copy link"), 1500); }
    catch { prompt("Copy this link", location.href); }
  });
  $("btn-csv").addEventListener("click", async () => {
    if (!state.result || !state.selected) return;
    const csv = await call("csv", {});
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${state.selected.source}_${state.selected.station_id}.csv`.replace(/[^\w.-]+/g, "_");
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  });
  $("btn-ci").addEventListener("click", async () => {
    if (!state.result || !state.result.ffa) return;
    const btn = $("btn-ci");
    btn.disabled = true; btn.textContent = "Bootstrapping 1,000 GEV fits…";
    try {
      const ci = await call("flood_ci", {});
      state.result.ffa.fits.gev_bootstrap = ci;
      if (!state.result.methods.some((m) => m.name === ci.method.name)) state.result.methods.push(ci.method);
      renderFfaTable(state.result.ffa, state.result.unit);
      renderFfaPlot(state.result.ffa, state.result.unit, (SOURCE_STYLE[state.selected.source] || {}).color || FALLBACK_COLOR);
      renderMethods(state.result);
      btn.textContent = "Bootstrap CI added";
    } catch (err) {
      btn.disabled = false; btn.textContent = "Add bootstrap 90 % CI (GEV, slow)";
      setStatus(`Bootstrap failed: ${err.message}`, "error");
    }
  });
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

// ── boot ────────────────────────────────────────────────────────────────────

(async function boot() {
  trace("boot");
  initButtons();
  initSearch();
  const mapReady = initMap();
  trace("map init called");
  const catalogReady = loadCatalog().then(() => true).catch((err) => {
    console.error(err);
    $("count").textContent = "catalog unavailable";
    setStatus(`Could not load the station catalog: ${err.message}`, "error");
    return false;
  });
  const [mapOk, catalogOk] = await Promise.all([mapReady, catalogReady]);
  trace(`ready: map=${mapOk} catalog=${catalogOk} stations=${state.stations.length}`);
  state.mapOk = Boolean(mapOk && map);
  if (!catalogOk) return;
  if (mapOk) {
    addStationLayers(toFeatureCollection(state.stations));
    map.fitBounds([[-128, 12], [128, 62]], { padding: 12, animate: false }); // US west coast to Taiwan
  }
  buildLegend();
  refreshMapData();
  ensureWorker(); // warm Python in the background so the first click is quicker
  const m = location.hash.match(/#s=(.+)$/);
  if (m) selectStation(decodeURIComponent(m[1]), { fly: true });
  const pm = location.hash.match(/#p=(-?[\d.]+),(-?[\d.]+)$/);
  if (pm) {
    const lat = Number(pm[1]), lon = Number(pm[2]);
    if (state.mapOk) map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), 7) });
    selectPoint(lat, lon);
  }
})();
