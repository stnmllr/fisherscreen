import csv
import json

from app.output.funnel_artifacts import write_funnel_artifacts
from app.screener.funnel import (
    Dropout, FunnelStage, FunnelSummary, ReasonCode, SeverityBucket, Stage,
)


def _summary():
    stages = [FunnelStage(Stage.UNIVERSE, 3, 0, 3),
              FunnelStage(Stage.RESOLUTION, 3, 1, 2)]
    return FunnelSummary(stages=stages, review_flags=1, pass_through_count=0,
                         provenance={"stoxx_tier": "wikipedia"})


def _dropout():
    return Dropout("VOL", Stage.BASIS_GATES, ReasonCode.GATE_VOLUME,
                   SeverityBucket.REVIEW, True, False, 5e9, "Technology")


def test_writes_json_and_csv(tmp_path):
    paths = write_funnel_artifacts(_summary(), [_dropout()], tmp_path, "2026-06")
    names = {p.name for p in paths}
    assert names == {"2026-06-funnel_summary.json", "2026-06-dropouts.csv"}

    js = json.loads((tmp_path / "Universum" / "2026-06-funnel_summary.json").read_text("utf-8"))
    assert js["review_flags"] == 1
    assert js["provenance"]["stoxx_tier"] == "wikipedia"

    rows = list(csv.DictReader((tmp_path / "Universum" / "2026-06-dropouts.csv").read_text("utf-8").splitlines()))
    assert rows[0]["ticker"] == "VOL"
    assert rows[0]["reason_code"] == "GATE_VOLUME"
    assert rows[0]["severity_bucket"] == "REVIEW"
    assert rows[0]["is_large_cap"] == "True"
