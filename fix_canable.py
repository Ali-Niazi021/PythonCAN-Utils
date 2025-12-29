#!/usr/bin/env python3
"""
Quick fix for CANable - tries various methods to connect
"""

import time

print("CANable Connection Troubleshooter")
print("=" * 60)

# Method 1: Try with libusb backend explicitly
print("\n1. Trying with explicit libusb backend...")
try:
    import usb.core
    import usb.backend.libusb1
    
    # Point to the libusb-1.0.dll in project directory
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: r"C:\Users\Ali\Development\PythonCAN-Utils\libusb-1.0.dll")
    
    dev = usb.core.find(backend=backend, idVendor=0x1D50, idProduct=0x606F)
    if dev:
        print(f"✓ Found device with explicit backend!")
        print(f"  Device: {dev}")
        
        # Try to set configuration
        try:
            dev.set_configuration()
            print("✓ Configuration set successfully")
        except Exception as e:
            print(f"⚠ Could not set configuration: {e}")
    else:
        print("✗ Device not found even with explicit backend")
        
except Exception as e:
    print(f"✗ Error: {e}")

# Method 2: Try python-can with the explicit backend
print("\n2. Trying python-can with patched backend...")
try:
    import usb.core
    import usb.backend.libusb1
    
    # Patch the backend before importing can
    backend = usb.backend.libusb1.get_backend(
        find_library=lambda x: r"C:\Users\Ali\Development\PythonCAN-Utils\libusb-1.0.dll"
    )
    usb.core._BACKENDS = [backend]
    
    import can
    bus = can.Bus(interface='gs_usb', channel=0, bitrate=500000)
    print("✓✓✓ SUCCESS! Connected with patched backend!")
    print(f"  Bus: {bus}")
    
    # Try sending a test message
    msg = can.Message(arbitration_id=0x123, data=[0,1,2,3,4,5,6,7])
    bus.send(msg)
    print("✓ Test message sent!")
    
    bus.shutdown()
    print("✓ Disconnected cleanly")
    
except Exception as e:
    print(f"✗ Failed: {e}")

# Method 3: Check if device needs to be reset
print("\n3. Checking device state...")
try:
    import usb.core
    import usb.backend.libusb1
    
    backend = usb.backend.libusb1.get_backend(
        find_library=lambda x: r"C:\Users\Ali\Development\PythonCAN-Utils\libusb-1.0.dll"
    )
    
    dev = usb.core.find(backend=backend, idVendor=0x1D50, idProduct=0x606F)
    if dev:
        print(f"  Device found")
        print(f"  Current configuration: {dev.get_active_configuration()}")
        
        # Try to reset the device
        print("  Attempting device reset...")
        try:
            dev.reset()
            print("✓ Device reset successful")
            time.sleep(2)
        except Exception as e:
            print(f"⚠ Reset failed: {e}")
    else:
        print("✗ Device not found")
        
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 60)
print("NEXT STEPS:")
print("  If Method 2 worked:")
print("    → The CANable is working! The backend just needs patching")
print("    → I'll update the driver to use the explicit backend")
print()
print("  If nothing worked:")
print("    → Unplug and replug the CANable USB cable")
print("    → Run this script again")
print("    → Or use PCAN-USB instead (it works now)")
print("=" * 60)
