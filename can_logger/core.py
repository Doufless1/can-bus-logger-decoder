"""
Core CAN protocol abstractions, hardware-style acceptance filtering, and ring buffer.

Automotive CAN (Controller Area Network) Architecture Overview:
- Implements ISO 11898-1 standard data link and physical layer principles.
- Operates with differential signaling (CAN_H and CAN_L) where logical 0 is
  dominant (differential voltage ~2.0V) and logical 1 is recessive (0.0V).
- Message priority is resolved non-destructively through bitwise arbitration
  over the arbitration ID field during frame transmission.
"""

import time
import queue
from dataclasses import dataclass
from typing import Optional, List, Set

@dataclass
class CANFrame:
    """
    Represents an atomic physical layer CAN 2.0A/B data frame.

    Fields:
      timestamp: Floating-point monotonic or epoch time (seconds) recorded upon
                 reception by the transceiver/interface driver.
      arbitration_id: Message identifier (11-bit for standard CAN 2.0A; 29-bit for
                      extended CAN 2.0B / SAE J1939 protocols).
      is_extended: Boolean flag indicating IDE (Identifier Extension) bit state.
      dlc: Data Length Code specifying byte count in payload (0 to 8 bytes for classic CAN).
      data: Immutable raw bytes payload transmitted on the bus.
    """
    timestamp: float
    arbitration_id: int
    is_extended: bool
    dlc: int
    data: bytes

    @property
    def hex_id(self) -> str:
        return f"0x{self.arbitration_id:03X}" if not self.is_extended else f"0x{self.arbitration_id:08X}"

    @property
    def hex_data(self) -> str:
        return self.data.hex().upper()


class CANFilter:
    """
    Hardware-style mask and acceptance filter for arbitration IDs.
    By default (mask=0), all frames are accepted.
    """
    def __init__(self, allowed_ids: Optional[Set[int]] = None, mask: int = 0x000, code: int = 0x000):
        self.allowed_ids = allowed_ids
        self.mask = mask
        self.code = code

    def matches(self, arbitration_id: int) -> bool:
        if self.allowed_ids is not None:
            return arbitration_id in self.allowed_ids
        if self.mask == 0:
            return True
        return (arbitration_id & self.mask) == (self.code & self.mask)


class RingBuffer:
    """
    Bounded, thread-safe FIFO between the code that receives frames and the code
    that processes them (built on queue.Queue, so it uses a lock internally).
    When it is full the newest frame is dropped and counted, so a slow consumer
    shows up as a number instead of silently losing data.
    """
    def __init__(self, capacity: int = 50000):
        self.capacity = capacity
        self.queue: queue.Queue = queue.Queue(maxsize=capacity)
        self.dropped_frames: int = 0
        self.total_received: int = 0

    def push(self, frame: CANFrame) -> bool:
        self.total_received += 1
        try:
            self.queue.put_nowait(frame)
            return True
        except queue.Full:
            self.dropped_frames += 1
            return False

    def pop(self, timeout: Optional[float] = 0.05) -> Optional[CANFrame]:
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_empty(self) -> bool:
        return self.queue.empty()

    def size(self) -> int:
        return self.queue.qsize()

    def stats(self) -> dict:
        return {
            "total_received": self.total_received,
            "dropped_frames": self.dropped_frames,
            "queued": self.queue.qsize(),
        }


class VirtualCANBus:
    """
    A pure-Python stand-in for a CAN bus: frames sent to it pass the acceptance
    filter and land in a RingBuffer. It does not talk to SocketCAN; for a real
    or virtual python-can interface see python_can_adapter.py.
    """
    def __init__(self, channel: str = "vcan0", filter_engine: Optional[CANFilter] = None,
                 buffer_capacity: int = 50000):
        self.channel = channel
        self.filter = filter_engine or CANFilter()
        self.buffer = RingBuffer(capacity=buffer_capacity)
        self.is_active = True

    def send(self, frame: CANFrame) -> bool:
        if not self.is_active:
            return False
        if self.filter.matches(frame.arbitration_id):
            return self.buffer.push(frame)
        return False

    def recv(self, timeout: float = 0.05) -> Optional[CANFrame]:
        return self.buffer.pop(timeout=timeout)

    def shutdown(self):
        self.is_active = False
