import pandas as pd

from can_logger.anomaly_detector import AnomalyDetector

FEATURES = ["EngineSpeed", "ThrottlePosition", "EngineLoad"]


def test_multivariate_alert_text_rounds_values_for_display():
    rows = [
        {"timestamp": i * 0.1, "EngineSpeed": 1500.0 + i * 10, "ThrottlePosition": 20.0, "EngineLoad": 25.0}
        for i in range(20)
    ]
    # 150 * 0.392 is 58.800000000000004 in floating point
    rows.append({"timestamp": 2.1, "EngineSpeed": 4800.0, "ThrottlePosition": 0.0, "EngineLoad": 150 * 0.392})

    alerts = AnomalyDetector(contamination=0.1).detect_multivariate_faults(pd.DataFrame(rows), FEATURES)

    flagged = [a for a in alerts if a["values"]["EngineSpeed"] == 4800.0]
    assert flagged
    assert "EngineLoad=58.8" in flagged[0]["description"]
    assert "58.800000000000004" not in flagged[0]["description"]
