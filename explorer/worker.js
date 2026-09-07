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
  // The wheel keeps its filename between deploys, so a browser that has been
  // here before will happily serve yesterday's Python against today's page
  // (seen in the wild: a cached wheel without a module the page had just
  // started calling). Fetch it ourselves with cache: "reload", hand the bytes
  // to Pyodide's filesystem, and install from there.
  let wheelSpec = wheelUrl;
  try {
    const resp = await fetch(wheelUrl, { cache: "reload" });
    if (!resp.ok) throw new Error(`wheel ${resp.status}`);
    pyodide.FS.writeFile(`/tmp/${wheels.wheel}`, new Uint8Array(await resp.arrayBuffer()));
    wheelSpec = `emfs:/tmp/${wheels.wheel}`;
  } catch (err) {
    console.warn("could not pre-fetch the wheel, falling back to the URL:", err);
  }
  await micropip.install(["pyodide-http", wheelSpec]);

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

// The full record is requested unless the page passes a cap in years (#270).
// The catalog's first date for the station travels with the request so Python
// can ask from it, and say in the note when the agency served less than that.
async function analyze({ id, source, station_id, years, period_start }) {
  post("progress", { text: "Fetching the record from the agency…" });
  const cap = Number(years) > 0 ? `years=${Math.round(Number(years))}, ` : "";
  const since = period_start ? `period_start=${JSON.stringify(String(period_start).slice(0, 10))}, ` : "";
  const code = `
import json
_STORE.clear()
_res = analysis.analyze_station(${JSON.stringify(source)}, ${JSON.stringify(station_id)}, ${cap}${since}store=_STORE)
_STORE["result"] = _res
json.dumps(_res)
`;
  const out = await pyodide.runPythonAsync(code);
  post("result", { id, result: JSON.parse(out) });
}

async function anywhere({ id, lat, lon, years }) {
  post("progress", { text: "Asking Open-Meteo about this point (ERA5 climate, GloFAS discharge)…" });
  const code = `
import json
_STORE.clear()
_res = analysis.anywhere(${Number(lat)}, ${Number(lon)}, years=${Number(years) || 10})
_STORE["result"] = _res
json.dumps(_res)
`;
  const out = await pyodide.runPythonAsync(code);
  post("result", { id, result: JSON.parse(out) });
}

async function floodCi({ id }) {
  const code = `
import json
json.dumps(analysis.flood_ci(_STORE["series"]))
`;
  const out = await pyodide.runPythonAsync(code);
  post("result", { id, result: JSON.parse(out) });
}

async function csv({ id }) {
  const out = await pyodide.runPythonAsync(`
analysis.to_csv(_STORE["result"])
`);
  post("result", { id, result: out });
}

// "What can be answered here": aquascope.explore.assess_site over the catalog
// the page handed over (send it first with "catalog"). The page passes the
// catchment area and donor count it already holds, since BasinATLAS and the
// similarity table are read by DuckDB-WASM on the main thread, not here.
async function assess({ id, lat, lon, radius_km, problem, area_km2, donors }) {
  post("progress", { text: "Checking what the record here supports…" });
  self.__aqAssess = JSON.stringify({
    lat: Number(lat), lon: Number(lon), radius_km: Number(radius_km) || 50, problem: problem || null,
    area_km2: Number.isFinite(Number(area_km2)) && area_km2 !== null ? Number(area_km2) : null,
    donors: Number.isFinite(Number(donors)) && donors !== null ? Number(donors) : null,
  });
  const code = `
import json
from js import __aqAssess
_a = json.loads(__aqAssess)
json.dumps(analysis.assess_site(
    _a["lat"], _a["lon"], radius_km=_a["radius_km"], problem=_a.get("problem"),
    area_km2=_a.get("area_km2"), donors=_a.get("donors"),
))
`;
  try {
    const out = await pyodide.runPythonAsync(code);
    post("result", { id, result: JSON.parse(out) });
  } finally {
    self.__aqAssess = null;
  }
}

// The main thread already holds the station catalog (DuckDB-WASM); hand it to
// Python once so find_stations() answers from memory instead of the Hub
// (httpx / pyarrow do not run here).
let catalogLoaded = false;
async function catalog({ id, rows }) {
  self.__aqCatalog = JSON.stringify(rows);
  await pyodide.runPythonAsync(`
import json
from js import __aqCatalog
from aquascope.archive import catalog as _catalog
_catalog.set_catalog(json.loads(__aqCatalog))
`);
  self.__aqCatalog = null;
  catalogLoaded = true;
  post("result", { id, result: { n: rows.length } });
}

// The Analyst (aquascope.ai_engine.analyst.ask) runs unchanged in the browser:
// the OpenAI-compatible call goes through urllib (sync XHR via pyodide-http),
// straight from this worker to the provider the user picked. The key never
// touches any server of ours (there is none).
async function ask({ id, question, provider, model, api_key, base_url, max_steps }) {
  self.__aqAskEvent = (text) => post("ask_progress", { id, text: String(text) });
  self.__aqAsk = JSON.stringify({ question, provider, model, api_key, base_url, max_steps: Number(max_steps) || 8 });
  const code = `
import json
from js import __aqAsk, __aqAskEvent
from aquascope.ai_engine import analyst as _analyst
_args = json.loads(__aqAsk)
_res = _analyst.ask(
    _args["question"],
    provider=_args.get("provider") or None,
    model=_args.get("model") or None,
    api_key=_args.get("api_key") or None,
    base_url=_args.get("base_url") or None,
    max_steps=int(_args.get("max_steps") or 8),
    on_event=lambda m: __aqAskEvent(m),
    # The record on screen, so run_python can work on it (#234).
    data={"df": _STORE["frame"]} if _STORE.get("frame") is not None else None,
)
json.dumps({
    "answer": _res.answer,
    "markdown": _res.to_markdown(),
    "model": _res.model,
    "provider": _res.provider,
    "steps": _res.steps,
    "tool_calls": [{"name": c.name, "arguments": c.arguments, "ok": c.ok} for c in _res.tool_calls],
    "data_used": _res.data_used,
    "methods": _res.methods,
    "checks": _res.checks,
    "verified": _res.verified,
    "study": _res.study,
})
`;
  try {
    const out = await pyodide.runPythonAsync(code);
    post("result", { id, result: JSON.parse(out) });
  } finally {
    self.__aqAsk = null;
    self.__aqAskEvent = null;
  }
}

// ── Solve: a problem at a place, planned first ──────────────────────────────
// The two halves of aquascope.ai_engine.team, the same code the CLI and the MCP
// server run. The page has already run the reconnaissance (with the catchment
// area and donor count only it can read), so it travels in as `recon` and the
// Scout is not asked again. A model is used only when the page passes one.
// The Explorer's drawer moved from Solve to Study (below); these messages stay
// for the other faces that mirror them, and cost nothing while unused.

function solveArgs() {
  return `provider=_a.get("provider") or None, model=_a.get("model") or None,
    api_key=_a.get("api_key") or None, base_url=_a.get("base_url") or None`;
}

// The plan half: the playbook the chips or the keyword rules pick, the branch
// the tree selects for the data that exists, the study it fills. Nothing runs.
async function solvePlan({ id, problem, lat, lon, playbook, intake, recon, provider, model, api_key, base_url }) {
  self.__aqSolve = JSON.stringify({
    problem: problem || "", lat: Number(lat), lon: Number(lon), playbook: playbook || null,
    intake: intake || null, recon: recon || null, provider, model, api_key, base_url,
  });
  const code = `
import json
from js import __aqSolve
from aquascope.ai_engine import team as _team
_a = json.loads(__aqSolve)
_res = _team.solve(
    _a["problem"], lat=_a["lat"], lon=_a["lon"], playbook=_a.get("playbook"), intake=_a.get("intake"),
    recon=_a.get("recon"), ${solveArgs()},
    execute=False,
)
json.dumps(_res.to_dict(), default=str)
`;
  try {
    const out = await pyodide.runPythonAsync(code);
    post("result", { id, result: JSON.parse(out) });
  } finally {
    self.__aqSolve = null;
  }
}

// The intake a small model wrote on the reader's device, made safe by the
// package's own rules (aquascope.playbooks.coerce_intake): a field the playbook
// has not got is dropped, a value the field cannot take becomes its default.
// An unknown playbook comes back as null, and the page falls back to the
// keyword rules solve_plan applies anyway.
async function coerceIntake({ id, playbook, intake }) {
  self.__aqIntake = JSON.stringify({ playbook: playbook || null, intake: intake || null });
  const code = `
import json
from js import __aqIntake
from aquascope import playbooks as _pbk
_a = json.loads(__aqIntake)
try:
    _pb = _pbk.load(_a["playbook"] or "")
    _out = {"playbook": _pb.id, "intake": _pbk.coerce_intake(_pb, _a.get("intake"))}
except _pbk.PlaybookError as exc:
    _out = {"playbook": None, "intake": None, "error": str(exc)}
json.dumps(_out, default=str)
`;
  try {
    const out = await pyodide.runPythonAsync(code);
    post("result", { id, result: JSON.parse(out) });
  } finally {
    self.__aqIntake = null;
  }
}

// The run half: the reviewed study (edited or not) with its gates, one bounded
// replan, the Reviewer's "not established" list and the Narrator. Every
// timeline event is posted as it happens, the way ask() streams its tool log.
// BasinATLAS cannot be read here (no pyogrio in Pyodide), so the sub-basin and
// attribute row the page found with DuckDB and FlatGeobuf travel in as
// `catchment`, and the package builds describe_catchment's payload from them.
async function solveRun({ id, study, recon, catchment, provider, model, api_key, base_url }) {
  self.__aqSolveEvent = (text) => post("solve_progress", { id, event: JSON.parse(text) });
  self.__aqSolve = JSON.stringify({ study, recon: recon || null, catchment: catchment || null, provider, model, api_key, base_url });
  const code = `
import json
from js import __aqSolve, __aqSolveEvent
from aquascope.ai_engine import team as _team
_a = json.loads(__aqSolve)
_tools = {}
_c = _a.get("catchment")
if _c and (_c.get("sub_basin") or {}).get("hybas_id") is not None:
    from aquascope.archive import basins as _basins
    _tools["describe_catchment"] = lambda lat=None, lon=None, **_kw: _basins.describe_catchment_from_row(
        lat, lon, _c["sub_basin"], _c.get("row"), n_upstream=_c.get("n_upstream"))
_res = _team.run_reviewed(
    _a["study"], recon=_a.get("recon"), ${solveArgs()},
    on_event=lambda e: __aqSolveEvent(json.dumps(e, default=str)),
    tools=_tools or None,
)
json.dumps(_res.to_dict(), default=str)
`;
  try {
    const out = await pyodide.runPythonAsync(code);
    post("result", { id, result: JSON.parse(out) });
  } finally {
    self.__aqSolve = null;
    self.__aqSolveEvent = null;
  }
}



// ── Studio: a complete study at a place, by a crew of roles ─────────────────
// aquascope.studio.Studio, the same Coordinator the CLI and the MCP tools run.
// The page holds the workspace dict between calls; the worker keeps its own
// copy WITH the artifact bytes (_STUDIO, by workspace id) so a figure or a
// document never crosses to the page except on request: `file` returns one
// artifact by id, `export` the bundle zip. Events and PNG figures are posted
// as they happen. matplotlib is loaded before the first run, openpyxl and
// python-docx before the first bundle, never on a visit that runs no study.
//
// The Python between the markers is plain functions over dicts, so the test
// suite can run it in CPython against the studio fixtures.

const STUDIO_PY = `
# --- studio face (explorer) ---
import base64 as _b64
import io as _io
import json as _json

from aquascope.studio import Studio as _Studio

_STUDIO = {}      # workspace id -> Studio, with the artifact bytes


def _studio_tools(catchment):
    """describe_catchment from the sub-basin row the page found (BasinATLAS is read by DuckDB-WASM on the
    main thread; pyogrio does not run here)."""
    tools = {}
    c = catchment or {}
    if (c.get("sub_basin") or {}).get("hybas_id") is not None:
        from aquascope.archive import basins as _basins

        tools["describe_catchment"] = lambda lat=None, lon=None, **_kw: _basins.describe_catchment_from_row(
            lat, lon, c["sub_basin"], c.get("row"), n_upstream=c.get("n_upstream"))
    return tools


def _with_recon_context(a, fn):
    """Run fn with the Scout's assess_site carrying the catchment area and donor count only the page can
    read (BasinATLAS and the donor table are DuckDB-WASM reads on the main thread); restored afterwards."""
    import aquascope.explore as _ex

    base = _ex.assess_site
    ctx = {"area_km2": a.get("area_km2"), "donors": a.get("donors")}

    def assess_site(lat, lon, **kw):
        for key, value in ctx.items():
            if kw.get(key) is None and value is not None:
                kw[key] = value
        return base(lat, lon, **kw)

    _ex.assess_site = assess_site
    try:
        return fn()
    finally:
        _ex.assess_site = base


def _studio_model(a):
    return {"provider": a.get("provider") or None, "model": a.get("model") or None,
            "api_key": a.get("api_key") or None, "base_url": a.get("base_url") or None}


def _studio_open(a, on_event, on_artifact):
    """The Studio for this call: from the worker's own copy (with the bytes) when it has one, else from the
    page's workspace dict. Rebuilt every call so the model and the callbacks are this call's."""
    ws = a.get("workspace") or {}
    kept = _STUDIO.get(ws.get("id"))
    d = kept.to_dict() if kept is not None else ws
    s = _Studio.from_dict(d, tools=_studio_tools(a.get("catchment")), on_event=on_event, on_artifact=on_artifact,
                          **_studio_model(a))
    _STUDIO[s.ws.id] = s
    return s


def _studio_reply(s, r):
    return {"reply": r.to_dict(), "workspace": s.to_dict(with_artifacts=False), "status": s.ws.status}


def _studio_file(art):
    return {"id": art.id, "name": art.name, "media_type": art.media_type, "size": art.size,
            "data": _b64.b64encode(art.data).decode("ascii")}


def studio_call(a, on_event=None, on_artifact=None, store=None):
    """One message from the page. op is start, say, approve, follow_up, file or export."""
    return _with_recon_context(a, lambda: _studio_dispatch(a, on_event, on_artifact, store))


def _studio_dispatch(a, on_event, on_artifact, store):
    op = a.get("op")
    if op == "start":
        tables = dict(a.get("tables") or {})
        frame = (store or {}).get("frame") if store is not None else None
        if a.get("use_frame") and frame is not None:
            tables[str(a.get("frame_label") or "my-data")] = frame.to_csv(index=False)
        s = _Studio(float(a["lat"]), float(a["lon"]), data=tables or None, intake=a.get("intake") or None,
                    tools=_studio_tools(a.get("catchment")), on_event=on_event, on_artifact=on_artifact,
                    **_studio_model(a))
        brief = a.get("brief") or {}
        if isinstance(brief.get("decision"), str) and brief["decision"].strip():
            s.ws.brief.decision = brief["decision"].strip()
        if isinstance(brief.get("quantities"), list):
            s.ws.brief.quantities = [str(q) for q in brief["quantities"] if str(q).strip()]
        _STUDIO[s.ws.id] = s
        r = s.say(str(a.get("text") or ""))
        if brief and s.ws.brief.source == "rules":
            s.ws.brief.source = "device"
        return _studio_reply(s, r)
    s = _studio_open(a, on_event, on_artifact)
    if op == "say":
        return _studio_reply(s, s.say(str(a.get("text") or "")))
    if op == "approve":
        return _studio_reply(s, s.approve(a.get("edits") or None))
    if op == "follow_up":
        return _studio_reply(s, s.follow_up(str(a.get("text") or "")))
    if op == "file":
        art = s.ws.artifact(str(a.get("artifact_id") or ""))
        if art is None:
            return {"error": f"no artifact {a.get('artifact_id')!r} in this study"}
        return _studio_file(art)
    if op == "export":
        from aquascope.studio.deliverables.bundle import bundle_bytes

        data = bundle_bytes(s.ws)
        return {"id": "bundle", "name": "bundle.zip", "media_type": "application/zip", "size": len(data),
                "data": _b64.b64encode(data).decode("ascii")}
    return {"error": f"unknown op {op!r}"}


def studio_table(name, data_b64):
    """An Excel upload as CSV text, so it travels in the workspace like any other table."""
    import pandas as pd

    df = pd.read_excel(_io.BytesIO(_b64.b64decode(data_b64)))
    return {"name": name, "csv": df.to_csv(index=False), "n": int(len(df)), "columns": [str(c) for c in df.columns]}
# --- end studio face ---
`;

let studioDefined = false;
let plottingLoaded = false;
let docsLoaded = false;

async function ensureStudioPython() {
  if (studioDefined) return;
  await pyodide.runPythonAsync(STUDIO_PY);
  studioDefined = true;
}

const studioNote = (id, detail) => post("studio_progress", { id, event: { role: "coordinator", step: null, event: "loading", detail } });

// The figures need matplotlib (in the Pyodide distribution), the workbook and
// the Word report need openpyxl and python-docx (from PyPI through micropip).
// Loaded once, before the first run; a failed document install is a note, and
// the bundle says the Word file was skipped.
async function ensurePlotting(id) {
  if (plottingLoaded) return;
  studioNote(id, "Loading the plotting library (once)");
  await pyodide.loadPackage("matplotlib");
  plottingLoaded = true;
}

async function ensureDocs(id) {
  if (docsLoaded) return;
  studioNote(id, "Loading the document libraries (once)");
  try {
    await pyodide.pyimport("micropip").install(["openpyxl", "python-docx"]);
  } catch (err) {
    console.warn("the document libraries did not install; the Word file will be skipped:", err);
    studioNote(id, "The document libraries did not load; the bundle will carry no Word file");
  }
  docsLoaded = true;
}

// One studio call at a time. The arguments travel through a global the Python
// reads at its start, and runPythonAsync yields before it runs (it scans the
// code for imports), so two calls in flight read each other's: seen when a
// follow-up was stopped on the page (abandoned here, still running) and the
// next message arrived behind it with JsNull for its arguments.
let studioChain = Promise.resolve();
function studioSerial(m) {
  const run = studioChain.then(() => studio(m));
  studioChain = run.catch(() => {});
  return run;
}

async function studio(m) {
  const { id, type: _type, ...args } = m;
  await ensureStudioPython();
  if (args.op === "table") {
    await ensureDocs(id);
    self.__aqStudio = JSON.stringify({ name: args.name || "table.xlsx", data: args.data || "" });
    const code = `
import json
from js import __aqStudio
_a = json.loads(__aqStudio)
json.dumps(studio_table(_a["name"], _a["data"]), default=str)
`;
    try {
      const out = await pyodide.runPythonAsync(code);
      post("result", { id, result: JSON.parse(out) });
    } finally {
      self.__aqStudio = null;
    }
    return;
  }
  if (args.op === "approve" || args.op === "follow_up") {
    await ensurePlotting(id);
    await ensureDocs(id);
  }
  self.__aqStudio = JSON.stringify(args);
  self.__aqStudioEvent = (text) => post("studio_progress", { id, event: JSON.parse(text) });
  self.__aqStudioArtifact = (text) => post("studio_artifact", { id, artifact: JSON.parse(text) });
  const code = `
import json
from js import __aqStudio, __aqStudioEvent, __aqStudioArtifact
_a = json.loads(__aqStudio)
_out = studio_call(
    _a,
    on_event=lambda e: __aqStudioEvent(json.dumps(e, default=str)),
    # PNG figures travel with their bytes so the page can show them as they land; SVG and CSV without.
    on_artifact=lambda art: __aqStudioArtifact(
        json.dumps(art.to_dict(with_data=art.media_type == "image/png"), default=str)),
    store=_STORE,
)
json.dumps(_out, default=str)
`;
  try {
    const out = await pyodide.runPythonAsync(code);
    post("result", { id, result: JSON.parse(out) });
  } finally {
    self.__aqStudio = null;
    self.__aqStudioEvent = null;
    self.__aqStudioArtifact = null;
  }
}

// ── the workbench: analyses of the user's own table ─────────────────────────
// aquascope.workbench holds what the dashboard pages used to hold, as plain
// functions returning JSON, so the browser runs exactly what the CLI runs.

async function ingestText({ id, text, filename, options }) {
  post("progress", { text: "Reading the file and working out its columns…" });
  self.__aqIngest = JSON.stringify({ text, filename: filename || "upload.csv", options: options || {} });
  const code = `
import json
from js import __aqIngest
from aquascope import ingest as _ingest
_args = json.loads(__aqIngest)
_res = _ingest.ingest_text(_args["text"], _args["filename"], **(_args.get("options") or {}))
_STORE["frame"] = _res["series"].rename("value").to_frame().reset_index().rename(columns={"index": "date"})
_STORE["result"] = _res["analysis"]
json.dumps({
    "mapping": _res["mapping"],
    "qa": _res["qa"],
    "analysis": _res["analysis"],
    "n": int(len(_res["series"])),
})
`;
  const out = await pyodide.runPythonAsync(code);
  self.__aqIngest = null;
  post("result", { id, result: JSON.parse(out) });
}

// A table the page already holds (CSV text), kept for the workbench analyses.
async function loadTable({ id, csv, label }) {
  self.__aqCsv = csv;
  const code = `
import json, io
import pandas as pd
from js import __aqCsv
_STORE["frame"] = pd.read_csv(io.StringIO(__aqCsv))
from aquascope import workbench as _wb
json.dumps({"n": int(len(_STORE["frame"])), "columns": [str(c) for c in _STORE["frame"].columns],
            "insights": _wb.insights(_STORE["frame"])})
`;
  const out = await pyodide.runPythonAsync(code);
  self.__aqCsv = null;
  post("result", { id, result: { ...JSON.parse(out), label: label || "table" } });
}

async function workbench({ id, analysis, params }) {
  post("progress", { text: `Running ${analysis}…` });
  self.__aqWb = JSON.stringify({ analysis, params: params || {} });
  const code = `
import json
from js import __aqWb
from aquascope import workbench as _wb
_a = json.loads(__aqWb)
_frame = _STORE.get("frame")
_res = _wb.run(_a["analysis"], _frame, **(_a.get("params") or {}))
_res.pop("frame", None)
json.dumps(_res)
`;
  const out = await pyodide.runPythonAsync(code);
  self.__aqWb = null;
  post("result", { id, result: JSON.parse(out) });
}

// The gauge record currently on screen, handed to the workbench.
async function frameFromStation({ id }) {
  const code = `
import json
import pandas as pd
_res = _STORE.get("result") or {}
_series = _res.get("series") or {}
_STORE["frame"] = pd.DataFrame({"date": pd.to_datetime(_series.get("t", [])), "discharge": _series.get("v", [])})
from aquascope import workbench as _wb
json.dumps({"n": int(len(_STORE["frame"])), "columns": ["date", "discharge"],
            "insights": _wb.insights(_STORE["frame"])})
`;
  const out = await pyodide.runPythonAsync(code);
  post("result", { id, result: JSON.parse(out) });
}


// Run one analyst tool by name, for the showcase's "run the tools again": the
// deterministic half of a recorded answer, live, with no model and no key.
async function runTool({ id, name, arguments: args }) {
  self.__aqTool = JSON.stringify({ name, args: args || {} });
  const code = `
import json
from js import __aqTool
from aquascope.ai_engine import analyst as _analyst
_a = json.loads(__aqTool)
_specs = {s.name: s for s in _analyst._tool_specs()}
_spec = _specs.get(_a["name"])
if _spec is None:
    _out = {"error": f"unknown tool {_a['name']}"}
else:
    try:
        _out = _spec.func(**(_a.get("args") or {}))
    except Exception as exc:
        _out = {"error": f"{type(exc).__name__}: {exc}"}
json.dumps(_out, default=str)
`;
  const out = await pyodide.runPythonAsync(code);
  self.__aqTool = null;
  post("result", { id, result: JSON.parse(out) });
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "init") { ready = init(m); await ready; return; }
    await ready;
    if (m.type === "analyze") return await analyze(m);
    if (m.type === "anywhere") return await anywhere(m);
    if (m.type === "assess") return await assess(m);
    if (m.type === "flood_ci") return await floodCi(m);
    if (m.type === "csv") return await csv(m);
    if (m.type === "catalog") return await catalog(m);
    if (m.type === "ask") return await ask(m);
    if (m.type === "solve_plan") return await solvePlan(m);
    if (m.type === "coerce_intake") return await coerceIntake(m);
    if (m.type === "solve_run") return await solveRun(m);
    if (m.type === "studio") return await studioSerial(m);
    if (m.type === "ingest") return await ingestText(m);
    if (m.type === "load_table") return await loadTable(m);
    if (m.type === "workbench") return await workbench(m);
    if (m.type === "tool") return await runTool(m);
    if (m.type === "frame_from_station") return await frameFromStation(m);
  } catch (err) {
    // Pyodide raises PythonError with the full traceback in .message; keep the
    // exception line (last non-empty) and log the whole thing for debugging.
    const full = String(err && err.message ? err.message : err);
    console.error(full);
    const lines = full.split("\n").filter((l) => l.trim());
    post("error", { id: m.id, message: lines[lines.length - 1] || "unknown error" });
  }
};
