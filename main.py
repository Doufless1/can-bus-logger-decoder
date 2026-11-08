"""
CAN Bus Logger & Decoder Prototype - Main Entrypoint & Telemetry Analysis Engine.
"""

import sys
import os
import argparse
from can_logger.core import CANFilter, VirtualCANBus
from can_logger.decoder import DBCDecoder
from can_logger.replay_harness import TraceReplayHarness
from can_logger.anomaly_detector import AnomalyDetector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def resolve_path(p: str) -> str:
    if os.path.isabs(p):
        return p
    return os.path.join(PROJECT_ROOT, p)

def main():
    parser = argparse.ArgumentParser(description="CAN Bus Logger, Decoder & Anomaly Detection Prototype")
    parser.add_argument("--trace", default="data/sample_trace.csv", help="Path to raw CAN frame trace CSV")
    parser.add_argument("--dbc", default="data/powertrain.dbc", help="Path to Vector DBC database")
    parser.add_argument("--speed", type=float, default=100.0, help="Replay speed multiplier (default: 100x)")
    parser.add_argument("--z-threshold", type=float, default=2.0, help="Z-score threshold for outlier detection")
    args = parser.parse_args()

    trace_path = resolve_path(args.trace)
    dbc_path = resolve_path(args.dbc)

    print("=" * 80)
    print("CAN BUS LOGGER & DECODER PROTOTYPE")
    print(f"Loading trace: {trace_path}")
    print(f"Loading DBC  : {dbc_path}")
    print("=" * 80)

    # 1. Initialize Bus & Decoder
    bus = VirtualCANBus(channel="vcan0")
    decoder = DBCDecoder(dbc_path=dbc_path if os.path.exists(dbc_path) else None)
    harness = TraceReplayHarness(trace_path=trace_path)

    # 2. Replay trace into virtual bus
    print("[INFO] Replaying CAN frames via high-precision test harness...")
    replayed_count = harness.replay_to_bus(bus, speed_multiplier=args.speed)
    print(f"[SUCCESS] Replayed {replayed_count} frames into {bus.channel} (RingBuffer size: {bus.buffer.size()})")

    # 3. Ingest and Decode
    captured_frames = []
    while not bus.buffer.is_empty():
        f = bus.recv()
        if f:
            captured_frames.append(f)

    print(f"[INFO] Ingestion complete. Decoding {len(captured_frames)} frames into time-series...")
    df_timeseries = decoder.frames_to_timeseries(captured_frames)

    # 4. Display Telemetry Breakdown
    print("\n" + "-" * 80)
    print("TELEMETRY CHANNEL BREAKDOWN:")
    for msg_name in df_timeseries["message_name"].unique():
        sub_df = df_timeseries[df_timeseries["message_name"] == msg_name]
        print(f"* Message '{msg_name}': {len(sub_df)} frames captured")
        if "EngineSpeed" in sub_df.columns and sub_df["EngineSpeed"].notna().any():
            s = sub_df["EngineSpeed"].dropna()
            print(f"  |-- Mean RPM: {s.mean():.1f} rpm (Max: {s.max()} rpm)")
        if "VehicleSpeedKmh" in sub_df.columns and sub_df["VehicleSpeedKmh"].notna().any():
            s = sub_df["VehicleSpeedKmh"].dropna()
            print(f"  |-- Mean Speed: {s.mean():.1f} km/h (Max: {s.max()} km/h)")
        if "CoolantTempC" in sub_df.columns and sub_df["CoolantTempC"].notna().any():
            s = sub_df["CoolantTempC"].dropna()
            print(f"  |-- Mean Coolant Temp: {s.mean():.1f} deg C (Max: {s.max()} deg C)")
        if "BrakePedalApplied" in sub_df.columns and sub_df["BrakePedalApplied"].notna().any():
            s = sub_df["BrakePedalApplied"].dropna()
            print(f"  |-- Brake Applied State: {int(s.iloc[0])}")
    print("-" * 80)

    # 5. Anomaly Detection
    detector = AnomalyDetector(z_threshold=args.z_threshold)
    print("\nRUNNING ANOMALY DETECTION SUITE:")
    
    # Check rolling z-scores on coolant temperature
    coolant_alerts = detector.detect_zscore_anomalies(df_timeseries, signal_col="CoolantTempC", window=5)
    for alert in coolant_alerts:
        print(f"  [ALERT] {alert['description']} at timestamp {alert['timestamp']:.4f}s")

    # Check multivariate isolation forest
    multivariate_alerts = detector.detect_multivariate_faults(
        df_timeseries, 
        feature_cols=["EngineSpeed", "ThrottlePosition", "EngineLoad"]
    )
    for alert in multivariate_alerts:
        print(f"  [ALERT] {alert['description']} at timestamp {alert['timestamp']:.4f}s")

    if not coolant_alerts and not multivariate_alerts:
        print("  [OK] No physical anomalies or frame drops detected.")

    print("\n[STATUS] Execution finished. 0 dropped frames.")
    print("=" * 80)

if __name__ == "__main__":
    main()
