# PythonCAN-Utils Copilot Instructions

## Project Overview
CAN bus utility suite with dual adapter support (PCAN-USB, CANable) featuring a FastAPI backend and React frontend for real-time CAN communication, DBC decoding, and STM32 firmware flashing.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React Frontend (port 3001)                                 │
│  webserver/frontend/src/                                    │
├─────────────────────────────────────────────────────────────┤
│  REST API + WebSocket → Real-time CAN streams               │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Backend (port 8000)                                │
│  webserver/backend/api.py → CANBackend class                │
├─────────────────────────────────────────────────────────────┤
│  Driver Layer: drivers/PCAN_Driver.py, CANable_Driver.py    │
│  Both expose identical API: connect(), send_message(),      │
│  start_receive_thread(), disconnect()                       │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start Commands
```bash
# One-click start (backend + frontend + browser)
python start.py
# Or on Windows: double-click start.bat

# Manual backend only
cd webserver/backend && python api.py

# Manual frontend only (port 3001)
cd webserver/frontend && set PORT=3001 && npm start
```

## Key Patterns

### Driver Interface Pattern
Both `PCANDriver` and `CANableDriver` share the same interface. When adding features, implement in both:
```python
driver.connect(channel, baudrate)
driver.send_message(can_id, data_bytes, is_extended, is_remote)
driver.start_receive_thread(callback)  # Async message reception
driver.disconnect()
```

### WebSocket Message Flow
1. Driver receive thread calls `_on_message_received()` in `CANBackend`
2. Messages are decoded via DBC if loaded, then broadcast to all WebSocket clients
3. Frontend `websocket.js` parses and routes to React state in `App.js`

### DBC File Handling
- Upload via `/dbc/upload` endpoint → stored in `webserver/backend/dbc_files/`
- Last loaded file tracked in `last_loaded.txt` for persistence
- Decoding uses `cantools` library with extended ID support (mask `0x1FFFFFFF`)

### Pydantic Models
All API request/response types defined in `api.py` lines 70-175. Follow this pattern for new endpoints.

## Frontend Conventions
- Components in `webserver/frontend/src/components/` with matching `.css` files
- State management in `App.js` with props drilling to child components
- API service layer in `services/api.js` (axios), WebSocket in `services/websocket.js`
- Use `lucide-react` for icons (see imports in `CANExplorer.js`)

## CANable-Specific Notes
- Requires `libusb-1.0.dll` in project root on Windows
- Uses `gs_usb` interface (candleLight firmware) via `python-can`
- USB setup in `CANable_Driver.py` lines 25-50 must run before `python-can` import

## Testing
```bash
# Backend API tests
cd webserver/backend && python test_api.py

# Direct CAN driver tests
python test_canable.py
python test_can_direct.py
```

## File Locations
| Purpose | Location |
|---------|----------|
| Main entry point | `start.py`, `start.bat` |
| Backend API | `webserver/backend/api.py` |
| CAN Drivers | `drivers/PCAN_Driver.py`, `drivers/CANable_Driver.py` |
| Firmware Flasher | `drivers/Firmware_Flasher.py` |
| Frontend App | `webserver/frontend/src/App.js` |
| API Service | `webserver/frontend/src/services/api.js` |
| DBC Storage | `webserver/backend/dbc_files/` |
| Bootloader DBC | `bootloader/STM32L432_Bootloader.dbc` |

## Adding New Features

### New REST Endpoint
1. Add Pydantic model in `api.py` (request/response schemas)
2. Add endpoint function with proper typing
3. Update `services/api.js` in frontend if UI needed

### New CAN Adapter Support
1. Create driver in `drivers/` following `PCANDriver`/`CANableDriver` interface
2. Add import and availability check in `api.py` lines 38-50
3. Add to `DeviceType` enum and `CANBackend.connect()` switch
