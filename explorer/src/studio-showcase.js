// Recorded studies: what the crew does with a model, replayed with no key.
//
// The maintainer records a dozen studies with a model (aquascope.studio.showcase)
// and commits the bundles under showcase/studies/. This module reads them: the
// index the intake offers as chips, one recording (the workspace without its
// bytes, the report, the figures, the meta), the plan a page hands back to the
// worker to re-run the numbers live, and the label that says the prose is a
// recording. Pure: no DOM, no imports, node-importable; the fetch is injectable
// for the tests.

const FILES = ["meta.json", "workspace.json", "report.md"];

function base(baseUrl) {
  return String(baseUrl || "").replace(/\/+$/, "");
}

function joinUrl(baseUrl, ...parts) {
  const head = base(baseUrl);
  const tail = parts.map((p) => String(p).replace(/^\/+|\/+$/g, "")).filter(Boolean).join("/");
  return head ? `${head}/${tail}` : tail;
}

async function getJson(fetchFn, url) {
  const res = await fetchFn(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

async function getText(fetchFn, url) {
  const res = await fetchFn(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.text();
}

// The index at `${baseUrl}/index.json`. A missing index (nothing published yet)
// is an empty list, not an error; a broken one throws.
export async function recordedIndex(baseUrl, { fetch: fetchFn = globalThis.fetch, version = "" } = {}) {
  const url = joinUrl(baseUrl, "index.json") + (version ? `?v=${encodeURIComponent(version)}` : "");
  const res = await fetchFn(url);
  if (res.status === 404) return { generated: null, aquascope_version: null, note: "", studies: [] };
  if (!res.ok) throw new Error(`recorded studies index: ${res.status}`);
  const data = await res.json();
  const studies = Array.isArray(data && data.studies) ? data.studies : [];
  return { ...data, studies };
}

// One recording: { id, meta, workspace, report, figures: [{name, url, caption, step, id}], files: {name: url} }.
export async function loadRecorded(baseUrl, id, { fetch: fetchFn = globalThis.fetch, version = "" } = {}) {
  if (!id || /[^A-Za-z0-9_-]/.test(String(id))) throw new Error(`not a recording id: ${id}`);
  const q = version ? `?v=${encodeURIComponent(version)}` : "";
  const url = (name) => joinUrl(baseUrl, id, name) + q;
  const [meta, workspace] = await Promise.all([getJson(fetchFn, url("meta.json")), getJson(fetchFn, url("workspace.json"))]);
  const hasReport = !Array.isArray(meta.files) || meta.files.includes("report.md");
  const report = hasReport ? await getText(fetchFn, url("report.md")).catch(() => "") : "";
  const captions = new Map();
  for (const a of (workspace && workspace.artifacts) || []) {
    if (a && a.name) captions.set(String(a.name).split("/").pop(), a);
  }
  const figures = (Array.isArray(meta.figures) ? meta.figures : [])
    .map((f) => (typeof f === "string" ? { name: f } : f))
    .filter((f) => f && f.name)
    .map((f) => {
      const art = captions.get(f.name) || {};
      return {
        name: f.name,
        url: joinUrl(baseUrl, id, "figures", f.name) + q,
        caption: f.caption || art.caption || "",
        step: f.step || art.step || null,
        id: f.id || art.id || null,
      };
    });
  const files = {};
  for (const name of Array.isArray(meta.files) ? meta.files : FILES) {
    if (!name.startsWith("figures/")) files[name] = url(name);
  }
  return { id, meta, workspace, report, figures, files };
}

// The plan of a recorded workspace as the dict a page sends to approve(plan=...):
// the version-3 study without the run's results, so the worker runs every step
// again at the same place with the same arguments and gates, keyless. Null when
// the recording holds no plan (a decline at intake).
export function replayPlan(workspace) {
  const study = workspace && workspace.study;
  if (!study || !Array.isArray(study.steps) || !study.steps.length) return null;
  const plan = JSON.parse(JSON.stringify(study));
  delete plan.results;
  if (plan.plan && typeof plan.plan === "object") {
    delete plan.plan.replans;
    delete plan.plan.replanned_from;
  }
  plan.steps = plan.steps.map((s) => {
    const step = { ...s };
    delete step.result;
    delete step.sha256;
    return step;
  });
  return plan;
}

// What a page needs to start the same study at the same place before it
// approves the replayed plan: the site, the problem, the intake and the tables.
export function replayBrief(workspace) {
  const site = (workspace && workspace.site) || {};
  const brief = (workspace && workspace.brief) || {};
  return {
    lat: site.lat, lon: site.lon,
    text: brief.problem || "",
    intake: { ...(brief.intake || {}) },
    tables: { ...((workspace && workspace.tables) || {}) },
  };
}

// "recorded on 2026-09-07 with claude-sonnet-5, 0.42 USD" (or "with no model").
export function recordedLabel(meta) {
  const m = meta || {};
  const date = String(m.recorded || m.date || "").slice(0, 10) || "an unknown date";
  const model = m.model ? String(m.model) : "no model";
  const usd = Number(m.usd);
  const cost = m.model && Number.isFinite(usd) && usd > 0 ? `, ${usd.toFixed(2)} USD` : "";
  return `recorded on ${date} with ${model}${cost}`;
}

// The one-line chip text for an index row: the title, or the headline, or the id.
export function chipText(row) {
  const r = row || {};
  return String(r.title || r.headline || r.id || "").trim();
}
