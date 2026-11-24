"""
Core CAN protocol abstractions, hardware-style acceptance filtering, and ring buffer.

Functional Safety (ISO 26262) Considerations:
- Deterministic frame timing and bounded queue latency prevent stale sensor states.
- Explicit drop accounting enables early detection of bus overload and ECU faults.

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
        """
        Returns canonical hex string representation padded according to frame format.
        - Standard 11-bit IDs range 0x000 - 0x7FF (padded to 3 hex nibbles).
        - Extended 29-bit IDs range 0x00000000 - 0x1FFFFFFF (padded to 8 hex nibbles).
        """
        return f"0x{self.arbitration_id:03X}" if not self.is_extended else f"0x{self.arbitration_id:08X}"

    @property
    def hex_data(self) -> str:
        """Returns uppercase hexadecimal string representation of the raw payload bytes."""
        return self.data.hex().upper()


class CANFilter:
    """
    Hardware-style mask and acceptance filter for arbitration IDs.

    Emulates hardware acceptance filtering built into standalone CAN controllers
    (such as Microchip MCP2515 or NXP SJA1000). Hardware filtering discards
    unwanted bus traffic directly at the silicon level, preventing CPU interrupt
    flooding and freeing host processing budget for relevant telemetry.

    By default (mask=0), all frames are accepted.
    """
    def __init__(self, allowed_ids: Optional[Set[int]] = None, mask: int = 0x000, code: int = 0x000):
        self.allowed_ids = allowed_ids
        self.mask = mask
        self.code = code

    def matches(self, arbitration_id: int) -> bool:
        """
        Evaluates whether an arbitration ID passes the configured acceptance filter.

        Evaluation logic:
        1. Explicit whitelist check: If allowed_ids set is provided, performs O(1) set membership.
        2. Pass-through default: If mask is 0x000, all bits are "don't care", returning True.
        3. Bitwise mask/code evaluation:
           (arbitration_id & mask) == (code & mask)
           - Mask bit = 1: The bit must match the corresponding bit in code.
           - Mask bit = 0: The bit is ignored (wildcard).
        """
        if self.allowed_ids is not None:
            return arbitration_id in self.allowed_ids
        if self.mask == 0:
            return True
        return (arbitration_id & self.mask) == (self.code & self.mask)


class RingBuffer:
    """
    Bounded, thread-safe FIFO between the code that receives frames and the code
    that processes them.

    Architecture:
    - Decouples high-frequency I/O ingestion from variable-latency downstream decoding.
    - Built on queue.Queue, utilizing an internal mutex lock and condition variables
      (not_empty, not_full) to guarantee race-free thread synchronization.
    - Implements backpressure protection: When capacity is reached, newest inbound frames
      are discarded and tracked via dropped_frames counter rather than blocking the bus
      or consuming unbounded host RAM.
    """
    def __init__(self, capacity: int = 50000):
        self.capacity = capacity
        self.queue: queue.Queue = queue.Queue(maxsize=capacity)
        self.dropped_frames: int = 0
        self.total_received: int = 0

    def push(self, frame: CANFrame) -> bool:
        """
        Non-blocking enqueue of an incoming frame.

        Accounting semantics:
        - Increments total_received counter unconditionally.
        - Attempts put_nowait(); if the queue has reached maxsize, catches queue.Full,
          increments dropped_frames, and returns False without raising an exception.
        """
        self.total_received += 1
        try:
            self.queue.put_nowait(frame)
            return True
        except queue.Full:
            self.dropped_frames += 1
            return False

    def pop(self, timeout: Optional[float] = 0.05) -> Optional[CANFrame]:
        """
        Dequeues the next frame with a bounded timeout.

        A short timeout (default 50ms) prevents downstream consumer worker threads from
        busy-waiting or hanging indefinitely when the bus is quiet, allowing clean
        interruption during system shutdown.
        """
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_empty(self) -> bool:
        return self.queue.empty()

    def size(self) -> int:
        return self.queue.qsize()

    def stats(self) -> dict:
        """
        Returns point-in-time telemetry snapshot of queue performance metrics.
        Useful for health monitoring, packet drop alarms, and buffer sizing diagnostics.
        """
        return {
            "total_received": self.total_received,
            "dropped_frames": self.dropped_frames,
            "queued": self.queue.qsize(),
        }


class VirtualCANBus:
    """
    A pure-Python stand-in for a CAN bus transceiver and channel.

    Provides a mock physical communication channel:
    - Frames sent to it pass through the acceptance filter engine before enqueueing.
    - Enqueues accepted traffic into a dedicated internal RingBuffer.
    - Isolated from OS networking (does not require root/SocketCAN privileges),
      making it ideal for unit testing, reproducible replay, and offline analytics.
    """
    def __init__(self, channel: str = "vcan0", filter_engine: Optional[CANFilter] = None,
                 buffer_capacity: int = 50000):
        self.channel = channel
        self.filter = filter_engine or CANFilter()
        self.buffer = RingBuffer(capacity=buffer_capacity)
        self.is_active = True

    def send(self, frame: CANFrame) -> bool:
        """
        Transmits a frame across the virtual bus.
        Evaluates bus active status, applies filter matching, and pushes to buffer.
        Returns True if accepted and buffered, False otherwise.
        """
        if not self.is_active:
            return False
        if self.filter.matches(frame.arbitration_id):
            return self.buffer.push(frame)
        return False

    def recv(self, timeout: float = 0.05) -> Optional[CANFrame]:
        """Pulls the next available frame from the bus RX buffer with timeout."""
        if not self.is_active:
            return None
        return self.buffer.pop(timeout=timeout)

    def shutdown(self):
        self.is_active = False
