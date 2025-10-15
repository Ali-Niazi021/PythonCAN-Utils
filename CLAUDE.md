# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PythonCAN-Utils is a comprehensive CAN bus utility suite that supports both PCAN-USB and CANable adapters. It consists of three main components:
1. **Object-oriented CAN drivers** ([drivers/PCAN_Driver.py](drivers/PCAN_Driver.py), [drivers/CANable_Driver.py](drivers/CANable_Driver.py))
2. **GUI application** ([GUI_Master.py](GUI_Master.py)) - PCAN-Explorer-like interface with DBC support
3. **Firmware flasher** ([Flash_Application.py](Flash_Application.py)) - STM32L432 CAN bootloader utility

## Development Setup

### Environment Setup
```powershell
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Applications
```powershell
# GUI application (PCAN default)
python GUI_Master.py

# GUI with CANable (specify device index)
python GUI_Master.py --device canable --channel 0

# Firmware flasher (PCAN default)
python Flash_Application.py firmware.bin

# Firmware flasher with CANable
python Flash_Application.py firmware.bin --device canable --channel 0

# List available devices
python Flash_Application.py --list-devices --device pcan
python Flash_Application.py --list-devices --device canable
```

## Architecture

### Driver Layer (drivers/)

Both drivers provide a **unified API** with identical method signatures:

**Key Methods:**
- `connect(channel, baudrate, fd_mode=False)` - Connect to device
- `disconnect()` - Disconnect from device
- `send_message(can_id, data, is_extended=False, is_remote=False)` - Send CAN message
- `read_message(timeout=1.0)` - Read single CAN message
- `start_receive_thread(callback)` - Background reception with callback
- `stop_receive_thread()` - Stop background reception
- `get_available_devices()` - Scan for devices
- `get_bus_status()` - Get bus status
- `clear_receive_queue()` - Clear pending messages

**Properties:**
- `is_connected` - Connection status
- `channel` - Current channel
- `baudrate` - Current baud rate

#### PCAN Driver ([drivers/PCAN_Driver.py](drivers/PCAN_Driver.py))

- Uses `python-can` library with PCAN interface
- Requires PCAN-Basic driver installed on Windows
- Channels: `PCANChannel.USB1` through `USB16`
- Uses `PCANBasic()` for device enumeration
- Channel format: `PCANChannel` enum (e.g., `PCANChannel.USB1`)

#### CANable Driver ([drivers/CANable_Driver.py](drivers/CANable_Driver.py))

- Uses `python-can` with `gs_usb` interface (Candle API)
- Requires `libusb-1.0.dll` (Windows) or libusb (Linux/Mac)
- Uses `pyusb` for USB device enumeration
- Supports CANable devices with candleLight firmware
- Channel format: Integer device index (0, 1, 2, ...)
- VID/PID pairs in `GS_USB_DEVICES` list

**Important:** CANable uses direct USB access (not serial SLCAN), providing better performance.

### Application Layer

#### GUI Application ([GUI_Master.py](GUI_Master.py:1-1525))

Four-tab interface built with DearPyGUI:

1. **CAN Explorer Tab** - Live message monitoring with DBC decoding
   - Message table with auto-update
   - DBC file support via `cantools` library
   - Send CAN messages
   - Export to CSV
   - Real-time statistics (message rate, unique IDs)

2. **Thermistor Monitor Tab** - 8-channel temperature display
   - Monitors CAN IDs `0x710-0x713` (Thermistor_Pair_0 through 3)
   - Monitors CAN IDs `0x720-0x721` (ADC_Raw_0_3 and ADC_Raw_4_7)
   - Automatically decodes using DBC
   - Color-coded temperature display

3. **Cell Voltage Monitor Tab** - BQ76952 battery monitoring
   - Monitors 16 individual cell voltages
   - Stack voltage display
   - CAN IDs `0x731-0x735` (BQ76952_Stack_Voltage, Cell_Voltages_1_4 through 13_16)
   - 1mV resolution display

4. **Firmware Flasher Tab** - Integrated STM32 bootloader
   - Flash firmware via CAN bus
   - Progress tracking
   - Erase, write, verify, jump operations

**Key Architecture Patterns:**
- Driver abstraction: `self.driver` can be either `PCANDriver` or `CANableDriver`
- Message callback: `_on_message_received()` handles all incoming CAN messages
- Threading: Background receive thread for continuous monitoring
- Thread-safe: Uses `self.message_lock` for message data access

#### Firmware Flasher ([Flash_Application.py](Flash_Application.py:1-1042))

Standalone CLI tool for flashing STM32L432 via CAN bootloader.

**Bootloader Protocol:**
- Host CAN ID: `0x701`
- Bootloader CAN ID: `0x700`
- Commands: `CMD_ERASE_FLASH`, `CMD_WRITE_DATA`, `CMD_READ_FLASH`, `CMD_JUMP_TO_APP`, `CMD_GET_STATUS`, `CMD_SET_ADDRESS`
- Responses: `RESP_ACK`, `RESP_NACK`, `RESP_ERROR`, `RESP_READY`, `RESP_DATA`

**Flash Process:**
1. Connect to CAN device (500 kbps)
2. Wait for bootloader READY message
3. Erase flash (timeout: 15 seconds)
4. Set address to `APP_START_ADDRESS` (0x08008000)
5. Write firmware in 4-byte chunks
6. Bootloader buffers 2 chunks (8 bytes) before flash write
7. Verify by reading back (optional)
8. Jump to application (optional)

**Important:**
- Firmware is padded to 4-byte boundary for STM32 flash alignment
- Each 4-byte chunk requires ACK before continuing
- Write timeout: 1 second per chunk
- Max firmware size: 224 KB

## Common Development Patterns

### Adding Support for New CAN Adapters

To add a new CAN adapter:
1. Create new driver in `drivers/` (e.g., `MyAdapter_Driver.py`)
2. Implement the unified API methods (see driver methods above)
3. Add import and availability flag in [GUI_Master.py](GUI_Master.py:24-41) and [Flash_Application.py](Flash_Application.py:28-46)
4. Add device type to argument parser choices

### Adding New CAN Message Handlers

For GUI message handling:
1. Add message ID constants (if needed)
2. Create handler method in `PCANExplorerGUI` class
3. Call handler from `_on_message_received()` callback
4. Update UI in handler (use `dpg.set_value()` for updates)

Example pattern:
```python
def _on_message_received(self, msg):
    # Check message ID and route to handler
    if 0x710 <= msg.id <= 0x713:
        self._update_thermistor_data(msg.id, msg.data)
```

### Working with DBC Files

The GUI uses `cantools` library for DBC support:
```python
# Load DBC
self.dbc_database = cantools.database.load_file(file_path)

# Get message by ID
message = self.dbc_database.get_message_by_frame_id(can_id)

# Decode message
decoded = message.decode(data)  # Returns dict of signal names to values

# Access signal metadata
signal = message.get_signal_by_name(signal_name)
unit = signal.unit
scale = signal.scale
choices = signal.choices  # For enum signals
```

### Bootloader Command Structure

All bootloader commands follow 8-byte CAN format:
- Byte 0: Command byte
- Bytes 1-7: Command-specific data (padded with 0x00)

Example for `CMD_SET_ADDRESS`:
```python
addr_bytes = [
    (address >> 24) & 0xFF,  # MSB first (big-endian)
    (address >> 16) & 0xFF,
    (address >> 8) & 0xFF,
    address & 0xFF
]
send_command(CMD_SET_ADDRESS, addr_bytes)
```

Example for `CMD_WRITE_DATA` (4-byte chunk):
```python
cmd_data = [0x04] + list(chunk)  # 0x04 = length, then 4 data bytes
send_command(CMD_WRITE_DATA, cmd_data)
```

## Important Implementation Notes

### CANable Device Index vs Port

- **GUI and Flash Tool:** Use integer device index (0, 1, 2) as channel
- Device index from `get_available_devices()` list position
- Not a COM port or serial device path

### Thread Safety

GUI message handling uses threading:
- Background thread continuously receives CAN messages
- `self.message_lock` protects `self.message_data` dictionary
- UI updates must use `dpg.set_value()` (DearPyGUI is thread-safe for this)

### DearPyGUI Patterns

- Create elements with `tag="element_name"` for later access
- Update values: `dpg.set_value("element_name", new_value)`
- Configure properties: `dpg.configure_item("element_name", color=(r, g, b))`
- Tables: Add rows with `dpg.table_row()`, store row tag for updates

### Firmware Padding

STM32 flash requires 8-byte alignment:
- Firmware padded to 4-byte boundary (ensures 8-byte alignment)
- Bootloader buffers two 4-byte chunks before writing 8 bytes to flash
- Padding bytes should be `0xFF` (erased flash state)

## Error Handling Patterns

### Driver Connection Errors

Both drivers return `False` on connection failure and print error messages. Check return value:
```python
if not driver.connect(channel, baudrate):
    # Handle error
    return False
```

### Bootloader Communication

Always check for ACK/NACK responses:
```python
response = wait_response()
if response and response[0] == RESP_ACK:
    # Success
elif response and response[0] == RESP_NACK:
    error_code = response[1] if len(response) > 1 else 0
    # Handle specific error
else:
    # Timeout or unexpected response
```

### DBC Decoding

DBC decode can fail if message not in database:
```python
try:
    message = self.dbc_database.get_message_by_frame_id(can_id)
    decoded = message.decode(data)
except:
    # Message not in DBC or decode error - handle gracefully
    pass
```

## Key Files Reference

- [drivers/PCAN_Driver.py](drivers/PCAN_Driver.py) - PCAN adapter driver (100-600 lines)
- [drivers/CANable_Driver.py](drivers/CANable_Driver.py) - CANable adapter driver (100-580 lines)
- [GUI_Master.py](GUI_Master.py) - Main GUI application (1525 lines)
- [Flash_Application.py](Flash_Application.py) - Firmware flasher CLI (1042 lines)
- [requirements.txt](requirements.txt) - Python dependencies
- [README.md](README.md) - User documentation and usage examples

## Dependencies

- `python-can>=4.0.0` - CAN bus library (supports both PCAN and gs_usb)
- `pyusb>=1.2.1` - USB device enumeration for CANable
- `dearpygui>=1.10.0` - GUI framework
- `cantools>=39.0.0` - DBC file parsing

External dependencies:
- **PCAN:** PCAN-Basic driver from PEAK-System (Windows)
- **CANable:** libusb-1.0.dll in project root (Windows) or system libusb (Linux/Mac)
