#!/usr/bin/env python3
"""Simple test to isolate the connection issue"""

import os
import sys

# Setup libusb FIRST
dll_path = r'C:\Users\Ali\Development\PythonCAN-Utils\libusb-1.0.dll'
os.environ['PATH'] = os.path.dirname(dll_path) + os.pathsep + os.environ['PATH']

print("Step 1: Setting up libusb backend...")
import usb.backend.libusb1
import usb.core
backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
usb.core._BACKENDS = [backend]
print("✓ Backend configured")

print("\nStep 2: Testing device access...")
dev = usb.core.find(idVendor=0x1D50, idProduct=0x606F)
if dev:
    print(f"✓ Device found: {dev}")
else:
    print("✗ Device not found")
    sys.exit(1)

print("\nStep 3: Importing python-can...")
import can
print("✓ python-can imported")

print("\nStep 4: Attempting connection...")
try:
    bus = can.Bus(interface='gs_usb', channel=0, index=0, bitrate=500000)
    print("✓✓✓ CONNECTION SUCCESSFUL!")
    print(f"  Bus interface: gs_usb")
    print(f"  Channel: 0")
    print(f"  Bitrate: 500000")
    
    print("\nStep 5: Sending test message...")
    msg = can.Message(arbitration_id=0x123, data=[0xDE, 0xAD, 0xBE, 0xEF])
    bus.send(msg)
    print("✓ Message sent successfully")
    
    print("\nStep 6: Shutting down...")
    bus.shutdown()
    print("✓ Disconnected cleanly")
    
    print("\n" + "="*60)
    print("SUCCESS! CANable is working correctly!")
    print("="*60)
    
except Exception as e:
    print(f"\n✗ Connection failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
