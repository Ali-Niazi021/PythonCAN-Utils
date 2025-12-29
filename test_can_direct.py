#!/usr/bin/env python3
"""Direct CANable connection test with monkey-patching"""

import os
import sys

# Setup libusb path
dll_path = r'C:\Users\Ali\Development\PythonCAN-Utils\libusb-1.0.dll'
os.environ['PATH'] = os.path.dirname(dll_path) + os.pathsep + os.environ['PATH']

# Patch usb.core backend BEFORE any imports
import usb.backend.libusb1
import usb.core
backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
usb.core._BACKENDS = [backend]

print("✓ Patched usb.core backend")

# Import python-can first so it imports gs_usb
import can
import can.interfaces.gs_usb

# Now patch the GsUsb class that python-can imported
from gs_usb.gs_usb import GsUsb as GsUsbClass

# Store original scan method  
_original_scan = GsUsbClass.scan

# Create patched scan that uses our backend
@staticmethod  
def patched_scan():
    """Patched scan that forces our libusb backend"""
    import usb.core as core
    # Temporarily force backend
    old_backends = getattr(core, '_BACKENDS', None)
    core._BACKENDS = [backend]
    try:
        result = _original_scan()
        print(f"  [patched_scan] Found {len(result)} devices")
        return result
    finally:
        if old_backends:
            core._BACKENDS = old_backends

# Replace scan method on the class
GsUsbClass.scan = patched_scan

# Also replace it in the python-can module's reference
can.interfaces.gs_usb.GsUsb.scan = patched_scan

print("✓ Patched GsUsb.scan() in both modules")

# Test it
devs = GsUsbClass.scan()
print(f"✓ Direct scan found {len(devs)} device(s)")

print("\nAttempting connection...")
try:
    bus = can.Bus(interface='gs_usb', channel=0, bitrate=500000)
    print("✓✓✓ SUCCESS! Connected to CANable!")
    print(f"  Bus: {bus}")
    
    # Try sending a message
    msg = can.Message(arbitration_id=0x123, data=[0x11, 0x22, 0x33, 0x44])
    bus.send(msg)
    print("✓ Test message sent!")
    
    bus.shutdown()
    print("✓ Disconnected cleanly")
    
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
