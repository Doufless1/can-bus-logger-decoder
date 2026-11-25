"""
DBC-driven CAN signal decoding and physical value reconstruction.

Vector DBC Specification Overview:
- DBC (Database CAN) files define the layout, scaling, offsets, and physical
  units of raw binary payloads transmitted across CAN arbitration IDs.
- Syntax:
  * BO_ <ID> <MessageName>: <DLC> <TransmitterNode>
  * SG_ <SignalName> : <StartBit>|<Length>@<Endianness><Sign> (<Factor>,<Offset>) [<Min>|<Max>] "<Unit>" <ReceiverNodes>
"""

import struct
from typing import Dict, Any, Optional
import pandas as pd
from .core import CANFrame

try:
    import cantools
    HAS_CANTOOLS = True
except ImportError:
    HAS_CANTOOLS = False

class DBCDecoder:
    """
    Decodes raw byte payloads into physical engineering units using Vector DBC specs.

    Dual-Engine Design:
    1. Primary Engine: High-performance cantools database parser, capable of dynamic
       signal decoding, multiplexed signals, and complex DBC definitions.
    2. Standalone Fallback Engine: Deterministic, pure-Python bitwise decoder supporting
       core powertrain telemetry without external binary dependencies.
    """
    def __init__(self, dbc_path: Optional[str] = None):
        self.dbc_path = dbc_path
        self.db = None
        if dbc_path and HAS_CANTOOLS:
            try:
                self.db = cantools.database.load_file(dbc_path)
            except Exception:
                self.db = None

    def decode_frame(self, frame: CANFrame) -> Optional[Dict[str, Any]]:
        """
        Extracts named physical signals from a CANFrame.

        Signal Scaling Formula:
            physical_value = raw_integer * factor + offset

        Units and ranges adhere to SAE J1939 / ISO standard automotive conventions.
        """
        # If cantools database is loaded, use it
        if self.db:
            try:
                msg = self.db.get_message_by_frame_id(frame.arbitration_id)
                signals = msg.decode(frame.data)
                return {
                    "timestamp": frame.timestamp,
                    "message_name": msg.name,
                    "arbitration_id": frame.hex_id,
                    **signals
                }
            except KeyError:
                return None

        # Standalone deterministic decoder for standard Powertrain DBC specification
        # Endianness: Little-endian (Intel) is used across powertrain telemetry signals,
        # where the least significant byte is stored at the lowest memory address.
        raw = frame.data
        if frame.arbitration_id == 0x100 and len(raw) >= 4:
            # EngineData (0x100):
            # - EngineSpeed (bytes 0-1, 16-bit uint, scale 0.25 rpm/bit, range 0-16383.75 rpm)
            # - ThrottlePosition (byte 2, 8-bit uint, scale 0.392 %/bit, range 0-100%)
            # - EngineLoad (byte 3, 8-bit uint, scale 0.392 %/bit, range 0-100%)
            raw_rpm = int.from_bytes(raw[0:2], byteorder="little")
            rpm = round(raw_rpm * 0.25, 2)
            throttle = round(raw[2] * 0.392, 2)
            load = round(raw[3] * 0.392, 2)
            return {
                "timestamp": frame.timestamp,
                "message_name": "EngineData",
                "arbitration_id": "0x100",
                "EngineSpeed": rpm,
                "ThrottlePosition": throttle,
                "EngineLoad": load
            }
        elif frame.arbitration_id == 0x200 and len(raw) >= 2:
            # VehicleSpeed (0x200):
            # - VehicleSpeedKmh (bytes 0-1, 16-bit uint, scale 0.01 km/h/bit, range 0-655.35 km/h)
            # Transmitted periodically by the ABS / Wheel Speed sensor module.
            raw_spd = int.from_bytes(raw[0:2], byteorder="little")
            speed = round(raw_spd * 0.01, 2)
            return {
                "timestamp": frame.timestamp,
                "message_name": "VehicleSpeed",
                "arbitration_id": "0x200",
                "VehicleSpeedKmh": speed
            }
        elif frame.arbitration_id == 0x300 and len(raw) >= 3:
            # ThermalStatus (0x300):
            # Automotive temperature sensors use an offset of -40 deg C to allow
            # representing sub-zero freezing temperatures with unsigned 8-bit bytes (0-255).
            # Formula: temp_degC = raw_byte - 40 (Range: -40 deg C to +215 deg C)
            coolant = raw[0] - 40
            oil = raw[1] - 40
            intake = raw[2] - 40
            return {
                "timestamp": frame.timestamp,
                "message_name": "ThermalStatus",
                "arbitration_id": "0x300",
                "CoolantTempC": coolant,
                "OilTempC": oil,
                "IntakeAirTempC": intake
            }
        elif frame.arbitration_id == 0x400 and len(raw) >= 2:
            # BrakeStatus (0x400) Bitfield Unpacking:
            # - BrakePedalApplied: Bit 0 (1-bit flag: 0 = Released, 1 = Pressed)
            # - BrakePressureBar: Bits 1-15 (15-bit uint, scale 0.1 bar/bit, range 0-3276.7 bar)
            # Shift raw integer right by 1 to isolate pressure bits after checking bit 0.
            raw_val = int.from_bytes(raw[0:2], byteorder="little")
            applied = raw_val & 0x01
            pressure = round((raw_val >> 1) * 0.1, 2)
            return {
                "timestamp": frame.timestamp,
                "message_name": "BrakeStatus",
                "arbitration_id": "0x400",
                "BrakePedalApplied": applied,
                "BrakePressureBar": pressure
            }
        return None

    def frames_to_timeseries(self, frames: list[CANFrame]) -> pd.DataFrame:
        """
        Decodes a sequence of raw frames into a unified chronological time-series DataFrame.
        """
        decoded_records = []
        for f in frames:
            dec = self.decode_frame(f)
            if dec:
                decoded_records.append(dec)
        
        if not decoded_records:
            return pd.DataFrame()

        df = pd.DataFrame(decoded_records)
        return df.sort_values(by="timestamp")
