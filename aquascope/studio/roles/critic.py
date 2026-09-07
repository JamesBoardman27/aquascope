"""The Critic: an independent pass over the draft report against the results.

Deterministic first: :func:`aquascope.ai_engine.verify.verify` over the
report's answer and sections against the tool results (with the gates' own
words in the pool, as the Solve team does), the failed gates, the steps that
did not run, the plan's notes. Those make the "what this study does not
establish" list. With a model, one more call reads the sections and the
compact results and returns issues with a section, a severity (``fix`` or
``note``) and the fix; the Author is called again once when anything is a
``fix``.
"""

from __future__ import annotations

from typing import Any

from aquascope.studio.model import Model, compact
from aquascope.studio.prompts import CRITIC
from aquascope.studio.workspace import Workspace

__all__ = ["critique", "not_established", "tool_results"]


def tool_results(ws: Workspace) -> list[dict[str, Any]]:
    """The run's results in the shape ``verify`` reads, fallbacks included, plus the gates pool."""
    seen: list[dict[str, Any]] = []
    run = ws.run or {}
    for r in run.get("results") or []:
        if r.get("skipped"):
            continue
        seen.append({"name": r.get("tool"), "arguments": r.get("arguments") or {}, "payload": r.get("result"),
                     "ok": bool(r.get("ok"))})
        fb = r.get("fallback")
        if isinstance(fb, dict) and fb.get("tool"):
            seen.append({"name": fb["tool"], "arguments": fb.get("arguments") or {}, "payload": fb.get("result"),
                         "ok": bool(fb.get("ok"))})
    gates = [g for r in (run.get("results") or []) for g in (r.get("gates") or [])]
    all_gates = run.get("gates") or gates
    pool = {"gates": gates, "plan": (ws.study or {}).get("plan") or {},
            # the counts the Author writes ("3 steps ran, 7 of 7 gates passed") are results too
            "n_steps": len(run.get("results") or []), "n_gates": len(all_gates),
            "n_passed": sum(1 for g in all_gates if g.get("passed")),
            "n_failed": sum(1 for g in all_gates if not g.get("passed")),
            "n_not_established": len(not_established(ws)), "n_replans": run.get("replans") or 0}
    seen.append({"name": "gates", "arguments": {}, "payload": pool, "ok": True})
    datasets = [d.to_dict() for d in ws.inventory.datasets] if ws.inventory else []
    stations = [d for d in datasets if d.get("kind") == "station"]
    short = [d for d in stations if (d.get("years") or 0) < 1]
    seen.append({"name": "inventory", "arguments": {}, "ok": True, "payload": {
        "datasets": datasets, "n_datasets": len(datasets), "n_stations": len(stations),
        "n_short": len(short), "n_listed": len(datasets) - len(short)}})
    return seen


def not_established(ws: Workspace) -> list[str]:
    """What the run did not establish, from the gates, the failed steps, the stop and the plan's notes."""
    out: list[str] = []
    run = ws.run or {}
    for g in run.get("failed_gates") or []:
        out.append(f"Step {g.get('step')}, gate {g.get('check')}: {g.get('detail')}")
    for r in run.get("results") or []:
        if not r.get("ok"):
            out.append(f"Step {r.get('id')} ({r.get('tool')}) did not run: {r.get('error')}")
    if run.get("stop_reason"):
        out.append(f"The study stopped at {run.get('stopped_at')}: {run['stop_reason']}")
    for n in ((ws.study or {}).get("plan") or {}).get("notes") or []:
        out.append(str(n))
    return out


def _draft(ws: Workspace) -> str:
    report = ws.report or {}
    parts = [str(report.get("answer") or "")]
    for s in report.get("sections") or []:
        if s.get("id") in ("appendix", "references"):
            continue
        parts.append(str(s.get("text") or ""))
    return "\n\n".join(p for p in parts if p)


def critique(ws: Workspace, model: Model | None) -> dict[str, Any]:
    """Write ``ws.critique`` (``checks``, ``issues``, ``not_established``) from the draft in ``ws.report``."""
    from aquascope.ai_engine.verify import verify

    draft = _draft(ws)
    results = tool_results(ws)
    checks = verify(draft, results, question=ws.brief.problem)
    missing = not_established(ws)
    for c in checks.failed:
        missing.append(c.detail or c.name)
    issues: list[dict[str, Any]] = []
    if model:
        report = ws.report or {}
        obj = model.call_json("critic", CRITIC, {
            "problem": ws.brief.problem, "answer": report.get("answer"),
            "sections": [{"id": s.get("id"), "title": s.get("title"), "text": s.get("text")}
                         for s in report.get("sections") or [] if s.get("id") not in ("appendix", "references")],
            "key_numbers": report.get("key_numbers"),
            "results": [{"id": r.get("id"), "tool": r.get("tool"), "ok": r.get("ok"), "error": r.get("error"),
                         "gates": r.get("gates"), "result": compact(r.get("result"))}
                        for r in (ws.run or {}).get("results") or []],
            "not_established": missing,
            "checks": [c.to_dict() for c in checks.failed],
        })
        for raw in (obj or {}).get("issues") or []:
            if not isinstance(raw, dict) or not raw.get("text"):
                continue
            severity = "fix" if str(raw.get("severity") or "").lower() == "fix" else "note"
            issues.append({"section": str(raw.get("section") or "summary"), "severity": severity,
                           "text": str(raw["text"]), "fix": str(raw.get("fix") or "")})
    ws.critique = {"ok": checks.ok and not any(i["severity"] == "fix" for i in issues),
                   "checks": checks.to_dict()["checks"], "issues": issues, "not_established": missing}
    ws.event("critic", "checks", f"{len(checks.checks) - len(checks.failed)} of {len(checks.checks)} checks passed"
             + (f"; {len(issues)} issue(s) from the model" if issues else ""))
    return ws.critique
