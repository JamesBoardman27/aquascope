"""The documents a study becomes: a technical report, a technical memorandum, or a note that says it could not.

The composer decides what a reader sees and in what order; the renderers
(:mod:`.render_docx`, :mod:`.render_html`, :mod:`.render_md`) decide how it
looks. The editorial rules, taken from how a good hydrology report and a
good journal paper are written:

* **The answer first.** The summary opens with the number that answers the
  question, the interval that belongs to it, the grade and the reason for
  the grade, in sentences, before any method.
* **Organised by question, not by step.** The results are the design value,
  whether the record is stationary, how it compares with an independent
  check, not "step s1", "step s2". The plan's steps survive as the method.
* **Every figure earns its place.** A figure goes in the body only when it
  carries a claim the text makes (the frequency curve under the design
  value, the trend plot under the stationarity verdict); at most six; the
  rest go to an appendix. No figure repeats a table.
* **Numbers as a reader wants them.** Three significant figures, units as
  written by hand, a value and its interval in one cell, one row per return
  period, the design period in bold.
* **Limits as limitations.** Each condition, caveat and unresolved check is
  a bullet, once, in plain words; raw gate plumbing and error text are
  translated or left out.
* **Honest failure.** A study that established nothing becomes a one-page
  note saying what failed and what to do next, never a report.

Every number comes from :class:`aquascope.studio.document.facts.Facts`, which
reads only what the tools returned.
"""

from __future__ import annotations

import re
from typing import Any

from aquascope.studio.document import text as tx
from aquascope.studio.document.facts import GRADE_MEANING, GRADE_WORDS, TOOL_WORDS, Facts, facts_of
from aquascope.studio.document.model import (
    Bullets,
    Callout,
    Document,
    Figure,
    Heading,
    KeyValue,
    PageBreak,
    Para,
    Signoff,
    Table,
)
from aquascope.studio.document.style import HouseStyle
from aquascope.studio.workspace import Workspace

__all__ = ["build_memo", "build_report", "is_failed_study"]

#: At most this many figures in the body of a report; the rest go to the appendix.
MAX_BODY_FIGURES = 6

#: The figure that carries the answer, by problem kind (playbook), in order of preference.
HERO: dict[str, tuple[str, ...]] = {
    "flood_risk": ("frequency_curve", "regional_growth", "pot_frequency", "nonstationary_levels", "trend"),
    "flood_change": ("nonstationary_levels", "change_points", "trend", "frequency_curve"),
    "supply_reliability": ("reliability_curve", "fdc"),
    "drought_status": ("drought_strip", "propagation"),
    "groundwater_decline": ("drought_strip", "recharge", "trend", "series"),
    "ungauged_flow": ("signatures_band", "glofas_series"),
    "water_quality": ("wqi_bars", "who_exceedances", "samples_by_parameter"),
    "irrigation_feasibility": ("demand_monthly", "et0_monthly", "reliability_curve"),
    "climate_change": ("projection_spread", "scenario_bars"),
    "catchment_response": ("model_fit", "scenario_bars"),
}

#: Figures that belong in the body for a problem kind after the hero (others go to the appendix).
SUPPORTING: dict[str, tuple[str, ...]] = {
    "flood_risk": ("trend", "series", "glofas_series", "signatures_band"),
    "flood_change": ("trend", "series", "frequency_curve"),
    "supply_reliability": ("series", "fdc", "trend", "monthly_climate"),
    "drought_status": ("monthly_climate", "series", "propagation"),
    "groundwater_decline": ("series", "trend", "propagation", "recharge"),
    "ungauged_flow": ("glofas_series", "monthly_climate", "donors_map"),
    "water_quality": ("samples_by_parameter", "who_exceedances"),
    "irrigation_feasibility": ("et0_monthly", "monthly_climate", "reliability_curve"),
    "climate_change": ("scenario_bars", "monthly_climate"),
    "catchment_response": ("scenario_bars", "series"),
}

#: Figure kinds that say the same thing as another kind already placed: drawn once.
SAME_AS = {"annual_maxima": ("trend", "frequency_curve")}


# ── helpers ─────────────────────────────────────────────────────────────────


def is_failed_study(ws: Workspace, facts: Facts | None = None) -> bool:
    """True when nothing the study ran established a result: the documents become a study note."""
    f = facts or facts_of(ws)
    if not f.steps:
        return True
    return not any(s.get("ok") for s in f.steps) or (f.grade == "not_established" and not f.headline.get("value")
                                                       and not any(s.get("ok") and s["tool"] not in
                                                                   ("describe_catchment",) for s in f.steps))


def _kind_of(a: Any) -> str:
    """A figure artifact's kind: its meta, else the tail of a ``fig-{step}-{kind}`` id, else the id itself."""
    kind = (a.meta or {}).get("kind")
    if kind:
        return str(kind)
    m = re.match(r"^fig-[^-]+-(.+)$", a.id)
    return m.group(1) if m else a.id


def _figures(ws: Workspace) -> dict[str, list[Figure]]:
    """Every PNG figure artifact as a document :class:`Figure`, by kind, in step order."""
    out: dict[str, list[Figure]] = {}
    for a in ws.artifacts:
        if a.kind != "figure" or a.media_type != "image/png" or not a.data:
            continue
        kind = _kind_of(a)
        svg = ws.artifact(a.id + "-svg")
        out.setdefault(kind, []).append(Figure(id=f"{a.step}-{kind}", png=a.data, caption=tx.clean_units(a.caption),
                                               svg=svg.data if svg is not None else None, path=a.name or ""))
    return out


class _Placer:
    """Hands out figures: each kind once, at most :data:`MAX_BODY_FIGURES` in the body, the rest kept for the
    appendix. ``take`` returns the figure for the body (or None) and remembers it."""

    def __init__(self, figs: dict[str, list[Figure]], prefer_step: dict[str, str]):
        self.figs = figs
        self.prefer = prefer_step
        self.placed: list[str] = []
        self.body = 0

    def _pick(self, kind: str) -> Figure | None:
        cands = self.figs.get(kind) or []
        if not cands:
            return None
        step = self.prefer.get(kind)
        if step:
            for f in cands:
                if f.id.startswith(step + "-"):
                    return f
        return cands[-1]

    def take(self, kind: str) -> Figure | None:
        if kind in self.placed or self.body >= MAX_BODY_FIGURES:
            return None
        if any(k in self.placed for k in SAME_AS.get(kind, ())):
            return None
        f = self._pick(kind)
        if f is None:
            return None
        self.placed.append(kind)
        self.body += 1
        return f

    def rest(self) -> list[Figure]:
        out = []
        for kind, cands in self.figs.items():
            if kind in self.placed or any(k in self.placed for k in SAME_AS.get(kind, ())):
                continue
            pick = self._pick(kind)
            if pick is not None:
                out.append(pick)
        return out


def tx_clean(text: str) -> str:
    from aquascope.studio.document.facts import _clean_reason

    return _clean_reason(text)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = tx.sentence(tx.clean_units(it))
        key = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()[:90]
        if not s or key in seen:
            continue
        if any(key in k or k in key for k in seen if len(k) > 40 and len(key) > 40):
            continue
        seen.add(key)
        out.append(s)
    return out


def _site_sentence(f: Facts) -> str:
    where = tx.coord(f.lat, f.lon)
    if f.site_name:
        return f"{f.site_label}, at {where}" if where else f.site_label
    return f"the site at {where}" if where else "the site"


def _record_period(f: Facts) -> str:
    r = f.record
    if not r:
        return ""
    start, end = str(r.get("start") or "")[:10], str(r.get("end") or "")[:10]
    return f"{start} to {end}" if start and end else ""


def _fits_at(f: Facts, t: float | None) -> dict[str, dict[str, Any]]:
    """Each fit's value (and interval) at return period ``t``."""
    out: dict[str, dict[str, Any]] = {}
    if not f.ffa or t is None:
        return out
    try:
        i = [float(x) if x is not None else None for x in f.ffa["T"]].index(float(t))
    except ValueError:
        return out
    for name, fit in f.ffa["fits"].items():
        q = fit["q"][i] if i < len(fit["q"]) else None
        ci = fit["ci"][i] if fit.get("ci") and i < len(fit["ci"]) else None
        out[name] = {"q": q, "ci": ci, "level": fit.get("level"), "label": fit["label"]}
    return out


def _design_t(f: Facts) -> float | None:
    if f.return_period:
        return f.return_period
    if f.ffa and f.ffa.get("T"):
        ts = [t for t in f.ffa["T"] if t]
        return 100.0 if 100.0 in ts else (max(ts) if ts else None)
    return None


def _t(t: float | None) -> str:
    return f"{int(t)}" if t is not None and float(t).is_integer() else tx.num(t)


# ── prose: the summary ──────────────────────────────────────────────────────


def _flood_summary(f: Facts) -> list[str]:
    t = _design_t(f)
    at = _fits_at(f, t)
    u = f.ffa.get("unit") or "m3/s"
    sentences: list[str] = []
    gev, lp3, ml = at.get("gev_lmoments"), at.get("lp3"), at.get("gev_bootstrap")
    main = gev or lp3 or ml
    if not main or main.get("q") is None:
        return sentences
    n = f.ffa.get("n_years")
    yrs = f.ffa.get("years") or []
    span = f" ({min(yrs)} to {max(yrs)})" if yrs else ""
    main_name = "a GEV distribution fitted by L-moments" if main is gev else \
        ("a Log-Pearson III distribution" if main is lp3 else "a GEV distribution fitted by maximum likelihood")
    sentences.append(f"The {_t(t)}-year flood at {f.site_label} is estimated at {tx.value(main['q'], u)}, from "
                     f"{main_name} to {tx.plural(int(n), 'complete year') if n else 'the'} of annual maximum "
                     f"daily-mean flow{span}.")
    others = []
    for alt in (lp3, ml):
        if alt is None or alt is main or alt.get("q") is None:
            continue
        diff = (alt["q"] - main["q"]) / main["q"] * 100 if main["q"] else None
        piece = f"{alt['label']} gives {tx.value(alt['q'], u)}"
        if diff is not None and round(abs(diff)) >= 1:
            piece += f" ({abs(diff):.0f} % {'lower' if diff < 0 else 'higher'})"
        elif diff is not None:
            piece += " (within 1 %)"
        if alt.get("ci") and alt["ci"][0] is not None and alt["ci"][1] is not None:
            lvl = f"a {alt['level'] * 100:g} % interval" if alt.get("level") else "an interval"
            piece += f", with {lvl} of {tx.band(alt['ci'][0], alt['ci'][1], u)}"
        others.append(piece)
    if others:
        sentences.append(tx.sentence("; ".join(others[:1]) + ("" if len(others) < 2 else
                                                              f". {others[1][:1].upper()}{others[1][1:]}")))
    stat = []
    if f.trend:
        verdict = "no significant trend" if (f.trend.get("p") or 1) >= 0.05 else "a significant trend"
        stat.append(f"{verdict} (Mann-Kendall p = {tx.p_value(f.trend.get('p'))})")
    if f.change and f.change.get("p") is not None:
        word = "a significant step change" if f.change.get("significant") else "no significant step change"
        stat.append(f"{word} (Pettitt p = {tx.p_value(f.change.get('p'))}"
                    + (f", around {f.change['year']}" if f.change.get("significant") and f.change.get("year") else "")
                    + ")")
    if stat:
        sentences.append(f"The annual maxima show {tx.join(stat)}.")
    return sentences


def _generic_answer(f: Facts) -> str:
    h = f.headline
    if h.get("value") is None:
        return ""
    label = str(h.get("label") or "").strip()
    if label:
        lab = label[:1].lower() + label[1:] if not label[:2].isupper() else label
        return f"The {lab} at {f.site_label} is {tx.value(h['value'], h.get('unit'))}."
    ans = re.sub(r"\s*\((established|indicative|screening|not established)\)\.?$", ".", h.get("answer") or "")
    return tx.sentence(ans)


def summary_sentences(f: Facts) -> list[str]:
    """The executive summary in sentences: answer, interval, stationarity, grade with its reason, the main
    condition."""
    out: list[str] = []
    is_flood = bool(f.ffa) and (f.playbook in ("flood_risk", "") or "flood" in f.question.lower())
    if is_flood and not f.asks_trend:
        out += _flood_summary(f)
    elif f.asks_trend and f.trend:
        sl = f.trend.get("slope")
        p = f.trend.get("p")
        sig = p is not None and p < 0.05
        direction = ("increasing" if (sl or 0) > 0 else "decreasing") if sig else "neither clearly increasing nor " \
                                                                                   "decreasing"
        out.append(f"Annual maximum flow at {f.site_label} is {direction}: the Mann-Kendall test gives "
                   f"p = {tx.p_value(p)} over {tx.plural(int(f.trend.get('n') or 0), 'year')} and the Sen slope is "
                   f"{tx.value(sl, (f.trend.get('unit') or '') + ' per year')}.")
        if not sig:
            out.append("At the 5 % level the record does not resolve a change in either direction.")
        out += [s for s in _flood_summary(f)[:1]]
    if not out:
        ans = _generic_answer(f)
        if ans:
            out.append(ans)
    if f.record and not is_flood:
        out.append(f"The analysis uses {_record_words(f)}.")
    out.append(f"The answer is graded **{GRADE_WORDS.get(f.grade, f.grade).lower()}**. {f.grade_reason}")
    if is_flood:
        out.append("The values are daily means, which understate instantaneous peaks.")
    elif f.conditions:
        out.append(tx.assumption(f.conditions[0]))
    return [tx.clean_units(s) for s in out if s]


def _record_words(f: Facts) -> str:
    r = f.record
    var = str(r.get("variable") or "the record").replace("_", " ")
    agency = r.get("agency") or (str(r.get("source") or "").upper())
    period = _record_period(f)
    yrs = tx.years(r.get("years"))
    return (f"the {var} record of {f.site_label}" + (f" ({agency})" if agency and agency not in f.site_label else "")
            + (f", {period}" if period else "") + (f", {yrs}" if yrs else ""))


# ── tables ──────────────────────────────────────────────────────────────────


def return_level_table(f: Facts) -> Table | None:
    if not f.ffa or not f.ffa.get("T"):
        return None
    u = tx.unit(f.ffa.get("unit") or "m3/s")
    order = [n for n in ("gev_lmoments", "lp3", "gev_bootstrap") if n in f.ffa["fits"]]
    cols = ["Return period (years)", "AEP (%)"]
    for name in order:
        fit = f.ffa["fits"][name]
        cols.append(fit["label"])
        if fit.get("ci"):
            cols.append(f"{fit['level'] * 100:g} % interval" if fit.get("level") else "Interval")
    rows: list[list[Any]] = []
    emphasis: list[int] = []
    design = _design_t(f)
    for i, t in enumerate(f.ffa["T"]):
        if t is None:
            continue
        row: list[Any] = [_t(t), tx.num(100.0 / t, 2) if t else ""]
        for name in order:
            fit = f.ffa["fits"][name]
            row.append(tx.num(fit["q"][i]) if i < len(fit["q"]) else "")
            if fit.get("ci"):
                ci = fit["ci"][i] if i < len(fit["ci"]) else [None, None]
                row.append(tx.span(ci[0], ci[1]))
        if design is not None and float(t) == float(design):
            emphasis.append(len(rows))
        rows.append(row)
    notes = []
    for name in order:
        fit = f.ffa["fits"][name]
        if fit.get("ci"):
            how = fit.get("interval_method")
            nb = f" from {fit['n_bootstrap']:,} resamples" if fit.get("n_bootstrap") else ""
            what = f"is the {how}{nb}" if how else f"was computed{nb}" if nb else "is the fit's own"
            notes.append(f"The {fit['label']} interval {what}; it belongs to that fit only.")
    if "gev_lmoments" in order and not f.ffa["fits"]["gev_lmoments"].get("ci"):
        notes.append("GEV (L-moments) is reported without an interval.")
    return Table(id="levels", columns=cols, rows=rows, caption=(
        f"Flood quantiles of annual maximum daily-mean flow at {f.site_label}, in {u}, by return period and annual "
        f"exceedance probability (AEP)" + (f"; the design return period ({_t(design)} years) is in bold"
                                            if emphasis else "") + "."),
        align=["r"] * len(cols), notes=notes, emphasis=emphasis)


def catchment_table(f: Facts) -> Table | None:
    rows = f.catchment.get("rows") or []
    if not rows:
        return None
    body = [[label, tx.num(v) if not (isinstance(v, float) and v.is_integer() and v > 50) else f"{int(v):,}",
             tx.unit(u)] for label, v, u in rows[:14]]
    src = "BasinATLAS (HydroATLAS v1.0)"
    return Table(id="catchment", columns=["Attribute", "Value", "Unit"], rows=body,
                 caption=f"Catchment attributes upstream of the site from {src}" +
                 (f", sub-basin {f.catchment['hybas_id']}" if f.catchment.get("hybas_id") else "") + ".",
                 align=["l", "r", "l"], compact=True)


def data_table(f: Facts) -> Table | None:
    rows: list[list[Any]] = []
    if f.record:
        r = f.record
        rows.append([f.site_label, str(r.get("agency") or str(r.get("source") or "").upper()),
                     str(r.get("variable") or "").replace("_", " "), _years_span(r.get("start"), r.get("end")),
                     tx.years(r.get("years")), "Primary record"])
    if f.catchment.get("rows"):
        rows.append(["Catchment upstream of the site", "BasinATLAS (HydroATLAS v1.0)", "attributes", "", "",
                     "Catchment description"])
    if f.climate:
        rows.append(["ERA5 cell at the site", str(f.climate.get("source") or "ERA5 via Open-Meteo"),
                     "precipitation, ET₀, temperature",
                     _years_span(f.climate.get("start"), f.climate.get("end")),
                     tx.years(f.climate.get("years")), "Climate context"])
    if f.glofas:
        rows.append(["GloFAS grid cell nearest the site", "GloFAS v4 via Open-Meteo", "modelled discharge", "", "",
                     "Independent check"])
    if f.regional.get("k"):
        rows.append([f"{f.regional['k']} donor catchments", "Similar-basin pool", "flow signatures", "", "",
                     "Transfer to the site"])
    if not rows:
        return None
    return Table(id="data", columns=["Dataset", "Provider", "Variable", "Period", "Length", "Role"], rows=rows,
                 caption="Data used in this study.", align=["l", "l", "l", "l", "r", "l"])


def _years_span(start: Any, end: Any) -> str:
    a, b = str(start or "")[:4], str(end or "")[:4]
    return f"{a}\u2013{b}" if a.isdigit() and b.isdigit() else ""


def checks_table(f: Facts) -> Table | None:
    if not f.checks:
        return None
    words = {"passed": "Passed", "failed": "Failed", "skipped": "Not run"}
    tool_of = {s["id"]: TOOL_WORDS.get(s["tool"], s["tool"]) for s in f.steps}
    rows = []
    for ch in f.checks:
        sentence = ch.sentence[:1].upper() + ch.sentence[1:]
        detail = _short_detail(ch.detail)
        rows.append([tool_of.get(ch.step, ch.step)[:1].upper() + tool_of.get(ch.step, ch.step)[1:], sentence,
                     words.get(ch.verdict, ch.verdict), detail])
    return Table(id="checks", columns=["Analysis", "Check", "Result", "What was found"], rows=rows,
                 caption="The checks each analysis had to pass before its result was used.",
                 align=["l", "l", "l", "l"])


def _full_detail(d: str) -> str:
    d = tx.clean_units(d)
    d = re.sub(r"^skipped:\s*", "", d)
    d = re.sub(r"'([a-z_]+)' is present", lambda m: m.group(1).replace("_", " ") + " returned", d)
    d = d.replace("gev lmoments", "GEV (L-moments)").replace("Glofas", "GloFAS").replace("glofas", "GloFAS")
    d = d.rstrip(". ")
    return d[:1].upper() + d[1:] if d else ""


def _short_detail(d: str) -> str:
    """The first sentence of a check's detail, for a table cell."""
    d = _full_detail(d)
    if len(d) > 160:
        first = re.split(r"(?<=[.;:])\s+", d)[0].rstrip(".;:")
        d = first if len(first) <= 200 else d[:160].rsplit(" ", 1)[0]
    return d


def grade_table() -> Table:
    rows = [[GRADE_WORDS[g], GRADE_MEANING[g]] for g in ("established", "indicative", "screening",
                                                         "not_established")]
    return Table(id="grades", columns=["Grade", "Meaning"], rows=rows,
                 caption="The grades an answer can carry.", align=["l", "l"])


def nearby_table(f: Facts) -> Table | None:
    rows: list[list[Any]] = []
    by_id: dict[str, list[Any]] = {}
    used = f.record.get("station_id")
    for n in f.nearby:
        if used and n["id"] == f.site_id:
            continue
        var = str(n.get("variable") or "").replace("_", " ")
        if n["id"] in by_id:
            if var and var not in by_id[n["id"]][2]:
                by_id[n["id"]][2] += f", {var}"
            continue
        y = n.get("years")
        length = "unknown" if not y else ("under 1 year" if float(y) < 1 else tx.years(y))
        row = [n["name"], n["id"], var, tx.num(n.get("km"), 2) if n.get("km") is not None else "", length]
        by_id[n["id"]] = row
        rows.append(row)
        if len(rows) >= 8:
            break
    if not rows:
        return None
    return Table(id="nearby", columns=["Station", "Identifier", "Variable", "Distance (km)", "Record"],
                 rows=rows, caption="Other gauging stations found near the site.",
                 align=["l", "l", "l", "r", "r"])


# ── sections ────────────────────────────────────────────────────────────────


def _control_rows(f: Facts, style: HouseStyle, kind: str) -> list[tuple[str, str]]:
    rows = []
    if style.project:
        rows.append(("Project", style.project))
    if style.client:
        rows.append(("Client", style.client))
    rows.append(("Site", f.site_label + (f", {tx.coord(f.lat, f.lon)}" if f.site_name and f.lat is not None
                                        else "")))
    rows.append(("Question", tx.sentence(f.question) if not f.question.endswith("?") else f.question))
    if style.reference:
        rows.append(("Reference", style.reference))
    rows.append(("Version", style.version))
    rows.append(("Status", style.status or "Issued"))
    rows.append(("Date", f.created))
    rows.append(("Prepared by", style.preparer))
    rows.append(("Checked by", style.checked_by or "Not yet checked"))
    if kind == "report":
        rows.append(("Approved by", style.approved_by or "Not yet approved"))
    rows.append(("Study identifier", f"{f.workspace_id} (AquaScope {f.version})"))
    return rows


def _title(f: Facts) -> tuple[str, str]:
    """(title, subtitle): what was estimated, where."""
    t = _design_t(f)
    pb = f.playbook
    if f.asks_trend:
        head = "Flood trend assessment"
    elif pb == "flood_risk" or (f.ffa and "flood" in f.question.lower()):
        head = f"{_t(t)}-year design flood estimate" if t else "Flood frequency assessment"
    else:
        head = {"supply_reliability": "Supply reliability assessment", "drought_status": "Drought status assessment",
                "groundwater_decline": "Groundwater level assessment", "ungauged_flow": "Flow estimate for an "
                "ungauged site", "water_quality": "Water quality assessment", "irrigation_feasibility":
                "Irrigation water demand assessment", "climate_change": "Climate change sensitivity assessment",
                "catchment_response": "Catchment response assessment", "flood_change": "Flood change assessment"
                }.get(pb, "Hydrological assessment")
    sub = f.site_name or (f"Site at {tx.coord(f.lat, f.lon)}" if f.lat is not None else "")
    return head, sub


def build_report(ws: Workspace, style: HouseStyle | None = None, facts: Facts | None = None) -> Document:
    """The technical report of a study (or the study note when nothing was established)."""
    style = style or HouseStyle()
    f = facts or facts_of(ws)
    if is_failed_study(ws, f):
        return build_note(ws, style, f)
    title, sub = _title(f)
    doc = Document(title=title, subtitle=sub, kind="Technical report", status=style.status,
                   meta={"organisation": style.author_line, "date": f.created, "site": f.site_label,
                         "reference": style.reference, "version": style.version})
    doc.add(KeyValue(_control_rows(f, style, "report")), Signoff(_signoff_roles(style)), PageBreak())
    prefer = {"frequency_curve": f.ffa.get("step", ""), "trend": f.trend.get("step", "")}
    placer = _Placer(_figures(ws), {k: v for k, v in prefer.items() if v})

    # Summary
    doc.add(Heading("Summary", numbered=False))
    doc.add(_answer_callout(f))
    doc.add(Para(" ".join(summary_sentences(f)), style="lead"))

    # 1 Introduction
    doc.add(Heading("Introduction"))
    intro = [f"This report answers the question “{f.question.strip().rstrip('.')}”" +
             (f" for {_site_sentence(f)}." if f.site_label else ".")]
    if f.decision:
        intro.append(f"The answer is needed for a decision on {f.decision.rstrip('.')}.")
    q = [x for x in ws.brief.quantities if x]
    if q:
        intro.append(f"The quantities sought are {tx.join([tx.clean_units(x) for x in q])}.")
    intake = {k: v for k, v in (ws.brief.intake or {}).items() if v not in (None, "")}
    choices = []
    if intake.get("return_period"):
        choices.append(f"a design return period of {intake['return_period']} years")
    if intake.get("years"):
        choices.append(f"the most recent {intake['years']} years of record")
    if choices:
        intro.append(f"The study was set up with {tx.join(choices)}.")
    doc.add(Para(" ".join(intro)))
    scope = (f.record.get("coverage_rule") and "") or ""
    elig_scope = _scope_sentence(ws)
    if elig_scope or scope:
        doc.add(Para(elig_scope))

    # 2 Site and catchment
    if f.catchment.get("rows") or f.site_label:
        doc.add(Heading("Site and catchment"))
        doc.add(Para(_catchment_para(f)))
        doc.add(catchment_table(f))
        doc.add(placer.take("site_map"))

    # 3 Data
    doc.add(Heading("Data"))
    doc.add(Para(_data_para(f)))
    doc.add(data_table(f))
    hydro = placer.take("series")
    if hydro is not None:
        doc.add(Para(f"{{fig:{hydro.id}}} shows the record used."), hydro)
    nt = nearby_table(f)
    if nt is not None and len(nt.rows) >= 1:
        doc.add(Para(_nearby_para(f, nt)), nt)

    # 4 Method
    doc.add(Heading("Method"))
    doc.add(Para(_method_intro(f)))
    doc.add(Bullets(_method_steps(ws, f), numbered=True))
    assumptions = _dedupe([*(ws.brief.assumptions or []), *(((ws.study or {}).get("plan") or {}).get(
        "assumptions") or [])])
    assumptions = [a for a in assumptions if not re.search(r"\b(option|intake field|recorded as the integer|"
                                                           r"unanswered)\b", a, re.I)]
    if assumptions:
        doc.add(Heading("Assumptions", level=2))
        doc.add(Bullets(assumptions[:8], numbered=True))
    alts = ((ws.study or {}).get("plan") or {}).get("alternatives") or []
    alt_lines = []
    for a in alts:
        if isinstance(a, dict) and a.get("method"):
            alt_lines.append(f"{str(a['method']).replace('_', ' ').capitalize()} was not used: "
                             f"{tx.clean_units(str(a.get('why_not') or '').rstrip('.'))}.")
    if alt_lines:
        doc.add(Heading("Methods considered and not used", level=2))
        doc.add(Bullets(alt_lines[:5]))

    # 5 Results
    doc.add(Heading("Results"))
    hero_kinds = HERO.get(f.playbook, ())
    supporting = SUPPORTING.get(f.playbook, ())
    handled_steps: set[str] = set()
    if f.ffa and not f.asks_trend:
        _ffa_section(doc, f, placer)
        handled_steps.add(str(f.ffa.get("step")))
    if f.trend and (f.ffa or f.asks_trend):
        _trend_section(doc, f, placer)
    if f.asks_trend and f.ffa:
        _ffa_section(doc, f, placer)
    if f.regional.get("estimates"):
        _regional_section(doc, f, placer)
    for step in f.steps:
        if step["tool"] in ("describe_catchment", "anywhere", "similar_basins", "regionalize_signatures",
                            "assess_site", "find_stations", "catalog_search"):
            continue
        if step["id"] in handled_steps or (step["tool"] in ("analyze_station", "flood_frequency") and f.ffa):
            continue
        _generic_section(doc, ws, f, step, placer, hero_kinds + supporting)
    if f.climate or f.glofas:
        _context_section(doc, f, placer)

    # 6 Checks and grade
    doc.add(Heading("Checks and confidence"))
    passed = sum(1 for c in f.checks if c.verdict == "passed")
    failed = sum(1 for c in f.checks if c.verdict == "failed")
    skipped = sum(1 for c in f.checks if c.verdict == "skipped")
    ct = checks_table(f)
    if ct is not None:
        parts = [f"{passed} of {len(f.checks)} checks passed"]
        if failed:
            parts.append(f"{failed} failed")
        if skipped:
            parts.append(f"{skipped} could not be run")
        doc.add(Para(f"Each analysis carried checks that its result had to pass before it was used "
                     f"({{tab:checks}}): {tx.join(parts)}."))
        doc.add(ct)
    gate_notes = {c.detail for c in f.checks}
    agree = [c for c in f.consistency if c.get("agree") is not None and c.get("note")
             and not re.match(r"^s\d+(\.fallback)?: ", str(c.get("a") or ""))
             and tx_clean(str(c["note"])) not in gate_notes]
    if agree:
        lines = []
        for c in agree:
            note = tx.clean_units(str(c["note"]))
            lines.append(("Consistent: " if c["agree"] else "Inconsistent: ") + note[:1].lower() + note[1:])
        doc.add(Para("Where two results bear on the same quantity they were compared:"))
        doc.add(Bullets(_dedupe(lines)[:6]))
    doc.add(Para(f"The answer is graded **{GRADE_WORDS.get(f.grade, f.grade).lower()}**. {f.grade_reason} "
                 f"{{tab:grades}} gives what each grade means."))
    doc.add(grade_table())

    # 7 Limitations
    lims = _limitations(ws, f)
    if lims:
        doc.add(Heading("Limitations"))
        doc.add(Bullets(lims))

    # 8 Recommendations
    doc.add(Heading("Recommendations"))
    doc.add(Bullets(_recommendations(f), numbered=True))

    # References
    refs = clean_references(f.references)
    if refs:
        doc.add(Heading("References", numbered=False))
        doc.add(Bullets(refs))

    # Appendices
    rest = placer.rest()
    if rest:
        doc.add(PageBreak(), Heading("Appendix A. Supplementary figures", numbered=False))
        for fig in rest:
            doc.add(fig)
    doc.add(Heading(("Appendix B" if rest else "Appendix A") + ". Reproducibility", numbered=False))
    doc.add(Para(_repro_para(f)))
    return doc.finalize()


def _signoff_roles(style: HouseStyle) -> list[tuple[str, str]]:
    return [("Prepared by", style.prepared_by), ("Checked by", style.checked_by),
            ("Approved by", style.approved_by)]


def _answer_callout(f: Facts) -> Callout:
    rows: list[tuple[str, str]] = []
    h = f.headline
    title = "Answer"
    body = ""
    t = _design_t(f)
    at = _fits_at(f, t)
    u = (f.ffa.get("unit") if f.ffa else None) or h.get("unit")
    if f.ffa and not f.asks_trend and at:
        main = at.get("gev_lmoments") or at.get("lp3") or at.get("gev_bootstrap")
        body = f"{_t(t)}-year flood: {tx.value(main['q'], u)}"
        rows.append(("Estimator", main["label"] + " on annual maximum daily-mean flow"))
        for name in ("lp3", "gev_bootstrap"):
            alt = at.get(name)
            if alt and alt.get("ci") and alt["ci"][0] is not None:
                lvl = f"{alt['level'] * 100:g} %" if alt.get("level") else ""
                rows.append((f"{lvl} interval".strip(), f"{tx.band(alt['ci'][0], alt['ci'][1], u)} "
                                                        f"({alt['label']})"))
                break
        others = [f"{v['label']} {tx.value(v['q'], u)}" for k, v in at.items() if v is not main and v.get("q")]
        if others:
            rows.append(("Other fits", tx.join(others)))
    elif f.asks_trend and f.trend:
        p = f.trend.get("p")
        body = ("No significant trend in annual maximum flow" if (p or 1) >= 0.05 else
                ("Annual maximum flow is increasing" if (f.trend.get("slope") or 0) > 0 else
                 "Annual maximum flow is decreasing"))
        rows.append(("Mann-Kendall", f"p = {tx.p_value(p)}, n = {f.trend.get('n')} years"))
        rows.append(("Sen slope", tx.value(f.trend.get("slope"), (f.trend.get("unit") or "") + " per year")))
    elif h.get("value") is not None:
        label = str(h.get("label") or "Estimate")
        body = f"{label}: {tx.value(h['value'], h.get('unit'))}"
        if h.get("interval") and isinstance(h["interval"], (list, tuple)) and len(h["interval"]) == 2:
            rows.append(("Interval", tx.band(h["interval"][0], h["interval"][1], h.get("unit"))))
    else:
        body = tx.sentence(h.get("answer") or "See the results.")
    rows.append(("Grade", GRADE_WORDS.get(f.grade, f.grade)))
    if f.record:
        rows.append(("Based on", _record_words(f)))
    tone = {"established": "answer", "indicative": "answer", "screening": "caution"}.get(f.grade, "fail")
    return Callout(title=title, body=tx.clean_units(body), rows=[(a, tx.clean_units(b)) for a, b in rows],
                   tone=tone)


def _scope_sentence(ws: Workspace) -> str:
    for r in (ws.run or {}).get("results") or []:
        p = r.get("result") if isinstance(r.get("result"), dict) else {}
        el = p.get("eligibility") if isinstance(p.get("eligibility"), dict) else None
        if el and el.get("scope"):
            scope = str(el["scope"]).rstrip(".")
            return (f"Scope: {scope[:1].lower() + scope[1:]}. The flood statistics are computed from daily-mean "
                    f"flows, which understate instantaneous peaks, and are not a full Bulletin 17C or national "
                    f"guideline procedure.")
    return ""


def _catchment_para(f: Facts) -> str:
    c = f.catchment
    s = [f"The study site is {_site_sentence(f)}."]
    bits = []
    if c.get("area_km2"):
        bits.append(f"drains {tx.value(c['area_km2'], 'km2')}")
    if c.get("elevation_m") is not None:
        bits.append(f"has a mean elevation of {tx.value(c['elevation_m'], 'm')}")
    if c.get("precipitation_mm_yr") is not None:
        bits.append(f"receives about {tx.value(c['precipitation_mm_yr'], 'mm')} of precipitation a year")
    if bits:
        s.append(f"The catchment upstream {tx.join(bits)} ({{tab:catchment}}).")
    climate = []
    if c.get("aridity_index") is not None:
        ai = c["aridity_index"]
        zone = "humid" if ai >= 0.65 else "dry sub-humid" if ai >= 0.5 else "semi-arid" if ai >= 0.2 else "arid"
        climate.append(f"an aridity index (P/PET) of {tx.num(ai)}, {zone}")
    if c.get("snow_cover_pct"):
        climate.append(f"snow cover over {tx.num(c['snow_cover_pct'])} % of the catchment in an average year")
    if climate:
        s.append(f"It has {tx.join(climate)}.")
    reg = c.get("regulation_pct")
    if reg is not None:
        s.append("No reservoir regulation is recorded upstream." if reg == 0 else
                 f"Reservoirs regulate the flow ({tx.num(reg)} % degree of regulation).")
    return " ".join(s)


def _data_para(f: Facts) -> str:
    r = f.record
    if not r:
        return ("No measured record at the site was used. The estimates rest on the datasets listed in "
                "{tab:data}.")
    s = [f"The primary record is the daily {str(r.get('variable') or 'flow').replace('_', ' ')} series of "
         f"{f.site_label}" + (f", published by the {r['agency']}" if r.get("agency") else "") +
         (f", from {_record_period(f)}" if _record_period(f) else "") + "."]
    cy = r.get("complete_years")
    if cy:
        rule = str(r.get("coverage_rule") or "").rstrip(".")
        s.append(f"Of its {tx.years(r.get('years'))}, {cy} are complete enough to contribute an annual maximum"
                 + (f" ({rule[:1].lower() + rule[1:]})" if rule else "") + ".")
    if r.get("license") or r.get("attribution"):
        s.append(f"Data licence: {tx.clean_units(r.get('attribution') or r.get('license'))}.")
    s.append("{tab:data} lists every dataset the study drew on.")
    return " ".join(s)


def _nearby_para(f: Facts, nt: Table) -> str:
    unknown = [r for r in nt.rows if r[-1] == "unknown"]
    s = (f"{len(nt.rows)} other station{'s were' if len(nt.rows) > 1 else ' was'} found near the site "
         f"({{tab:nearby}}).")
    if unknown:
        s += (f" The record length of {len(unknown)} of them is not known to the catalogue; they were not used, "
              f"but a request to the agency may show that one of them has a usable record.")
    return s


def _method_intro(f: Facts) -> str:
    return ("The study was planned as a sequence of analyses, each with checks its result had to pass before it "
            "was used. The analyses, in the order they ran:")


def _method_steps(ws: Workspace, f: Facts) -> list[str]:
    out = []
    for s in f.steps:
        tool = s["tool"]
        line = TOOL_WORDS.get(tool, tool.replace("_", " "))
        line = line[:1].upper() + line[1:]
        detail = _method_detail(f, s)
        if detail:
            line += f": {detail}"
        if not s.get("ran"):
            line += " (did not complete)"
        elif s.get("fallback_used"):
            line += " (the planned method did not pass its checks; its fallback was used)"
        out.append(tx.sentence(tx.clean_units(line)))
    return out


def _method_detail(f: Facts, s: dict[str, Any]) -> str:
    tool = s["tool"]
    if tool == "flood_frequency" or (tool == "analyze_station" and f.ffa and f.ffa.get("step") == s["id"]):
        fits = f.ffa.get("fits") or {}
        parts = []
        if "gev_lmoments" in fits:
            parts.append("a generalised extreme value (GEV) distribution fitted by L-moments (Hosking, 1990)")
        if "lp3" in fits:
            parts.append("a Log-Pearson III distribution fitted to the logarithms by the method of moments")
        if "gev_bootstrap" in fits:
            nb = fits["gev_bootstrap"].get("n_bootstrap")
            parts.append("a GEV fitted by maximum likelihood with a nonparametric bootstrap"
                         + (f" of {nb:,} resamples" if nb else "") + " for its interval")
        return (f"{tx.join(parts)}, each fitted to the annual maxima of the complete years" if parts else "")
    if tool == "analyze_station":
        return ("record statistics, the flow-duration curve, the annual maxima and the Mann-Kendall trend test "
                "with Sen's slope on them")
    if tool == "describe_catchment":
        return "area, elevation, climate, land cover and regulation of the catchment upstream of the site"
    if tool == "anywhere":
        return ("mean monthly climate from the ERA5 reanalysis and modelled daily discharge from GloFAS v4 for the "
                "grid cell at the site, as context and as an independent check")
    if tool == "similar_basins":
        return "gauged catchments most like this one in climate, terrain and land cover"
    if tool == "regionalize_signatures":
        return "flow signatures transferred from the donor catchments, with leave-one-out skill"
    rat = str(s.get("rationale") or "")
    return _first_clause(rat)


def _first_clause(text: str) -> str:
    t = " ".join(text.split())
    m = re.match(r"(.{20,220}?[.;])\s", t + " ")
    out = (m.group(1) if m else t[:220]).rstrip(".;")
    return out[:1].lower() + out[1:] if out else ""


def _ffa_section(doc: Document, f: Facts, placer: _Placer) -> None:
    doc.add(Heading("Design flood" if not f.asks_trend else "Flood magnitudes", level=2))
    sents = _flood_summary(f)[:2]
    lt = return_level_table(f)
    if lt is not None:
        sents.append("{tab:levels} gives the quantiles of each fit at every return period.")
    doc.add(Para(tx.clean_units(" ".join(sents))))
    doc.add(lt)
    fig = placer.take("frequency_curve")
    if fig is not None:
        doc.add(Para(_ffa_fig_para(f, fig.id)), fig)


def _ffa_fig_para(f: Facts, fid: str) -> str:
    rm = f.ffa.get("record_max") or {}
    s = [f"{{fig:{fid}}} plots the fits against the observed annual maxima on Gumbel probability paper."]
    at = _fits_at(f, _design_t(f))
    gev, lp3 = at.get("gev_lmoments"), at.get("lp3")
    if gev and lp3 and gev.get("q") and lp3.get("q"):
        spread = abs(gev["q"] - lp3["q"]) / max(gev["q"], lp3["q"]) * 100
        s.append(f"At {_t(_design_t(f))} years the two main fits differ by {spread:.0f} %, so the choice of "
                 f"distribution {'is not what limits' if spread < 10 else 'matters to'} the estimate.")
    if rm.get("value") is not None:
        u = f.ffa.get("unit")
        s.append(f"The largest flood in the record, {tx.value(rm['value'], u)} in {rm.get('year')}, sits at an "
                 f"empirical return period of about {tx.num(rm.get('empirical_return_period'), 2)} years.")
    return tx.clean_units(" ".join(s))


def _trend_section(doc: Document, f: Facts, placer: _Placer) -> None:
    tr = f.trend
    on_maxima = "max" in str(tr.get("on") or "").lower()
    if f.asks_trend:
        title = "Trend in annual maximum flow" if on_maxima else "Trend in annual flow"
    else:
        title = "Stationarity of the annual maxima" if on_maxima else "Trend in the annual means"
    doc.add(Heading(title, level=2))
    p = tr.get("p")
    sig = p is not None and p < 0.05
    series = tx.plural(int(tr.get("n") or 0), "annual maximum", "annual maxima") if on_maxima else \
        tx.plural(int(tr.get("n") or 0), "annual mean")
    s = [f"The Mann-Kendall test on {series} gives "
         f"p = {tx.p_value(p)} (Kendall's tau {tx.num(tr.get('tau'), 2)}), with a Sen slope of "
         f"{tx.value(tr.get('slope'), (tr.get('unit') or '') + ' per year')}."]
    if sig:
        s.append("The trend is significant at the 5 % level.")
    elif on_maxima:
        s.append("There is no significant monotonic trend at the 5 % level, which supports fitting a stationary "
                 "distribution.")
    else:
        s.append("There is no significant monotonic trend at the 5 % level. The test ran on the annual means; a "
                 "trend in the floods themselves would need the test on the annual maxima.")
    if f.change and f.change.get("p") is not None:
        ch = f.change
        if ch.get("significant"):
            s.append(f"The Pettitt test finds a significant step change around {ch.get('year')} "
                     f"(p = {tx.p_value(ch['p'])}), with the mean annual maximum moving from "
                     f"{tx.num(ch.get('before'))} to {tx.num(ch.get('after'))}.")
        else:
            s.append(f"The Pettitt test finds no significant step change (p = {tx.p_value(ch['p'])}).")
    fig = placer.take("trend")
    if fig is not None:
        s.append(f"{{fig:{fig.id}}} shows the series and the Sen slope.")
    doc.add(Para(tx.clean_units(" ".join(s))))
    doc.add(fig)


def _regional_section(doc: Document, f: Facts, placer: _Placer) -> None:
    reg = f.regional
    doc.add(Heading("Transfer from similar catchments", level=2))
    k = reg.get("k")
    est = reg.get("estimates") or {}
    skill = reg.get("skill") or {}
    s = [f"Flow signatures were transferred to the site from {k or 'the'} donor catchments that resemble it."]
    good = [(n, (skill.get(n) or {}).get("nse")) for n in est if isinstance(skill.get(n), dict)
            and (skill[n] or {}).get("nse") is not None]
    if good:
        best = max(good, key=lambda x: x[1])
        worst = min(good, key=lambda x: x[1])
        s.append(f"Their leave-one-out skill ranges from a Nash-Sutcliffe efficiency of {tx.num(worst[1], 2)} to "
                 f"{tx.num(best[1], 2)}; a signature with skill near zero is no better than the regional mean.")
    fig = placer.take("signatures_band")
    if fig is not None:
        s.append(f"{{fig:{fig.id}}} shows each signature with its band across donors.")
    doc.add(Para(" ".join(s)))
    doc.add(fig)


def _context_section(doc: Document, f: Facts, placer: _Placer) -> None:
    doc.add(Heading("Climate context and independent check", level=2))
    s = []
    cl = f.climate
    if cl:
        s.append(f"The ERA5 reanalysis gives a mean annual precipitation of {tx.value(cl.get('p'), 'mm')} and a "
                 f"reference evapotranspiration of {tx.value(cl.get('et0'), 'mm')} at the site"
                 + (f" over {tx.years(cl.get('years'))} ending {str(cl.get('end'))[:10]}" if cl.get("years") else "")
                 + (f", a {cl.get('aridity_class')} climate" if cl.get("aridity_class") else "") + ".")
    g = f.glofas
    if g:
        if g.get("comparable") is False:
            s.append("The GloFAS modelled discharge could not serve as an independent check: no model grid cell "
                     "could be verified as sharing the gauge's catchment, so the comparison was not made.")
        elif g.get("ratio") is not None:
            s.append(f"The GloFAS modelled mean flow is {tx.num(g['ratio'], 2)} times the observed mean at the "
                     f"nearest comparable grid cell.")
    fig = placer.take("glofas_series") if f.playbook == "ungauged_flow" else None
    mfig = placer.take("monthly_climate") if f.playbook in ("drought_status", "irrigation_feasibility",
                                                            "ungauged_flow", "climate_change") else None
    for fg in (fig, mfig):
        if fg is not None:
            s.append(f"{{fig:{fg.id}}} shows it.")
    if s:
        doc.add(Para(tx.clean_units(" ".join(s))))
    doc.add(fig, mfig)


_STEP_NOISE = re.compile(r"(Gates?:[^.]*\.|\bStep s\d+\b[^.]*?:|\(step s\d+\))", re.I)


def _generic_section(doc: Document, ws: Workspace, f: Facts, step: dict[str, Any], placer: _Placer,
                     wanted: tuple[str, ...]) -> None:
    tool = step["tool"]
    title = TOOL_WORDS.get(tool, tool.replace("_", " "))
    prose = f.prose.get(f"results-{step['id']}", "")
    prose = _STEP_NOISE.sub("", prose)
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", " ".join(prose.split())) if x and len(x) > 3]
    if not step.get("ran"):
        sentences = [f"This analysis did not complete: {step.get('error') or 'no usable result'}."]
    has_figure = any(a.kind == "figure" and a.step == step["id"] and a.media_type == "image/png"
                     for a in ws.artifacts)
    if not sentences and not has_figure:
        return
    doc.add(Heading(title[:1].upper() + title[1:], level=2))
    doc.add(Para(tx.clean_units(" ".join(sentences[:6]))) if sentences else None)
    for a in ws.artifacts:
        if a.kind != "figure" or a.step != step["id"] or a.media_type != "image/png":
            continue
        kind = _kind_of(a)
        if kind in wanted or not wanted:
            fig = placer.take(kind)
            if fig is not None:
                doc.add(Para(f"{{fig:{fig.id}}} shows the result."), fig)


def _limitations(ws: Workspace, f: Facts) -> list[str]:
    items = [tx.assumption(c) for c in f.conditions] + list(f.limitations)
    for ch in f.checks:
        if ch.verdict == "skipped":
            items.append(f"A check could not be run ({ch.sentence}): {_full_detail(ch.detail)}")
        elif ch.verdict == "failed":
            items.append(f"A check failed ({ch.sentence}): {_full_detail(ch.detail)}")
    items += f.caveats
    rep = ws.report or {}
    for x in [*((ws.critique or {}).get("not_established") or []), *(rep.get("not_established") or [])]:
        x = tx_clean(str(x))
        if x and not re.match(r"^Step s\d+, gate ", x):
            items.append(f"Not established by this study: {x[:1].lower() + x[1:]}")
    return _dedupe(items)[:12]


def _recommendations(f: Facts) -> list[str]:
    recs = []
    g = f.grade
    h = f.headline
    t = _design_t(f)
    if f.ffa and not f.asks_trend:
        at = _fits_at(f, t)
        main = at.get("gev_lmoments") or at.get("lp3") or at.get("gev_bootstrap")
        if main and main.get("q") is not None:
            u = f.ffa.get("unit")
            if g == "established":
                recs.append(f"Use {tx.value(main['q'], u)} as the {_t(t)}-year daily-mean flood, with the interval "
                            f"in {{tab:levels}}.")
            elif g == "indicative":
                recs.append(f"Treat {tx.value(main['q'], u)} as an indicative {_t(t)}-year daily-mean flood: adequate "
                            f"for options and sizing studies, and to be confirmed before final design.")
            else:
                recs.append(f"Use {tx.value(main['q'], u)} for screening only.")
            recs.append("Convert the daily-mean estimate to an instantaneous peak (a peak-to-daily ratio from the "
                        "agency's instantaneous record, or a regional ratio) before sizing a structure.")
    elif h.get("value") is not None:
        recs.append(f"Use the result as a{'n' if g in ('established', 'indicative') else ''} "
                    f"{GRADE_WORDS.get(g, g).lower()} estimate.")
    for w in f.would_change[:2]:
        m = re.match(r"^a longer record for (.+?):\s*(.+)$", w, re.I)
        if m:
            recs.append(f"A longer record would firm up the {m.group(1)}; the site check also notes that "
                        f"{m.group(2).rstrip('.')}.")
        else:
            recs.append(tx.sentence(f"What would strengthen the answer: {w[:1].lower() + w[1:]}"))
    for r in f.data_requests[:3]:
        recs.append(tx.sentence(f"Obtain {r['what'][:1].lower() + r['what'][1:]}" +
                                (f": {r['why'][:1].lower() + r['why'][1:]}" if r.get("why") else "")))
    recs.append("Have the study checked by a hydrologist before it is relied on; the checked-by line on the cover "
                "is blank until then.")
    return _dedupe(recs)


def _repro_para(f: Facts) -> str:
    s = [f"This document was generated by AquaScope {f.version} (study {f.workspace_id})."]
    if f.model:
        s.append(f"A language model ({f.model} via {f.provider}) planned the study and drafted parts of the "
                 f"interpretation; every number in this document was computed by the analyses, not by the model.")
    else:
        s.append("No language model was used: the plan came from a playbook and the text from templates.")
    snap = f.record.get("data_snapshot") if f.record else None
    if snap:
        s.append(f"The record analysed has the content hash {str(snap)[:23]}..., so a re-run can confirm it used "
                 f"the same data.")
    s.append("The bundle contains study.yaml, which replays every analysis and its checks with "
             "“aquascope run study.yaml”, the notebook study.ipynb, which does the same and redraws the figures, "
             "and workbook.xlsx with every table.")
    return " ".join(s)


# ── references ──────────────────────────────────────────────────────────────

#: Fuller forms of registry citations that arrive abbreviated. Each is a standard, verifiable reference.
_REF_FIX = {
    r"^Kendall \(1975\)\.?$": "Kendall, M. G. (1975). Rank Correlation Methods. 4th ed. Charles Griffin, London.",
}


def clean_references(refs: list[str]) -> list[str]:
    """The reference list: abbreviated entries expanded where the full form is standard, entries without an
    author and a year dropped (a bare claim with a DOI is a note, not a reference), duplicates of the same work
    (same title words) kept once, sorted by first author."""
    out: dict[str, str] = {}
    for r in refs:
        r = " ".join(str(r or "").split()).strip()
        for pat, full in _REF_FIX.items():
            if re.match(pat, r):
                r = full
        if not r:
            continue
        if not re.match(r"^[A-Z][A-Za-z'\-]+(,| et al| and|\s[A-Z]\.|\s\()", r) and "Open-Meteo" not in r \
                and "HydroATLAS" not in r and "AquaScope" not in r:
            continue
        title_key = _title_key(r)
        if title_key in out:
            if len(r) > len(out[title_key]):
                out[title_key] = r
            continue
        out[title_key] = r if r.endswith(".") else r + "."
    return sorted(out.values(), key=lambda x: x.lower())


def _title_key(ref: str) -> str:
    """The words of a reference's title (after the year), so two editions of Bulletin 17C collapse to one."""
    m = re.search(r"\((?:\d{4}[a-z]?|n\.d\.)\)\.?\s*(.+)", ref)
    body = m.group(1) if m else ref
    words = re.findall(r"[a-z]{4,}", body.lower())[:6]
    return " ".join(words) or ref.lower()


# ── the memorandum ──────────────────────────────────────────────────────────


def build_memo(ws: Workspace, style: HouseStyle | None = None, facts: Facts | None = None) -> Document:
    """The technical memorandum: the answer, its basis, one figure, the conditions, the recommendation, on two
    or three pages."""
    style = style or HouseStyle()
    f = facts or facts_of(ws)
    if is_failed_study(ws, f):
        return build_note(ws, style, f)
    title, sub = _title(f)
    doc = Document(title=title, subtitle=sub, kind="Technical memorandum", status=style.status,
                   meta={"organisation": style.author_line, "date": f.created, "site": f.site_label,
                         "reference": style.reference, "version": style.version})
    doc.add(KeyValue(_control_rows(f, style, "memo")))
    doc.add(Heading("Question"))
    q = f.question.strip()
    doc.add(Para(f"“{q.rstrip('.')}”" + (f" The answer informs a decision on {f.decision.rstrip('.')}."
                                         if f.decision else "")))
    doc.add(Heading("Answer"))
    doc.add(_answer_callout(f))
    doc.add(Para(" ".join(summary_sentences(f))))
    figs = _figures(ws)
    hero = None
    placer = _Placer(figs, {"frequency_curve": f.ffa.get("step", ""), "trend": f.trend.get("step", "")})
    for kind in HERO.get(f.playbook, ()) + ("frequency_curve", "trend", "signatures_band", "fdc", "series"):
        hero = placer.take(kind)
        if hero is not None:
            break
    lt = return_level_table(f) if f.ffa and not f.asks_trend else None
    if hero is not None or lt is not None:
        doc.add(Heading("Basis"))
        if lt is not None:
            # In a memo the table is cut to the design period and its neighbours.
            keep = _memo_rows(lt)
            lt.rows = [lt.rows[i] for i in keep]
            lt.emphasis = [keep.index(i) for i in lt.emphasis if i in keep]
            doc.add(lt)
        if hero is not None:
            doc.add(hero)
    lims = _limitations(ws, f)[:5]
    if lims:
        doc.add(Heading("Conditions and limitations"))
        doc.add(Bullets(lims))
    doc.add(Heading("Recommendation"))
    doc.add(Bullets(_recommendations(f), numbered=True))
    doc.add(Para(f"The full technical report (report.docx) gives the data, method, every check and the "
                 f"references; the workbook and study.yaml in the same bundle let a checker reproduce each "
                 f"number. AquaScope {f.version}, study {f.workspace_id}.", style="small"))
    doc.add(Signoff(_signoff_roles(style)[:2]))
    return doc.finalize()


def _memo_rows(t: Table) -> list[int]:
    n = len(t.rows)
    if n <= 4:
        return list(range(n))
    if t.emphasis:
        e = t.emphasis[0]
        keep = sorted({max(0, e - 2), max(0, e - 1), e, min(n - 1, e + 1)})
        return keep
    return list(range(n))[-4:]


# ── the study note (nothing established) ────────────────────────────────────


def build_note(ws: Workspace, style: HouseStyle | None = None, facts: Facts | None = None) -> Document:
    """One page for a study that established nothing: what was asked, what was tried, what failed in plain
    words, and what to do next. It is never dressed as a report."""
    style = style or HouseStyle()
    f = facts or facts_of(ws)
    doc = Document(title="The study could not be completed", subtitle=f.site_name or tx.coord(f.lat, f.lon),
                   kind="Study note", status="NOT ESTABLISHED",
                   meta={"organisation": style.author_line, "date": f.created, "site": f.site_label,
                         "reference": style.reference, "version": style.version})
    doc.add(KeyValue([("Question", f.question), ("Site", _site_sentence(f)), ("Date", f.created),
                      ("Study identifier", f"{f.workspace_id} (AquaScope {f.version})")]))
    doc.add(Callout(title="No answer", tone="fail", body=(
        "None of the analyses that should answer the question produced a result that passed its checks, so this "
        "note gives no number. Nothing below should be read as an estimate.")))
    doc.add(Heading("What was tried", numbered=False))
    doc.add(Bullets(_method_steps(ws, f) or ["No analysis ran."], numbered=True))
    if f.failures:
        doc.add(Heading("What failed", numbered=False))
        doc.add(Bullets([tx.sentence(f"The {x['what']}: {x['why']}") for x in f.failures][:8]))
    doc.add(Heading("What to do next", numbered=False))
    doc.add(Bullets(_next_steps(f), numbered=True))
    nt = nearby_table(f)
    if nt is not None:
        doc.add(Heading("Stations near the site", numbered=False))
        doc.add(nt)
    return doc.finalize()


def _next_steps(f: Facts) -> list[str]:
    out = []
    why = " ".join(x["why"] for x in f.failures).lower()
    if "network" in why or "could not be reached" in why:
        out.append("Check the internet connection and run the study again: at least one data service could not "
                   "be reached, which says nothing about the site.")
    unknown = [n for n in f.nearby if not n.get("years") and str(n.get("variable")) in ("discharge", "water_level")]
    if unknown:
        n = unknown[0]
        out.append(f"{n['name']} ({n['id']}) measures {str(n['variable']).replace('_', ' ')} "
                   f"{tx.num(n.get('km'), 2)} km from the site, but the catalogue does not know its record length. "
                   f"Ask the agency for its record, or name it with --at so the crew fetches it.")
    for r in f.data_requests[:3]:
        out.append(tx.sentence(f"Supply {r['what'][:1].lower() + r['what'][1:]}"))
    out.append("Attach a record of your own (a CSV of dates and values) with --data; the crew uses it in place of "
               "a catalogue record.")
    return _dedupe(out)
