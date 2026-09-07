// node --test explorer/tests/
import test from "node:test";
import assert from "node:assert/strict";

import {
  chipText, loadRecorded, recordedIndex, recordedLabel, replayBrief, replayPlan,
} from "../src/studio-showcase.js";

const META = {
  id: "kingston-flood", title: "Design flood of the Thames at Kingston", kind: "flood_risk",
  model: "claude-sonnet-5", provider: "anthropic", recorded: "2026-09-07T10:11:12+00:00", usd: 0.4213,
  files: ["workspace.json", "report.md", "study.yaml", "figures/s3_frequency_curve.png"],
  figures: [{ name: "s3_frequency_curve.png", id: "fig-s3-frequency_curve", step: "s3", caption: "The curve" }],
};

const WORKSPACE = {
  site: { lat: 51.415, lon: -0.308 },
  brief: { problem: "Design flow for a road crossing", intake: { return_period: 100 } },
  tables: { "upload:my_flows.csv": "date,flow_m3s\n2000-01-01,1\n" },
  study: {
    version: 3, title: "t", question: "q", author: "methodologist",
    plan: { playbook: "flood_risk", branch: "at_site", author: "methodologist", replans: [{ step: "s3" }],
      replanned_from: { branch: "x" }, caveats: ["c"] },
    steps: [
      { id: "s1", tool: "describe_catchment", arguments: { lat: 51.415, lon: -0.308 }, result: { a: 1 }, sha256: "x" },
      { id: "s3", tool: "flood_frequency", arguments: { source: "uk_ea", station_id: "k" },
        expects: [{ check: "min_years", value: 20, path: "years" }] },
    ],
    results: [{ id: "s1", result: {} }],
  },
  artifacts: [{ id: "fig-s3-frequency_curve", name: "figures/s3_frequency_curve.png", caption: "From the workspace",
    step: "s3" }],
};

const INDEX = { generated: "2026-09-07T12:00:00+00:00", aquascope_version: "0.15.1", note: "n",
  studies: [{ id: "kingston-flood", title: META.title, headline: "About 520 m3/s.", usd: 0.42 }] };

function fakeFetch(routes) {
  const calls = [];
  const f = async (url) => {
    calls.push(url);
    const path = url.split("?")[0];
    const hit = routes[path];
    if (hit === undefined) return { ok: false, status: 404, json: async () => ({}), text: async () => "" };
    return {
      ok: true, status: 200,
      json: async () => (typeof hit === "string" ? JSON.parse(hit) : hit),
      text: async () => (typeof hit === "string" ? hit : JSON.stringify(hit)),
    };
  };
  f.calls = calls;
  return f;
}

test("recordedIndex parses the index and busts the cache with a version", async () => {
  const fetch = fakeFetch({ "showcase/studies/index.json": INDEX });
  const idx = await recordedIndex("showcase/studies/", { fetch, version: "abc" });
  assert.equal(idx.studies.length, 1);
  assert.equal(idx.studies[0].id, "kingston-flood");
  assert.equal(fetch.calls[0], "showcase/studies/index.json?v=abc");
});

test("recordedIndex is empty when nothing is published and throws on a server error", async () => {
  const none = await recordedIndex("./showcase/studies", { fetch: fakeFetch({}) });
  assert.deepEqual(none.studies, []);
  const broken = async () => ({ ok: false, status: 500 });
  await assert.rejects(() => recordedIndex("x", { fetch: broken }), /500/);
  const odd = fakeFetch({ "x/index.json": { studies: "not a list" } });
  assert.deepEqual((await recordedIndex("x", { fetch: odd })).studies, []);
});

test("loadRecorded returns the workspace, the report, the figures with urls and the meta", async () => {
  const fetch = fakeFetch({
    "showcase/studies/kingston-flood/meta.json": META,
    "showcase/studies/kingston-flood/workspace.json": WORKSPACE,
    "showcase/studies/kingston-flood/report.md": "# Design flood\n\nAbout 520 m3/s.",
  });
  const rec = await loadRecorded("showcase/studies", "kingston-flood", { fetch, version: "v1" });
  assert.equal(rec.id, "kingston-flood");
  assert.equal(rec.meta.model, "claude-sonnet-5");
  assert.equal(rec.workspace.site.lat, 51.415);
  assert.match(rec.report, /520 m3\/s/);
  assert.deepEqual(rec.figures, [{
    name: "s3_frequency_curve.png", url: "showcase/studies/kingston-flood/figures/s3_frequency_curve.png?v=v1",
    caption: "The curve", step: "s3", id: "fig-s3-frequency_curve",
  }]);
  assert.deepEqual(Object.keys(rec.files), ["workspace.json", "report.md", "study.yaml"]);
  assert.equal(rec.files["study.yaml"], "showcase/studies/kingston-flood/study.yaml?v=v1");
  assert.ok(fetch.calls.every((u) => u.endsWith("?v=v1")));
});

test("loadRecorded takes captions from the workspace, tolerates a missing report, refuses a bad id", async () => {
  const meta = { ...META, files: ["workspace.json"], figures: ["s3_frequency_curve.png"] };
  const fetch = fakeFetch({ "b/kingston-flood/meta.json": meta, "b/kingston-flood/workspace.json": WORKSPACE });
  const rec = await loadRecorded("b", "kingston-flood", { fetch });
  assert.equal(rec.report, "");
  assert.equal(rec.figures[0].caption, "From the workspace");
  assert.equal(rec.figures[0].url, "b/kingston-flood/figures/s3_frequency_curve.png");
  await assert.rejects(() => loadRecorded("b", "../etc", { fetch }), /not a recording id/);
  await assert.rejects(() => loadRecorded("b", "missing", { fetch }), /404/);
});

test("replayPlan is the study without the run, and does not touch the workspace", () => {
  const before = JSON.stringify(WORKSPACE);
  const plan = replayPlan(WORKSPACE);
  assert.equal(plan.version, 3);
  assert.equal(plan.results, undefined);
  assert.deepEqual(plan.plan, { playbook: "flood_risk", branch: "at_site", author: "methodologist", caveats: ["c"] });
  assert.deepEqual(plan.steps[0], { id: "s1", tool: "describe_catchment", arguments: { lat: 51.415, lon: -0.308 } });
  assert.deepEqual(plan.steps[1].expects, [{ check: "min_years", value: 20, path: "years" }]);
  assert.equal(JSON.stringify(WORKSPACE), before);
  assert.equal(replayPlan({ study: null }), null);
  assert.equal(replayPlan({ study: { steps: [] } }), null);
  assert.equal(replayPlan(undefined), null);
});

test("replayBrief carries the site, the problem, the intake and the tables", () => {
  assert.deepEqual(replayBrief(WORKSPACE), {
    lat: 51.415, lon: -0.308, text: "Design flow for a road crossing", intake: { return_period: 100 },
    tables: { "upload:my_flows.csv": "date,flow_m3s\n2000-01-01,1\n" },
  });
  assert.deepEqual(replayBrief({}), { lat: undefined, lon: undefined, text: "", intake: {}, tables: {} });
});

test("recordedLabel names the date, the model and the cost", () => {
  assert.equal(recordedLabel(META), "recorded on 2026-09-07 with claude-sonnet-5, 0.42 USD");
  assert.equal(recordedLabel({ date: "2026-09-07", model: "claude-sonnet-5", usd: 0 }),
    "recorded on 2026-09-07 with claude-sonnet-5");
  assert.equal(recordedLabel({ recorded: "2026-09-07T00:00:00+00:00", model: null }),
    "recorded on 2026-09-07 with no model");
  assert.equal(recordedLabel({}), "recorded on an unknown date with no model");
});

test("chipText prefers the title", () => {
  assert.equal(chipText(INDEX.studies[0]), META.title);
  assert.equal(chipText({ id: "x", headline: "h" }), "h");
  assert.equal(chipText({ id: "x" }), "x");
  assert.equal(chipText(null), "");
});
