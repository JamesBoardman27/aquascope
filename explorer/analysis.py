"""AquaScope Explorer: the Python half of "click a gauge, get the numbers".

This module runs unchanged in CPython (tests) and inside Pyodide in the
browser (``worker.js`` loads it and calls :func:`analyze_station`). It uses
only aquascope's public collectors and hydrology functions, so what the page
shows is exactly what ``pip install aquascope`` computes.

Everything returned is plain JSON: lists, dicts, numbers, strings, ``None``.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from aquascope.registry import SOURCES, build_collector

logger = logging.getLogger("aquascope.explorer")

RETURN_PERIODS = [2, 5, 10, 25, 50, 100]
MIN_YEARS_FOR_FFA = 10

METHODS: dict[str, dict[str, str]] = {
    "gev_lmoments": {
        "name": "GEV fitted by L-moments",
        "text": "Annual maxima (calendar years) fitted to a Generalized Extreme Value distribution with "
        "L-moment estimators (Hosking 1990); return levels from the fitted quantile function.",
        "citation": "Hosking, J. R. M. (1990). L-moments: analysis and estimation of distributions using linear "
        "combinations of order statistics. J. R. Stat. Soc. B, 52(1), 105-124.",
    },
    "lp3": {
        "name": "Log-Pearson III (Bulletin 17C style)",
        "text": "Log-transformed annual maxima fitted to a Pearson type III distribution; station skew, "
        "frequency factors and analytical confidence limits after Bulletin 17C.",
        "citation": "England, J. F. Jr. et al. (2018). Guidelines for determining flood flow frequency, "
        "Bulletin 17C. USGS Techniques and Methods 4-B5.",
    },
    "gev_bootstrap": {
        "name": "GEV (MLE, L-moment seeded) with bootstrap CI",
        "text": "Maximum-likelihood GEV seeded from L-moments with the shape bounded to |k| <= 0.5; "
        "90 % confidence bands from 1,000 bootstrap resamples of the annual maxima.",
        "citation": "Coles, S. (2001). An Introduction to Statistical Modeling of Extreme Values. Springer.",
    },
    "fdc": {
        "name": "Flow-duration curve",
        "text": "Empirical exceedance probabilities of daily flow (Weibull plotting positions); "
        "Q95 and Q10 read from the curve.",
        "citation": "Vogel, R. M., & Fennessey, N. M. (1994). Flow-duration curves I: new interpretation and "
        "confidence intervals. J. Water Resour. Plann. Manage., 120(4), 485-504.",
    },
    "trend": {
        "name": "Mann-Kendall trend on annual means",
        "text": "Non-parametric Mann-Kendall test with Sen's slope on the annual mean series.",
        "citation": "Mann, H. B. (1945). Nonparametric tests against trend. Econometrica, 13, 245-259; "
        "Sen, P. K. (1968). J. Am. Stat. Assoc., 63, 1379-1389.",
    },
}


def _iso(d: Any) -> str | None:
    if d is None:
        return None
    if isinstance(d, (datetime, pd.Timestamp)):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


def _clean(x: Any) -> Any:
    """Make numbers JSON-safe (NaN/inf -> None)."""
    if isinstance(x, float):
        return None if (math.isnan(x) or math.isinf(x)) else round(x, 4)
    return x


# ── fetching ────────────────────────────────────────────────────────────────


def _records_to_series(records: list, prefer: str | None = None) -> tuple[pd.Series | None, str, str]:
    """Turn a list of aquascope readings into (series, variable, unit).

    Handles StreamflowReading, WaterLevelReading, ClimateReading and
    WaterQualitySample (discharge / gage height / rainfall parameters).
    """
    if not records:
        return None, "", ""
    rows: list[tuple[datetime, float]] = []
    variable, unit = "", ""
    for r in records:
        name = type(r).__name__
        if name == "StreamflowReading":
            variable, unit = "discharge", getattr(r, "unit", "m3/s")
            rows.append((r.reading_datetime, float(r.discharge_cms)))
        elif name == "WaterLevelReading":
            variable, unit = "water_level", getattr(r, "unit", "m")
            rows.append((r.reading_datetime, float(r.water_level)))
        elif name == "ClimateReading":
            if r.parameter != "rainfall_mm":
                continue
            variable, unit = "precipitation", getattr(r, "unit", "mm")
            rows.append((r.sample_datetime, float(r.value)))
        elif name == "WaterQualitySample":
            p = (r.parameter or "").lower()
            if "discharge" in p or p == "q":
                var = "discharge"
            elif "gage" in p or "level" in p or p == "h":
                var = "water_level"
            elif "rain" in p or "precip" in p:
                var = "precipitation"
            else:
                continue
            if prefer and var != prefer:
                continue
            variable, unit = var, getattr(r, "unit", "")
            rows.append((r.sample_datetime, float(r.value)))
    if not rows:
        return None, "", ""
    s = pd.Series({t: v for t, v in rows}).sort_index()
    s.index = pd.to_datetime(s.index, utc=True).tz_localize(None)
    s = s[~s.index.duplicated(keep="last")]
    return s, variable, unit


def fetch_series(source: str, station_id: str, *, years: int = 40) -> dict[str, Any]:
    """Fetch the observed record for one station through aquascope's collectors.

    Returns ``{"series": pd.Series | None, "variable": str, "unit": str,
    "note": str}``. ``note`` explains record-length limits of the source.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}")
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(years * 365.25))
    note = ""

    if source == "usgs":
        number = station_id.split("-", 1)[-1]
        c = build_collector("usgs")
        span = int(years * 365.25)
        recs = c.collect(station_id=number, days=span, collection="daily", parameter="00060", max_items=None)
        s, var, unit = _records_to_series(recs)
        if s is None:
            recs = c.collect(station_id=number, days=span, collection="daily", parameter="00065", max_items=None)
            s, var, unit = _records_to_series(recs)
        note = "USGS daily values (NWIS), full period requested."
    elif source == "uk_ea":
        c = build_collector("uk_ea")
        measure = _uk_ea_pick_measure(c, station_id)
        s = None
        var = unit = ""
        if measure:
            recs = c.collect(measure=measure, min_date=start.isoformat(), max_date=end.isoformat(), max_items=None)
            s, var, unit = _records_to_series(recs)
        note = f"Environment Agency Hydrology API, measure {measure or 'n/a'}."
    elif source == "hubeau_hydrometrie":
        c = build_collector("hubeau_hydrometrie")
        recs = c.collect(code_station=station_id, grandeur_hydro="Q", days=30)
        s, var, unit = _records_to_series(recs)
        if s is None:
            recs = c.collect(code_station=station_id, grandeur_hydro="H", days=30)
            s, var, unit = _records_to_series(recs)
        note = (
            "Hub'Eau real-time observations cover the last 30 days; long daily records (obs_elab) come with "
            "#188 Phase 1."
        )
    elif source == "pegelonline":
        c = build_collector("pegelonline")
        recs = c.collect(station_id=station_id, timeseries=("Q", "W"), days=31)
        s, var, unit = _records_to_series(recs, prefer="discharge")
        if s is None:
            s, var, unit = _records_to_series(recs)
        note = "PEGELONLINE serves the last 31 days only."
    elif source == "ireland_opw":
        c = build_collector("ireland_opw")
        recs = c.collect(stations=[{"properties": {"ref": station_id}}])
        s, var, unit = _records_to_series(recs)
        note = "waterlevel.ie month file (15-minute levels, last month)."
    elif source == "taiwan_cwa":
        # CODIS answers one month per request, so 40 years is 480 round trips.
        # Ten years (~120 requests) keeps the click-to-chart wait tolerable.
        cwa_years = min(years, 10)
        cwa_start = end - timedelta(days=int(cwa_years * 365.25))
        c = build_collector("taiwan_cwa")
        recs = c.collect(station_ids=[station_id], start=cwa_start.isoformat(), end=end.isoformat())
        s, var, unit = _records_to_series(recs)
        note = f"CWA CODIS daily rainfall, last {cwa_years} years (one request per month at the source)."
    else:
        raise ValueError(f"{source} has no Explorer fetch path yet")

    return {"series": s, "variable": var, "unit": unit, "note": note}


# EA stations publish several measures per property (daily min / mean / max,
# 15-minute instantaneous). One series at a time: prefer the daily mean flow.
_UK_EA_PREFERENCE = (
    ("flow", 86400, "mean"),
    ("level", 86400, "mean"),
    ("rainfall", 86400, "total"),
    ("groundwaterLevel", 86400, "mean"),
    ("level", 86400, "max"),
    ("flow", 900, "instantaneous"),
)


def _uk_ea_pick_measure(collector, station_id: str) -> str | None:
    """Return the measure @id to fetch for a station (see ``_UK_EA_PREFERENCE``)."""
    try:
        data = collector.client.get_json(f"id/stations/{station_id}.json")
    except Exception as exc:  # noqa: BLE001
        logger.info("uk_ea station lookup failed for %s: %s", station_id, exc)
        return None
    items = data.get("items") or []
    station = items[0] if isinstance(items, list) and items else items
    measures = station.get("measures") or []
    if isinstance(measures, dict):
        measures = [measures]

    def stat(m: dict) -> str:
        v = m.get("valueStatistic")
        v = v.get("@id", "") if isinstance(v, dict) else str(v or "")
        return v.rsplit("/", 1)[-1]

    def notation(m: dict) -> str | None:
        mid = m.get("@id")
        return str(mid).rsplit("/", 1)[-1] if mid else None  # the collector wants the notation, not the URL

    for parameter, period, statistic in _UK_EA_PREFERENCE:
        for m in measures:
            if m.get("parameter") == parameter and int(m.get("period") or 0) == period and stat(m) == statistic:
                return notation(m)
    daily = [m for m in measures if int(m.get("period") or 0) == 86400 and m.get("@id")]
    if daily:
        return notation(daily[0])
    return notation(measures[0]) if measures else None


# ── analytics ───────────────────────────────────────────────────────────────


def _annual_max(s: pd.Series) -> pd.Series:
    daily = s.resample("D").mean()
    counts = daily.resample("YS").count()
    am = daily.resample("YS").max()
    # keep years with at least ~80 % coverage so a partial first/last year does not fake a low maximum
    return am[counts >= 292].dropna()


def analyze_series(s: pd.Series, variable: str, unit: str) -> dict[str, Any]:
    """Compute Phase-0 analytics for a series. Pure function, JSON-safe output."""
    from aquascope.hydrology.flood_frequency import fit_gev_lmoments, fit_lp3
    from aquascope.hydrology.flow_duration import flow_duration_curve

    s = s.dropna()
    out: dict[str, Any] = {
        "variable": variable,
        "unit": unit,
        "n": int(len(s)),
        "start": _iso(s.index.min()) if len(s) else None,
        "end": _iso(s.index.max()) if len(s) else None,
        "years": round((s.index.max() - s.index.min()).days / 365.25, 1) if len(s) > 1 else 0.0,
        "stats": {
            "mean": _clean(float(s.mean())) if len(s) else None,
            "median": _clean(float(s.median())) if len(s) else None,
            "min": _clean(float(s.min())) if len(s) else None,
            "max": _clean(float(s.max())) if len(s) else None,
        },
        "methods": [],
        "notes": [],
    }
    if not len(s):
        return out

    # hydrograph: daily means, capped at ~25k points for the browser
    daily = s.resample("D").mean().dropna()
    if len(daily) > 25_000:
        daily = daily.iloc[:: int(math.ceil(len(daily) / 25_000))]
    out["series"] = {"t": [d.strftime("%Y-%m-%d") for d in daily.index], "v": [_clean(float(v)) for v in daily.values]}

    am = _annual_max(s)
    out["annual_max"] = {"year": [int(y) for y in am.index.year], "v": [_clean(float(v)) for v in am.values]}

    if variable == "discharge":
        fdc = flow_duration_curve(daily)
        step = max(1, len(fdc.exceedance) // 200)
        out["fdc"] = {
            "exceedance": [_clean(float(x)) for x in fdc.exceedance[::step]],
            "q": [_clean(float(x)) for x in fdc.discharge[::step]],
            "q95": _clean(float(fdc.percentiles.get(95, float("nan")))),
            "q50": _clean(float(fdc.percentiles.get(50, float("nan")))),
            "q10": _clean(float(fdc.percentiles.get(10, float("nan")))),
        }
        out["methods"].append(METHODS["fdc"])

        if len(am) >= MIN_YEARS_FOR_FFA:
            ffa: dict[str, Any] = {"n_years": int(len(am)), "return_periods": RETURN_PERIODS, "fits": {}}
            try:
                g = fit_gev_lmoments(am, return_periods=RETURN_PERIODS)
                ffa["fits"]["gev_lmoments"] = {
                    "q": [_clean(float(g.return_periods[rp])) for rp in RETURN_PERIODS],
                    "params": [_clean(float(p)) for p in g.params],
                }
                out["methods"].append(METHODS["gev_lmoments"])
            except Exception as exc:  # noqa: BLE001
                ffa["fits"]["gev_lmoments"] = {"error": str(exc)}
            try:
                lp3 = fit_lp3(am, return_periods=RETURN_PERIODS, ci_level=0.90)
                ffa["fits"]["lp3"] = {
                    "q": [_clean(float(lp3.return_periods[rp])) for rp in RETURN_PERIODS],
                    "ci": [[_clean(float(a)), _clean(float(b))] for a, b in
                           (lp3.confidence_intervals.get(rp, (float("nan"), float("nan"))) for rp in RETURN_PERIODS)],
                    "params": [_clean(float(p)) for p in lp3.params],
                }
                out["methods"].append(METHODS["lp3"])
            except Exception as exc:  # noqa: BLE001
                ffa["fits"]["lp3"] = {"error": str(exc)}
            out["ffa"] = ffa
        else:
            out["notes"].append(
                f"Flood frequency needs at least {MIN_YEARS_FOR_FFA} complete years of daily flow; this record has "
                f"{len(am)}."
            )

    if len(am) >= 8:
        try:
            from aquascope.analysis.trends import mann_kendall, sens_slope

            annual_mean = s.resample("YS").mean().dropna()
            mk = mann_kendall(annual_mean.values)
            slope = sens_slope(annual_mean.values)
            out["trend"] = {
                "on": "annual mean",
                "p_value": _clean(float(mk.p_value)),
                "tau": _clean(float(mk.tau)),
                "trend": str(mk.trend),
                "sens_slope_per_year": _clean(float(slope.slope)),
                "n_years": int(mk.n_samples),
            }
            out["methods"].append(METHODS["trend"])
        except Exception as exc:  # noqa: BLE001
            logger.info("trend skipped: %s", exc)
    return out


def flood_ci(s: pd.Series) -> dict[str, Any]:
    """The slow part: bootstrap GEV confidence bands (called on demand)."""
    from aquascope.hydrology.flood_frequency import fit_gev

    am = _annual_max(s.dropna())
    r = fit_gev(am, return_periods=RETURN_PERIODS, ci_level=0.90)
    return {
        "q": [_clean(float(r.return_periods[rp])) for rp in RETURN_PERIODS],
        "ci": [[_clean(float(a)), _clean(float(b))] for a, b in
               (r.confidence_intervals.get(rp, (float("nan"), float("nan"))) for rp in RETURN_PERIODS)],
        "params": [_clean(float(p)) for p in r.params],
        "method": METHODS["gev_bootstrap"],
    }


def analyze_station(
    source: str, station_id: str, *, years: int = 40, store: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Fetch + analyse one station. The entry point the browser worker calls.

    Pass ``store`` (any dict) to keep the fetched pandas Series under
    ``store["series"]`` for follow-up calls such as :func:`flood_ci` and
    :func:`to_csv` without a second fetch.
    """
    meta = SOURCES[source]
    fetched = fetch_series(source, station_id, years=years)
    if store is not None:
        store["series"] = fetched["series"]
        store["source"], store["station_id"] = source, station_id
    result: dict[str, Any] = {
        "source": source,
        "station_id": station_id,
        "agency": meta.agency,
        "license": meta.license,
        "attribution": meta.attribution,
        "fetch_note": fetched["note"],
    }
    s = fetched["series"]
    if s is None or s.empty:
        result.update({"n": 0, "error": "The source returned no observations for this station."})
        return result
    result.update(analyze_series(s, fetched["variable"], fetched["unit"]))
    return result


def to_csv(result: dict[str, Any]) -> str:
    """CSV of the daily series in a result dict (for the download button)."""
    series = result.get("series") or {"t": [], "v": []}
    unit = result.get("unit", "")
    lines = [f"date,{result.get('variable', 'value')}_{unit}".replace("/", "_per_")]
    lines += [f"{t},{'' if v is None else v}" for t, v in zip(series["t"], series["v"])]
    return "\n".join(lines) + "\n"
