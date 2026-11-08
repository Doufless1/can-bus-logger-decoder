"""
DBC-driven CAN signal decoding and physical value reconstruction.
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
    Provides graceful standalone parsing fallback if cantools is not yet installed.
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
        raw = frame.data
        if frame.arbitration_id == 0x100 and len(raw) >= 4:
            # EngineData: Speed (16b, factor 0.25), Throttle (8b, factor 0.392), Load (8b, factor 0.392)
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
            # VehicleSpeed: Speed (16b, factor 0.01)
            raw_spd = int.from_bytes(raw[0:2], byteorder="little")
            speed = round(raw_spd * 0.01, 2)
            return {
                "timestamp": frame.timestamp,
                "message_name": "VehicleSpeed",
                "arbitration_id": "0x200",
                "VehicleSpeedKmh": speed
            }
        elif frame.arbitration_id == 0x300 and len(raw) >= 3:
            # ThermalStatus: Coolant (8b, offset -40), Oil (8b, offset -40), Intake (8b, offset -40)
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
            # BrakeStatus: Applied (1b), Pressure (15b, factor 0.1)
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
        df.sort_values(by="timestamp", inplace=True)
        return df
