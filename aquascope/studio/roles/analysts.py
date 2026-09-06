"""The Analysts: run the plan with its gates, draw the figures as results land, replan once.

The runner is :func:`aquascope.study.run_study`, unchanged: every step in
order, its gates after it, a fallback once, a stop with the reason. What
this module adds is the table loader for the client's uploads
(``load_table``), the figure and table makers called after every step result
(when the deliverables package is importable; skipped with an event
otherwise), and the bounded replan of the Solve team: a branch replan
through the playbook when the plan asks for one, else a Specialist's
proposal from the model, validated against the catalogue before it runs.

The steps run sequentially. ``run_study`` owns the dependency order, the
result references (``{{ result.s2.x }}``) and the stop-on-gate semantics; a
parallel pass over independent steps would have to reimplement those, and
the network fetch behind each step is what takes the time, not Python. So
no thread pool here, in Pyodide or out of it.
"""

from __future__ import annotations

import functools
import io
from datetime import datetime, timezone
from typing import Any

from aquascope.studio import catalogue
from aquascope.studio.model import Model, compact
from aquascope.studio.prompts import SPECIALIST
from aquascope.studio.workspace import Artifact, Workspace
from aquascope.study import Study, StudyRun, run_study

__all__ = ["load_table", "prior_run", "run"]


# ── the table loader ────────────────────────────────────────────────────────


def load_table(ws: Workspace, table: str, value_column: str | None = None,
               datetime_column: str | None = None) -> dict[str, Any]:
    """A client's upload as a step payload: ``{"series": {"t", "v"}, "n", "years", "unit", "columns", ...}`` for a
    datetime/value table, ``{"samples": [rows], "n", "columns"}`` for anything else."""
    import pandas as pd

    from aquascope import ingest

    csv = ws.tables.get(table)
    if csv is None:
        alt = next((k for k in ws.tables if k.endswith(table) or table.endswith(k)), None)
        if alt is None:
            return {"error": f"no table {table!r} in the workspace; the uploads are {sorted(ws.tables) or 'none'}"}
        table, csv = alt, ws.tables[alt]
    df = pd.read_csv(io.StringIO(csv), dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    columns = list(df.columns)
    out: dict[str, Any] = {"table": table, "columns": columns, "source": "upload", "station_id": table,
                           "name": table, "unit": None}
    try:
        mapping = ingest.guess_mapping(df)
        if value_column:
            if value_column not in df.columns:
                return {"error": f"no column {value_column!r} in {table}; the columns are {columns}", **out}
            mapping.value_column = value_column
        if datetime_column:
            if datetime_column not in df.columns:
                return {"error": f"no column {datetime_column!r} in {table}; the columns are {columns}", **out}
            mapping.datetime_column = datetime_column
        raw = ingest.apply_mapping(df, mapping)
        series, qa = ingest.qa_series(raw, n_rows_in=len(df))
    except (ValueError, TypeError, KeyError) as exc:
        rows = [{k: (None if v != v else v) for k, v in r.items()} for r in df.to_dict("records")]
        out.update({"n": len(rows), "samples": rows, "note": f"not a datetime/value series ({exc}); the rows are "
                                                             "passed as samples"})
        return out
    out.update({
        "variable": mapping.variable, "unit": mapping.unit or None, "n": int(qa.n_values),
        "years": round(qa.n_days_span / 365.25, 2) if qa.n_days_span else 0.0,
        "start": qa.start, "end": qa.end,
        "series": {"t": [t.isoformat() for t in series.index], "v": [float(v) for v in series.values]},
        "stats": {"mean": float(series.mean()), "min": float(series.min()), "max": float(series.max())} if len(series)
        else {},
        "qa": qa.to_dict(), "mapping": mapping.to_dict(),
    })
    return out


# ── figures and tables per step ─────────────────────────────────────────────


def _as_artifact(item: Any) -> Artifact | None:
    if isinstance(item, Artifact):
        return item
    if isinstance(item, dict) and item.get("id"):
        return Artifact.from_dict(item)
    return None


def _draw(ws: Workspace, run: StudyRun, drawn: set[str], on_artifact: Any) -> None:
    """Call the deliverables' makers on every result not drawn yet; an event when they cannot be."""
    try:
        from aquascope.studio.deliverables.figures import figures_for
        from aquascope.studio.deliverables.tables import tables_for
    except ImportError as exc:
        if "deliverables" not in drawn:
            drawn.add("deliverables")
            ws.event("analyst", "figures_skipped", f"deliverables not importable: {exc}")
        return
    for r in run.results:
        entries = [(r.get("id"), r)]
        fb = r.get("fallback")
        if isinstance(fb, dict) and fb.get("tool"):
            entries.append((f"{r.get('id')}.fallback", fb))
        for sid, rec in entries:
            if not sid or sid in drawn or not rec.get("ok") or not isinstance(rec.get("result"), dict):
                continue
            drawn.add(sid)
            payload = rec["result"]
            made: list[Any] = []
            try:
                made += list(figures_for(sid, rec.get("tool"), payload, unit=payload.get("unit"), site=ws.site) or [])
            except Exception as exc:  # noqa: BLE001 - a figure that cannot be drawn is a note, not a stop
                ws.event("analyst", "figures_skipped", f"{type(exc).__name__}: {exc}", step=sid)
            try:
                made += list(tables_for(sid, rec.get("tool"), payload) or [])
            except Exception as exc:  # noqa: BLE001
                ws.event("analyst", "figures_skipped", f"tables: {type(exc).__name__}: {exc}", step=sid)
            n = 0
            for item in made:
                art = _as_artifact(item)
                if art is None:
                    continue
                art.step = art.step or sid
                ws.add_artifact(art)
                n += 1
                if on_artifact:
                    try:
                        on_artifact(art)
                    except Exception:  # noqa: BLE001 - a face's callback must not stop the study
                        pass
            if n:
                ws.event("analyst", "figures", f"{n} artifact(s)", step=sid)


# ── the run ─────────────────────────────────────────────────────────────────


def prior_run(ws: Workspace) -> StudyRun | None:
    """The last run as a StudyRun, so a re-run reuses the steps that passed (same id, tool and arguments)."""
    if not ws.run or not ws.run.get("results"):
        return None
    study = ws.study_obj() or Study(question=ws.brief.problem)
    return StudyRun(study=study, results=[dict(r) for r in ws.run["results"]],
                    started=str(ws.run.get("started") or ""), finished=str(ws.run.get("finished") or ""),
                    ok=bool(ws.run.get("ok")), stopped_at=ws.run.get("stopped_at"),
                    stop_reason=ws.run.get("stop_reason"))


def _reusable(prior: StudyRun | None, study: Study) -> StudyRun | None:
    """The prior run without the results whose step now carries different gates (a new return period changes
    the gate, not the arguments; the runner would otherwise keep the old gate outcome)."""
    if prior is None:
        return None
    keep = []
    for r in prior.results:
        old = prior.study.step_by_id(str(r.get("id")))
        new = study.step_by_id(str(r.get("id")))
        if old is not None and new is not None and old.expects != new.expects:
            continue
        keep.append(r)
    if len(keep) == len(prior.results):
        return prior
    return StudyRun(study=prior.study, results=keep, started=prior.started, finished=prior.finished, ok=prior.ok,
                    stopped_at=prior.stopped_at, stop_reason=prior.stop_reason)


def _carry(old: Study, new: Study) -> Study:
    """A replanned study keeps the version-3 plan block of the one it replaces."""
    from aquascope.studio.roles.methodologist import _outputs_for

    new.version = 3
    new.plan = dict(new.plan or {})
    for key in ("author", "objective", "decision", "methodology", "assumptions", "alternatives",
                "limitations_expected", "citations"):
        if key not in new.plan and (old.plan or {}).get(key) is not None:
            new.plan[key] = old.plan[key]
    new.plan.setdefault("methodology", [s.rationale or s.tool for s in new.steps])
    new.question = old.question
    for s in new.steps:
        if not s.outputs:
            s.outputs = _outputs_for(s)
    return new


def run(ws: Workspace, model: Model | None, *, tools: dict[str, Any] | None = None, on_artifact: Any = None,
        max_replans: int = 1, prior: StudyRun | None = None) -> StudyRun:
    """Run ``ws.study`` with gates, figures and one bounded replan; write ``ws.run`` and the study's results."""
    from aquascope import playbooks as pbk

    study = ws.study_obj()
    if study is None or not study.steps:
        raise ValueError("there is no plan to run")
    text = ws.brief.problem
    intake = dict(ws.brief.intake)
    recon = dict(ws.inventory.recon) if ws.inventory else {}
    plan = study.plan or {}
    known = {p["id"] for p in pbk.list_playbooks() if "error" not in p}
    pb = pbk.load(plan["playbook"]) if plan.get("playbook") in known else None
    kind = plan.get("playbook")

    def say(event: dict[str, Any]) -> None:
        ws.event(str(event.get("role") or "runner"), str(event.get("event") or ""), str(event.get("detail") or ""),
                 step=event.get("step"))

    callables = catalogue.callables({**(tools or {}), catalogue.LOAD_TABLE: functools.partial(load_table, ws)})
    prior = _reusable(prior, study)
    drawn: set[str] = set()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ws.event("analyst", "start", f"{len(study.steps)} step(s)")
    run_ = run_study(study, on_event=say, prior=prior, tools=callables)
    _draw(ws, run_, drawn, on_artifact)
    replans = 0
    attempts = 0
    while run_.stop_reason and attempts < max_replans:
        attempts += 1
        if run_.replan:
            branch = run_.replan["branch"]
            if pb is None:
                ws.event("analyst", "replan_declined", "no playbook to fill the branch from", step=run_.stopped_at)
                break
            try:
                new = pbk.plan(pb, recon, intake, branch=branch, problem_text=text)
            except pbk.Declined as exc:
                ws.event("analyst", "replan_declined", exc.reason, step=run_.stopped_at)
                break
            new = _carry(study, new)
            new.plan["replanned_from"] = {"branch": plan.get("branch"), "step": run_.stopped_at,
                                          "reason": run_.replan.get("reason")}
            ws.event("analyst", "replan", f"branch {branch} after {run_.stop_reason}", step=run_.stopped_at)
            study = new
            replans += 1
            run_ = run_study(study, on_event=say, prior=run_, tools=callables)
            _draw(ws, run_, drawn, on_artifact)
            continue
        if not model:
            break
        failed = next((r for r in run_.results if r.get("id") == run_.stopped_at), None)
        step = study.step_by_id(run_.stopped_at or "")
        if failed is None or step is None:
            break
        from aquascope.ai_engine.team import SPECIALIST_PROMPTS, _recon_summary

        proposal = model.call_json("analyst", f"{SPECIALIST_PROMPTS.get(kind, SPECIALIST_PROMPTS['default'])}\n"
                                   f"{SPECIALIST}", {
            "problem": text, "playbook": kind, "site": ws.site,
            "failed_step": {"id": step.id, "tool": step.tool, "arguments": step.arguments,
                            "rationale": step.rationale},
            "failed_gates": [g for g in failed.get("gates") or [] if not g.get("passed")],
            "result": compact(failed.get("result")),
            "earlier_fallback": compact(failed.get("fallback")) if failed.get("fallback") else None,
            "recon": _recon_summary(recon),
            "tools": [{"tool": e["tool"], "arguments": list(e["arguments"]), "gates": e["gates"]}
                      for e in catalogue.compact(ws.brief.kind)[:20]],
        }, step=step.id)
        if not proposal or not proposal.get("tool"):
            ws.event("analyst", "no_fallback", (proposal or {}).get("rationale")
                     or "the specialist proposed no usable fallback", step=step.id)
            break
        fb_step = {"tool": str(proposal["tool"]), "arguments": dict(proposal.get("arguments") or {}),
                   "rationale": str(proposal.get("rationale") or "proposed by the specialist after the gate failed"),
                   "expects": [g for g in (proposal.get("expects") or []) if isinstance(g, dict)]}
        ids = {s.id for s in study.steps if s.id}
        errors = catalogue.validate_step({"id": f"{step.id}.fallback", **fb_step}, known_ids=ids,
                                         sufficiency=ws.inventory.sufficiency if ws.inventory else None)
        if errors:
            ws.event("analyst", "no_fallback", "the proposal did not pass the validator: " + "; ".join(errors[:3]),
                     step=step.id)
            break
        step.fallback = {"step": fb_step}
        study.plan = dict(study.plan or {})
        study.plan.setdefault("replans", []).append({"step": step.id, "reason": run_.stop_reason, "fallback": fb_step})
        ws.event("analyst", "replan", f"fallback {fb_step['tool']}: {fb_step['rationale']}", step=step.id)
        replans += 1
        run_ = run_study(study, on_event=say, prior=run_, tools=callables)
        _draw(ws, run_, drawn, on_artifact)

    ws.set_study(study)
    ws.run = {
        "ok": bool(run_.ok), "results": [dict(r) for r in run_.results], "gates": run_.gates,
        "failed_gates": run_.failed_gates, "stopped_at": run_.stopped_at, "stop_reason": run_.stop_reason,
        "started": started, "finished": run_.finished or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "replans": replans,
    }
    ws.event("analyst", "gates", f"{len(run_.gates) - len(run_.failed_gates)} of {len(run_.gates)} gates passed"
             + (f"; stopped at {run_.stopped_at}" if run_.stop_reason else ""))
    return run_
