#!/usr/bin/env python3
"""Test CANable connection after Zadig WinUSB driver installation"""

import sys

print("Testing CANable with different methods...")
print("=" * 60)

# Test 1: Check USB enumeration with pyusb
print("\n1. Checking USB device enumeration with pyusb...")
try:
    import usb.core
    import usb.util
    
    dev = usb.core.find(idVendor=0x1D50, idProduct=0x606F)
    if dev:
        print(f"✓ Found CANable device")
        print(f"  Bus: {dev.bus}, Address: {dev.address}")
        try:
            manufacturer = usb.util.get_string(dev, dev.iManufacturer)
            product = usb.util.get_string(dev, dev.iProduct)
            serial = usb.util.get_string(dev, dev.iSerialNumber)
            print(f"  Manufacturer: {manufacturer}")
            print(f"  Product: {product}")
            print(f"  Serial: {serial}")
        except Exception as e:
            print(f"  ⚠ Could not read device strings: {e}")
    else:
        print("✗ No CANable device found")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Try python-can gs_usb with index 0
print("\n2. Testing python-can gs_usb with channel=0...")
try:
    import can
    bus = can.Bus(interface='gs_usb', channel=0, bitrate=500000)
    print("✓ Connected with channel=0!")
    bus.shutdown()
    print("✓ Disconnected")
except Exception as e:
    print(f"✗ Failed: {e}")

# Test 3: Try python-can gs_usb with channel='can0'
print("\n3. Testing python-can gs_usb with channel='can0'...")
try:
    import can
    bus = can.Bus(interface='gs_usb', channel='can0', bitrate=500000)
    print("✓ Connected with channel='can0'!")
    bus.shutdown()
    print("✓ Disconnected")
except Exception as e:
    print(f"✗ Failed: {e}")

# Test 4: Check gs_usb backend directly
print("\n4. Checking gs_usb backend internals...")
try:
    from can.interfaces import gs_usb as gs_module
    print(f"  gs_usb module: {gs_module.__file__}")
    
    # Try to see what the backend is looking for
    import usb.core
    
    # Search for all USB devices that might be gs_usb
    all_devices = list(usb.core.find(find_all=True))
    gs_devices = []
    
    # Known gs_usb VID/PID combinations
    gs_usb_ids = [
        (0x1D50, 0x606F),  # CANable
        (0x1209, 0x0001),  # CANtact
        (0x16D0, 0x0F67),  # candleLight
    ]
    
    for dev in all_devices:
        if (dev.idVendor, dev.idProduct) in gs_usb_ids:
            gs_devices.append(dev)
            print(f"  Found gs_usb device: VID=0x{dev.idVendor:04X}, PID=0x{dev.idProduct:04X}")
    
    print(f"  Total gs_usb compatible devices: {len(gs_devices)}")
    
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 60)
print("Recommendations:")
print("  1. If all tests failed, try rebooting Windows")
print("  2. In Zadig, ensure you selected 'WinUSB' (not libusbK)")
print("  3. Verify the device shows as 'canable gs_usb' in Device Manager")
print("  4. Alternative: Use PCAN-USB instead (works immediately)")
print("=" * 60)
