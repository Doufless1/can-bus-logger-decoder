"""
Writes captured CAN frames to disk as CSV, in the same format the trace replay
harness reads (timestamp, arbitration_id, is_extended, dlc, data_hex).
"""

from .core import CANFrame


class CSVFrameLogger:
    HEADER = "timestamp,arbitration_id,is_extended,dlc,data_hex\n"

    def __init__(self, path: str):
        self.path = path
        self.frames_written = 0
        self._file = None

    def __enter__(self):
        self._file = open(self.path, "w", newline="")
        self._file.write(self.HEADER)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._file.close()
        self._file = None

    def write(self, frame: CANFrame) -> None:
        self._file.write(
            f"{frame.timestamp:.6f},{frame.hex_id},{frame.is_extended},{frame.dlc},{frame.data.hex()}\n"
        )
        self.frames_written += 1
