// AquaScope Explorer, worker thread: Pyodide + aquascope. Fetches the observed
// record through aquascope's own collectors and runs aquascope.explore (the
// same code the CLI and MCP server use). Sync XHR (pyodide-http) is allowed in
// workers, so the page stays responsive while Python is busy.

let pyodide = null;
let ready = null;

function post(type, extra = {}) { self.postMessage({ type, ...extra }); }

async function init({ pyodideIndexURL, wheelsJson }) {
  post("progress", { text: "Loading Python runtime (Pyodide)…" });
  importScripts(`${pyodideIndexURL}pyodide.js`);
  pyodide = await loadPyodide({ indexURL: pyodideIndexURL });

  post("progress", { text: "Loading numpy, scipy, pandas…" });
  await pyodide.loadPackage(["micropip", "numpy", "scipy", "pandas", "pydantic", "httpx"]);

  post("progress", { text: "Installing aquascope…" });
  const wheels = await (await fetch(wheelsJson, { cache: "no-store" })).json();
  const wheelUrl = new URL(wheels.wheel, wheelsJson).href;
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(["pyodide-http", wheelUrl]);

  await pyodide.runPythonAsync(`
import json, logging
logging.basicConfig(level=logging.WARNING)
import pyodide_http
pyodide_http.patch_all()
import aquascope.explore as analysis
_STORE = {}
`);
  post("ready");
}

async function analyze({ id, source, station_id, years }) {
  post("progress", { text: "Fetching the record from the agency…" });
  const code = `
import json, analysis
_STORE.clear()
_res = analysis.analyze_station(${JSON.stringify(source)}, ${JSON.stringify(station_id)}, years=${Number(years) || 40}, store=_STORE)
_STORE["result"] = _res
json.dumps(_res)
`;
  const out = await pyodide.runPythonAsync(code);
  post("result", { id, result: JSON.parse(out) });
}

async function floodCi({ id }) {
  const code = `
import json, analysis
json.dumps(analysis.flood_ci(_STORE["series"]))
`;
  const out = await pyodide.runPythonAsync(code);
  post("result", { id, result: JSON.parse(out) });
}

async function csv({ id }) {
  const out = await pyodide.runPythonAsync(`
import analysis
analysis.to_csv(_STORE["result"])
`);
  post("result", { id, result: out });
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "init") { ready = init(m); await ready; return; }
    await ready;
    if (m.type === "analyze") return await analyze(m);
    if (m.type === "flood_ci") return await floodCi(m);
    if (m.type === "csv") return await csv(m);
  } catch (err) {
    const msg = String(err && err.message ? err.message : err).split("\n").filter(Boolean).slice(-3).join(" ");
    post("error", { id: m.id, message: msg });
  }
};
