"""
Core CAN protocol abstractions, hardware-style acceptance filtering, and ring buffer.
"""

import time
import queue
from dataclasses import dataclass
from typing import Optional, List, Set

@dataclass
class CANFrame:
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
    High-throughput, thread-safe circular buffer for raw CAN frame streaming.
    Tracks dropped frames on buffer overflow.
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


class VirtualCANBus:
    """
    Simulates a high-speed virtual CAN interface (SocketCAN vcan0 emulator).
    """
    def __init__(self, channel: str = "vcan0", filter_engine: Optional[CANFilter] = None):
        self.channel = channel
        self.filter = filter_engine or CANFilter()
        self.buffer = RingBuffer()
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
