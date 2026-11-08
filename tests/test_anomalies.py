import os
import sys
import pytest
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from can_logger.anomaly_detector import AnomalyDetector

def test_rolling_zscore_detects_spike():
    detector = AnomalyDetector(z_threshold=2.5)
    # Baseline steady temperature at 90C +/- 1 with one 145C severe spike
    temps = [90.0, 90.5, 91.0, 89.5, 90.2, 90.8, 89.9, 90.1, 90.4, 145.0]
    df = pd.DataFrame({
        "timestamp": [i * 0.1 for i in range(len(temps))],
        "CoolantTempC": temps
    })

    alerts = detector.detect_zscore_anomalies(df, "CoolantTempC", window=5, min_std=1.0)
    assert len(alerts) >= 1
    assert any(a["value"] == 145.0 for a in alerts)
    assert alerts[-1]["type"] == "ROLLING_Z_SCORE"

def test_multivariate_fault_detection():
    detector = AnomalyDetector(contamination=0.1)
    # 20 steady baseline rows + 1 extreme outlier
    data = []
    for i in range(20):
        data.append({"timestamp": i * 0.1, "EngineSpeed": 1500 + i * 10, "ThrottlePosition": 20.0, "EngineLoad": 25.0})
    # Implausible outlier: High RPM with 0 throttle and max load
    data.append({"timestamp": 2.1, "EngineSpeed": 7200.0, "ThrottlePosition": 0.0, "EngineLoad": 99.0})

    df = pd.DataFrame(data)
    alerts = detector.detect_multivariate_faults(df, ["EngineSpeed", "ThrottlePosition", "EngineLoad"])
    assert len(alerts) >= 1
    assert any(a["values"]["EngineSpeed"] == 7200.0 for a in alerts)
