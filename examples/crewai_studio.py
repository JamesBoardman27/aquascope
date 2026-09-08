#!/usr/bin/env python3
"""Map aquascope's Studio crew onto CrewAI agents.

The crew behind ``aquascope studio`` is six plain functions over one
workspace (``aquascope.studio.roles``): Consultant, Scout, Methodologist,
Analysts, Critic, Author. They need no agent framework (the browser runs
them in a worker), so they drop into CrewAI as the tools of six agents, one
task each, in that order. The Coordinator's state machine
(``aquascope.studio.Studio``) is what the tasks call; CrewAI adds the
conversation around it, nothing in between the numbers and the report.

    pip install crewai            # not an aquascope dependency
    python examples/crewai_studio.py --lat 51.415 --lon -0.308 \\
        --problem "Design flow for a road crossing, 100-year return period"

Without CrewAI installed the file still runs: ``run_plain`` calls the same
role functions in order, which is exactly what the Coordinator does.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

CREWAI_MISSING = (
    "This example maps aquascope's Studio crew onto CrewAI, which aquascope does not depend on. "
    "Install it next to aquascope with:  pip install crewai"
)

try:
    from crewai import Agent, Crew, Process, Task
    from crewai.tools import tool as crewai_tool

    HAVE_CREWAI = True
except ImportError:  # the role functions below run without it
    HAVE_CREWAI = False
    Agent = Crew = Process = Task = crewai_tool = None  # type: ignore[assignment]


# ── the roles as functions over one workspace ────────────────────────────────


class StudioTools:
    """The six role functions bound to one workspace, each returning a short JSON string an agent can read."""

    def __init__(self, lat: float, lon: float, **model_kwargs: Any):
        from aquascope.studio import Studio

        self.studio = Studio(lat=lat, lon=lon, **model_kwargs)

    @property
    def ws(self) -> Any:
        return self.studio.workspace

    def consult(self, text: str) -> str:
        """Consultant: take the brief (or answer its questions); returns the questions or the brief."""
        reply = self.studio.say(text)
        return json.dumps({"kind": reply.kind, "text": reply.text[:2000]})

    def scout(self) -> str:
        """Scout: the inventory of what exists at the site (runs inside say() when the brief is ready)."""
        inv = self.ws.inventory
        return json.dumps({"datasets": [d.to_dict() for d in inv.datasets] if inv else []})

    def plan(self) -> str:
        """Methodologist: the plan as a numbered checklist."""
        from aquascope.studio.roles.methodologist import plan_text

        return plan_text(self.ws.study)

    def run(self, edits_json: str = "") -> str:
        """Analysts: approve the plan (optionally with edits as JSON) and run it with gates."""
        edits = json.loads(edits_json) if edits_json.strip() else None
        reply = self.studio.approve(edits=edits)
        run = self.ws.run or {}
        return json.dumps({"kind": reply.kind, "ok": run.get("ok"), "gates": run.get("gates"),
                           "stop_reason": run.get("stop_reason")})

    def critique(self) -> str:
        """Critic: the checks and issues on the draft (the Coordinator ran it inside approve())."""
        return json.dumps(self.ws.critique or {})

    def report(self) -> str:
        """Author: the report's answer and key numbers."""
        r = self.ws.report or {}
        return json.dumps({"title": r.get("title"), "answer": r.get("answer"), "key_numbers": r.get("key_numbers"),
                           "not_established": r.get("not_established")})


# ── CrewAI mapping ──────────────────────────────────────────────────────────


def build_crew(tools: StudioTools, problem: str) -> Any:
    """Six agents, one task each, sequential. Each agent's only tool is its role function."""
    if not HAVE_CREWAI:
        raise ImportError(CREWAI_MISSING)

    consult = crewai_tool("consult")(tools.consult)
    scout = crewai_tool("scout")(tools.scout)
    plan = crewai_tool("plan")(tools.plan)
    run = crewai_tool("run")(tools.run)
    critique = crewai_tool("critique")(tools.critique)
    report = crewai_tool("report")(tools.report)

    def agent(role: str, goal: str, tool: Any) -> Any:
        return Agent(role=role, goal=goal, backstory=f"You are the {role} of AquaScope Studio; you only use your "
                     "tool and you never invent a number.", tools=[tool], allow_delegation=False, verbose=False)

    consultant = agent("Consultant", "Take the brief; answer its questions with 'just go' when nothing is known.",
                       consult)
    scout_agent = agent("Scout", "List what exists at the site.", scout)
    methodologist = agent("Methodologist", "Show the plan for the reviewer.", plan)
    analysts = agent("Analysts", "Run the approved plan with its gates.", run)
    critic = agent("Critic", "Report the checks and issues on the draft.", critique)
    author = agent("Author", "Hand back the answer with its key numbers and what is not established.", report)
    tasks = [
        Task(description=f"Call consult with: {problem}. If it returns questions, call consult again with 'just go'.",
             expected_output="the brief or the plan", agent=consultant),
        Task(description="Call scout.", expected_output="the datasets", agent=scout_agent),
        Task(description="Call plan.", expected_output="the numbered plan", agent=methodologist),
        Task(description="Call run with no edits.", expected_output="the gate outcomes", agent=analysts),
        Task(description="Call critique.", expected_output="the checks", agent=critic),
        Task(description="Call report.", expected_output="the answer", agent=author),
    ]
    return Crew(agents=[consultant, scout_agent, methodologist, analysts, critic, author], tasks=tasks,
                process=Process.sequential, verbose=False)


def run_plain(tools: StudioTools, problem: str) -> str:
    """The same six calls in order, no framework: what the Coordinator does."""
    first = json.loads(tools.consult(problem))
    if first["kind"] == "questions":
        tools.consult("just go")
    tools.scout()
    print(tools.plan())
    tools.run()
    tools.critique()
    return tools.report()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="aquascope's Studio crew as CrewAI agents")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--problem", default="Design flow for a road crossing, 100-year return period")
    ap.add_argument("--provider", default=None, help="a model for the roles (keyless otherwise)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--plain", action="store_true", help="call the roles directly, without CrewAI")
    ap.add_argument("--out", default=None, help="write the bundle here")
    args = ap.parse_args(argv)
    tools = StudioTools(args.lat, args.lon, provider=args.provider, model=args.model,
                        on_event=lambda e: print(f"  · {e['role']}: {e['event']} {e['detail']}", file=sys.stderr))
    if args.plain or not HAVE_CREWAI:
        if not args.plain:
            print(CREWAI_MISSING + "; running the roles directly.", file=sys.stderr)
        print(run_plain(tools, args.problem))
    else:
        build_crew(tools, args.problem).kickoff()
        print(tools.report())
    if args.out:
        print(tools.studio.export(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
