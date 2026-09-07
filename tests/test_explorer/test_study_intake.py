"""Study's on-device brief: the first sentence read into a decision, quantities, a return period, timescales.

The page asks a small model on the reader's device for one JSON object and
hands what it wrote to the worker as the brief and the intake; the Consultant's
own rules fill the rest and ask for what is missing. These checks cover the
pure half of the page (the prompt, the schema, the reply reader) with node, and
the wiring between the modules.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPLORER = ROOT / "explorer"
INTAKE = EXPLORER / "src" / "intake.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _node(script: str) -> dict:
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout)


@needs_node
def test_the_prompt_and_schema_ask_for_one_object_and_no_invented_numbers() -> None:
    got = _node(f"""
    const m = await import({json.dumps(INTAKE.as_uri())});
    console.log(JSON.stringify({{ prompt: m.briefPrompt(), schema: m.briefSchema() }}));
    """)
    prompt, schema = got["prompt"], got["schema"]
    assert "ONE JSON object" in prompt and "Never invent a number" in prompt
    for field in ("decision", "quantities", "return_period", "timescales"):
        assert field in prompt and field in schema["properties"]
    assert schema["properties"]["return_period"] == {"type": "integer"}
    assert schema["properties"]["timescales"]["items"] == {"type": "integer"}
    assert "—" not in prompt and "–" not in prompt


@needs_node
def test_the_reply_reader_keeps_what_is_usable_and_drops_the_rest() -> None:
    got = _node(f"""
    const m = await import({json.dumps(INTAKE.as_uri())});
    console.log(JSON.stringify([
      m.parseBriefReply('{{"decision": "size a culvert", "quantities": ["the 100-year flow"], "return_period": 100}}'),
      m.parseBriefReply('Sure! {{"return_period": 200}} there you go'),
      m.parseBriefReply('{{"timescales": [1, 3, 12, 0, 500, "x"]}}'),
      m.parseBriefReply('{{"return_period": 1}}'),
      m.parseBriefReply('{{"return_period": 50.5, "decision": "   "}}'),
      m.parseBriefReply('{{"quantities": "not a list"}}'),
      m.parseBriefReply('not json at all'),
      m.parseBriefReply(''),
      m.parseBriefReply('[{{"return_period": 100}}]'),
    ]));
    """)
    assert got[0] == {"brief": {"decision": "size a culvert", "quantities": ["the 100-year flow"]},
                      "intake": {"return_period": 100}}
    assert got[1] == {"brief": {}, "intake": {"return_period": 200}}      # prose around the object is tolerated
    assert got[2] == {"brief": {}, "intake": {"timescales": [1, 3, 12]}}  # out-of-range months are dropped, not clamped
    assert got[3] is None                                                  # a 1-year return period is not one
    assert got[4] is None                                                  # no fraction, no blank
    assert got[5] is None and got[6] is None and got[7] is None
    assert got[8] == {"brief": {}, "intake": {"return_period": 100}}      # the object inside a list is still found


def test_the_page_the_worker_and_the_package_agree_on_the_brief_path() -> None:
    studio = (EXPLORER / "src" / "studio.js").read_text(encoding="utf-8")
    worker = (EXPLORER / "worker.js").read_text(encoding="utf-8")
    local = (EXPLORER / "src" / "local-model.js").read_text(encoding="utf-8")
    # the on-device call is one bounded call with a schema, never a download started from Study
    assert "generateJsonLocally" in studio and "localModelReady" in studio
    assert "briefPrompt()" in studio and "briefSchema()" in studio and "parseBriefReply" in studio
    assert re.search(r'availability\(\)\) === "available"', local), "Study must not start a model download"
    assert "timeoutMs" in local and "responseConstraint" in local
    # what the device read travels as the intake and the proposed brief; the engine takes the proposal when it
    # can (Studio.say(text, proposed=...)), else the worker sets the fields itself and marks the source
    assert 'proposed: brief ? { brief, source: "device" } : null' in studio
    assert 'a.get("intake")' in worker and 'a.get("proposed")' in worker and 's.say(text, proposed=proposed)' in worker
    assert 'source = proposed["source"]' in worker
    for text in (studio, worker, local, INTAKE.read_text(encoding="utf-8")):
        assert "—" not in text and "–" not in text
