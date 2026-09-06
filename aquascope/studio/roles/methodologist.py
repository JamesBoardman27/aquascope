"""The Methodologist: the plan, a version-3 study composed for the data at hand.

Keyless, the plan is the playbook tree's (``playbooks.plan``), promoted to
version 3 with an objective, a methodology (one sentence per step) and the
brief's assumptions. With a model, one call composes the steps from the
catalogue, given the brief, the inventory, the sufficiency table, the gate
vocabulary and the tree's own plan as an exemplar; the plan then passes
:func:`aquascope.studio.catalogue.validate_plan` (the tool exists, the
arguments are its own, the gates are known, a method the registry calls not
defensible here is refused). Errors get one repair call; a plan that still
fails falls back to the tree when a playbook applies and is declined
otherwise, with the errors listed. Nothing runs here.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from aquascope.studio import catalogue
from aquascope.studio.model import Model
from aquascope.studio.prompts import METHODOLOGIST, METHODOLOGIST_CHANGE, METHODOLOGIST_REPAIR
from aquascope.studio.workspace import Workspace
from aquascope.study import Step, Study

__all__ = ["change", "plan", "plan_text", "revise"]

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_]+)\.")
MIN_STEPS, MAX_STEPS = 1, 12


# ── helpers ──────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _first_sentence(text: str | None) -> str:
    text = " ".join((text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return m.group(1) if m else text


def _outputs_for(step: Step) -> list[dict[str, Any]]:
    entry = catalogue.get(step.tool)
    if entry is None:
        return []
    sid = step.id or step.tool
    out = [{"kind": "figure", "id": f"{sid}_{f}", "caption": f"{f.replace('_', ' ')} from {step.tool}"}
           for f in entry.figures]
    out += [{"kind": "table", "id": f"{sid}_{t}", "caption": f"{t.replace('_', ' ')} from {step.tool}"}
            for t in entry.tables]
    return out


def _playbook(ws: Workspace) -> Any | None:
    from aquascope import playbooks as pbk

    pid = ws.brief.playbook
    if not pid:
        return None
    try:
        return pbk.load(pid)
    except pbk.PlaybookError:
        return None


def _recon(ws: Workspace) -> dict[str, Any]:
    return dict(ws.inventory.recon) if ws.inventory else {"point": dict(ws.site or {}), "stations": [],
                                                           "context": {"years_by_variable": {}}, "sufficiency": []}


def _promote(ws: Workspace, study: Study, *, author: str) -> Study:
    """Make a study version 3: objective, methodology, assumptions and outputs on every step."""
    b = ws.brief
    study.version = 3
    study.plan = dict(study.plan or {})
    study.plan["author"] = author
    study.plan.setdefault("objective", b.decision or _first_sentence(b.problem))
    study.plan.setdefault("decision", b.decision)
    study.plan.setdefault("methodology", [_first_sentence(s.rationale) or f"{s.tool}" for s in study.steps])
    study.plan.setdefault("assumptions", list(b.assumptions))
    for s in study.steps:
        if not s.outputs:
            s.outputs = _outputs_for(s)
    if b.problem:
        study.question = b.problem
    if study.problem is not None:
        study.problem.setdefault("text", b.problem)
    return study


def _tree(ws: Workspace, *, branch: str | None = None) -> Study:
    """The playbook tree's plan for this site, promoted to version 3. Raises ``playbooks.Declined``."""
    from aquascope import playbooks as pbk

    pb = _playbook(ws)
    if pb is None:
        raise pbk.Declined("no playbook applies", kind="no_playbook")
    study = pbk.plan(pb, _recon(ws), dict(ws.brief.intake), branch=branch, problem_text=ws.brief.problem)
    study = _promote(ws, study, author="playbook")
    ws.brief.intake = dict((study.problem or {}).get("params") or ws.brief.intake)
    return study


def _caveats_and_citations(ws: Workspace) -> tuple[list[str], list[str]]:
    from aquascope import playbooks as pbk

    pb = _playbook(ws)
    if pb is None:
        return [], []
    try:
        ctx = pbk.evaluation_context(pb, _recon(ws), dict(ws.brief.intake))
        return pbk.caveats_for(pb, ctx), list(pb.citations)
    except (pbk.Declined, pbk.PlaybookError):
        return [], list(pb.citations)


def _catalogue_for(problem: str | None, *, uploads: bool) -> list[dict[str, Any]]:
    """The catalogue as the Methodologist reads it: the entries that serve the problem, the generic site and
    station tools, the table tools only when there is a table, ``about`` cut short. Tokens matter."""
    from aquascope.methods import METHODS

    rows: list[dict[str, Any]] = []
    for row in catalogue.compact(problem):
        entry = catalogue.get(row["tool"])
        if entry is None or entry.kind == "recon" or entry.id == "find_stations":
            continue
        if entry.kind in ("frame", "weather", "none") and not uploads:
            continue
        if entry.methods and problem:
            serves = any(problem in METHODS[m].problems for m in entry.methods if m in METHODS)
            if not serves and entry.kind in ("station", "site"):
                continue
        row = dict(row)
        row["about"] = row["about"][:110]
        rows.append(row)
    return rows


def _inventory_compact(ws: Workspace) -> dict[str, Any]:
    inv = ws.inventory
    if inv is None:
        return {}
    keep = ("id", "kind", "variable", "source", "station_id", "name", "distance_km", "years", "resolution", "n")
    datasets = []
    for d in inv.datasets:
        row = {k: v for k, v in d.to_dict().items() if k in keep}
        if d.quality:
            row["quality"] = d.quality.get("verdict")
            if d.quality.get("unit"):
                row["unit"] = d.quality["unit"]
            if d.quality.get("columns"):
                row["columns"] = d.quality["columns"][:12]
        datasets.append(row)
    catchment = inv.catchment or {}
    return {
        "site": inv.site,
        "datasets": datasets,
        "years_by_variable": inv.years_by_variable,
        "catchment": {k: catchment.get(k) for k in ("upstream_area_km2", "area_km2", "dams", "sub_basin")
                      if catchment.get(k) is not None},
        "donors": inv.donors,
        "sufficiency": [{k: r.get(k) for k in ("method", "status", "reason")} for r in inv.sufficiency],
        "notes": inv.notes[:6],
    }


def _brief_compact(ws: Workspace) -> dict[str, Any]:
    b = ws.brief
    return {k: v for k, v in b.to_dict().items()
            if k in ("problem", "decision", "quantities", "period", "horizon", "constraints", "kind", "playbook",
                     "intake", "assumptions") and v not in (None, [], {})}


def _placeholder_errors(step: dict[str, Any]) -> list[str]:
    """Placeholders other than ``{{ result.<id>.<path> }}`` in the arguments, the gates or the fallback."""
    errors: list[str] = []
    sid = step.get("id") or "?"
    stack: list[tuple[str, Any]] = [("arguments", step.get("arguments")), ("expects", step.get("expects")),
                                    ("fallback", step.get("fallback"))]
    while stack:
        where, item = stack.pop()
        if isinstance(item, str):
            for m in _PLACEHOLDER.finditer(item):
                if m.group(1) != "result":
                    errors.append(f"step {sid}: {where} carries the placeholder '{{{{ {m.group(1)}.… }}}}'; write "
                                  "the concrete value from the inventory")
        elif isinstance(item, dict):
            stack.extend((where, v) for v in item.values())
        elif isinstance(item, list):
            stack.extend((where, v) for v in item)
    return errors


def _normalise(steps: Any) -> list[dict[str, Any]]:
    """Steps as the runner reads them: ids, mappings and lists where the shape demands them."""
    out: list[dict[str, Any]] = []
    if not isinstance(steps, list):
        return out
    for i, raw in enumerate(steps, 1):
        if not isinstance(raw, dict):
            continue
        step: dict[str, Any] = {
            "id": str(raw.get("id") or f"s{i}"),
            "tool": str(raw.get("tool") or ""),
            "arguments": dict(raw["arguments"]) if isinstance(raw.get("arguments"), dict) else {},
            "rationale": str(raw.get("rationale") or ""),
            "expects": [g for g in (raw.get("expects") or []) if isinstance(g, dict)],
            "depends_on": [str(d) for d in (raw.get("depends_on") or []) if d],
            "outputs": [o for o in (raw.get("outputs") or []) if isinstance(o, dict) and o.get("id")],
        }
        if raw.get("method"):
            step["method"] = str(raw["method"])
        fb = raw.get("fallback")
        if isinstance(fb, dict) and isinstance(fb.get("step"), dict):
            fstep = fb["step"]
            step["fallback"] = {"step": {"tool": str(fstep.get("tool") or ""),
                                         "arguments": dict(fstep.get("arguments") or {}),
                                         "rationale": str(fstep.get("rationale") or ""),
                                         "expects": [g for g in (fstep.get("expects") or []) if isinstance(g, dict)]}}
        elif fb == "stop":
            step["fallback"] = "stop"
        out.append(step)
    return out


def _unwrap(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    """A repair reply that echoes the context's shape (``{"plan": {...}}``) is the plan inside it."""
    if isinstance(obj, dict) and "steps" not in obj and isinstance(obj.get("plan"), dict):
        return obj["plan"]
    return obj


def _check(obj: dict[str, Any] | None, ws: Workspace) -> tuple[list[dict[str, Any]], list[str]]:
    obj = _unwrap(obj)
    if not obj:
        return [], ["the model returned no plan"]
    steps = _normalise(obj.get("steps"))
    if not steps:
        return [], ["the plan has no steps"]
    if len(steps) > MAX_STEPS:
        return steps, [f"the plan has {len(steps)} steps; at most {MAX_STEPS}"]
    sufficiency = ws.inventory.sufficiency if ws.inventory else None
    errors = catalogue.validate_plan(steps, sufficiency=sufficiency)
    for s in steps:
        errors += _placeholder_errors(s)
    return steps, errors


def _study_from(ws: Workspace, obj: dict[str, Any], steps: list[dict[str, Any]], *,
                base: Study | None = None) -> Study:
    """A version-3 study from the model's plan object (``base`` keeps an earlier plan's block on a change)."""
    b = ws.brief
    site = dict(ws.site or {})
    caveats, citations = _caveats_and_citations(ws)
    model_cites = [str(c) for c in (obj.get("citations") or []) if isinstance(c, str)]
    plan_block: dict[str, Any] = dict(base.plan or {}) if base else {}
    plan_block.update({
        "author": "methodologist",
        "playbook": b.playbook,
        "objective": str(obj.get("objective") or plan_block.get("objective") or b.decision
                         or _first_sentence(b.problem)),
        "decision": str(obj.get("decision") or plan_block.get("decision") or b.decision or ""),
        "methodology": [str(m) for m in (obj.get("methodology") or [])] or [_first_sentence(s["rationale"])
                                                                             for s in steps],
        "assumptions": list(dict.fromkeys([*b.assumptions, *[str(a) for a in (obj.get("assumptions") or [])]])),
        "alternatives": obj.get("alternatives") if isinstance(obj.get("alternatives"), list)
        else plan_block.get("alternatives") or [],
        "limitations_expected": [str(x) for x in (obj.get("limitations_expected") or [])]
        or plan_block.get("limitations_expected") or [],
        "citations": list(dict.fromkeys([*citations, *model_cites])),
        "caveats": caveats,
    })
    plan_block["rationale"] = plan_block["objective"]
    if ws.inventory and ws.inventory.notes:
        plan_block["recon_notes"] = list(ws.inventory.notes[:8])
    where = f"{site.get('lat')}, {site.get('lon')}" if site else "the site"
    study = Study(
        question=b.problem, title=str(obj.get("title") or f"{plan_block['objective'][:60]}: {where}"),
        steps=[Step.from_dict(s) for s in steps], author="methodologist", model=ws.model, version=3,
        problem={k: v for k, v in {"kind": b.kind, "site": site, "params": dict(b.intake), "text": b.problem}.items()
                 if v is not None},
        plan=plan_block, created=_now(),
    )
    for s in study.steps:
        if not s.outputs:
            s.outputs = _outputs_for(s)
    return study


def _model_plan(ws: Workspace, model: Model) -> tuple[Study | None, list[str]]:
    from aquascope import playbooks as pbk
    from aquascope.gates import CHECKS

    exemplar: dict[str, Any] | None = None
    try:
        tree = _tree(ws)
        exemplar = {"playbook": tree.plan.get("playbook"), "branch": tree.plan.get("branch"),
                    "rationale": tree.plan.get("rationale"),
                    "steps": [s.to_dict() for s in tree.steps], "caveats": tree.plan.get("caveats")}
    except pbk.Declined as exc:
        exemplar = {"playbook": ws.brief.playbook, "declined": exc.reason}
    except pbk.PlaybookError:
        exemplar = None
    uploads = bool(ws.inventory and ws.inventory.uploads())
    context = {
        "brief": _brief_compact(ws),
        "inventory": _inventory_compact(ws),
        "catalogue": _catalogue_for(ws.brief.kind, uploads=uploads),
        "gates": CHECKS,
        "exemplar": exemplar,
    }
    obj = model.call_json("methodologist", METHODOLOGIST, context)
    steps, errors = _check(obj, ws)
    if errors and obj is not None:
        ws.event("methodologist", "invalid", "; ".join(errors[:6]))
        repaired = model.call_json("methodologist", METHODOLOGIST_REPAIR, {
            "plan": obj, "errors": errors, "catalogue": context["catalogue"], "gates": list(CHECKS),
            "inventory": context["inventory"],
        })
        repaired = _unwrap(repaired)
        steps2, errors2 = _check(repaired, ws)
        if repaired is not None and not errors2:
            obj, steps, errors = repaired, steps2, []
            ws.event("methodologist", "repaired", f"{len(steps)} steps pass the validator")
        else:
            errors = errors2 if repaired is not None else errors
    if errors:
        return None, errors
    return _study_from(ws, obj or {}, steps), []


def _decline(ws: Workspace, reason: str) -> None:
    ws.declined_reason = reason
    ws.set_status("declined")
    ws.event("methodologist", "declined", reason)
    ws.say("methodologist", f"Declined: {reason}", kind="declined", payload={"reason": reason})


def _announce(ws: Workspace, study: Study) -> None:
    ws.set_study(study)
    text = plan_text(ws.study)
    plan = study.plan or {}
    ws.event("methodologist", "plan", f"{plan.get('author')}: {len(study.steps)} step(s)"
             + (f", playbook {plan.get('playbook')}" if plan.get("playbook") else "")
             + (f", branch {plan.get('branch')}" if plan.get("branch") else ""))
    ws.say("methodologist", text, kind="plan", payload={"study": ws.study})


# ── the public functions ─────────────────────────────────────────────────────


def plan(ws: Workspace, model: Model | None) -> Study | None:
    """Write the plan into ``ws.study`` and announce it; on a decline set the status and return None."""
    from aquascope import playbooks as pbk

    known = sorted(p["id"] for p in pbk.list_playbooks() if "error" not in p)
    study: Study | None = None
    if model:
        study, errors = _model_plan(ws, model)
        if study is None:
            if ws.brief.playbook:
                ws.event("methodologist", "fallback", "the model's plan did not pass the validator, the tree is used: "
                         + "; ".join(errors[:4]))
                try:
                    study = _tree(ws)
                    study.plan["model_plan_rejected"] = errors[:8]
                except pbk.Declined as exc:
                    _decline(ws, exc.reason)
                    return None
            else:
                _decline(ws, "The model's plan did not pass the validator and no playbook covers this problem: "
                         + "; ".join(errors[:6]))
                return None
    elif ws.brief.playbook:
        try:
            study = _tree(ws)
        except pbk.Declined as exc:
            _decline(ws, exc.reason)
            return None
    else:
        _decline(ws, f"No playbook covers this problem; say which of {', '.join(known)} it is, or add a model.")
        return None
    _announce(ws, study)
    return study


def revise(ws: Workspace, model: Model | None, edits: dict[str, Any] | list[dict[str, Any]]) -> Study:
    """Apply the user's edits to the plan and validate it again.

    ``edits`` is either a replacement list of steps, ``{"steps": [...]}``, or a
    mapping of step id to overrides (``{"s3": {"arguments": {"k": 8}, "expects": [...]}}``;
    ``{"s2": None}`` drops a step). Raises ``ValueError`` with the validator's
    errors when the edited plan is not acceptable; the plan is left unchanged then.
    """
    if not ws.study:
        raise ValueError("there is no plan to edit")
    steps = [dict(s) for s in ws.study.get("steps") or []]
    if isinstance(edits, list):
        steps = _normalise(edits)
    elif isinstance(edits, dict) and isinstance(edits.get("steps"), list):
        steps = _normalise(edits["steps"])
    elif isinstance(edits, dict):
        kept: list[dict[str, Any]] = []
        for s in steps:
            sid = str(s.get("id"))
            if sid not in edits:
                kept.append(s)
                continue
            override = edits[sid]
            if override is None:
                continue
            if not isinstance(override, dict):
                raise ValueError(f"the edit for step {sid} must be a mapping or null")
            s = dict(s)
            if isinstance(override.get("arguments"), dict):
                s["arguments"] = {**(s.get("arguments") or {}), **_split_overrides(s, override["arguments"])}
            for key in ("expects", "depends_on", "outputs"):
                if isinstance(override.get(key), list):
                    s[key] = override[key]
            for key in ("rationale", "method", "tool"):
                if override.get(key) is not None:
                    s[key] = override[key]
            if "fallback" in override:
                s["fallback"] = override["fallback"]
            kept.append(s)
        steps = _normalise(kept)
    sufficiency = ws.inventory.sufficiency if ws.inventory else None
    errors = catalogue.validate_plan(steps, sufficiency=sufficiency)
    for s in steps:
        errors += _placeholder_errors(s)
    if not steps:
        errors.append("the edited plan has no steps")
    if errors:
        ws.event("methodologist", "invalid", "edit refused: " + "; ".join(errors[:6]))
        raise ValueError("; ".join(errors))
    study = Study.from_dict(ws.study)
    study.steps = [Step.from_dict(s) for s in steps]
    study.plan = dict(study.plan or {})
    study.plan["edited"] = True
    study.plan["methodology"] = [_first_sentence(s.rationale) or s.tool for s in study.steps]
    study.results = {}
    for s in study.steps:
        if not s.outputs:
            s.outputs = _outputs_for(s)
    ws.set_study(study)
    ws.event("methodologist", "edited", f"{len(study.steps)} step(s) after the user's edits")
    ws.say("methodologist", plan_text(ws.study), kind="plan", payload={"study": ws.study})
    return study


def _split_overrides(step: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """An override that is not one of the tool's arguments but a key of one of the step's gates (``return_period``)
    lands on those gates; the rest are arguments, which the validator then judges."""
    entry = catalogue.get(str(step.get("tool") or ""))
    args: dict[str, Any] = {}
    for key, value in overrides.items():
        gates = [g for g in (step.get("expects") or []) if isinstance(g, dict) and key in g]
        if entry is not None and key not in entry.arguments and gates:
            step["expects"] = [dict(g, **{key: value}) if key in g else g for g in step["expects"]]
            continue
        args[key] = value
    return args


def change(ws: Workspace, model: Model | None, request: str, *, intake: dict[str, Any] | None = None) -> Study | None:
    """A change after the report: with a model, steps added or replaced for the request; keyless, the tree
    planned again with the changed intake. Returns the new study (announced) or None with the reason logged."""
    from aquascope import playbooks as pbk

    if intake:
        ws.brief.intake.update(intake)
        ws.event("methodologist", "intake", "changed: " + ", ".join(f"{k}={v}" for k, v in intake.items()))
    base = ws.study_obj()
    study: Study | None = None
    if model and base is not None:
        from aquascope.gates import CHECKS

        results = {r.get("id"): {"ok": r.get("ok"),
                                 "gates": [f"{g.get('check')}: {'ok' if g.get('passed') else 'failed'}"
                                           for g in (r.get("gates") or [])]}
                   for r in (ws.run or {}).get("results") or []}
        uploads = bool(ws.inventory and ws.inventory.uploads())
        obj = model.call_json("methodologist", METHODOLOGIST_CHANGE, {
            "request": request, "brief": _brief_compact(ws),
            "steps": [{**s.to_dict(), "outcome": results.get(s.id)} for s in base.steps],
            "inventory": _inventory_compact(ws),
            "catalogue": _catalogue_for(ws.brief.kind, uploads=uploads), "gates": CHECKS,
        })
        steps, errors = _check(obj, ws)
        if errors and obj is not None:
            ws.event("methodologist", "invalid", "; ".join(errors[:6]))
            repaired = _unwrap(model.call_json("methodologist", METHODOLOGIST_REPAIR, {
                "plan": obj, "errors": errors, "gates": list(CHECKS)}))
            steps2, errors2 = _check(repaired, ws)
            if repaired is not None and not errors2:
                obj, steps, errors = repaired, steps2, []
        if not errors:
            study = _study_from(ws, obj or {}, steps, base=base)
            study.plan["changed_for"] = request
            if isinstance((obj or {}).get("methodology"), list):
                study.plan["methodology"] = [str(m) for m in obj["methodology"]]
        else:
            ws.event("methodologist", "fallback", "the change did not pass the validator: " + "; ".join(errors[:4]))
    if study is None:
        if not ws.brief.playbook:
            ws.event("methodologist", "declined", "no playbook to plan the change from and no valid model plan")
            return None
        try:
            study = _tree(ws)
            study.plan["changed_for"] = request
        except pbk.Declined as exc:
            ws.event("methodologist", "declined", exc.reason)
            return None
    _announce(ws, study)
    return study


def plan_text(study: dict[str, Any] | None) -> str:
    """The plan as a numbered checklist: objective, then each step with tool, arguments, method, gates and
    rationale, then the caveats count. What the CLI prints and a face can show."""
    if not study:
        return "No plan."
    plan = study.get("plan") or {}
    steps = study.get("steps") or []
    head = f"Plan ({plan.get('author') or study.get('author')}"
    if plan.get("playbook"):
        head += f", playbook {plan['playbook']}"
    if plan.get("branch"):
        head += f", branch {plan['branch']}"
    lines = [f"{head}, {len(steps)} step(s))"]
    if plan.get("objective"):
        lines.append(f"  Objective: {plan['objective']}")
    for n in (plan.get("notes") or []):
        lines.append(f"  note: {n}")
    for i, s in enumerate(steps, 1):
        args = ", ".join(f"{k}={v!r}" for k, v in (s.get("arguments") or {}).items())
        lines.append(f"  {i}. [{s.get('id')}] {s.get('tool')}({args})"
                     + (f"  method {s['method']}" if s.get("method") else ""))
        if s.get("rationale"):
            lines.append(f"     {s['rationale']}")
        for g in s.get("expects") or []:
            where = g.get("path") or ", ".join(g.get("paths") or [])
            value = f" {g['value']}" if g.get("value") is not None else ""
            lines.append(f"     gate {g.get('check')}{value} on {where}")
        fb = s.get("fallback")
        if isinstance(fb, dict) and isinstance(fb.get("step"), dict):
            lines.append(f"     fallback: {fb['step'].get('tool')}")
        elif isinstance(fb, dict) and fb.get("branch"):
            lines.append(f"     fallback: replan on branch {fb['branch']}")
    for a in (plan.get("assumptions") or [])[:5]:
        lines.append(f"  assumes: {a}")
    if plan.get("caveats"):
        lines.append(f"  {len(plan['caveats'])} caveat(s) will be printed verbatim in the report.")
    lines.append("  Edit a step with 's3.return_period=200' style overrides, or approve to run.")
    return "\n".join(lines)
