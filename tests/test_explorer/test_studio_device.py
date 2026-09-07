"""The device model as the Methodologist and the Author (explorer/src/studio-device.js), under node.

The module is pure: it takes the context the engine would send its model, the
exported prompts, and a `generate` function, which is a fake here. What is
checked is the flow the page relies on (one call for the plan, the summary and
the recommendations first and the steps while the model is quick, the cap on
calls), the reply reader, the context trimming, the words on the card, and
that a study store with no IndexedDB answers quietly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPLORER = ROOT / "explorer"
DEVICE = EXPLORER / "src" / "studio-device.js"
STORE = EXPLORER / "src" / "study-store.js"
STUDIO = EXPLORER / "src" / "studio.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _node(script: str) -> dict:
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout)


PRELUDE = f"""
const d = await import({json.dumps(DEVICE.as_uri())});
const log = [];
const planModel = async ({{ system, prompt, schema }}) => {{
  log.push({{ system, prompt: prompt.length, schema: Boolean(schema) }});
  return 'Here you go: ' + JSON.stringify({{ objective: "the design flow", steps: [
    {{ id: "s1", tool: "analyze_station", arguments: {{ source: "uk_ea", station_id: "3400TH" }} }} ] }});
}};
"""


@needs_node
def test_the_plan_is_one_call_with_the_engines_prompt_and_the_schema() -> None:
    got = _node(f"""
    {PRELUDE}
    const ctx = {{ system: "You are the Methodologist", brief: {{ decision: "size a culvert" }}, catalogue: [] }};
    const res = await d.planOnDevice({{ context: ctx,
      prompts: {{ schemas: {{ plan: {{ type: "object" }} }} }}, generate: planModel }});
    const none = await d.planOnDevice({{ context: {{ brief: {{}} }}, generate: planModel }});
    const empty = await d.planOnDevice({{ context: ctx, generate: async () => "no json here" }});
    const noSteps = await d.planOnDevice({{ context: ctx,
      generate: async () => JSON.stringify({{ objective: "x", steps: [] }}) }});
    const slow = await d.planOnDevice({{ context: ctx,
      generate: async () => {{ throw new Error("the on-device model took more than 25 s"); }} }});
    console.log(JSON.stringify({{ res, none, empty, noSteps, slow, log }}));
    """)
    assert got["res"]["plan"]["source"] == "device"
    assert got["res"]["plan"]["steps"][0]["tool"] == "analyze_station" and got["res"]["error"] is None
    assert got["log"] == [{"system": "You are the Methodologist", "prompt": got["log"][0]["prompt"], "schema": True}]
    assert got["none"]["plan"] is None and "no prompt" in got["none"]["error"]
    assert got["empty"]["plan"] is None and got["empty"]["error"] == "the reply was not JSON"
    assert got["noSteps"]["plan"] is None and got["noSteps"]["error"] == "the reply had no steps"
    assert got["slow"]["plan"] is None and "25 s" in got["slow"]["error"]


@needs_node
def test_the_prose_is_summary_and_recommendations_first_then_the_steps_while_quick_capped() -> None:
    got = _node(f"""
    {PRELUDE}
    const asked = [];
    const author = (delayMs) => async ({{ prompt }}) => {{
      const want = JSON.parse(prompt.split("\\nWrite only")[0]).write;
      asked.push(want);
      await new Promise((r) => setTimeout(r, delayMs));
      return JSON.stringify({{ sections: Object.fromEntries(want.map((k) => [k, `prose for ${{k}}`])) }});
    }};
    const ctx = {{ system: "You are the Author", steps: [
      {{ id: "s1", ok: true, result: {{ a: 1 }} }}, {{ id: "s2", ok: true, result: {{ b: 2 }} }},
      {{ id: "s3", ok: false, error: "x" }}, {{ id: "s4", ok: true, result: {{ c: 3 }} }}, {{ id: "s5",
        ok: true, result: {{ d: 4 }} }} ] }};
    const quick = await d.narrateOnDevice({{ context: ctx, generate: author(0) }});
    const quickAsked = asked.splice(0);
    const slow = await d.narrateOnDevice({{ context: ctx, generate: author(0), fastMs: 0 }});
    const slowAsked = asked.splice(0);
    const nothing = await d.narrateOnDevice({{ context: ctx, generate: async () => "{{}}" }});
    const failed = await d.narrateOnDevice({{ context: ctx,
      generate: async () => {{ throw new Error("took more than 25 s"); }} }});
    console.log(JSON.stringify({{ quick, quickAsked, slow, slowAsked, nothing, failed, ids: d.resultStepIds(ctx) }}));
    """)
    assert got["ids"] == ["s1", "s2", "s4", "s5"], "a failed step and a step with no result are not narrated"
    assert got["quickAsked"] == [["summary", "recommendations"], ["results-s1"], ["results-s2"], ["results-s4"]]
    assert got["quick"]["calls"] == 4 and set(got["quick"]["sections"]) == {
        "summary", "recommendations", "results-s1", "results-s2", "results-s4"}
    assert got["slowAsked"] == [["summary", "recommendations"]], "a slow first call earns no per-step calls"
    assert got["slow"]["calls"] == 1 and set(got["slow"]["sections"]) == {"summary", "recommendations"}
    assert got["nothing"]["sections"] == {} and got["nothing"]["error"] == "the reply carried no section"
    assert got["failed"]["sections"] == {} and "25 s" in got["failed"]["error"]


@needs_node
def test_the_words_on_the_card() -> None:
    got = _node(f"""
    {PRELUDE}
    console.log(JSON.stringify([
      d.planLine({{ used: "proposed", model: "Chrome's built-in model" }}),
      d.planLine({{ used: "tree", errors: ["step s1: unknown tool 'nope'", "more"], model: "x" }}),
      d.planLine({{ used: "tree", errors: [] }}),
      d.planLine({{ author: "playbook" }}), d.planLine({{ author: "methodologist" }}),
        d.planLine({{ author: "device", model: "Nano" }}),
      d.proseLine({{ writtenBy: "device", dropped: 2, model: "Chrome's built-in model" }}),
      d.proseLine({{ writtenBy: "device", dropped: 1, model: "Nano" }}),
      d.proseLine({{ writtenBy: "device", dropped: [], model: "Nano" }}),
      d.proseLine({{ writtenBy: "template" }}),
      d.proseLine({{ failed: "the device model took more than 25 s" }}),
    ]));
    """)
    assert got == [
        "planned on this device with Chrome's built-in model",
        "the playbook's plan (the device model's plan did not pass the validator: step s1: unknown tool 'nope')",
        "the playbook's plan",
        "the playbook's plan", "planned by the model", "planned on this device with Nano",
        "written on this device with Chrome's built-in model; 2 sentences dropped by the checks",
        "written on this device with Nano; 1 sentence dropped by the checks",
        "written on this device with Nano; nothing dropped by the checks",
        None,
        "the template text stands; the device model took more than 25 s",
    ]
    for line in got:
        assert line is None or ("—" not in line and "–" not in line)


@needs_node
def test_the_context_is_cut_to_size_and_the_reply_reader_is_lenient() -> None:
    got = _node(f"""
    {PRELUDE}
    const catalogue = Array.from({{ length: 60 }}, (_, i) => ({{ id: "tool" + i, kind: "station",
      purpose: "p".repeat(400) + ". More.",
      arguments: {{ a: {{ type: "number" }}, b: {{ type: "string" }} }}, methods: ["m"] }}));
    const big = {{ system: "S", brief: {{ decision: "d" }}, exemplar: {{ steps: [{{ tool: "tool3" }}] }}, catalogue,
      gates: {{ min_years: {{}}, ok: {{}} }}, inventory: {{ datasets: Array.from({{ length: 30 }}, (_,
        i) => ({{ id: "ds" + i }})) }} }};
    const small = d.compactContext({{ system: "S", brief: {{ x: 1 }} }});
    const cut = d.compactContext(big, 6000);
    const hard = d.compactContext(big, 300);
    const steps = d.compactContext({{ system: "S", steps: [{{ id: "s1",
      result: {{ series: Array.from({{ length: 500 }}, (_, i) => i), note: "n".repeat(1000) }} }}] }}, 400);
    console.log(JSON.stringify({{
      small, cutLen: JSON.stringify(cut).length, cutTools: cut.catalogue.map((e) => e.id).slice(0, 3),
        nTools: cut.catalogue.length,
      cutArgs: cut.catalogue[0].arguments, cutGates: cut.gates, cutDs: cut.inventory.datasets.length,
        keepsExemplar: cut.exemplar.steps[0].tool,
      hard: {{ truncated: hard.truncated, len: hard.text.length }},
      stepsLen: JSON.stringify(steps).length, series: steps.steps[0].result.series.length,
      replies: [d.parseJsonReply('```json\\n{{"a": 1}}\\n```'),
        d.parseJsonReply('Sure {{"a": {{"b": 2}}}} ok'), d.parseJsonReply('[1]'), d.parseJsonReply(''),
        d.parseJsonReply('{{"a": 1}}')],
    }}));
    """)
    assert got["small"] == {"brief": {"x": 1}}, "the system prompt never travels in the prompt"
    assert got["cutLen"] <= 6000
    assert got["cutTools"][0] == "tool3", "the tools the tree uses come first"
    assert got["nTools"] == 13 and got["cutArgs"] == ["a", "b"] and got["cutGates"] == ["min_years", "ok"]
    assert got["cutDs"] == 8 and got["keepsExemplar"] == "tool3"
    assert got["hard"] == {"truncated": True, "len": 300}
    assert got["stepsLen"] <= 400 or got["series"] == 12, "a long result is shrunk before anything is cut"
    assert got["replies"] == [{"a": 1}, {"a": {"b": 2}}, None, None, {"a": 1}]


@needs_node
def test_the_store_answers_quietly_without_indexeddb() -> None:
    got = _node(f"""
    const s = await import({json.dumps(STORE.as_uri())});
    const now = Date.parse("2026-09-07T12:00:00Z");
    console.log(JSON.stringify({{
      saved: await s.saveStudy({{ id: "abc", ws: {{}} }}), latest: await s.latestStudy("uk_ea/3400TH"),
        list: await s.listStudies(),
      loaded: await s.loadStudy("abc"), keep: s.KEEP,
      ago: [s.agoWords(now - 30e3, now), s.agoWords(now - 5 * 60e3, now), s.agoWords(now - 3 * 3600e3, now),
            s.agoWords(now - 26 * 3600e3, now), s.agoWords(now - 3 * 86400e3, now)],
    }}));
    """)
    assert got["saved"] is False and got["latest"] is None and got["list"] == [] and got["loaded"] is None
    assert got["keep"] == 5
    assert got["ago"] == ["just now", "5 min ago", "3 h ago", "yesterday", "3 days ago"]


def test_the_page_wires_the_device_crew_the_stop_and_the_store() -> None:
    studio = STUDIO.read_text(encoding="utf-8")
    worker = (EXPLORER / "worker.js").read_text(encoding="utf-8")
    client = (EXPLORER / "src" / "worker-client.js").read_text(encoding="utf-8")
    # the device plans at review and writes after the run, through the worker's context, check_plan and narrate
    for needed in ('op: "context", role: "methodologist"', 'op: "context", role: "author"', 'op: "check_plan"',
                   'op: "narrate"', 'op: "prompts"', "planOnDevice(", "narrateOnDevice(", "localModelReady()"):
        assert needed in studio, needed
    assert "loadLocalModel" not in studio, "Study never starts a model download"
    # Stop terminates the worker and keeps the page's copy of the study
    assert "restartWorker()" in studio and "export function restartWorker()" in client
    assert "worker.terminate()" in client and "state.pending.clear()" in client
    assert "Stopped; the figures made so far are gone, the plan is kept." in studio
    # the study is saved after every reply and offered back; a workspace.json resumes
    for needed in ("saveStudy(", "latestStudy(", "loadStudy(", 'data-act="resume"', "looksLikeWorkspace(", ".json$"):
        assert needed in studio, needed
    # the worker guards every new op on the engine having the method
    for needed in ('getattr(s, "narrate", None)', '_accepts(s.say, "proposed")', '_accepts(s.approve, "plan")',
                   'getattr(s, f"{role}_context", None)', 'getattr(_prompts, "as_json", None)'):
        assert needed in worker, needed
    for text in (studio, worker, client, DEVICE.read_text(encoding="utf-8"), STORE.read_text(encoding="utf-8")):
        assert "—" not in text and "–" not in text
