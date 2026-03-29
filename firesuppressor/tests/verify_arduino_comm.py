"""
tests/verify_arduino_comm.py
============================
Unit test for Arduino communication formatting and clamping.
Uses a mock serial object to verify the sent strings.
"""

import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force enable for testing
os.environ["ENABLE_ARDUINO"] = "1"

from hardware.arduino_comm import ArduinoCommunicator

def test_clamping_and_format():
    print("Testing Arduino Communication...")
    
    # Mock serial
    mock_serial = MagicMock()
    
    # Initialize communicator
    comm = ArduinoCommunicator(port="MOCK")
    comm.serial = mock_serial
    comm._connected = True
    
    # Case 1: Standard values
    print("  Testing standard values (120, 60, 200, 1, 2)...")
    comm.send(pan=120, tilt=60, pressure=200, pump=1, mode=2)
    mock_serial.write.assert_called_with(b"120,60,200,1,2\n")
    
    # Case 2: Out of bounds (High)
    print("  Testing out of bounds (High: 200, 200, 300, 1, 5)...")
    comm.send(pan=200, tilt=200, pressure=300, pump=1, mode=5)
    mock_serial.write.assert_called_with(b"180,180,255,1,2\n")
    
    # Case 3: Out of bounds (Low)
    print("  Testing out of bounds (Low: -10, -50, -5, 0, -1)...")
    comm.send(pan=-10, tilt=-50, pressure=-5, pump=0, mode=-1)
    mock_serial.write.assert_called_with(b"0,0,0,0,0\n")
    
    # Case 4: Zero values
    print("  Testing zero values...")
    comm.send(0, 0, 0, 0, 0)
    mock_serial.write.assert_called_with(b"0,0,0,0,0\n")

    print("\n✅ Verification SUCCESS: Arduino message format and clamping are CORRECT.")

if __name__ == "__main__":
    try:
        test_clamping_and_format()
    except AssertionError as e:
        print(f"\n❌ Verification FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        sys.exit(1)
