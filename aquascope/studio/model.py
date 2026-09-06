"""The per-role model call: compact JSON in, a JSON object out, tokens counted per role.

Every role of the crew that uses a model uses it the same way: one stateless
call with a system prompt and a compact JSON context, never a transcript. The
reply is expected to be one JSON object (a fenced block is accepted). Errors
and unparseable replies come back as ``None`` and the role falls back to its
keyless behaviour; nothing here raises on the model's account.

The transport is the one ``aquascope.ai_engine`` already has (OpenAI-style
chat completions, the Anthropic translation, the browser path through
urllib), reached through ``team._model_for`` so a provider, a model name, a
key, a base URL or a ready client resolve exactly as they do for ``solve``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from aquascope.studio.workspace import Workspace

MAX_CONTEXT_CHARS = 60_000

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def json_block(text: str | None) -> dict[str, Any] | None:
    """The first JSON object in a reply: the whole text, a fenced block, or the outermost braces."""
    if not text:
        return None
    text = text.strip()
    for candidate in (text, *(m.group(1) for m in _FENCE.finditer(text))):
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
        if isinstance(obj, dict):
            return obj
    return None


class Model:
    """A model the roles may call, charged to the workspace's ledger, or absent (``Model.none()``)."""

    def __init__(self, inner: Any, ws: Workspace, *, say: Callable[[dict[str, Any]], None] | None = None):
        self._inner = inner      # aquascope.ai_engine.team._Model or None
        self.ws = ws
        self._say = say

    @classmethod
    def resolve(
        cls,
        ws: Workspace,
        *,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
        say: Callable[[dict[str, Any]], None] | None = None,
    ) -> Model:
        """A model only when one is asked for (a provider, a name, a key, a base URL or a client); never from the
        environment alone, so a keyless study stays keyless even with a key in the shell."""
        from aquascope.ai_engine.team import _model_for

        timeline: list[dict[str, Any]] = []

        def relay(event: dict[str, Any]) -> None:
            ws.event(event.get("role") or "model", event.get("event") or "model", str(event.get("detail") or ""),
                     step=event.get("step"))
            if say:
                say(event)

        inner, cfg = _model_for(provider, model, api_key, base_url, client, ws.ledger, timeline, relay)
        if inner is not None:
            # The Methodologist reads the catalogue, which is longer than a Solve role's context.
            inner.max_context_chars = MAX_CONTEXT_CHARS
        ws.model = cfg.get("model")
        ws.provider = cfg.get("provider")
        return cls(inner, ws, say=say)

    @classmethod
    def none(cls, ws: Workspace) -> Model:
        return cls(None, ws)

    @property
    def available(self) -> bool:
        return self._inner is not None

    def __bool__(self) -> bool:
        return self.available

    def call(self, role: str, system: str, context: dict[str, Any], *, step: str | None = None) -> str | None:
        """The raw text of one call, or None (no model, an error, an empty reply)."""
        if self._inner is None:
            return None
        return self._inner.call(role, system, context, step=step)

    def call_json(self, role: str, system: str, context: dict[str, Any], *, step: str | None = None,
                  retries: int = 1) -> dict[str, Any] | None:
        """One call whose reply must be a JSON object; one retry asking for JSON only when it was not."""
        text = self.call(role, system, context, step=step)
        obj = json_block(text)
        attempts = 0
        while obj is None and text is not None and attempts < retries:
            attempts += 1
            obj = json_block(self.call(role, system + "\nReply with one JSON object and nothing else.", context,
                                       step=step))
        return obj


def compact(obj: Any, *, depth: int = 0, max_list: int = 12, max_str: int = 400) -> Any:
    """A payload cut to what a role needs to see: lists capped, long strings and series dropped, depth bounded."""
    if depth > 6:
        return "..."
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in ("series", "points", "samples", "daily", "monthly_series", "png", "svg", "data"):
                if isinstance(v, (list, dict)):
                    out[k] = f"<{len(v)} entries omitted>"
                continue
            out[k] = compact(v, depth=depth + 1, max_list=max_list, max_str=max_str)
        return out
    if isinstance(obj, list):
        head = [compact(x, depth=depth + 1, max_list=max_list, max_str=max_str) for x in obj[:max_list]]
        if len(obj) > max_list:
            head.append(f"... {len(obj) - max_list} more")
        return head
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + "..."
    if isinstance(obj, float):
        return round(obj, 6)
    return obj
