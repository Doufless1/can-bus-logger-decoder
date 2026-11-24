"""
Connects the logger to a real python-can bus (SocketCAN, PCAN, Kvaser, or
python-can's built-in "virtual" interface) by copying received messages into a
RingBuffer from a background thread.
"""

import threading

import can

from .core import CANFrame, RingBuffer


def frame_from_message(msg: can.Message) -> CANFrame:
    return CANFrame(
        timestamp=msg.timestamp,
        arbitration_id=msg.arbitration_id,
        is_extended=msg.is_extended_id,
        dlc=msg.dlc,
        data=bytes(msg.data),
    )


class PythonCANCapture:
    def __init__(self, bus: can.BusABC, buffer: RingBuffer):
        self.bus = bus
        self.buffer = buffer
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            msg = self.bus.recv(timeout=0.1)
            if msg is not None:
                self.buffer.push(frame_from_message(msg))
