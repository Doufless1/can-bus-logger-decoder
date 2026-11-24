import os

from can_logger.pipeline import run_pipeline
from can_logger.replay_harness import TraceReplayHarness

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE = os.path.join(ROOT, "data", "sample_trace.csv")
DBC = os.path.join(ROOT, "data", "powertrain.dbc")


def test_pipeline_decodes_every_frame_of_the_sample_trace():
    result = run_pipeline(TRACE, DBC, speed_multiplier=1000.0)

    assert result.stats["total_received"] == 25
    assert result.stats["dropped_frames"] == 0
    assert len(result.captured_frames) == 25
    assert len(result.timeseries) == 25


def test_pipeline_reports_the_real_drop_count_when_the_buffer_is_too_small():
    result = run_pipeline(TRACE, DBC, speed_multiplier=1000.0, buffer_capacity=5)

    assert result.stats["total_received"] == 25
    assert result.stats["dropped_frames"] == 20
    assert len(result.captured_frames) == 5


def test_pipeline_finds_the_anomalies_injected_in_the_sample_trace():
    result = run_pipeline(TRACE, DBC, speed_multiplier=1000.0)

    assert any(a["value"] == 145.0 for a in result.zscore_alerts)
    assert len(result.multivariate_alerts) >= 1


def test_pipeline_can_log_the_captured_frames_to_csv(tmp_path):
    out = tmp_path / "captured.csv"

    result = run_pipeline(TRACE, DBC, speed_multiplier=1000.0, log_csv=str(out))

    logged = TraceReplayHarness(str(out)).load_frames()
    assert len(logged) == len(result.captured_frames) == 25
