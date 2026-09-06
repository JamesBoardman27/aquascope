"""Studio: a crew of roles that does a complete study at a place, with any data, and reports it.

    you -> Consultant -> Scout -> Methodologist -> you -> Analysts -> Critic -> Author -> bundle

The crew shares one :class:`~aquascope.studio.workspace.Workspace`. The
Consultant writes the brief, the Scout the data inventory, the Methodologist
a version-3 study composed from the :mod:`~aquascope.studio.catalogue` and
validated against the method registry, the Analysts run it with gates, the
Critic checks the draft, the Author assembles the bundle (Word, Markdown,
HTML, Excel, PNG and SVG figures, a notebook, study.yaml, one zip). The
Coordinator (:class:`Studio`) owns the state machine and the faces (CLI, MCP,
the Explorer's worker) are thin over it.

Keyless, every role has a deterministic behaviour (keyword rules, the playbook
tree, templates) and the bundle is still produced. With a model, each role
makes stateless calls with compact JSON, never a transcript.

    from aquascope.studio import Studio

    s = Studio(lat=51.415, lon=-0.308, provider="anthropic")
    reply = s.say("Design flow for a road crossing, 100-year return period")
    # reply.questions -> answer them with s.say(...), or s.say("just go")
    s.approve()                       # runs the crew to the bundle
    s.export("out/")                  # writes the files
"""

from __future__ import annotations

from typing import Any

from aquascope.studio.workspace import Artifact, Brief, Dataset, Inventory, Message, Question, Workspace

__all__ = [
    "Artifact", "Brief", "Dataset", "Inventory", "Message", "Question", "Workspace", "Studio",
]


def __getattr__(name: str) -> Any:
    # The Coordinator imports the roles; keep the package import light for the workspace-only users.
    if name == "Studio":
        from aquascope.studio.coordinator import Studio

        return Studio
    raise AttributeError(name)
