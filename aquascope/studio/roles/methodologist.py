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

__all__ = ["change", "plan", "plan_text", "revise", "sufficiency_for_validation", "wants_upload"]

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_]+)\.")
_STEP_IN_ERROR = re.compile(r"^(?:fallback of )?step ([^:]+):")
_UPLOAD_WORDS = re.compile(
    r"\b(my|own|this|these|attached|uploaded)\s+(?:\w+\s+){0,2}(record|data|file|table|upload|series|csv)\b|"
    r"\b(upload|csv)\b", re.I,
)
MIN_STEPS, MAX_STEPS = 1, 12
#: Steps that frame a study but are not an analysis on their own.
_FRAMING_TOOLS = frozenset({"describe_catchment", "find_stations", "assess_site", "load_table", "eda", "quality"})
#: The workbench step per problem kind over an attached table (F): tool, method, the key its gate checks.
_UPLOAD_STEPS: dict[str, list[tuple[str, str | None, str]]] = {
    "flood_risk": [("return_periods", "at_site_flood_frequency", "return_levels"),
                   ("flow_duration", "flow_duration", "percentiles")],
    "supply_reliability": [("flow_duration", "flow_duration", "percentiles"), ("signatures", None, "signatures"),
                           ("baseflow", "baseflow_separation", "bfi")],
    "ungauged_flow": [("flow_duration", "flow_duration", "percentiles"), ("signatures", None, "signatures"),
                      ("baseflow", "baseflow_separation", "bfi")],
    "groundwater_decline": [("sgi_drought", "sgi", "current"), ("recharge", "recharge_wtf", "value_mm_per_year")],
    "water_quality": [("who_screen", None, "rows"), ("wqi", "water_quality_index", "ccme")],
}
_GENERIC_UPLOAD_STEPS: list[tuple[str, str | None, str]] = [("eda", None, "n_records"), ("quality", None, "n_records"),
                                                          ("signatures", None, "signatures")]


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


def _uploads(ws: Workspace) -> list[Any]:
    inv = ws.inventory
    return [d for d in (inv.uploads() if inv else []) if (d.quality or {}).get("verdict") != "unreadable"]


def sufficiency_for_validation(ws: Workspace) -> list[dict[str, Any]] | None:
    """The registry's verdicts the validator judges a ``method`` against: the site's table, and for a method whose
    variable an attached table carries, the better of the site's verdict and the table's own record."""
    from aquascope.methods import METHODS, SiteContext, assess_method

    inv = ws.inventory
    if inv is None:
        return None
    rows = {r.get("method"): dict(r) for r in inv.sufficiency if isinstance(r, dict)}
    order = {"defensible": 0, "marginal": 1, "not_defensible": 2, "not defensible": 2}
    rp = ws.brief.intake.get("return_period")
    for d in _uploads(ws):
        if not d.variable or not d.years:
            continue
        ctx = SiteContext(years_by_variable={d.variable: float(d.years)},
                          resolution_by_variable={d.variable: "monthly" if d.resolution == "monthly" else "daily"},
                          return_period=float(rp) if isinstance(rp, (int, float)) else None)
        for m in METHODS.values():
            if m.variable != d.variable:
                continue
            verdict = assess_method(m, ctx)
            verdict["station"] = {"source": "upload", "station_id": d.id}
            old = rows.get(m.id)
            if old is None or order.get(str(verdict["status"]), 2) < order.get(str(old.get("status")), 2):
                rows[m.id] = verdict
    return list(rows.values())


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


def _fix_methods(steps: list[dict[str, Any]], kind: str | None) -> list[str]:
    """A ``method`` the tool does not apply is not fatal: it becomes the entry's first method that serves the
    problem, or goes; one note per change (A)."""
    from aquascope.methods import METHODS

    notes: list[str] = []
    for step in steps:
        method = step.get("method")
        if not method:
            continue
        entry = catalogue.get(str(step.get("tool") or ""))
        if entry is None:
            continue
        fits = method in METHODS and (not entry.methods or method in entry.methods)
        if fits:
            continue
        replacement = next((m for m in entry.methods if m in METHODS and (not kind or kind in METHODS[m].problems)),
                           None)
        if replacement:
            step["method"] = replacement
            notes.append(f"step {step.get('id')}: method {method!r} is not one {entry.id} applies; "
                         f"{replacement!r} stands in")
        else:
            step.pop("method", None)
            notes.append(f"step {step.get('id')}: method {method!r} is not one {entry.id} applies; dropped")
    return notes


def _errors_of(steps: list[dict[str, Any]], ws: Workspace) -> list[str]:
    errors = catalogue.validate_plan(steps, sufficiency=sufficiency_for_validation(ws))
    for st in steps:
        errors += _placeholder_errors(st)
    return errors


def _check(obj: dict[str, Any] | None, ws: Workspace) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """The steps, the validator's errors and the notes (methods repaired) for a model's plan object."""
    obj = _unwrap(obj)
    if not obj:
        return [], ["the model returned no plan"], []
    steps = _normalise(obj.get("steps"))
    if not steps:
        return [], ["the plan has no steps"], []
    if len(steps) > MAX_STEPS:
        return steps, [f"the plan has {len(steps)} steps; at most {MAX_STEPS}"], []
    notes = _fix_methods(steps, ws.brief.kind)
    return steps, _errors_of(steps, ws), notes


def _has_analysis(steps: list[dict[str, Any]]) -> bool:
    return any(str(st.get("tool")) not in _FRAMING_TOOLS for st in steps)


def _prune(steps: list[dict[str, Any]], ws: Workspace) -> tuple[list[dict[str, Any]], list[str]]:
    """The plan minus the steps the validator names (and the steps that then lose what they depend on),
    until what remains validates. Returns the kept steps and one note per removed step."""
    kept = [dict(st) for st in steps]
    notes: list[str] = []
    for _ in range(len(steps) + 1):
        errors = _errors_of(kept, ws)
        if not errors:
            break
        bad: dict[str, str] = {}
        for e in errors:
            m = _STEP_IN_ERROR.match(e)
            if m:
                bad.setdefault(m.group(1), e)
        if not bad:
            return [], notes + errors
        notes += [f"step {sid} removed: {reason}" for sid, reason in bad.items()]
        kept = [st for st in kept if str(st.get("id")) not in bad]
    return kept, notes


def _study_from(ws: Workspace, obj: dict[str, Any], steps: list[dict[str, Any]], *,
                base: Study | None = None, notes: list[str] | None = None) -> Study:
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
    if notes:
        plan_block["notes"] = list(dict.fromkeys([*(plan_block.get("notes") or []), *notes]))
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


def _uploads_compact(ws: Workspace) -> list[dict[str, Any]]:
    out = []
    for d in _uploads(ws):
        q = d.quality or {}
        out.append({"id": d.id, "variable": d.variable, "unit": q.get("unit"), "years": d.years, "n": d.n,
                    "resolution": d.resolution, "columns": (q.get("columns") or [])[:12], "quality": q.get("verdict")})
    return out


def _model_plan(ws: Workspace, model: Model) -> tuple[Study | None, list[str]]:
    from aquascope import playbooks as pbk
    from aquascope.gates import CHECKS

    exemplar: dict[str, Any] | None = None
    try:
        tree = _upload_tree(ws) if wants_upload(ws) else _tree(ws)
        exemplar = {"playbook": tree.plan.get("playbook"), "branch": tree.plan.get("branch"),
                    "rationale": tree.plan.get("rationale"),
                    "steps": [st.to_dict() for st in tree.steps], "caveats": tree.plan.get("caveats")}
    except pbk.Declined as exc:
        exemplar = {"playbook": ws.brief.playbook, "declined": exc.reason}
    except pbk.PlaybookError:
        exemplar = None
    uploads = _uploads_compact(ws)
    context = {
        "uploads": uploads or None,
        "brief": _brief_compact(ws),
        "inventory": _inventory_compact(ws),
        "catalogue": _catalogue_for(ws.brief.kind, uploads=bool(uploads)),
        "gates": CHECKS,
        "exemplar": exemplar,
    }
    obj = model.call_json("methodologist", METHODOLOGIST, context)
    steps, errors, notes = _check(obj, ws)
    if errors and obj is not None:
        ws.event("methodologist", "invalid", "; ".join(errors[:6]))
        repaired = _unwrap(model.call_json("methodologist", METHODOLOGIST_REPAIR, {
            "plan": obj, "errors": errors, "catalogue": context["catalogue"], "gates": list(CHECKS),
            "inventory": context["inventory"], "uploads": uploads or None,
        }))
        steps2, errors2, notes2 = _check(repaired, ws)
        if repaired is not None and steps2 and not errors2:
            obj, steps, errors, notes = repaired, steps2, [], notes + notes2
            ws.event("methodologist", "repaired", f"{len(steps)} steps pass the validator")
        else:
            kept, pruned = _prune(steps, ws)
            if kept and _has_analysis(kept):
                ws.event("methodologist", "pruned", f"{len(steps) - len(kept)} invalid step(s) removed, "
                         f"{len(kept)} kept: " + "; ".join(pruned[:4]))
                steps, errors, notes = kept, [], notes + pruned
            else:
                errors = errors2 if repaired is not None and errors2 else errors
    if errors:
        return None, errors
    return _study_from(ws, obj or {}, steps, notes=notes), []


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
            study = _upload_tree(ws) if wants_upload(ws) else _tree(ws)
        except pbk.Declined as exc:
            _decline(ws, exc.reason)
            return None
    else:
        _decline(ws, f"No playbook covers this problem; say which of {', '.join(known)} it is, or add a model.")
        return None
    _announce(ws, study)
    return study


def wants_upload(ws: Workspace) -> bool:
    """Plan on an attached table when the text points at it (my/own/this record, data, file, table, upload, csv)
    or when no gauge within reach carries the variable the playbook needs."""
    uploads = _uploads(ws)
    if not uploads:
        return False
    if _UPLOAD_WORDS.search(ws.brief.problem or ""):
        return True
    pb = _playbook(ws)
    if pb is None or not pb.variable:
        return False
    return pb.variable not in (ws.inventory.years_by_variable if ws.inventory else {})


def _upload_tree(ws: Workspace) -> Study:
    """The keyless plan over an attached table: load_table, then the workbench steps for the problem kind, each
    with a gate on its result key, the registry consulted on every method. Raises ``Declined`` when nothing
    defensible remains."""
    from aquascope import playbooks as pbk
    from aquascope.methods import METHODS, SiteContext, assess_method

    pb = _playbook(ws)
    if pb is None:
        raise pbk.Declined("no playbook applies", kind="no_playbook")
    uploads = _uploads(ws)
    upload = next((d for d in uploads if d.variable == pb.variable), None) or \
        next((d for d in uploads if d.variable), None) or uploads[0]
    intake = pbk.fill_intake(pb, dict(ws.brief.intake))
    ws.brief.intake = dict(intake)
    site = dict(ws.site or {})
    rp = intake.get("return_period")
    years = float(upload.years or 0.0)
    ctx = SiteContext(years_by_variable={upload.variable: years} if upload.variable else {},
                      resolution_by_variable={upload.variable: "monthly" if upload.resolution == "monthly"
                                              else "daily"} if upload.variable else {},
                      return_period=float(rp) if isinstance(rp, (int, float)) else None)
    steps: list[Step] = [Step(
        tool=catalogue.LOAD_TABLE, id="s1", arguments={"table": upload.id},
        rationale=f"The attached table {upload.id} ({upload.variable or 'rows'}"
                  + (f", {years:g} years" if years else "") + ") is the record this study is about.",
        expects=[{"check": "not_empty", "path": "n"}]
                + ([{"check": "min_years", "value": 1, "path": "years"}] if upload.variable else []),
    )]
    notes: list[str] = []
    recipe = list(_UPLOAD_STEPS.get(pb.id) or [])
    if pb.id == "drought_status":
        # workbench.spei needs a temperature or PET column and a from_step frame carries the value column only:
        # the table is profiled and the indices come from the ERA5 cell.
        recipe = [("eda", None, "n_records"), ("quality", None, "n_records")]
        notes.append("SPI and SPEI over an attached table need a temperature series the table loader does not "
                     "carry; the indices are computed for the ERA5 cell instead.")
    if not upload.variable and pb.id != "water_quality":
        recipe = [("eda", None, "n_records"), ("quality", None, "n_records")]
    if not recipe:
        recipe = _GENERIC_UPLOAD_STEPS
    n = 1
    for tool, method, key in recipe:
        if method and method in METHODS and upload.variable:
            verdict = assess_method(METHODS[method], ctx)
            if verdict.get("status") == "not_defensible":
                notes.append(f"step {tool} dropped: {method} is not defensible on the table: {verdict.get('reason')}")
                continue
            if verdict.get("status") == "marginal":
                notes.append(f"{METHODS[method].label} is marginal on the table: {verdict.get('reason')}")
        n += 1
        args: dict[str, Any] = {"from_step": "s1"}
        if tool == "return_periods":
            periods = sorted({2, 5, 10, 25, 50, 100, *([int(rp)] if isinstance(rp, (int, float)) else [])})
            args.update({"distribution": "gev", "periods": periods})
        if tool == "wqi":
            args["use"] = str(intake.get("use") or "drinking")
        steps.append(Step(tool=tool, id=f"s{n}", arguments=args, method=method, depends_on=["s1"],
                          rationale=f"{catalogue.get(tool).about if catalogue.get(tool) else tool} on the table.",
                          expects=[{"check": "not_empty", "path": key}]))
        if tool == "return_periods":
            n += 1
            steps.append(Step(tool=tool, id=f"s{n}", arguments={**args, "distribution": "lp3"}, method=method,
                              depends_on=["s1"], rationale="A second distribution (Log-Pearson III) on the same "
                              "maxima, so the spread between fits can be quoted.",
                              expects=[{"check": "not_empty", "path": key}]))
    if pb.id == "drought_status" and site.get("lat") is not None:
        n += 1
        args = {"lat": site["lat"], "lon": site["lon"], "years": 40}
        if intake.get("timescales"):
            args["timescales"] = list(intake["timescales"])
        steps.append(Step(tool="drought_indices", id=f"s{n}", arguments=args, method="spei_reanalysis",
                          rationale="SPI and SPEI for the ERA5 cell, the indices the table cannot yield alone.",
                          expects=[{"check": "not_empty", "path": "indices"}]))
    if not any(st.tool not in _FRAMING_TOOLS for st in steps):
        raise pbk.Declined("The attached table supports no defensible analysis for this problem: "
                           + "; ".join(notes), kind="refused", playbook=pb.id)
    caveats, citations = _caveats_and_citations(ws)
    where = f"{site.get('lat')}, {site.get('lon')}" if site else "the site"
    study = Study(
        question=ws.brief.problem, title=f"{pb.title} on {upload.id}: {where}", steps=steps, author="playbook",
        version=3,
        problem={"kind": pb.problem, "site": site, "params": dict(intake), "text": ws.brief.problem},
        plan={"playbook": pb.id, "branch": "upload", "upload": upload.id,
              "rationale": f"The brief points at the attached table {upload.id}"
                           + (f" ({years:g} years of {upload.variable})" if upload.variable else "")
                           + "; the study runs on it rather than on a gauge within reach.",
              "caveats": caveats, "citations": citations, "notes": notes},
        created=_now(),
    )
    return _promote(ws, study, author="playbook")


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
    errors = _errors_of(steps, ws)
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
        steps, errors, notes = _check(obj, ws)
        if errors and obj is not None:
            ws.event("methodologist", "invalid", "; ".join(errors[:6]))
            repaired = _unwrap(model.call_json("methodologist", METHODOLOGIST_REPAIR, {
                "plan": obj, "errors": errors, "gates": list(CHECKS)}))
            steps2, errors2, notes2 = _check(repaired, ws)
            if repaired is not None and steps2 and not errors2:
                obj, steps, errors, notes = repaired, steps2, [], notes + notes2
            else:
                kept, pruned = _prune(steps, ws)
                if kept and _has_analysis(kept):
                    steps, errors, notes = kept, [], notes + pruned
        if not errors:
            study = _study_from(ws, obj or {}, steps, base=base, notes=notes)
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
            study = _upload_tree(ws) if wants_upload(ws) else _tree(ws)
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
