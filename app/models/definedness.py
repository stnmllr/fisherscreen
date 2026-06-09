"""DefinednessOutcome enum — shared between screener_record and metric_definedness."""
from __future__ import annotations

from enum import Enum


class DefinednessOutcome(str, Enum):
    METRIK_NA = "METRIK_NA"        # Fisher framework not applicable -> set record.metric_na, drop
    DEFINED = "DEFINED"            # has a real margin metric -> continue to the gross_margin gate
    UNASSESSABLE = "UNASSESSABLE"  # statement could not be fetched/assessed -> resolution divert
