# PythonCAN-Utils

A comprehensive Python-based CAN bus utility suite for PCAN-USB adapters, featuring an object-oriented driver and a graphical user interface similar to PCAN-Explorer.

## Features

### PCAN Driver (`PCAN_Driver.py`)
- **Object-Oriented Design**: Clean, Pythonic interface for PCAN devices
- **Device Management**: Scan, connect, and manage PCAN-USB adapters
- **Message Operations**: Send and receive CAN messages (standard/extended, data/remote frames)
- **Background Reception**: Asynchronous message reception with callback support
- **Bus Control**: Status monitoring, filtering, and queue management
- **Thread-Safe**: Safe for multi-threaded applications

### PCAN Explorer GUI (`PythonCAN-GUI.py`)
- **Visual Interface**: User-friendly GUI built with DearPyGUI
- **Live Monitoring**: Real-time CAN bus message display
- **Smart Message Handling**: Messages with the same ID are grouped with a counter
- **Message Transmission**: Send CAN messages with customizable parameters
- **Statistics**: Track message rates and unique IDs
- **Export Functionality**: Save captured messages to CSV
- **Period Calculation**: Automatic calculation of message transmission periods

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
- PCAN-USB adapter (PEAK-System hardware)
- PCAN-Basic driver installed (download from PEAK-System website)
- Windows OS (PCAN drivers are Windows-specific)

## Usage

### Using the PCAN Driver Programmatically

```python
from PCAN_Driver import PCANDriver, PCANChannel, PCANBaudRate

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

# Start background reception
def on_message(msg):
    print(f"Got message: {msg}")

driver.start_receive_thread(on_message)

# ... do other work ...

# Cleanup
driver.stop_receive_thread()
driver.disconnect()
```

### Using Context Manager

```python
from PCAN_Driver import PCANDriver, PCANChannel, PCANBaudRate

with PCANDriver() as driver:
    driver.connect(PCANChannel.USB1, PCANBaudRate.BAUD_500K)
    driver.send_message(0x456, b'\xAA\xBB\xCC\xDD')
    # Automatically disconnects when exiting the context
```

### Running the GUI Application

```powershell
python PythonCAN-GUI.py
```

## GUI Features

### Connection Panel
- **Channel Selection**: Choose from USB1-USB16
- **Baud Rate Selection**: Standard rates from 5K to 1M bps
- **Scan Devices**: Detect all connected PCAN adapters
- **Connect/Disconnect**: Manage connection to the adapter

### Message Transmission
- **CAN ID**: Enter in hexadecimal (e.g., 123)
- **Data**: Enter hex bytes space-separated (e.g., 01 02 03 04)
- **Extended ID**: Support for 29-bit identifiers
- **Remote Frame**: Send RTR frames

### Message Table
The table displays:
- **CAN ID**: Message identifier in hexadecimal
- **Type**: STD (standard), EXT (extended), STD-R/EXT-R (remote)
- **DLC**: Data Length Code
- **Data**: Message payload in hexadecimal
- **Count**: Number of times this ID was received
- **Last Received**: Timestamp of last reception
- **Period (ms)**: Time between consecutive messages with same ID

### Statistics
- **Total Messages**: Total count of received messages
- **Unique IDs**: Number of different CAN IDs observed
- **Message Rate**: Messages per second

### Actions
- **Clear Table**: Remove all messages from display
- **Export to CSV**: Save captured data to a timestamped CSV file

## Supported Baud Rates

- 1 Mbps (BAUD_1M)
- 800 kbps (BAUD_800K)
- 500 kbps (BAUD_500K)
- 250 kbps (BAUD_250K)
- 125 kbps (BAUD_125K)
- 100 kbps (BAUD_100K)
- And more down to 5 kbps

## Supported Channels

- PCAN_USBBUS1 through PCAN_USBBUS16

## Troubleshooting

### "No PCAN devices found"
- Ensure your PCAN-USB adapter is properly connected
- Install the PCAN-Basic driver from PEAK-System
- Check Windows Device Manager for the device

### "Failed to connect"
- Verify the device is not in use by another application
- Try disconnecting and reconnecting the USB adapter
- Check that the selected baud rate matches your CAN bus

### Import errors
- Make sure you've activated the virtual environment
- Reinstall dependencies: `pip install -r requirements.txt`

## Architecture

```
PythonCAN-Utils/
├── PCAN_Driver.py          # Core driver implementation
├── PythonCAN-GUI.py        # GUI application
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

### CANMessage Class

#### Attributes
- `id` - CAN identifier
- `data` - Message data (bytes)
- `timestamp` - Reception timestamp
- `is_extended` - Extended ID flag
- `is_remote` - Remote frame flag
- `is_error` - Error frame flag
- `is_fd` - CAN FD flag
- `dlc` - Data Length Code

## License

This project is created for educational and development purposes.

## Credits

Built with:
- [python-can](https://python-can.readthedocs.io/) - Python CAN bus library
- [DearPyGUI](https://dearpygui.readthedocs.io/) - Modern Python GUI framework
- [PCAN-Basic](https://www.peak-system.com/) - PEAK-System PCAN driver

## Author

GitHub Copilot - October 8, 2025
