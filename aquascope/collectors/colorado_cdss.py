"""
Collector for Colorado CDSS (Colorado Department of Statewide Transportation) water data.

API docs:
https://dwr.state.co.us/Rest/GET/Help/Api/GET-api-v2-telemetrystations-telemetrytimeseriesraw
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from aquascope.collectors.base import BaseCollector
from aquascope.schemas.water_data import DataSource, StreamflowReading
from aquascope.utils.http_client import CachedHTTPClient

logger = logging.getLogger(__name__)

CDSS_BASE_URL = "https://dwr.state.co.us/Rest/GET/api/v2/"
TELEMETRY_PATH = "telemetrystations/telemetrytimeseriesraw"
CFS_TO_CMS = 0.028316846592


class ColoradoCDSSCollector(BaseCollector):
    """
    Collector for Colorado CDSS (Colorado Department of Statewide Transportation) water data.
    """

    name = "colorado_cdss"

    def __init__(self, api_key: str | None = None, client: CachedHTTPClient | None = None):
        super().__init__(client or CachedHTTPClient(base_url=CDSS_BASE_URL))
        self.api_key = api_key

    def fetch_raw(
        self,
        *,
        abbrev: str,
        parameter: str = "DISCHRG",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Fetch raw data from the Colorado CDSS API.
        Parameters
        ----------
        abbrev
            CDSS station abbreviation. Multiple abbreviations may be supplied
            as a comma-separated string.
        parameter
            CDSS telemetry parameter. ``DISCHRG`` is discharge.
        **kwargs
            Additional CDSS query parameters, such as date filters.
        """
        if not abbrev or not abbrev.strip():
            raise ValueError("Colorado CDSS: 'abbrev' is required.")

        params: dict[str, Any] = {
            "format": "json",
            "abbrev": abbrev.strip(),
            "parameter": parameter,
            **kwargs,
        }

        if self.api_key:
            params["apiKey"] = self.api_key
        data = self.client.get_json(TELEMETRY_PATH, params=params)
        if not isinstance(data, list):
            logger.warning("Colorado CDSS: expected a list response, received %s.", type(data).__name__)
            return []
        return [row for row in data if isinstance(row, dict)]

    def normalise(
        self,
        raw: list[dict[str, Any]],
    ) -> Sequence[StreamflowReading]:
        """Convert CDSS discharge readings from cfs to m³/s."""

        readings: list[StreamflowReading] = []

        for row in raw:
            try:
                station_id = str(row["abbrev"]).strip()
                datetime_value = row["measDateTime"]
                discharge_cfs = float(row["measValue"])
                unit = str(row["measUnit"]).strip().lower()
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("Colorado CDSS: skipping malformed row: %s", exc)
                continue

            if not station_id or not datetime_value:
                logger.debug("Colorado CDSS: skipping row with missing station or datetime.")
                continue

            if unit not in {"cfs", "ft3/s", "ft³/s"}:
                logger.debug(
                    "Colorado CDSS: skipping unsupported discharge unit %r.",
                    row.get("measUnit"),
                )
                continue

            try:
                reading_datetime = datetime.fromisoformat(str(datetime_value).replace("Z", "+00:00"))
            except ValueError:
                logger.debug(
                    "Colorado CDSS: skipping invalid datetime %r.",
                    datetime_value,
                )
                continue

            readings.append(
                StreamflowReading(
                    source=DataSource.COLORADO_CDSS,
                    station_id=station_id,
                    station_name=None,
                    location=None,
                    reading_datetime=reading_datetime,
                    discharge_cms=discharge_cfs * CFS_TO_CMS,
                    source_type="in_situ",
                    unit="m3/s",
                    remark=_build_remark(row),
                )
            )

        return readings


def _build_remark(row: dict[str, Any]) -> str | None:
    """Combine non-empty CDSS quality flags into one remark."""
    flags = [f"{field}={row[field]}" for field in ("flagA", "flagB") if row.get(field) not in (None, "")]
    return "; ".join(flags) or None
