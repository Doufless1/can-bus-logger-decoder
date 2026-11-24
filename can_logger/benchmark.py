"""
Measures the capture-and-decode path on the machine that runs it:

    python -m can_logger.benchmark --frames 100000

A producer thread pushes frames into the bus while a consumer thread pops and
decodes them. This exercises the in-process pipeline (RingBuffer + DBC decoder),
not a physical CAN bus, so the numbers say nothing about real bus load.
"""

import argparse
import os
import platform
import threading
import time

import numpy as np

from .core import CANFrame, VirtualCANBus
from .decoder import DBCDecoder

DEFAULT_DBC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "powertrain.dbc")

# One example payload for each message in powertrain.dbc, sent in rotation.
SAMPLE_FRAMES = [
    (0x100, "6419283000000000", 8),
    (0x200, "3013000000000000", 8),
    (0x300, "828c4b0000000000", 8),
    (0x400, "00000000", 4),
]


def run_benchmark(n_frames: int = 100000, buffer_capacity: int = 50000, dbc_path: str = DEFAULT_DBC) -> dict:
    bus = VirtualCANBus(buffer_capacity=buffer_capacity)
    decoder = DBCDecoder(dbc_path=dbc_path)
    producer_done = threading.Event()
    decode_times_ns = []

    def produce():
        for i in range(n_frames):
            arb_id, data_hex, dlc = SAMPLE_FRAMES[i % len(SAMPLE_FRAMES)]
            bus.send(CANFrame(i * 0.001, arb_id, False, dlc, bytes.fromhex(data_hex)))
        producer_done.set()

    def consume():
        while True:
            frame = bus.recv(timeout=0.01)
            if frame is None:
                if producer_done.is_set() and bus.buffer.is_empty():
                    return
                continue
            started = time.perf_counter_ns()
            decoder.decode_frame(frame)
            decode_times_ns.append(time.perf_counter_ns() - started)

    producer = threading.Thread(target=produce)
    consumer = threading.Thread(target=consume)
    start = time.perf_counter()
    producer.start()
    consumer.start()
    producer.join()
    consumer.join()
    elapsed = time.perf_counter() - start

    frames_decoded = len(decode_times_ns)
    if frames_decoded:
        p50, p99 = np.percentile(decode_times_ns, [50, 99]) / 1e6
    else:
        p50 = p99 = 0.0

    return {
        "decoder": "cantools (DBC file)" if decoder.db else "built-in fallback",
        "frames_sent": n_frames,
        "frames_decoded": frames_decoded,
        "dropped_frames": bus.buffer.stats()["dropped_frames"],
        "elapsed_s": elapsed,
        "frames_per_second": frames_decoded / elapsed if elapsed > 0 else 0.0,
        "p50_decode_ms": float(p50),
        "p99_decode_ms": float(p99),
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark the CAN capture and decode pipeline")
    parser.add_argument("--frames", type=int, default=100000, help="Number of frames to send")
    parser.add_argument("--buffer", type=int, default=50000, help="Ring buffer capacity in frames")
    args = parser.parse_args()

    result = run_benchmark(n_frames=args.frames, buffer_capacity=args.buffer)

    print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")
    print(f"Decoder        : {result['decoder']}")
    print(f"Frames sent    : {result['frames_sent']}")
    print(f"Frames decoded : {result['frames_decoded']}")
    print(f"Frames dropped : {result['dropped_frames']}")
    print(f"Elapsed        : {result['elapsed_s']:.2f} s")
    print(f"Throughput     : {result['frames_per_second']:.0f} frames/s")
    print(f"Decode latency : p50 {result['p50_decode_ms']:.3f} ms, p99 {result['p99_decode_ms']:.3f} ms (decode step only)")


if __name__ == "__main__":
    main()
