"""
Anomaly detection engine: Rolling-window Z-Score and Multivariate Isolation Forest.
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

class AnomalyDetector:
    """
    Dual-stage anomaly detector for physical automotive telemetry.
    Stage 1: Univariate rolling-window Z-score (sudden physical deviations/spikes)
    Stage 2: Multivariate Isolation Forest (implausible cross-signal states)
    """
    def __init__(self, z_threshold: float = 3.0, contamination: float = 0.1):
        self.z_threshold = z_threshold
        self.contamination = contamination

    def detect_zscore_anomalies(self, df: pd.DataFrame, signal_col: str, window: int = 5, min_std: float = 1.0) -> List[Dict[str, Any]]:
        """
        Calculates running mean and standard deviation over preceding sliding window.
        Uses historical baseline (shift=1) with a minimum std floor to avoid zero-division.
        """
        alerts = []
        if signal_col not in df.columns:
            return alerts

        series = df[signal_col].dropna()
        if len(series) < window:
            return alerts

        # Historical rolling baseline (preceding frames)
        hist_mean = series.shift(1).rolling(window=window, min_periods=2).mean().bfill()
        hist_std = series.shift(1).rolling(window=window, min_periods=2).std().fillna(min_std)
        hist_std = np.maximum(hist_std, min_std)

        z_scores = (series - hist_mean) / hist_std

        outliers = series[z_scores.abs() > self.z_threshold]
        for idx, val in outliers.items():
            ts = df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx
            z_val = round(float(z_scores[idx]), 2)
            alerts.append({
                "type": "ROLLING_Z_SCORE",
                "signal": signal_col,
                "timestamp": ts,
                "value": val,
                "z_score": z_val,
                "description": f"Signal '{signal_col}' spiked to {val} (z-score: {z_val})"
            })
        return alerts

    def detect_multivariate_faults(self, df: pd.DataFrame, feature_cols: List[str]) -> List[Dict[str, Any]]:
        """
        Identifies cross-sensor correlation anomalies using Isolation Forest or heuristic validation.
        """
        alerts = []
        available_cols = [c for c in feature_cols if c in df.columns]
        if len(available_cols) < 2:
            return alerts

        subset = df[available_cols].dropna()
        if len(subset) < 5:
            return alerts

        if HAS_SKLEARN:
            contam = max(self.contamination, 0.05)
            clf = IsolationForest(
                n_estimators=100, 
                max_samples=min(len(subset), 256), 
                contamination=contam, 
                random_state=42
            )
            preds = clf.fit_predict(subset)
            anomaly_indices = subset.index[preds == -1]

            for idx in anomaly_indices:
                row = subset.loc[idx]
                ts = df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx
                values_summary = ", ".join([f"{col}={row[col]}" for col in available_cols])
                alerts.append({
                    "type": "ISOLATION_FOREST_MULTIVARIATE",
                    "timestamp": ts,
                    "signals": available_cols,
                    "values": row.to_dict(),
                    "description": f"Implausible correlation detected: {values_summary}"
                })
        else:
            # Domain-rule fallback: RPM > 4000 while Throttle == 0 and Load > 80
            for idx, row in subset.iterrows():
                rpm = row.get("EngineSpeed", 0)
                tps = row.get("ThrottlePosition", 0)
                load = row.get("EngineLoad", 0)
                if rpm > 4000 and tps == 0 and load > 80:
                    alerts.append({
                        "type": "IMPLAUSIBLE_TELEMETRY_HEURISTIC",
                        "timestamp": df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx,
                        "signals": available_cols,
                        "values": row.to_dict(),
                        "description": f"Implausible physics: High RPM ({rpm}) with Zero Throttle"
                    })
        return alerts
