# PythonCAN GUI - Tabbed Version

## Overview

**PythonCAN-GUI-Tabbed.py** is an all-in-one application that combines:
- **CAN Explorer** - Monitor and send CAN messages with DBC file support
- **Firmware Flasher** - Flash STM32L432 firmware via CAN bootloader

This eliminates the need to run separate programs and avoids PCAN device access conflicts.

## Features

### CAN Explorer Tab
- ✅ Connect to PCAN-USB devices (500 kbps default)
- ✅ Send/receive CAN messages
- ✅ Load DBC files for automatic message decoding
- ✅ Real-time message table with statistics
- ✅ Export messages to CSV
- ✅ Support for standard/extended IDs and remote frames

### Firmware Flasher Tab
- ✅ Select firmware .bin file
- ✅ Erase STM32L432 flash memory
- ✅ Flash firmware via CAN bootloader (4-byte chunk method)
- ✅ Real-time progress bar and logging
- ✅ Jump to application command

## Usage

### 1. Start the Application

```bash
python PythonCAN-GUI-Tabbed.py
```

### 2. Connect to PCAN

1. Select your PCAN channel (USB1, USB2, etc.)
2. Select baud rate (500K for bootloader)
3. Click **Connect**

**Note:** Once connected, both tabs share the same CAN connection - no conflicts!

### 3. CAN Explorer Tab

**Monitor Messages:**
- Switch to "CAN Explorer" tab
- Messages appear automatically in the table
- View decoded signals if DBC file is loaded

**Send Messages:**
- Enter CAN ID in hex (e.g., `123`)
- Enter data in hex (e.g., `01 02 03 04`)
- Click **Send**

**Load DBC File:**
- Click **Load DBC**
- Select your .dbc file
- Messages will be decoded automatically

### 4. Firmware Flasher Tab

**Flash Firmware:**
1. Switch to "Firmware Flasher" tab
2. Click **Browse** and select your .bin file
3. Click **Erase Flash** (wait for completion)
4. Click **Flash Firmware** (progress bar shows status)
5. Click **Jump to App** to start the application

**Monitor Flash Process:**
- Progress bar shows % complete
- Flash Log shows detailed messages
- Status text shows current operation

## Workflow Example

```
1. Connect to PCAN @ 500 kbps
2. Go to "Firmware Flasher" tab
3. Select firmware: CAN-Application-TEST.bin
4. Erase Flash → Wait for "Erase complete!"
5. Flash Firmware → Wait for "Flash complete!"
6. Jump to App
7. Go to "CAN Explorer" tab
8. Monitor application messages (heartbeat, etc.)
9. Load DBC file to decode messages
```

## Benefits Over Separate Scripts

| Old Way | New Way |
|---------|---------|
| Run Flash_Application.py | One program for everything |
| PCAN device locked | Share connection between tabs |
| Switch to PythonCAN-GUI.py | Switch tabs instead |
| PCAN device busy error | No conflicts! |
| Two terminal windows | Clean tabbed interface |

## Requirements

```
pip install python-can dearpygui cantools
```

## Troubleshooting

**"Not Connected" error:**
- Click Connect button at the top first
- Connection applies to both tabs

**Flash fails:**
- Ensure device is in bootloader mode
- Check baud rate is 500 kbps
- Verify firmware file is valid .bin

**DBC not loading:**
- Install cantools: `pip install cantools`
- Check DBC file for syntax errors

## Protocol Details

**Bootloader CAN IDs:**
- `0x701` - Host sends commands
- `0x700` - Bootloader responds

**Flash Method:**
- 4-byte chunks per CAN message
- Bootloader buffers 2 chunks for 8-byte flash writes
- Address: 0x08008000 (STM32L432)
- Max size: 224 KB

## Files

- `PythonCAN-GUI-Tabbed.py` - Main tabbed GUI (recommended)
- `PythonCAN-GUI.py` - Original CAN Explorer only
- `Flash_Application.py` - Standalone flash script (legacy)
- `PCAN_Driver.py` - PCAN hardware driver wrapper

---

**Author:** GitHub Copilot  
**Date:** October 8, 2025
