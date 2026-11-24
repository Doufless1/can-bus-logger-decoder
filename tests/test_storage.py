import pytest

from can_logger.core import CANFrame
from can_logger.replay_harness import TraceReplayHarness
from can_logger.storage import CSVFrameLogger


def test_csv_logger_round_trips_through_the_replay_loader(tmp_path):
    frames = [
        CANFrame(0.001, 0x100, False, 8, bytes.fromhex("6419283000000000")),
        CANFrame(0.0025, 0x400, False, 4, bytes.fromhex("00000000")),
        CANFrame(0.004, 0x18FEF100, True, 8, bytes.fromhex("FFFFFFFFFFFFFFFF")),
    ]
    path = tmp_path / "log.csv"

    with CSVFrameLogger(str(path)) as logger:
        for frame in frames:
            logger.write(frame)

    loaded = TraceReplayHarness(str(path)).load_frames()
    assert logger.frames_written == 3
    assert [(f.arbitration_id, f.is_extended, f.dlc, f.data) for f in loaded] == [
        (f.arbitration_id, f.is_extended, f.dlc, f.data) for f in frames
    ]
    assert [f.timestamp for f in loaded] == pytest.approx([f.timestamp for f in frames])
