"""
CAN Bus Logger & Decoder prototype - command line entry point.

Replays a recorded CAN trace, decodes it with a DBC file and checks the decoded
signals for anomalies.
"""

import argparse
import os

from can_logger.pipeline import run_pipeline

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def resolve_path(p: str) -> str:
    if os.path.isabs(p):
        return p
    return os.path.join(PROJECT_ROOT, p)


def print_channel_summary(timeseries):
    print("TELEMETRY CHANNEL BREAKDOWN:")
    for msg_name in timeseries["message_name"].unique():
        sub_df = timeseries[timeseries["message_name"] == msg_name]
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


def main():
    parser = argparse.ArgumentParser(description="CAN Bus Logger, Decoder & Anomaly Detection Prototype")
    parser.add_argument("--trace", default="data/sample_trace.csv", help="Path to raw CAN frame trace CSV")
    parser.add_argument("--dbc", default="data/powertrain.dbc", help="Path to DBC database")
    parser.add_argument("--speed", type=float, default=100.0, help="Replay speed multiplier (default: 100x)")
    parser.add_argument("--z-threshold", type=float, default=2.0, help="Z-score threshold for outlier detection")
    parser.add_argument("--buffer-capacity", type=int, default=50000, help="Ring buffer size in frames")
    parser.add_argument("--log-csv", default=None, help="Also save the captured raw frames to this CSV file")
    args = parser.parse_args()

    trace_path = resolve_path(args.trace)
    dbc_path = resolve_path(args.dbc)

    print("=" * 80)
    print("CAN BUS LOGGER & DECODER PROTOTYPE")
    print(f"Loading trace: {trace_path}")
    print(f"Loading DBC  : {dbc_path}")
    print("=" * 80)

    result = run_pipeline(
        trace_path,
        dbc_path,
        speed_multiplier=args.speed,
        z_threshold=args.z_threshold,
        buffer_capacity=args.buffer_capacity,
        log_csv=args.log_csv,
    )

    print(f"[INFO] Replayed {result.replayed_count} frames into the virtual bus")
    print(f"[INFO] Captured {len(result.captured_frames)} frames, decoded {len(result.timeseries)} into the time series")
    if args.log_csv:
        print(f"[INFO] Raw frames saved to {args.log_csv}")

    if result.timeseries.empty:
        print("[WARN] No frames could be decoded with this DBC file.")
    else:
        print("\n" + "-" * 80)
        print_channel_summary(result.timeseries)
        print("-" * 80)

    print("\nANOMALY DETECTION:")
    for alert in result.zscore_alerts + result.multivariate_alerts:
        print(f"  [ALERT] {alert['description']} at timestamp {alert['timestamp']:.4f}s")
    if not result.zscore_alerts and not result.multivariate_alerts:
        print("  [OK] No anomalies detected.")

    dropped = result.stats["dropped_frames"]
    print(f"\n[STATUS] Frames received: {result.stats['total_received']}, dropped: {dropped}")
    if dropped:
        print("[WARN] The ring buffer was full; raise --buffer-capacity to keep every frame.")
    print("=" * 80)


if __name__ == "__main__":
    main()
