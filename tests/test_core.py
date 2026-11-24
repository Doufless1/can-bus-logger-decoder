from can_logger.core import CANFrame, RingBuffer, VirtualCANBus


def make_frame(i: int) -> CANFrame:
    return CANFrame(timestamp=i * 0.001, arbitration_id=0x100, is_extended=False, dlc=8, data=bytes(8))


def test_ring_buffer_stats_report_drops_when_full():
    rb = RingBuffer(capacity=2)

    results = [rb.push(make_frame(i)) for i in range(3)]

    assert results == [True, True, False]
    assert rb.stats() == {"total_received": 3, "dropped_frames": 1, "queued": 2}


def test_virtual_bus_buffer_capacity_is_configurable():
    bus = VirtualCANBus(buffer_capacity=3)

    for i in range(5):
        bus.send(make_frame(i))

    assert bus.buffer.stats()["dropped_frames"] == 2
    assert bus.buffer.stats()["queued"] == 3
