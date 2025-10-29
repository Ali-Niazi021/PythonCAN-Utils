"""
CAN Communication Backend API
==============================
FastAPI backend for CAN device communication with WebSocket support.
Provides REST endpoints and real-time WebSocket streams for CAN messages.

Author: GitHub Copilot
Date: October 27, 2025
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, List, Union
from datetime import datetime
import asyncio
import json
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import shutil

# Add parent directories to path for driver imports
backend_dir = Path(__file__).parent
project_dir = backend_dir.parent.parent
sys.path.insert(0, str(project_dir))

# DBC files directory setup
DBC_DIR = backend_dir / "dbc_files"
DBC_DIR.mkdir(exist_ok=True)
LAST_DBC_FILE = DBC_DIR / "last_loaded.txt"

# Transmit lists directory setup
TRANSMIT_LISTS_DIR = backend_dir / "transmit_lists"
TRANSMIT_LISTS_DIR.mkdir(exist_ok=True)

# Import CAN drivers
try:
    from drivers.PCAN_Driver import PCANDriver, PCANChannel, PCANBaudRate, CANMessage as PCANMessage
    PCAN_AVAILABLE = True
except ImportError:
    PCAN_AVAILABLE = False
    print("Warning: PCAN_Driver not available")

try:
    from drivers.CANable_Driver import CANableDriver, CANableBaudRate, CANMessage as CANableMessage
    CANABLE_AVAILABLE = True
except ImportError:
    CANABLE_AVAILABLE = False
    print("Warning: CANable_Driver not available")

# Import firmware flasher
try:
    from drivers.Firmware_Flasher import FirmwareFlasher
    FIRMWARE_FLASHER_AVAILABLE = True
except ImportError:
    FIRMWARE_FLASHER_AVAILABLE = False
    print("Warning: Firmware_Flasher not available")

# Import DBC support
try:
    import cantools
    DBC_SUPPORT = True
except ImportError:
    DBC_SUPPORT = False
    print("Warning: cantools not installed. DBC support disabled.")


# ============================================================================
# Pydantic Models (API Request/Response Schemas)
# ============================================================================

class DeviceType(str, Enum):
    """Supported CAN device types"""
    PCAN = "pcan"
    CANABLE = "canable"


class ConnectionRequest(BaseModel):
    """Request to connect to a CAN device"""
    device_type: DeviceType
    channel: Union[str, int]  # Channel name for PCAN or device index for CANable
    baudrate: str  # e.g., "BAUD_500K"


class ConnectionResponse(BaseModel):
    """Response from connection attempt"""
    success: bool
    message: str
    device_type: Optional[str] = None
    channel: Optional[Union[str, int]] = None
    baudrate: Optional[str] = None


class DisconnectionResponse(BaseModel):
    """Response from disconnection attempt"""
    success: bool
    message: str


class DeviceInfo(BaseModel):
    """Information about an available CAN device"""
    device_type: str
    index: int
    name: str
    description: str
    available: bool
    occupied: Optional[bool] = None


class DeviceListResponse(BaseModel):
    """Response containing list of available devices"""
    pcan_available: bool
    canable_available: bool
    devices: List[DeviceInfo]


class BusStatusResponse(BaseModel):
    """Current bus status information"""
    connected: bool
    device_type: Optional[str] = None
    channel: Optional[Union[str, int]] = None
    baudrate: Optional[str] = None
    status: Optional[str] = None
    interface: Optional[str] = None


class CANMessageRequest(BaseModel):
    """Request to send a CAN message"""
    can_id: int
    data: List[int]  # List of bytes (0-255)
    is_extended: bool = False
    is_remote: bool = False


class CANMessageResponse(BaseModel):
    """Response after sending a CAN message"""
    success: bool
    message: str


class CANMessageData(BaseModel):
    """CAN message data structure"""
    id: int
    data: List[int]
    timestamp: float
    is_extended: bool
    is_remote: bool
    dlc: int


class DBCLoadRequest(BaseModel):
    """Request to load a DBC file"""
    file_path: str


class DBCLoadResponse(BaseModel):
    """Response from DBC file loading"""
    success: bool
    message: str
    file_path: Optional[str] = None
    message_count: Optional[int] = None


class TransmitListItem(BaseModel):
    """Single item in the transmit list"""
    id: str  # Unique ID for this item
    can_id: int
    data: List[int]  # List of bytes (0-255)
    is_extended: bool = False
    message_name: Optional[str] = None  # DBC message name if from DBC
    signals: Optional[Dict[str, Union[int, float, str]]] = None  # Signal values if from DBC
    description: Optional[str] = None


class TransmitListResponse(BaseModel):
    """Response containing transmit list"""
    success: bool
    items: List[TransmitListItem]
    dbc_file: Optional[str] = None


class SaveTransmitListRequest(BaseModel):
    """Request to save transmit list"""
    items: List[TransmitListItem]
    dbc_file: str


class DBCMessageInfo(BaseModel):
    """Information about a DBC message"""
    name: str
    frame_id: int
    is_extended: bool
    dlc: int
    length: int
    signal_count: int
    signals: List[dict]


class DBCMessagesResponse(BaseModel):
    """Response containing DBC message list"""
    success: bool
    messages: List[DBCMessageInfo]


class FirmwareFlashResponse(BaseModel):
    """Response from firmware flash operation"""
    success: bool
    message: str
    error: Optional[str] = None


# ============================================================================
# Backend Application State
# ============================================================================

class CANBackend:
    """Backend state management for CAN communication"""
    
    def __init__(self):
        self.driver: Optional[Union[PCANDriver, CANableDriver]] = None
        self.device_type: Optional[DeviceType] = None
        self.is_connected: bool = False
        self.dbc_database: Optional['cantools.database.Database'] = None
        self.dbc_file_path: Optional[str] = None
        
        # WebSocket connections
        self.active_connections: List[WebSocket] = []
        
        # Message statistics
        self.message_count: int = 0
        self.start_time: Optional[datetime] = None
    
    def get_available_devices(self) -> List[DeviceInfo]:
        """Get list of all available CAN devices"""
        devices = []
        
        # PCAN devices
        if PCAN_AVAILABLE:
            try:
                pcan_driver = PCANDriver()
                pcan_devices = pcan_driver.get_available_devices()
                for idx, dev in enumerate(pcan_devices):
                    devices.append(DeviceInfo(
                        device_type="pcan",
                        index=idx,
                        name=dev['channel'],
                        description=f"PCAN {dev['channel']}",
                        available=dev['available'],
                        occupied=dev.get('occupied', False)
                    ))
            except Exception as e:
                print(f"Error scanning PCAN devices: {e}")
        
        # CANable devices
        if CANABLE_AVAILABLE:
            try:
                canable_driver = CANableDriver()
                canable_devices = canable_driver.get_available_devices()
                for dev in canable_devices:
                    devices.append(DeviceInfo(
                        device_type="canable",
                        index=dev['index'],
                        name=f"Device {dev['index']}",
                        description=dev.get('description', f"CANable Device {dev['index']}"),
                        available=True
                    ))
            except Exception as e:
                print(f"Error scanning CANable devices: {e}")
        
        return devices
    
    def connect(self, device_type: DeviceType, channel: Union[str, int], baudrate: str) -> bool:
        """Connect to a CAN device"""
        if self.is_connected:
            return False
        
        try:
            # Create appropriate driver
            if device_type == DeviceType.PCAN:
                if not PCAN_AVAILABLE:
                    raise Exception("PCAN driver not available")
                
                self.driver = PCANDriver()
                pcan_channel = PCANChannel[channel]
                pcan_baudrate = PCANBaudRate[baudrate]
                
                if not self.driver.connect(pcan_channel, pcan_baudrate):
                    return False
                
            elif device_type == DeviceType.CANABLE:
                if not CANABLE_AVAILABLE:
                    raise Exception("CANable driver not available")
                
                self.driver = CANableDriver()
                canable_baudrate = CANableBaudRate[baudrate]
                
                if not self.driver.connect(int(channel), canable_baudrate):
                    return False
            
            else:
                raise Exception(f"Unknown device type: {device_type}")
            
            # Start receive thread
            self.driver.start_receive_thread(self._on_message_received)
            
            self.device_type = device_type
            self.is_connected = True
            self.start_time = datetime.now()
            self.message_count = 0
            
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from CAN device"""
        if not self.is_connected or not self.driver:
            return False
        
        try:
            self.driver.stop_receive_thread()
            self.driver.disconnect()
            self.driver = None
            self.is_connected = False
            self.device_type = None
            return True
        except Exception as e:
            print(f"Disconnection error: {e}")
            return False
    
    def send_message(self, can_id: int, data: List[int], 
                    is_extended: bool = False, is_remote: bool = False) -> bool:
        """Send a CAN message"""
        if not self.is_connected or not self.driver:
            return False
        
        try:
            data_bytes = bytes(data)
            return self.driver.send_message(can_id, data_bytes, is_extended, is_remote)
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    def get_bus_status(self) -> dict:
        """Get current bus status"""
        if not self.is_connected or not self.driver:
            return {'connected': False}
        
        status = self.driver.get_bus_status()
        status['device_type'] = self.device_type.value if self.device_type else None
        return status
    
    def load_dbc_file(self, file_path: str) -> bool:
        """Load a DBC file for message decoding"""
        if not DBC_SUPPORT:
            return False
        
        try:
            self.dbc_database = cantools.database.load_file(file_path, strict=False)
            self.dbc_file_path = file_path
            return True
        except Exception as e:
            print(f"DBC load error: {e}")
            return False
    
    def get_dbc_messages(self) -> List[dict]:
        """Get list of messages from loaded DBC file"""
        if not self.dbc_database:
            return []
        
        messages = []
        for msg in self.dbc_database.messages:
            try:
                is_extended = msg.frame_id > 0x7FF
                actual_id = msg.frame_id & 0x1FFFFFFF if is_extended else msg.frame_id
                
                signals = []
                for signal in msg.signals:
                    # Convert choices to plain dict (cantools returns NamedSignalValue objects)
                    choices_dict = {}
                    if signal.choices:
                        choices_dict = {int(k): str(v) for k, v in signal.choices.items()}
                    
                    signals.append({
                        'name': signal.name,
                        'start_bit': signal.start,
                        'length': signal.length,
                        'byte_order': signal.byte_order,
                        'scale': signal.scale,
                        'offset': signal.offset,
                        'minimum': signal.minimum,
                        'maximum': signal.maximum,
                        'unit': signal.unit or '',
                        'choices': choices_dict
                    })
                
                # Ensure length is an integer, default to 8 if not set
                msg_length = msg.length if msg.length is not None else 8
                
                messages.append({
                    'name': msg.name,
                    'frame_id': actual_id,
                    'is_extended': is_extended,
                    'dlc': msg_length,
                    'length': msg_length,
                    'signal_count': len(signals),
                    'signals': signals
                })
            except Exception as e:
                print(f"Error processing message {msg.name}: {e}")
                continue
        
        return messages
    
    def decode_message(self, can_id: int, data: bytes, is_extended: bool = False) -> Optional[dict]:
        """Decode a CAN message using DBC"""
        if not self.dbc_database:
            return None
        
        try:
            lookup_id = can_id | 0x80000000 if is_extended else can_id
            message = self.dbc_database.get_message_by_frame_id(lookup_id)
            decoded = message.decode(data)
            
            # Convert NamedSignalValue objects to regular Python types for JSON serialization
            # If a signal has enumerated values (VAL_ in DBC), use the name; otherwise use the numeric value
            # Also include units and other metadata from the signal definition
            signals = {}
            for key, value in decoded.items():
                # Get the signal definition for metadata
                signal = message.get_signal_by_name(key)
                
                # Extract the display value (enum name or numeric value)
                if hasattr(value, 'name') and value.name is not None:
                    # Use the enumerated text label (e.g., "FAULT" instead of 5)
                    display_value = value.name
                    raw_value = value.value
                elif hasattr(value, 'value'):
                    # No enum, just use the numeric value
                    display_value = value.value
                    raw_value = value.value
                else:
                    # Plain value (shouldn't happen with cantools, but just in case)
                    display_value = value
                    raw_value = value
                
                # Build signal info with metadata
                signal_info = {
                    'value': display_value,
                }
                
                # Add raw numeric value if different from display (for enums)
                if isinstance(display_value, str) and isinstance(raw_value, (int, float)):
                    signal_info['raw'] = raw_value
                
                # Add unit if available
                if signal.unit:
                    signal_info['unit'] = signal.unit
                
                # Add scale and offset if non-default
                if signal.scale != 1:
                    signal_info['scale'] = signal.scale
                if signal.offset != 0:
                    signal_info['offset'] = signal.offset
                
                # Add min/max range if specified
                if signal.minimum is not None:
                    signal_info['min'] = signal.minimum
                if signal.maximum is not None:
                    signal_info['max'] = signal.maximum
                
                signals[key] = signal_info
            
            return {
                'message_name': message.name,
                'signals': signals
            }
        except:
            return None
    
    async def _on_message_received(self, msg):
        """Callback for received CAN messages - broadcasts to all WebSocket clients"""
        self.message_count += 1
        
        # Convert message to JSON-serializable format
        message_data = {
            'id': msg.id,
            'data': list(msg.data),
            'timestamp': msg.timestamp,
            'is_extended': msg.is_extended,
            'is_remote': msg.is_remote,
            'dlc': msg.dlc
        }
        
        # Try to decode if DBC available
        if self.dbc_database:
            decoded = self.decode_message(msg.id, msg.data, msg.is_extended)
            if decoded:
                message_data['decoded'] = decoded
        
        # Broadcast to all connected WebSocket clients
        await self.broadcast_message(message_data)
    
    async def broadcast_message(self, message: dict):
        """Broadcast message to all connected WebSocket clients"""
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            if connection in self.active_connections:
                self.active_connections.remove(connection)
    
    async def add_websocket_connection(self, websocket: WebSocket):
        """Add a WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def remove_websocket_connection(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="CAN Communication Backend",
    description="REST API and WebSocket interface for CAN bus communication",
    version="1.0.0"
)

# CORS middleware for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global backend instance
backend = CANBackend()


# ============================================================================
# REST API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "CAN Communication Backend",
        "version": "1.0.0",
        "pcan_available": PCAN_AVAILABLE,
        "canable_available": CANABLE_AVAILABLE,
        "dbc_support": DBC_SUPPORT
    }


@app.get("/devices", response_model=DeviceListResponse)
async def get_devices():
    """Get list of available CAN devices"""
    devices = backend.get_available_devices()
    return DeviceListResponse(
        pcan_available=PCAN_AVAILABLE,
        canable_available=CANABLE_AVAILABLE,
        devices=devices
    )


@app.post("/connect", response_model=ConnectionResponse)
async def connect(request: ConnectionRequest):
    """Connect to a CAN device"""
    if backend.is_connected:
        raise HTTPException(status_code=400, detail="Already connected. Disconnect first.")
    
    success = backend.connect(request.device_type, request.channel, request.baudrate)
    
    if success:
        return ConnectionResponse(
            success=True,
            message="Connected successfully",
            device_type=request.device_type.value,
            channel=request.channel,
            baudrate=request.baudrate
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to connect to device")


@app.post("/disconnect", response_model=DisconnectionResponse)
async def disconnect():
    """Disconnect from CAN device"""
    if not backend.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to any device")
    
    success = backend.disconnect()
    
    if success:
        return DisconnectionResponse(success=True, message="Disconnected successfully")
    else:
        raise HTTPException(status_code=500, detail="Failed to disconnect")


@app.get("/status", response_model=BusStatusResponse)
async def get_status():
    """Get current bus status"""
    status = backend.get_bus_status()
    return BusStatusResponse(**status)


@app.post("/send", response_model=CANMessageResponse)
async def send_message(request: CANMessageRequest):
    """Send a CAN message"""
    if not backend.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to any device")
    
    success = backend.send_message(
        request.can_id,
        request.data,
        request.is_extended,
        request.is_remote
    )
    
    if success:
        return CANMessageResponse(success=True, message="Message sent successfully")
    else:
        raise HTTPException(status_code=500, detail="Failed to send message")


@app.post("/dbc/upload", response_model=DBCLoadResponse)
async def upload_dbc(file: UploadFile = File(...)):
    """Upload and load a DBC file"""
    if not DBC_SUPPORT:
        raise HTTPException(status_code=400, detail="DBC support not available (install cantools)")
    
    # Validate file extension
    if not file.filename.endswith('.dbc'):
        raise HTTPException(status_code=400, detail="File must have .dbc extension")
    
    try:
        # Save the uploaded file
        file_path = DBC_DIR / file.filename
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        
        # Load the DBC file
        success = backend.load_dbc_file(str(file_path))
        
        if success:
            # Save as last loaded file
            with open(LAST_DBC_FILE, 'w') as f:
                f.write(file.filename)
            
            message_count = len(backend.dbc_database.messages) if backend.dbc_database else 0
            return DBCLoadResponse(
                success=True,
                message=f"DBC file '{file.filename}' uploaded and loaded successfully",
                file_path=str(file_path),
                message_count=message_count
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to load DBC file")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@app.get("/dbc/current")
async def get_current_dbc():
    """Get information about currently loaded DBC file"""
    if not backend.dbc_database:
        return {
            "loaded": False,
            "filename": None,
            "message_count": 0
        }
    
    # Try to get filename from last loaded
    filename = "Unknown"
    if LAST_DBC_FILE.exists():
        with open(LAST_DBC_FILE, 'r') as f:
            filename = f.read().strip()
    
    return {
        "loaded": True,
        "filename": filename,
        "message_count": len(backend.dbc_database.messages)
    }


@app.get("/dbc/list")
async def list_dbc_files():
    """List all uploaded DBC files"""
    files = []
    for file_path in DBC_DIR.glob("*.dbc"):
        files.append({
            "filename": file_path.name,
            "size": file_path.stat().st_size,
            "modified": file_path.stat().st_mtime
        })
    return {"files": files}


@app.delete("/dbc/delete/{filename}")
async def delete_dbc_file(filename: str):
    """Delete a DBC file"""
    # Validate filename to prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    file_path = DBC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        file_path.unlink()
        
        # Clear last loaded if this was the last file
        if LAST_DBC_FILE.exists():
            with open(LAST_DBC_FILE, 'r') as f:
                last_filename = f.read().strip()
            if last_filename == filename:
                LAST_DBC_FILE.unlink()
                backend.dbc_database = None
        
        return {"success": True, "message": f"File '{filename}' deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


@app.post("/dbc/load", response_model=DBCLoadResponse)
async def load_dbc(request: DBCLoadRequest):
    """Load a DBC file (legacy endpoint for backward compatibility)"""
    if not DBC_SUPPORT:
        raise HTTPException(status_code=400, detail="DBC support not available (install cantools)")
    
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="DBC file not found")
    
    success = backend.load_dbc_file(request.file_path)
    
    if success:
        message_count = len(backend.dbc_database.messages) if backend.dbc_database else 0
        return DBCLoadResponse(
            success=True,
            message="DBC file loaded successfully",
            file_path=request.file_path,
            message_count=message_count
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to load DBC file")


@app.get("/dbc/messages", response_model=DBCMessagesResponse)
async def get_dbc_messages():
    """Get list of messages from loaded DBC file"""
    if not backend.dbc_database:
        raise HTTPException(status_code=400, detail="No DBC file loaded")
    
    messages = backend.get_dbc_messages()
    return DBCMessagesResponse(success=True, messages=messages)


@app.get("/stats")
async def get_stats():
    """Get message statistics"""
    if not backend.is_connected:
        return {
            "connected": False,
            "message_count": 0,
            "uptime_seconds": 0,
            "message_rate": 0
        }
    
    uptime = (datetime.now() - backend.start_time).total_seconds() if backend.start_time else 0
    message_rate = backend.message_count / uptime if uptime > 0 else 0
    
    return {
        "connected": True,
        "message_count": backend.message_count,
        "uptime_seconds": uptime,
        "message_rate": round(message_rate, 2)
    }


# ============================================================================
# Transmit List Endpoints
# ============================================================================

@app.post("/transmit_list/save")
async def save_transmit_list(request: SaveTransmitListRequest):
    """Save transmit list for a specific DBC file"""
    try:
        # Sanitize DBC filename for use as JSON filename
        dbc_filename = Path(request.dbc_file).stem
        json_filename = f"{dbc_filename}_transmit_list.json"
        json_path = TRANSMIT_LISTS_DIR / json_filename
        
        # Convert items to dict for JSON serialization
        items_data = [item.dict() for item in request.items]
        
        # Save to JSON file
        with open(json_path, 'w') as f:
            json.dump({
                "dbc_file": request.dbc_file,
                "items": items_data
            }, f, indent=2)
        
        return {
            "success": True,
            "message": f"Transmit list saved for {request.dbc_file}",
            "file_path": str(json_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save transmit list: {str(e)}")


@app.get("/transmit_list/load", response_model=TransmitListResponse)
async def load_transmit_list(dbc_file: str):
    """Load transmit list for a specific DBC file"""
    try:
        # Sanitize DBC filename for use as JSON filename
        dbc_filename = Path(dbc_file).stem
        json_filename = f"{dbc_filename}_transmit_list.json"
        json_path = TRANSMIT_LISTS_DIR / json_filename
        
        if not json_path.exists():
            return TransmitListResponse(
                success=True,
                items=[],
                dbc_file=dbc_file
            )
        
        # Load from JSON file
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        items = [TransmitListItem(**item) for item in data.get("items", [])]
        
        return TransmitListResponse(
            success=True,
            items=items,
            dbc_file=data.get("dbc_file", dbc_file)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load transmit list: {str(e)}")


@app.post("/dbc/encode_message")
async def encode_message(message_name: str, signals: str):
    """Encode a DBC message with signal values into raw bytes"""
    if not DBC_SUPPORT:
        raise HTTPException(status_code=501, detail="DBC support not available (cantools not installed)")
    
    if not backend.dbc_database:
        raise HTTPException(status_code=400, detail="No DBC file loaded")
    
    try:
        # Parse signals from JSON string
        import json
        signals_dict = json.loads(signals)
        
        # Find the message in the DBC database
        message = backend.dbc_database.get_message_by_name(message_name)
        
        # Encode the message with the provided signal values
        data = message.encode(signals_dict)
        
        # Check if it's an extended ID and extract the actual ID
        is_extended = message.frame_id > 0x7FF
        actual_id = message.frame_id & 0x1FFFFFFF if is_extended else message.frame_id
        
        return {
            "success": True,
            "message_name": message_name,
            "can_id": actual_id,
            "is_extended": is_extended,
            "data": list(data),
            "length": len(data)
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Message '{message_name}' not found in DBC file")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid signals JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to encode message: {str(e)}")


@app.post("/flash_firmware", response_model=FirmwareFlashResponse)
async def flash_firmware(file: UploadFile = File(...), module_number: int = Form(0)):
    """Flash firmware to a BMS module"""
    print(f"[FLASH] Starting firmware flash for module {module_number}, file: {file.filename}")
    
    if not FIRMWARE_FLASHER_AVAILABLE:
        raise HTTPException(status_code=501, detail="Firmware flasher not available")
    
    if not backend.is_connected:
        raise HTTPException(status_code=400, detail="CAN bus not connected")
    
    if not backend.driver:
        raise HTTPException(status_code=500, detail="No CAN driver available")
    
    # Validate module number (0-5 for TREV BMS)
    if not 0 <= module_number <= 5:
        raise HTTPException(status_code=400, detail="Module number must be between 0 and 5")
    
    # Validate file is .bin
    if not file.filename.endswith('.bin'):
        raise HTTPException(status_code=400, detail="File must be a .bin firmware file")
    
    try:
        # Save uploaded file temporarily
        temp_dir = Path(__file__).parent / "temp"
        temp_dir.mkdir(exist_ok=True)
        temp_file_path = temp_dir / file.filename
        
        print(f"[FLASH] Saving file to {temp_file_path}")
        with open(temp_file_path, 'wb') as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = temp_file_path.stat().st_size
        print(f"[FLASH] File saved, size: {file_size} bytes")
        
        # Create firmware flasher with progress callback
        def progress_callback(progress):
            # TODO: Send progress updates via WebSocket
            print(f"[FLASH] Progress: {progress.stage} - {progress.progress}% - {progress.message}")
        
        print(f"[FLASH] Creating FirmwareFlasher instance")
        flasher = FirmwareFlasher(backend.driver, progress_callback)
        
        print(f"[FLASH] Starting flash_firmware() call")
        # Flash the firmware (with verify and jump to application)
        # Pass Path object, not string
        success = flasher.flash_firmware(
            firmware_path=temp_file_path,  # Pass Path object directly
            module_number=module_number,
            verify=True,
            jump=True
        )
        
        if not success:
            print(f"[FLASH] Flash failed - flasher returned False")
            raise Exception("Firmware flash operation failed")
        
        print(f"[FLASH] Flash completed successfully")
        # Clean up temp file
        temp_file_path.unlink(missing_ok=True)
        
        return FirmwareFlashResponse(
            success=True,
            message=f"Firmware successfully flashed to module {module_number}"
        )
        
    except FileNotFoundError as e:
        # Clean up temp file on error
        if 'temp_file_path' in locals():
            temp_file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail=f"Firmware file not found: {str(e)}")
    except Exception as e:
        # Clean up temp file on error
        if 'temp_file_path' in locals():
            temp_file_path.unlink(missing_ok=True)
        
        # Log the full error for debugging
        import traceback
        print(f"Firmware flash error: {str(e)}")
        print(traceback.format_exc())
        
        raise HTTPException(status_code=500, detail=f"Firmware flash failed: {str(e)}")


# ============================================================================
# WebSocket Endpoint for Real-time CAN Messages
# ============================================================================

@app.websocket("/ws/can")
async def websocket_can_messages(websocket: WebSocket):
    """WebSocket endpoint for real-time CAN message streaming"""
    await backend.add_websocket_connection(websocket)
    
    try:
        while True:
            # Keep connection alive and handle any client messages
            data = await websocket.receive_text()
            # Echo back for heartbeat
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        backend.remove_websocket_connection(websocket)
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        backend.remove_websocket_connection(websocket)


# ============================================================================
# Application Lifecycle
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    print("=" * 60)
    print("CAN Communication Backend Starting")
    print("=" * 60)
    print(f"PCAN Available: {PCAN_AVAILABLE}")
    print(f"CANable Available: {CANABLE_AVAILABLE}")
    print(f"DBC Support: {DBC_SUPPORT}")
    print("=" * 60)
    
    # Auto-load last DBC file if it exists
    if DBC_SUPPORT and LAST_DBC_FILE.exists():
        try:
            with open(LAST_DBC_FILE, 'r') as f:
                last_filename = f.read().strip()
            
            dbc_path = DBC_DIR / last_filename
            if dbc_path.exists():
                if backend.load_dbc_file(str(dbc_path)):
                    msg_count = len(backend.dbc_database.messages) if backend.dbc_database else 0
                    print(f"✓ Auto-loaded DBC file: {last_filename} ({msg_count} messages)")
                else:
                    print(f"✗ Failed to auto-load DBC file: {last_filename}")
            else:
                print(f"ℹ Last DBC file not found: {last_filename}")
        except Exception as e:
            print(f"✗ Error auto-loading DBC file: {e}")
    
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    print("\nShutting down...")
    if backend.is_connected:
        backend.disconnect()
    print("Backend stopped")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the backend server"""
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()
