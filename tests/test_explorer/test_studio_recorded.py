"""The recorded studies on the Study board (#366): the wiring between the page's modules.

The pure halves (studio-showcase.js, studio-recorded.js) are node:test suites
under explorer/tests/; this checks what only the wiring can get wrong: the
chips on the intake board, a chip opening a recording with no worker call,
Re-run live approving the recorded plan at the recorded site, the #study=<id>
link, and the house style.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPLORER = ROOT / "explorer"


def _read(*parts: str) -> str:
    return (EXPLORER / Path(*parts)).read_text(encoding="utf-8")


def test_the_intake_offers_the_recorded_studies_and_a_chip_opens_one_without_the_worker() -> None:
    studio = _read("src", "studio.js")
    assert 'recordedIndex(RECORDED_BASE, { version: "__BUILD__" })' in studio
    assert 'RECORDED_BASE = "./showcase/studies/"' in studio
    assert "recordedChipsHtml(S.index, { showAll: S.moreRecorded })" in studio
    assert 'closest("[data-recorded]")' in studio and 'what === "more-recorded"' in studio
    body = studio[studio.index("async function openRecorded("):studio.index("async function rerunRecorded(")]
    assert "loadRecorded(RECORDED_BASE, id" in body and "recordedFigures(rec)" in body
    assert 'call("studio"' not in body and "job(" not in body, "opening a recording makes no worker call"
    done = studio[studio.index("function recordedDoneHtml("):studio.index("function declinedHtml(")]
    assert "recordedNoteHtml(rec.meta)" in done and "recordedFilesHtml(rec.files)" in done
    assert 'data-act="rerun"' in done and "Re-run live" in done and 'data-act="again"' in done
    assert "data-art=" not in done, "the recorded figures come from their urls, never fetched by id"


def test_re_run_live_runs_the_recorded_plan_at_the_recorded_site() -> None:
    studio = _read("src", "studio.js")
    body = studio[studio.index("async function rerunRecorded("):studio.index("// ── files in, files out")]
    assert "replayBrief(rec.workspace)" in body and "replayPlan(rec.workspace)" in body
    assert "actions.selectPoint(Number(b.lat), Number(b.lon)" in body, "the site marker is the recorded site"
    assert "start(b.text" in body and "{ intake: b.intake }" in body
    assert 'callStudio("say", { text: "just go" })' in body, "any question takes the defaults"
    assert 'plan: { ...plan, source: "recorded" }' in body
    assert "b.tables" in body, "the own-table case carries its CSV"
    assert "recordedPlanLine({ used: p.plan_used" in studio, "the foot says whose plan ran"


def test_a_study_link_with_an_id_opens_that_recording() -> None:
    url = _read("src", "url.js")
    assert "out.studyId = v" in url and '/^[A-Za-z0-9_-]+$/' in url
    assert 'q.set("study", state.study.recorded || "1")' in url
    app = _read("app.js")
    assert "actions.openStudy(url.studyId ? { recorded: url.studyId } : {})" in app
    studio = _read("src", "studio.js")
    assert "export function openStudy({ fresh = false, recorded = null } = {})" in studio
    assert "if (recorded) { openRecorded(recorded); return; }" in studio
    core = _read("src", "core.js")
    assert "study: { running: false, recorded: null }" in core


def test_the_recorded_surface_writes_with_plain_hyphens() -> None:
    for parts in (("src", "studio-recorded.js"), ("src", "studio.js"), ("tests", "studio-recorded.test.mjs")):
        text = _read(*parts)
        assert "—" not in text and "–" not in text, parts[-1]
