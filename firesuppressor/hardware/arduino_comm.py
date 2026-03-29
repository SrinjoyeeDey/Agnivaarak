"""
hardware/arduino_comm.py
========================
Modular communication layer for Arduino over Serial (USB).
Sends computed outputs in the format: pan,tilt,pressure,pump,mode\n
"""

import os
import serial
import time
from loguru import logger

# Toggle flag: set via env var or default to False for safety
ENABLE_ARDUINO = os.getenv("ENABLE_ARDUINO", "0") == "1"

class ArduinoCommunicator:
    """
    Handles Serial connection and data transmission to Arduino.
    """
    def __init__(self, port: str = None, baudrate: int = 115200, timeout: float = 0.1):
        self.port = port or os.getenv("ARDUINO_PORT", "COM3")
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self._connected = False

        if ENABLE_ARDUINO:
            self.connect()

    def connect(self):
        """Attempts to connect to the Arduino, fails gracefully."""
        if not ENABLE_ARDUINO:
            return False

        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            # Allow Arduino time to reset after connection
            time.sleep(2)
            self._connected = True
            logger.success("✅ Connected to Arduino on {}", self.port)
            return True
        except Exception as e:
            logger.error("❌ Failed to connect to Arduino on {}: {}", self.port, e)
            self._connected = False
            self.serial = None
            return False

    def send(self, pan: float, tilt: float, pressure_level: str, mode: int, 
             fire_type: str = "A", intensity: str = "LOW"):
        """
        Sends the decision data to Arduino in the simple numeric format.
        Mappings:
            Pressure: OFF=0, LOW=1, MEDIUM=2, HIGH=3
            Mode: NORMAL=0, FIRE=1, EMERGENCY=2
            Fire Type: A=1, B=2, C=3, D=4
            Intensity: LOW=1, MEDIUM=2, HIGH=3
        Format: pan,tilt,pressure,mode,fire_type,intensity\n
        """
        if not ENABLE_ARDUINO or not self._connected or not self.serial:
            return

        # Map string parameters to numeric codes
        p_map = {"OFF": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "MAX": 3, "CRITICAL": 3}
        f_map = { "a": 1, "b": 2, "c": 3, "d": 4, "A": 1, "B": 2, "C": 3, "D": 4}
        i_map = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

        pan_c = max(0, min(180, int(pan)))
        tilt_c = max(0, min(180, int(tilt)))
        pressure_c = p_map.get(pressure_level.upper(), 0)
        mode_c = max(0, min(2, int(mode)))
        type_c = f_map.get(fire_type, 1)
        int_c = i_map.get(intensity.upper(), 1)

        msg = f"{pan_c},{tilt_c},{pressure_c},{mode_c},{type_c},{int_c}\n"
        
        try:
            self.serial.write(msg.encode('utf-8'))
            logger.debug("📡 Sent to Mapped Arduino: {}", msg.strip())
        except Exception as e:
            logger.error("⚠️ Serial communication error: {}. Disconnecting.", e)
            self._connected = False
            self.serial.close()
            self.serial = None

    def close(self):
        """Safely closes the serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self._connected = False
            logger.info("🔌 Disconnected from Arduino on {}", self.port)

# Global dedicated function as requested
_comm_instance = None

def send_to_arduino(pan: float, tilt: float, pressure_level: str, mode: int, 
                    fire_type: str = "A", intensity: str = "LOW"):
    """
    High-level API for sending data in the new mapped format.
    """
    global _comm_instance
    if _comm_instance is None:
        _comm_instance = ArduinoCommunicator()
    
    _comm_instance.send(pan, tilt, pressure_level, mode, fire_type, intensity)

def close_arduino_connection():
    """Shuts down the global communicator instance."""
    global _comm_instance
    if _comm_instance:
        _comm_instance.close()
        _comm_instance = None
