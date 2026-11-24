"""
The whole flow in one function: replay a trace into a bus, drain the frames,
optionally save them to CSV, decode them with the DBC and run the anomaly checks.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .anomaly_detector import AnomalyDetector
from .core import CANFrame, VirtualCANBus
from .decoder import DBCDecoder
from .replay_harness import TraceReplayHarness
from .storage import CSVFrameLogger

FEATURE_COLUMNS = ["EngineSpeed", "ThrottlePosition", "EngineLoad"]


@dataclass
class PipelineResult:
    replayed_count: int
    stats: Dict[str, int]
    captured_frames: List[CANFrame]
    timeseries: pd.DataFrame
    zscore_alerts: List[Dict[str, Any]]
    multivariate_alerts: List[Dict[str, Any]]


def run_pipeline(
    trace_path: str,
    dbc_path: Optional[str] = None,
    speed_multiplier: float = 100.0,
    z_threshold: float = 2.0,
    buffer_capacity: int = 50000,
    log_csv: Optional[str] = None,
) -> PipelineResult:
    bus = VirtualCANBus(channel="vcan0", buffer_capacity=buffer_capacity)
    decoder = DBCDecoder(dbc_path=dbc_path if dbc_path and os.path.exists(dbc_path) else None)

    replayed = TraceReplayHarness(trace_path=trace_path).replay_to_bus(bus, speed_multiplier=speed_multiplier)

    captured = []
    while not bus.buffer.is_empty():
        frame = bus.recv()
        if frame:
            captured.append(frame)

    if log_csv:
        with CSVFrameLogger(log_csv) as logger:
            for frame in captured:
                logger.write(frame)

    timeseries = decoder.frames_to_timeseries(captured)
    detector = AnomalyDetector(z_threshold=z_threshold)
    zscore_alerts = detector.detect_zscore_anomalies(timeseries, signal_col="CoolantTempC", window=5)
    multivariate_alerts = detector.detect_multivariate_faults(timeseries, feature_cols=FEATURE_COLUMNS)

    return PipelineResult(
        replayed_count=replayed,
        stats=bus.buffer.stats(),
        captured_frames=captured,
        timeseries=timeseries,
        zscore_alerts=zscore_alerts,
        multivariate_alerts=multivariate_alerts,
    )
