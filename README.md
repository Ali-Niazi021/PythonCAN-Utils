# PythonCAN-Utils

A comprehensive Python-based CAN bus utility suite for PCAN-USB and CANable adapters, featuring object-oriented drivers, a graphical user interface similar to PCAN-Explorer, and integrated STM32 bootloader firmware flashing.

## Features

### Dual CAN Adapter Support
- **PCAN-USB**: Professional USB-to-CAN adapter from PEAK-System
- **CANable**: Low-cost, open-source USB-to-CAN adapter (SLCAN protocol)

### PCAN Driver (`drivers/PCAN_Driver.py`)
- **Object-Oriented Design**: Clean, Pythonic interface for PCAN devices
- **Device Management**: Scan, connect, and manage PCAN-USB adapters
- **Message Operations**: Send and receive CAN messages (standard/extended, data/remote frames)
- **Background Reception**: Asynchronous message reception with callback support
- **Bus Control**: Status monitoring, filtering, and queue management
- **Thread-Safe**: Safe for multi-threaded applications

### CANable Driver (`drivers/CANable_Driver.py`)
- **SLCAN Protocol**: Communication via virtual serial port
- **Cross-Platform**: Works on Windows, Linux, and macOS
- **Compatible Interface**: Same API as PCAN driver for easy switching
- **Auto-Detection**: Scans for likely CANable devices
- **Message Operations**: Full support for standard and extended CAN frames

### CAN Explorer GUI (`GUI_Master.py`)
- **Visual Interface**: User-friendly GUI built with DearPyGUI
- **Device Selection**: Choose between PCAN and CANable at runtime
- **Live Monitoring**: Real-time CAN bus message display
- **DBC Support**: Automatic message decoding using DBC files
- **Smart Message Handling**: Messages grouped by ID with counters
- **Message Transmission**: Send CAN messages with customizable parameters
- **Thermistor Monitor**: 8-channel temperature display (application-specific)
- **Statistics**: Track message rates and unique IDs
- **Export Functionality**: Save captured messages to CSV
- **Period Calculation**: Automatic calculation of message transmission periods

### Firmware Flasher (`bootloader/Flash_Application.py`)
- **STM32 Bootloader**: Flash firmware to STM32L432 via CAN bus
- **Device Agnostic**: Works with both PCAN and CANable
- **Command-Line Interface**: Scriptable firmware updates
- **Verification**: Read-back verification of flashed data
- **Progress Tracking**: Real-time flashing progress
- **Integrated in GUI**: Flash firmware from the GUI application

## Installation

1. **Clone or download this repository**

2. **Create a virtual environment (recommended)**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

## Requirements

- Python 3.8 or higher
- **For PCAN**: PCAN-USB adapter + PCAN-Basic driver (Windows)
- **For CANable**: CANable device (works on Windows, Linux, macOS)
- **For GUI**: DearPyGUI library
- **For DBC Support**: cantools library

## Usage

### Using the CAN Drivers Programmatically

#### PCAN Example
```python
from drivers.PCAN_Driver import PCANDriver, PCANChannel, PCANBaudRate

# Create driver instance
driver = PCANDriver()

# Scan for available devices
devices = driver.get_available_devices()
print(f"Found {len(devices)} PCAN device(s)")

# Connect to PCAN-USB1 at 500 kbps
driver.connect(PCANChannel.USB1, PCANBaudRate.BAUD_500K)

# Send a message
driver.send_message(0x123, b'\x01\x02\x03\x04\x05\x06\x07\x08')

# Read a message
msg = driver.read_message(timeout=1.0)
if msg:
    print(f"Received: {msg}")

# Cleanup
driver.disconnect()
```

#### CANable Example
```python
from drivers.CANable_Driver import CANableDriver, CANableBaudRate

# Create driver instance
driver = CANableDriver()

# Scan for available devices
devices = driver.get_available_devices()
for dev in devices:
    if dev.get('is_likely_canable'):
        print(f"Found CANable on {dev['port']}")

# Connect to CANable at 500 kbps
# Windows: "COM3", Linux: "/dev/ttyACM0", macOS: "/dev/tty.usbmodem1"
driver.connect("COM3", CANableBaudRate.BAUD_500K)

# Send a message
driver.send_message(0x123, b'\x01\x02\x03\x04\x05\x06\x07\x08')

# Read a message
msg = driver.read_message(timeout=1.0)
if msg:
    print(f"Received: {msg}")

# Cleanup
driver.disconnect()
```

### Running the GUI Application

#### Default (PCAN)
```powershell
python GUI_Master.py
```

#### With CANable
```powershell
python GUI_Master.py --device canable --channel COM3
```

#### With PCAN (explicit)
```powershell
python GUI_Master.py --device pcan --channel USB1
```

### Flashing Firmware

#### Using PCAN (default)
```powershell
python bootloader/Flash_Application.py application.bin
python bootloader/Flash_Application.py application.bin --channel USB1
```

#### Using CANable
```powershell
python bootloader/Flash_Application.py application.bin --adapter canable --channel COM3
python bootloader/Flash_Application.py application.bin --adapter canable --channel /dev/ttyACM0
```

#### Additional Options
```powershell
# Skip verification
python bootloader/Flash_Application.py application.bin --no-verify

# Don't jump to application after flashing
python bootloader/Flash_Application.py application.bin --no-jump

# List available devices
python bootloader/Flash_Application.py --list-devices --adapter pcan
python bootloader/Flash_Application.py --list-devices --adapter canable

# Check bootloader status
python bootloader/Flash_Application.py --status-only --adapter canable --channel COM3
```

## GUI Features

### Connection Panel
- **Device Selection**: Choose between PCAN and CANable (if both drivers available)
- **Channel Selection**: PCAN channels (USB1-USB16) or CANable serial ports
- **Baud Rate Selection**: Standard rates from 10K to 1M bps
- **Connect/Disconnect**: Manage connection to the adapter

### CAN Explorer Tab
- **DBC Support**: Load DBC files for automatic message decoding
- **Message Transmission**: Send CAN messages with ID, data, extended/remote flags
- **Message Table**: Real-time display of all received messages
  - CAN ID, message name (from DBC), type, DLC, data
  - Decoded signal values (from DBC)
  - Message count, timestamp, and period
- **Statistics**: Total messages, unique IDs, message rate
- **Export**: Save messages to CSV

### Thermistor Monitor Tab
- **8-Channel Display**: Real-time temperature readings
- **ADC Values**: Raw ADC counts for each channel
- **Statistics**: Active channels, min/max/avg temperatures
- **Export**: Save temperature data to CSV

### Firmware Flasher Tab
- **File Selection**: Browse for .bin firmware files
- **Flash Operations**: Erase, flash, verify, and jump to application
- **Progress Tracking**: Real-time progress bar and status
- **Flash Log**: Detailed logging of all operations

## Supported Devices

### PCAN-USB
- **Channels**: USB1 through USB16
- **Platform**: Windows (requires PCAN-Basic driver)
- **Interface**: PEAK-System hardware

### CANable
- **Interface**: SLCAN protocol over virtual serial port
- **Platform**: Windows, Linux, macOS
- **Common Ports**: 
  - Windows: COM3, COM4, etc.
  - Linux: /dev/ttyACM0, /dev/ttyUSB0
  - macOS: /dev/tty.usbmodem1
- **Setup**: 
  - Linux: Add user to dialout group: `sudo usermod -a -G dialout $USER`
  - Linux: Or set permissions: `sudo chmod 666 /dev/ttyACM0`

## Supported Baud Rates

- 1 Mbps (BAUD_1M)
- 800 kbps (BAUD_800K) - PCAN only
- 500 kbps (BAUD_500K)
- 250 kbps (BAUD_250K)
- 125 kbps (BAUD_125K)
- 100 kbps (BAUD_100K)
- 50 kbps (BAUD_50K)
- 20 kbps (BAUD_20K)
- 10 kbps (BAUD_10K)

## Troubleshooting

### PCAN Issues

**"No PCAN devices found"**
- Ensure your PCAN-USB adapter is properly connected
- Install the PCAN-Basic driver from PEAK-System
- Check Windows Device Manager for the device

**"Failed to connect"**
- Verify the device is not in use by another application
- Try disconnecting and reconnecting the USB adapter
- Check that the selected baud rate matches your CAN bus

### CANable Issues

**"No serial ports found"**
- Ensure CANable is connected via USB
- On Windows, check Device Manager for COM port number
- On Linux, check `ls /dev/ttyACM*` or `ls /dev/ttyUSB*`

**"Failed to connect to CANable"**
- Verify the correct COM port / serial device
- On Linux: Check permissions with `ls -l /dev/ttyACM0`
- On Linux: Add user to dialout group (requires logout/login)
- Try disconnecting and reconnecting the device

**"Permission denied" (Linux)**
```bash
# Temporary fix
sudo chmod 666 /dev/ttyACM0

# Permanent fix
sudo usermod -a -G dialout $USER
# Then logout and login again
```

### General Issues

**Import errors**
- Make sure you've activated the virtual environment
- Reinstall dependencies: `pip install -r requirements.txt`

**GUI doesn't start**
- Check that dearpygui is installed: `pip install dearpygui`
- Try reinstalling: `pip uninstall dearpygui` then `pip install dearpygui`

## Architecture

```
PythonCAN-Utils/
├── bootloader/
│   ├── Flash_Application.py      # CLI firmware flasher
│   └── STM32L432_Bootloader.dbc  # Bootloader CAN protocol DBC
├── drivers/
│   ├── PCAN_Driver.py      # PCAN-USB driver
│   └── CANable_Driver.py   # CANable driver (SLCAN)
├── GUI_Master.py           # GUI application
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## API Reference

### PCANDriver Class

#### Methods
- `connect(channel, baudrate, fd_mode=False)` - Connect to PCAN device
- `disconnect()` - Disconnect from device
- `send_message(can_id, data, is_extended=False, is_remote=False)` - Send CAN message
- `read_message(timeout=1.0)` - Read single message
- `start_receive_thread(callback)` - Start background reception
- `stop_receive_thread()` - Stop background reception
- `get_available_devices()` - Scan for PCAN devices
- `get_bus_status()` - Get current bus status
- `set_filter(from_id, to_id, is_extended=False)` - Set acceptance filter
- `clear_receive_queue()` - Clear pending messages
- `reset_device()` - Reset the PCAN device

#### Properties
- `is_connected` - Connection status
- `channel` - Current channel
- `baudrate` - Current baud rate

### CANableDriver Class

#### Methods
- `connect(channel, baudrate, fd_mode=False)` - Connect to CANable device
  - `channel`: Serial port string (e.g., "COM3", "/dev/ttyACM0")
  - `baudrate`: CANableBaudRate enum value
- `disconnect()` - Disconnect from device
- `send_message(can_id, data, is_extended=False, is_remote=False)` - Send CAN message
- `read_message(timeout=1.0)` - Read single message
- `start_receive_thread(callback)` - Start background reception
- `stop_receive_thread()` - Stop background reception
- `get_available_devices()` - Scan for serial ports (potential CANable devices)
- `get_bus_status()` - Get current bus status
- `clear_receive_queue()` - Clear pending messages

#### Properties
- `is_connected` - Connection status
- `channel` - Current serial port
- `baudrate` - Current baud rate

### CANMessage Class (shared by both drivers)

#### Attributes
- `id` - CAN identifier
- `data` - Message data (bytes)
- `timestamp` - Reception timestamp
- `is_extended` - Extended ID flag
- `is_remote` - Remote frame flag
- `is_error` - Error frame flag
- `is_fd` - CAN FD flag (not supported by CANable)
- `dlc` - Data Length Code

## Command-Line Reference

### GUI_Master.py
```powershell
python GUI_Master.py [--device {pcan,canable}] [--channel CHANNEL]

Arguments:
  --device {pcan,canable}  CAN adapter type (default: pcan)
  --channel CHANNEL        PCAN channel (e.g., USB1) or CANable port (e.g., COM3)
```

### bootloader/Flash_Application.py
```powershell
python bootloader/Flash_Application.py FIRMWARE [OPTIONS]

Arguments:
  FIRMWARE                   Path to firmware .bin file

Options:
  --adapter {pcan,canable}   CAN adapter type (default: pcan)
  --channel CHANNEL          PCAN channel or CANable port
  --verify                   Verify by reading back (default: enabled)
  --no-verify                Skip verification
  --jump                     Jump to application after flashing (default: enabled)
  --no-jump                  Stay in bootloader
  --status-only              Only get bootloader status
  --list-devices             List available CAN devices
```

## Device Selection

The scripts support automatic device selection:

1. **No arguments**: Uses PCAN with default channel USB1
2. **`--adapter pcan`**: Explicitly use PCAN
3. **`--adapter canable`**: Use CANable adapter
4. **`--channel`**: Specify channel/port for selected device

Examples:
```powershell
# Default: PCAN USB1
python bootloader/Flash_Application.py firmware.bin

# PCAN USB2
python bootloader/Flash_Application.py firmware.bin --adapter pcan --channel USB2

# CANable on COM3
python bootloader/Flash_Application.py firmware.bin --adapter canable --channel COM3

# CANable on Linux
python bootloader/Flash_Application.py firmware.bin --adapter canable --channel /dev/ttyACM0
```

## License

This project is created for educational and development purposes.

## Credits

Built with:
- [python-can](https://python-can.readthedocs.io/) - Python CAN bus library
- [pyserial](https://pyserial.readthedocs.io/) - Serial port communication
- [DearPyGUI](https://dearpygui.readthedocs.io/) - Modern Python GUI framework
- [cantools](https://cantools.readthedocs.io/) - DBC file parsing
- [PCAN-Basic](https://www.peak-system.com/) - PEAK-System PCAN driver

## Author

GitHub Copilot - October 10, 2025
