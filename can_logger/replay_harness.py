"""
Trace Replay Test Harness: Replays recorded CAN traces with microsecond precision.
"""

import time
import pandas as pd
from typing import List, Generator, Optional
from .core import CANFrame, VirtualCANBus

class TraceReplayHarness:
    def __init__(self, trace_path: str):
        self.trace_path = trace_path

    def load_frames(self) -> List[CANFrame]:
        """Loads and parses raw CAN frames from CSV."""
        df = pd.read_csv(self.trace_path)
        frames = []
        for _, row in df.iterrows():
            arb_id = int(str(row["arbitration_id"]), 16) if str(row["arbitration_id"]).startswith("0x") else int(row["arbitration_id"])
            data_bytes = bytes.fromhex(str(row["data_hex"]))
            frames.append(CANFrame(
                timestamp=float(row["timestamp"]),
                arbitration_id=arb_id,
                is_extended=bool(row["is_extended"]),
                dlc=int(row["dlc"]),
                data=data_bytes
            ))
        return frames

    def replay_to_bus(self, bus: VirtualCANBus, speed_multiplier: float = 1.0, inject_fault: bool = False) -> int:
        """
        Replays recorded frames into the given CAN bus, preserving inter-frame delay.
        """
        frames = self.load_frames()
        if not frames:
            return 0

        count = 0
        prev_ts = frames[0].timestamp

        for i, frame in enumerate(frames):
            delta = (frame.timestamp - prev_ts) / max(speed_multiplier, 0.001)
            if delta > 0:
                time.sleep(min(delta, 0.05))  # Sleep up to delta, capped for test runs
            prev_ts = frame.timestamp

            # Optional synthetic fault injection
            if inject_fault and i == len(frames) // 2:
                # Corrupt payload
                corrupt_frame = CANFrame(
                    timestamp=frame.timestamp,
                    arbitration_id=frame.arbitration_id,
                    is_extended=frame.is_extended,
                    dlc=frame.dlc,
                    data=b"\xFF" * frame.dlc
                )
                bus.send(corrupt_frame)
            else:
                bus.send(frame)
            count += 1

        return count
