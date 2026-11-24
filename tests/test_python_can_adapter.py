import time

import can

from can_logger.core import RingBuffer
from can_logger.python_can_adapter import PythonCANCapture, frame_from_message


def drain(buffer: RingBuffer):
    frames = []
    while True:
        frame = buffer.pop(timeout=0.01)
        if frame is None:
            return frames
        frames.append(frame)


def test_frame_from_message_keeps_id_flags_and_payload():
    msg = can.Message(arbitration_id=0x18FEF100, is_extended_id=True, data=[1, 2, 3], timestamp=12.5)

    frame = frame_from_message(msg)

    assert frame.arbitration_id == 0x18FEF100
    assert frame.is_extended is True
    assert frame.dlc == 3
    assert frame.data == bytes([1, 2, 3])
    assert frame.timestamp == 12.5


def test_capture_thread_moves_frames_from_a_python_can_bus_into_the_ring_buffer():
    buffer = RingBuffer(capacity=100)
    sender = can.Bus(interface="virtual", channel="test_capture")
    receiver = can.Bus(interface="virtual", channel="test_capture")
    capture = PythonCANCapture(receiver, buffer)
    capture.start()
    try:
        for i in range(10):
            sender.send(can.Message(arbitration_id=0x100 + i, data=[i], is_extended_id=False))
        deadline = time.time() + 2.0
        while buffer.stats()["total_received"] < 10 and time.time() < deadline:
            time.sleep(0.01)
    finally:
        capture.stop()
        sender.shutdown()
        receiver.shutdown()

    assert buffer.stats()["total_received"] == 10
    assert [f.arbitration_id for f in drain(buffer)] == [0x100 + i for i in range(10)]
