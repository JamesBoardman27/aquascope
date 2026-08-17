"""The Archive: harvest AquaScope's sources into open, cloud-native files.

Phase 0 (#188) harvests every station catalog into ``stations.parquet``
(GeoParquet), ``stations.geojson`` and a ``health.json`` status report, and
publishes the folder to a public Hugging Face dataset. Observations follow in
Phase 1. Only sources whose terms allow it are ever mirrored; the registry's
``redistributable`` flag is the gate.

Requires the ``archive`` extra (``pip install "aquascope[archive]"``).
"""

from aquascope.archive.harvest import HarvestReport, harvest_stations, write_dataset_card
from aquascope.archive.publish import publish_folder

__all__ = ["HarvestReport", "harvest_stations", "publish_folder", "write_dataset_card"]
