"""The Consultant: from the client's words to a brief the crew can plan from.

Keyless, the brief comes from the keyword rules that pick a playbook
(``team.choose_playbook``), the intake hints the text states outright
(``team.intake_hints``) and the playbook's intake fields that have no default
and were not inferred, asked as questions (at most three). With a model, one
call reads the text, the site, a catalog-only reconnaissance and the uploads'
column names and returns the structured brief with its questions. Answers
arrive as later calls of :func:`consult`; "just go" proceeds on defaults.

After the report, :func:`classify_follow_up` says whether a follow-up is a
question (answered from the workspace) or a change (a new intake, a request
for the Methodologist).
"""

from __future__ import annotations

import io
import re
from typing import Any

from aquascope.studio.model import Model, compact
from aquascope.studio.prompts import CONSULTANT, CONSULTANT_ANSWERS, CONSULTANT_FOLLOW_UP
from aquascope.studio.workspace import Message, Question, Workspace

MAX_QUESTIONS = 3
RADIUS_KM = 50.0

_PROCEED = re.compile(
    r"^\s*(just go|go|go ahead|proceed|defaults?|use (the )?defaults?|ok(ay)?|yes|y|fine|continue|run|"
    r"whatever you think|your call)\s*[.!]?\s*$", re.I,
)
_SPLIT = re.compile(r"\s*(?:[,;\n]|\band\b)\s*", re.I)
_CHANGE = re.compile(
    r"\b(redo|re-?run|instead|change|switch|add|also (compute|run|check|fit)|extend|repeat|with a|use the|"
    r"another|different|longer|shorter|what about)\b", re.I,
)

__all__ = ["classify_follow_up", "consult", "known_playbooks"]


def known_playbooks() -> dict[str, Any]:
    """The playbooks by id (a broken file is skipped)."""
    from aquascope import playbooks as pbk

    out: dict[str, Any] = {}
    for row in pbk.list_playbooks():
        if "error" in row:
            continue
        try:
            out[row["id"]] = pbk.load(row["id"])
        except pbk.PlaybookError:
            continue
    return out


def _columns(ws: Workspace, tables: dict[str, Any] | None) -> dict[str, list[str]]:
    """The column names of every upload, without pandas when the header line is enough."""
    out: dict[str, list[str]] = {}
    for key, value in (tables or {}).items():
        cols = getattr(value, "columns", None)
        if cols is not None:
            out[key] = [str(c) for c in cols]
    for key, csv in ws.tables.items():
        if key in out:
            continue
        head = io.StringIO(csv).readline().strip()
        out[key] = [c.strip().strip('"') for c in head.split(",")] if head else []
    return out


def _quick_recon(ws: Workspace, problem: str | None) -> dict[str, Any] | None:
    """A catalog-only reconnaissance for the model's brief; None when it cannot be had."""
    site = ws.site or {}
    if site.get("lat") is None or site.get("lon") is None:
        return None
    try:
        from aquascope.ai_engine.team import _recon_summary
        from aquascope.explore import assess_site

        recon = assess_site(float(site["lat"]), float(site["lon"]), radius_km=RADIUS_KM, problem=problem)
        return _recon_summary(recon) if isinstance(recon, dict) else None
    except Exception as exc:  # noqa: BLE001 - the brief can be taken without it
        ws.event("consultant", "recon_skipped", f"{type(exc).__name__}: {exc}")
        return None


def _intake_schema(pb: Any) -> list[dict[str, Any]]:
    return [{"name": f.name, "type": f.type, "default": f.default, "options": f.options or None, "help": f.help}
            for f in pb.intake]


def _rules_questions(pb: Any | None, intake: dict[str, Any], known: dict[str, Any]) -> list[Question]:
    """The playbook's intake fields without a default and not inferred; or which playbook, when none matched."""
    if pb is None:
        return [Question(id="playbook", text="Which kind of problem is this? One of: " + ", ".join(sorted(known))
                         + ". Say 'just go' to let the crew decide (a model is needed for that).",
                         options=sorted(known))]
    out: list[Question] = []
    for f in pb.intake:
        if f.default is not None or intake.get(f.name) is not None:
            continue
        text = f.label or f.name
        if f.help:
            text += f" ({f.help})"
        out.append(Question(id=f.name, text=text, options=[str(o) for o in f.options] or None, default=f.default))
    return out[:MAX_QUESTIONS]


def _rules_quantities(playbook: str | None, intake: dict[str, Any]) -> list[str]:
    rp = intake.get("return_period")
    table = {
        "flood_risk": [f"the {rp or 100}-year return level with its interval and the spread between fits"],
        "ungauged_flow": [f"the {intake.get('statistic') or 'flow'} statistics transferred from donor gauges, "
                          "with a band"],
        "groundwater_decline": ["the trend in groundwater level with Sen's slope and its significance"],
        "drought_status": ["SPI and SPEI at the requested timescales, the current status and the worst on record"],
        "supply_reliability": ["the fraction of days, years and volume the demand is met"],
        "irrigation_feasibility": ["the seasonal crop water demand in mm, m3 and m3/s"],
        "water_quality": ["the water-quality index and the guideline exceedances per parameter"],
    }
    return table.get(playbook or "", [])


def _apply_brief(ws: Workspace, obj: dict[str, Any], known: dict[str, Any]) -> None:
    """Copy what a model wrote into the brief, kept within what the playbooks and the registry know."""
    from aquascope import playbooks as pbk

    b = ws.brief
    for key in ("decision", "period", "horizon"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            setattr(b, key, v.strip())
    for key in ("quantities", "constraints", "assumptions"):
        v = obj.get(key)
        if isinstance(v, list):
            setattr(b, key, [str(x) for x in v if isinstance(x, (str, int, float))])
    if isinstance(obj.get("deliverables"), list) and obj["deliverables"]:
        b.deliverables = [str(x) for x in obj["deliverables"]]
    playbook = obj.get("playbook")
    if isinstance(playbook, str) and playbook in known:
        b.playbook = playbook
        b.kind = known[playbook].problem
    elif isinstance(obj.get("kind"), str):
        b.kind = obj["kind"]
    intake = obj.get("intake")
    if isinstance(intake, dict):
        if b.playbook in known:
            coerced = pbk.coerce_intake(known[b.playbook], {**b.intake, **intake})
            b.intake = {k: v for k, v in coerced.items() if v is not None}
        else:
            b.intake.update({k: v for k, v in intake.items() if v is not None})
    questions: list[Question] = []
    for q in obj.get("questions") or []:
        if not isinstance(q, dict) or not q.get("text"):
            continue
        qid = str(q.get("id") or f"q{len(questions) + 1}")
        if b.intake.get(qid) is not None:
            continue
        opts = q.get("options")
        questions.append(Question(id=qid, text=str(q["text"]),
                                  options=[str(o) for o in opts] if isinstance(opts, list) and opts else None,
                                  default=q.get("default")))
    b.questions = questions[:MAX_QUESTIONS]
    b.ready = not b.questions and bool(obj.get("ready", True))


def _open(ws: Workspace, model: Model | None, text: str, tables: dict[str, Any] | None) -> Message:
    from aquascope.ai_engine.team import choose_playbook, intake_hints

    known = known_playbooks()
    b = ws.brief
    b.problem = text
    playbook, ambiguous = choose_playbook(text)
    playbook = playbook if playbook in known else None
    hints = intake_hints(text, playbook)
    for k, v in hints.items():
        b.intake.setdefault(k, v)
    b.playbook = playbook
    b.kind = known[playbook].problem if playbook else None
    b.source = "rules"
    ws.event("consultant", "keywords", f"rules pick {playbook or 'nothing'}" + (" (ambiguous)" if ambiguous else ""))

    obj = None
    if model:
        obj = model.call_json("consultant", CONSULTANT, {
            "problem": text, "site": ws.site,
            "recon": _quick_recon(ws, b.kind),
            "uploads": _columns(ws, tables),
            "intake_given": dict(b.intake),
            "rules_pick": {"playbook": playbook, "ambiguous": ambiguous},
            "playbooks": [{"id": pb.id, "problem": pb.problem, "title": pb.title, "intake": _intake_schema(pb)}
                          for pb in known.values()],
        })
    if obj:
        _apply_brief(ws, obj, known)
        b.source = "model"
        ws.event("consultant", "brief", f"model: playbook {b.playbook or 'none'}, {len(b.questions)} question(s)")
    else:
        pb = known.get(playbook) if playbook else None
        b.questions = _rules_questions(pb, b.intake, known)
        b.decision = b.decision or (str(b.intake["decision"]) if b.intake.get("decision") else None)
        b.quantities = b.quantities or _rules_quantities(playbook, b.intake)
        if pb is not None:
            for f in pb.intake:
                if f.default is not None and b.intake.get(f.name) is None and f.name not in {q.id for q in b.questions}:
                    b.assumptions.append(f"{f.label or f.name}: {f.default} (the playbook's default)")
        b.ready = not b.questions
        ws.event("consultant", "brief", f"rules: playbook {playbook or 'none'}, {len(b.questions)} question(s)")
    return _message(ws)


def _answer(ws: Workspace, model: Model | None, text: str) -> Message:
    from aquascope import playbooks as pbk
    from aquascope.ai_engine.team import intake_hints

    known = known_playbooks()
    b = ws.brief
    open_qs = b.open_questions
    if _PROCEED.match(text):
        for q in open_qs:
            q.answer = q.default if q.default is not None else ""
        b.assumptions.append("The client asked to proceed on the defaults.")
        b.ready = True
        ws.event("consultant", "answers", "proceed on defaults")
        return _message(ws)

    obj = None
    if model and open_qs:
        obj = model.call_json("consultant", CONSULTANT_ANSWERS, {
            "reply": text, "problem": b.problem, "playbook": b.playbook, "intake": dict(b.intake),
            "questions": [q.to_dict() for q in open_qs],
            "fields": _intake_schema(known[b.playbook]) if b.playbook in known else [],
        })
    if obj:
        answers = obj.get("answers") if isinstance(obj.get("answers"), dict) else {}
        for q in open_qs:
            if answers.get(q.id) is not None:
                q.answer = answers[q.id]
        if isinstance(obj.get("intake"), dict):
            b.intake.update({k: v for k, v in obj["intake"].items() if v is not None})
        if isinstance(obj.get("assumptions"), list):
            b.assumptions += [str(a) for a in obj["assumptions"]]
        if obj.get("ready") is True:
            for q in b.open_questions:
                q.answer = q.default if q.default is not None else ""
    else:
        hints = intake_hints(text, b.playbook)
        for q in open_qs:
            if q.id in hints:
                q.answer = hints[q.id]
        rest = [q for q in open_qs if q.answer is None]
        parts = [p for p in _SPLIT.split(text) if p.strip()] if len(rest) > 1 else [text.strip()]
        for q, part in zip(rest, parts):
            q.answer = _match_option(part, q.options) if q.options else part.strip()
        for k, v in hints.items():
            b.intake.setdefault(k, v)

    for q in b.questions:
        if q.answer is None or q.answer == "":
            continue
        if q.id == "playbook":
            picked = _match_option(str(q.answer), sorted(known))
            if picked in known:
                b.playbook, b.kind = picked, known[picked].problem
            else:
                q.answer = None
            continue
        b.intake[q.id] = q.answer
    if b.playbook in known:
        coerced = pbk.coerce_intake(known[b.playbook], b.intake)
        b.intake = {k: (coerced[k] if k in coerced else v) for k, v in b.intake.items() if v is not None}
        for k, v in coerced.items():
            if v is not None and k not in b.intake:
                b.intake[k] = v
    b.ready = not b.open_questions
    ws.event("consultant", "answers", f"{len(open_qs) - len(b.open_questions)} answered, "
             f"{len(b.open_questions)} open")
    return _message(ws)


def _match_option(text: str, options: list[str] | None) -> Any:
    if not options:
        return text.strip()
    low = text.strip().lower()
    for o in options:
        if low == str(o).lower():
            return o
    for o in options:
        if str(o).lower() in low or low in str(o).lower():
            return o
    return text.strip()


def _message(ws: Workspace) -> Message:
    b = ws.brief
    site = ws.site or {}
    where = f"{site.get('lat')}, {site.get('lon')}" if site else "the site"
    if b.open_questions:
        lines = ["Before the crew plans, a few things the text does not say:"]
        for i, q in enumerate(b.open_questions, 1):
            opts = f" [{', '.join(q.options)}]" if q.options else ""
            dflt = f" (default {q.default})" if q.default is not None else ""
            lines.append(f"{i}. {q.text}{opts}{dflt}")
        lines.append("Answer in order, or say 'just go' to proceed on the defaults.")
        text = "\n".join(lines)
        return ws.say("consultant", text, kind="questions",
                      payload={"questions": [q.to_dict() for q in b.open_questions], "brief": b.to_dict()})
    bits = [f"Brief: {b.decision or b.problem} at {where}"]
    if b.playbook:
        bits.append(f"playbook {b.playbook}")
    if b.intake:
        bits.append("intake " + ", ".join(f"{k}={v}" for k, v in b.intake.items() if v is not None))
    if b.assumptions:
        bits.append("assumed: " + "; ".join(b.assumptions[-3:]))
    return ws.say("consultant", "; ".join(bits) + ".", kind="brief", payload={"brief": b.to_dict()})


def consult(ws: Workspace, model: Model | None, text: str, *, site: dict[str, float] | None = None,
            tables: dict[str, Any] | None = None) -> Message:
    """Take the client's message: the first one opens the brief, later ones answer its questions.

    Returns the Consultant's message (``kind`` ``questions`` while questions are
    open, ``brief`` when the crew may proceed). ``site`` sets the workspace's
    site; ``tables`` are the uploads as DataFrames (their column names go into
    the model's context; the Scout reads the tables themselves).
    """
    ws.say("user", text)
    if site:
        ws.site = {"lat": float(site["lat"]), "lon": float(site["lon"])}
    if not ws.brief.problem:
        return _open(ws, model, text, tables)
    return _answer(ws, model, text)


def classify_follow_up(ws: Workspace, model: Model | None, text: str) -> dict[str, Any]:
    """A follow-up after the report: ``{"kind": "question", "answer"}`` or ``{"kind": "change", "intake",
    "request"}``. Keyless, a change is recognised by an intake the text states (a return period, a
    statistic, a crop) or by change words; anything else is answered from the report."""
    from aquascope.ai_engine.team import intake_hints

    b = ws.brief
    report = ws.report or {}
    if model:
        results = [{"id": r.get("id"), "tool": r.get("tool"), "ok": r.get("ok"), "result": compact(r.get("result"))}
                   for r in (ws.run or {}).get("results") or []]
        obj = model.call_json("consultant", CONSULTANT_FOLLOW_UP, {
            "follow_up": text, "problem": b.problem, "playbook": b.playbook, "intake": dict(b.intake),
            "report": {"answer": report.get("answer"), "key_numbers": report.get("key_numbers"),
                       "not_established": report.get("not_established")},
            "results": results,
        })
        if obj and obj.get("kind") in ("question", "change"):
            if obj["kind"] == "question":
                return {"kind": "question", "answer": str(obj.get("answer") or report.get("answer") or "")}
            intake = obj.get("intake") if isinstance(obj.get("intake"), dict) else {}
            return {"kind": "change", "intake": {k: v for k, v in intake.items() if v is not None},
                    "request": str(obj.get("request") or text)}
    hints = intake_hints(text, b.playbook)
    changed = {k: v for k, v in hints.items() if b.intake.get(k) != v}
    if changed or _CHANGE.search(text):
        return {"kind": "change", "intake": changed, "request": text}
    lines = [report.get("answer") or "The study produced no answer."]
    for kn in (report.get("key_numbers") or [])[:8]:
        lines.append(f"{kn.get('label')}: {kn.get('value')} {kn.get('unit') or ''} (step {kn.get('step')})".strip())
    return {"kind": "question", "answer": "\n".join(lines)}
