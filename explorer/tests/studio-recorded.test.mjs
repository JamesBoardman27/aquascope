// node --test explorer/tests/
import test from "node:test";
import assert from "node:assert/strict";

import {
  CHIP_LIMIT, recordedChipsHtml, recordedFigures, recordedFilesHtml, recordedNoteHtml, recordedPlanLine,
} from "../src/studio-recorded.js";

const ROWS = Array.from({ length: 8 }, (_, i) => ({
  id: `case-${i}`, title: `Study ${i} <b>`, shows: `what ${i} shows`, site: { name: `Site ${i}` },
}));

test("the chips are one line of label and at most six chips, with a more chip for the rest", () => {
  const html = recordedChipsHtml(ROWS);
  assert.equal((html.match(/data-recorded=/g) || []).length, CHIP_LIMIT);
  assert.match(html, /See a recorded study/);
  assert.match(html, /data-act="more-recorded">2 more</);
  assert.match(html, /Study 0 &lt;b&gt;/, "titles are escaped");
  assert.match(html, /title="what 0 shows"/);
  const all = recordedChipsHtml(ROWS, { showAll: true });
  assert.equal((all.match(/data-recorded=/g) || []).length, 8);
  assert.doesNotMatch(all, /more-recorded/);
  assert.equal(recordedChipsHtml([]), "");
  assert.match(recordedChipsHtml([{ id: "x" }]), /data-recorded="x"[^>]*>x</, "a row with only an id is offered by its id");
  assert.equal(recordedChipsHtml([{ title: "no id" }, null]), "", "a row with no id cannot be opened, so it is not offered");
  const few = recordedChipsHtml(ROWS.slice(0, 3));
  assert.equal((few.match(/data-recorded=/g) || []).length, 3);
  assert.doesNotMatch(few, /more-recorded/);
});

test("the note names the recording and says the numbers are the recording's", () => {
  const html = recordedNoteHtml({ recorded: "2026-09-07T14:17:39+00:00", model: "claude-sonnet-5", usd: 0.4213 });
  assert.match(html, /recorded on 2026-09-07 with claude-sonnet-5, 0\.42 USD; the numbers below were computed then; press Re-run live/);
  assert.match(html, /keyless\.<\/p>$/);
  assert.doesNotMatch(html, /[\u2014\u2013]/);
});

test("the file links point at the recorded files and say what is not recorded in three words", () => {
  const html = recordedFilesHtml({ "report.md": "u/report.md", "study.yaml": "u/study.yaml", "workspace.json": "u/ws.json", "meta.json": "u/m" });
  assert.match(html, /<a href="u\/report\.md" download="report\.md">Markdown<\/a>/);
  assert.match(html, /study\.yaml.*workspace\.json/);
  assert.doesNotMatch(html, /meta\.json/);
  assert.match(html, /Word, Excel: unrecorded/);
  assert.match(recordedFilesHtml({}), /^<p class="study-docs muted"><span>Word, Excel: unrecorded<\/span><\/p>$/);
});

test("the figures become board entries from their urls", () => {
  const figs = recordedFigures({ figures: [
    { name: "s3.png", url: "u/s3.png", caption: "The curve", step: "s3", id: "fig-s3" }, { name: "x" }, null,
  ] });
  assert.deepEqual(figs, [{ id: "fig-s3", src: "u/s3.png", caption: "The curve", step: "s3", job: null }]);
  assert.deepEqual(recordedFigures(null), []);
});

test("the plan line after a re-run says whose plan ran", () => {
  assert.equal(recordedPlanLine({ used: "proposed", model: "claude-sonnet-5" }), "the recorded plan (claude-sonnet-5), re-run keyless");
  assert.equal(recordedPlanLine({ used: "proposed" }), "the recorded plan, re-run keyless");
  assert.equal(recordedPlanLine({ used: "tree", errors: ["step s2: unknown tool 'x'"] }),
    "the playbook's plan (the recorded plan did not pass the validator: step s2: unknown tool 'x')");
  assert.equal(recordedPlanLine({ used: "tree" }), "the playbook's plan");
});
