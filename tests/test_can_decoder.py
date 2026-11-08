import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from can_logger.core import CANFrame, CANFilter, RingBuffer
from can_logger.decoder import DBCDecoder

def test_ring_buffer_push_pop():
    rb = RingBuffer(capacity=10)
    frame = CANFrame(timestamp=1.0, arbitration_id=0x100, is_extended=False, dlc=8, data=b"\x00"*8)
    assert rb.push(frame) is True
    assert rb.size() == 1
    popped = rb.pop()
    assert popped is not None
    assert popped.arbitration_id == 0x100
    assert rb.size() == 0

def test_can_filter_acceptance():
    can_filter = CANFilter(allowed_ids={0x100, 0x200})
    assert can_filter.matches(0x100) is True
    assert can_filter.matches(0x200) is True
    assert can_filter.matches(0x300) is False

def test_dbc_decoder_engine_data():
    decoder = DBCDecoder()
    # 0x1964 = 6500 in hex (little-endian: 64 19). 6500 * 0.25 = 1625.0 RPM
    # Throttle byte 2 = 0x28 (40 dec). 40 * 0.392 = 15.68 %
    # Load byte 3 = 0x30 (48 dec). 48 * 0.392 = 18.82 %
    data_payload = bytes.fromhex("6419283000000000")
    frame = CANFrame(timestamp=0.1, arbitration_id=0x100, is_extended=False, dlc=8, data=data_payload)
    decoded = decoder.decode_frame(frame)

    assert decoded is not None
    assert decoded["message_name"] == "EngineData"
    assert decoded["EngineSpeed"] == 1625.0
    assert decoded["ThrottlePosition"] == 15.68
    assert decoded["EngineLoad"] == 18.82

def test_dbc_decoder_thermal_status():
    decoder = DBCDecoder()
    # Coolant byte 0 = 0x82 (130 dec). 130 - 40 = 90 °C
    # Oil byte 1 = 0x8C (140 dec). 140 - 40 = 100 °C
    data_payload = bytes.fromhex("828c4b0000000000")
    frame = CANFrame(timestamp=0.2, arbitration_id=0x300, is_extended=False, dlc=8, data=data_payload)
    decoded = decoder.decode_frame(frame)

    assert decoded is not None
    assert decoded["message_name"] == "ThermalStatus"
    assert decoded["CoolantTempC"] == 90
    assert decoded["OilTempC"] == 100
