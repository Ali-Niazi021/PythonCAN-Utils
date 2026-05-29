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
from typing import Any, Optional, Dict, List, Union
from datetime import datetime
import asyncio
import json
import random
import time
import math
import hashlib
from enum import Enum
import atexit

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
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
DBC_CONFIG_FILE = DBC_DIR / "dbc_config.json"

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
    from drivers.CANable_Driver import CANableDriver, SocketCANDriver, CANableBaudRate, CANMessage as CANableMessage
    CANABLE_AVAILABLE = True
except ImportError:
    CANABLE_AVAILABLE = False
    print("Warning: CANable_Driver not available")

try:
    from drivers.NetworkCAN_Driver import NetworkCANDriver, NetworkCANBaudRate, CANMessage as NetworkCANMessage
    NETWORK_CAN_AVAILABLE = True
except ImportError:
    NETWORK_CAN_AVAILABLE = False
    print("Warning: NetworkCAN_Driver not available")

try:
    from drivers.Bluetooth_Driver import BluetoothCANDriver, BLUETOOTH_AVAILABLE, CANMessage as BluetoothCANMessage, get_paired_bluetooth_devices
    BLUETOOTH_CAN_AVAILABLE = BLUETOOTH_AVAILABLE
except ImportError:
    BLUETOOTH_CAN_AVAILABLE = False
    get_paired_bluetooth_devices = lambda: []
    print("Warning: Bluetooth_Driver not available")

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
    NETWORK = "network"
    BLUETOOTH = "bluetooth"


BUS_IDS = ("bus1", "bus2")


class ConnectionRequest(BaseModel):
    """Request to connect to a CAN device"""
    bus_id: Optional[str] = None
    device_type: DeviceType
    channel: Union[str, int]  # Channel name for PCAN or device index for CANable
    baudrate: str  # e.g., "BAUD_500K"


class ConnectionResponse(BaseModel):
    """Response from connection attempt"""
    success: bool
    message: str
    bus_id: Optional[str] = None
    connected_bus_count: int = 0
    device_type: Optional[str] = None
    channel: Optional[Union[str, int]] = None
    baudrate: Optional[str] = None


class DisconnectionRequest(BaseModel):
    """Request to disconnect one bus or all buses."""
    bus_id: Optional[str] = None


class DisconnectionResponse(BaseModel):
    """Response from disconnection attempt"""
    success: bool
    message: str
    bus_id: Optional[str] = None
    disconnected_bus_ids: List[str] = Field(default_factory=list)
    connected_bus_count: int = 0


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


class BusConnectionInfo(BaseModel):
    """Current per-bus connection state."""
    bus_id: str
    connected: bool
    device_type: Optional[str] = None
    channel: Optional[Union[str, int]] = None
    baudrate: Optional[str] = None
    status: Optional[str] = None
    interface: Optional[str] = None
    reason: Optional[str] = None
    message_count: int = 0
    uptime_seconds: float = 0
    message_rate: float = 0


class BusStatusResponse(BaseModel):
    """Current bus status information"""
    connected: bool
    connected_bus_count: int = 0
    primary_bus_id: Optional[str] = None
    device_type: Optional[str] = None
    channel: Optional[Union[str, int]] = None
    baudrate: Optional[str] = None
    status: Optional[str] = None
    interface: Optional[str] = None
    buses: List[BusConnectionInfo] = Field(default_factory=list)


class CANMessageRequest(BaseModel):
    """Request to send a CAN message"""
    bus_id: Optional[str] = None
    can_id: int
    data: List[int]  # List of bytes (0-255)
    is_extended: bool = False
    is_remote: bool = False


class CANMessageResponse(BaseModel):
    """Response after sending a CAN message"""
    success: bool
    message: str
    bus_id: Optional[str] = None


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


class DBCConfigItem(BaseModel):
    """Persisted DBC file entry."""
    filename: str
    enabled: bool = False


class DBCConfigUpdateRequest(BaseModel):
    """Atomic update for DBC ordering and enabled state."""
    files: List[DBCConfigItem]


class DBCFileInfo(BaseModel):
    """Frontend-facing DBC file metadata."""
    filename: str
    enabled: bool
    priority: int
    loaded: bool
    effective: bool
    message_count: int = 0
    size: int = 0
    modified: float = 0


class DBCConfigResponse(BaseModel):
    """Current multi-DBC state."""
    loaded: bool
    filename: Optional[str] = None
    message_count: int = 0
    active_signature: Optional[str] = None
    active_count: int = 0
    files: List[DBCFileInfo]


class TransmitListItem(BaseModel):
    """Single item in the transmit list"""
    id: str  # Unique ID for this item
    can_id: int
    data: List[int]  # List of bytes (0-255)
    is_extended: bool = False
    message_name: Optional[str] = None  # DBC message name if from DBC
    signals: Optional[Dict[str, Union[int, float, str]]] = None  # Signal values if from DBC
    description: Optional[str] = None
    cycle_time: Optional[int] = None  # Cycle time in ms for cyclic sending


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
    source_dbc: Optional[str] = None


class DBCMessagesResponse(BaseModel):
    """Response containing DBC message list"""
    success: bool
    messages: List[DBCMessageInfo]


class FirmwareFlashResponse(BaseModel):
    """Response from firmware flash operation"""
    success: bool
    message: str
    error: Optional[str] = None


class HVCTestModeToggleRequest(BaseModel):
    """Request payload for toggling HVC summary test mode."""
    enabled: bool


class HVCTestModeConfigRequest(BaseModel):
    """Request payload for all-module HVC summary override values."""
    min_voltage_v: float
    max_voltage_v: float
    min_temp_c: float
    max_temp_c: float
    error_flags_byte0: int = 0
    error_flags_byte1: int = 0
    error_flags_byte2: int = 0
    error_flags_byte3: int = 0
    warning_summary: int = 0
    fault_count: int = 0


# ============================================================================
# Backend Application State
# ============================================================================

class CANBackend:
    """Backend state management for CAN communication"""
    
    def __init__(self):
        self.bus_connections: Dict[str, Dict[str, Any]] = {
            bus_id: self._build_empty_bus_state(bus_id)
            for bus_id in BUS_IDS
        }
        self.driver: Optional[Union[PCANDriver, CANableDriver, SocketCANDriver, 'NetworkCANDriver']] = None
        self.device_type: Optional[DeviceType] = None
        self.is_connected: bool = False
        self.dbc_database: Optional['cantools.database.Database'] = None
        self.dbc_file_path: Optional[str] = None
        self.dbc_entries: List[Dict[str, Any]] = []
        
        # WebSocket connections
        self.active_connections: List[WebSocket] = []
        self.websocket_last_seen: Dict[WebSocket, float] = {}
        self.websocket_idle_timeout_seconds: float = 20.0
        
        # Message statistics
        self.message_count: int = 0
        self.start_time: Optional[datetime] = None
        
        # Event loop for async operations from threads
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.connection_state: str = 'disconnected'
        self.connection_reason: Optional[str] = None
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._simulation_task: Optional[asyncio.Task] = None
        self._simulation_current_task: Optional[asyncio.Task] = None
        self._simulation_active: bool = False
        self._simulation_started_monotonic: Optional[float] = None
        self._simulation_temp_enabled_dbc_files: set[str] = set()
        self._hvc_test_mode_task: Optional[asyncio.Task] = None
        self._hvc_test_mode_started_monotonic: Optional[float] = None
        self.hvc_test_mode_enabled: bool = False
        self.hvc_test_mode_interval_s: float = 0.5
        self.hvc_test_mode_config: Dict[str, float] = {
            'min_voltage_mv': 3200.0,
            'max_voltage_mv': 4100.0,
            'min_temp_c': 28.0,
            'max_temp_c': 55.0,
            'error_flags_byte0': 0,
            'error_flags_byte1': 0,
            'error_flags_byte2': 0,
            'error_flags_byte3': 0,
            'warning_summary': 0,
            'fault_count': 0,
        }
        self._shutdown_called: bool = False
        self._recovery_in_progress: bool = False
        self._user_requested_disconnect: bool = False

    def _build_empty_bus_state(self, bus_id: str) -> Dict[str, Any]:
        """Create one empty hardware bus slot."""
        return {
            'bus_id': bus_id,
            'connected': False,
            'driver': None,
            'device_type': None,
            'channel': None,
            'baudrate': None,
            'interface': None,
            'connection_state': 'disconnected',
            'connection_reason': None,
            'message_count': 0,
            'start_time': None,
            'recovery_in_progress': False,
            'user_requested_disconnect': False,
            'request_key': None,
        }

    def _normalize_bus_id(self, bus_id: str) -> str:
        """Validate and normalize a fixed bus slot identifier."""
        normalized = str(bus_id).strip().lower()
        if normalized not in BUS_IDS:
            raise ValueError(f"Invalid bus_id '{bus_id}'. Valid values: {', '.join(BUS_IDS)}")
        return normalized

    def _get_bus_slot(self, bus_id: str) -> Dict[str, Any]:
        """Return the mutable state for one bus slot."""
        return self.bus_connections[self._normalize_bus_id(bus_id)]

    def _get_connected_bus_ids(self) -> List[str]:
        """Return connected hardware bus ids in display order."""
        return [bus_id for bus_id in BUS_IDS if self.bus_connections[bus_id]['connected']]

    def _get_claimed_bus_ids(self) -> List[str]:
        """Return bus ids that currently own driver state."""
        return [bus_id for bus_id in BUS_IDS if self.bus_connections[bus_id]['driver'] is not None]

    def _get_recovering_bus_ids(self) -> List[str]:
        """Return bus ids currently trying to recover hardware."""
        return [
            bus_id for bus_id in BUS_IDS
            if self.bus_connections[bus_id]['recovery_in_progress']
        ]

    def get_connected_bus_count(self) -> int:
        """Return the number of active hardware buses."""
        return len(self._get_connected_bus_ids())

    def _get_primary_bus_id(self) -> Optional[str]:
        """Return the primary connected or recovering bus id."""
        connected_bus_ids = self._get_connected_bus_ids()
        if connected_bus_ids:
            return connected_bus_ids[0]

        recovering_bus_ids = self._get_recovering_bus_ids()
        if recovering_bus_ids:
            return recovering_bus_ids[0]

        claimed_bus_ids = self._get_claimed_bus_ids()
        return claimed_bus_ids[0] if claimed_bus_ids else None

    def _allocate_bus_id(self) -> Optional[str]:
        """Pick the first free bus slot."""
        for bus_id in BUS_IDS:
            slot = self.bus_connections[bus_id]
            if not slot['driver'] and not slot['connected'] and not slot['recovery_in_progress']:
                return bus_id
        return None

    def _resolve_connect_bus_id(self, bus_id: Optional[str]) -> str:
        """Resolve which bus slot should be used for a new connection."""
        if bus_id is None:
            allocated_bus_id = self._allocate_bus_id()
            if allocated_bus_id is None:
                raise ValueError("Both CAN bus slots are already in use")
            return allocated_bus_id

        normalized_bus_id = self._normalize_bus_id(bus_id)
        slot = self.bus_connections[normalized_bus_id]
        if slot['driver'] or slot['connected'] or slot['recovery_in_progress']:
            raise ValueError(f"{normalized_bus_id} is already connected")
        return normalized_bus_id

    def _resolve_active_bus_id(self, bus_id: Optional[str], *, allow_recovering: bool = False) -> str:
        """Resolve a target bus for send/disconnect operations."""
        if bus_id is not None:
            normalized_bus_id = self._normalize_bus_id(bus_id)
            slot = self.bus_connections[normalized_bus_id]
            if allow_recovering:
                if slot['driver'] is None and not slot['recovery_in_progress']:
                    raise ValueError(f"{normalized_bus_id} is not active")
            elif not slot['connected'] or slot['driver'] is None:
                raise ValueError(f"{normalized_bus_id} is not connected")
            return normalized_bus_id

        connected_bus_ids = self._get_connected_bus_ids()
        if len(connected_bus_ids) == 1:
            return connected_bus_ids[0]
        if len(connected_bus_ids) > 1:
            raise ValueError("Multiple CAN buses are connected. Specify bus_id.")

        if allow_recovering:
            claimed_bus_ids = self._get_claimed_bus_ids()
            if len(claimed_bus_ids) == 1:
                return claimed_bus_ids[0]
            if len(claimed_bus_ids) > 1:
                raise ValueError("Multiple CAN buses are active. Specify bus_id.")

        raise ValueError("Not connected to any CAN device")

    def resolve_target_bus_id(self, bus_id: Optional[str]) -> str:
        """Public helper for routes that need a unique connected bus."""
        return self._resolve_active_bus_id(bus_id)

    def _build_connection_request_key(self, device_type: DeviceType, channel: Union[str, int]) -> str:
        """Build a stable key for duplicate connection detection."""
        normalized_channel = str(channel).strip().lower()
        return f"{device_type.value}:{normalized_channel}"

    def _assert_bus_request_available(self, bus_id: str, device_type: DeviceType, channel: Union[str, int]):
        """Reject attempts to connect two slots to the same requested target."""
        requested_key = self._build_connection_request_key(device_type, channel)
        for other_bus_id in BUS_IDS:
            if other_bus_id == bus_id:
                continue

            other_slot = self.bus_connections[other_bus_id]
            if other_slot['driver'] is None:
                continue

            if other_slot.get('request_key') == requested_key:
                raise ValueError(
                    f"{other_bus_id} already uses that CAN device or SocketCAN interface"
                )

    def _read_driver_status(self, bus_id: str) -> Dict[str, Any]:
        """Return one driver's status and refresh cached slot metadata."""
        slot = self._get_bus_slot(bus_id)
        driver = slot['driver']
        if driver is None:
            return {}

        try:
            status = driver.get_bus_status()
        except Exception as e:
            print(f"[Status] Failed to read bus status for {bus_id}: {e}")
            return {}

        channel = status.get('channel')
        if channel not in (None, ''):
            slot['channel'] = channel

        interface = status.get('interface')
        if interface not in (None, ''):
            slot['interface'] = interface

        baudrate = status.get('baudrate')
        if baudrate not in (None, ''):
            slot['baudrate'] = baudrate

        return status

    def _assert_unique_resolved_target(self, bus_id: str):
        """Reject duplicate resolved device/interface assignments across slots."""
        slot = self._get_bus_slot(bus_id)
        for other_bus_id in BUS_IDS:
            if other_bus_id == bus_id:
                continue

            other_slot = self.bus_connections[other_bus_id]
            if other_slot['driver'] is None:
                continue

            same_request = bool(slot.get('request_key')) and slot.get('request_key') == other_slot.get('request_key')
            same_resolved = (
                slot.get('device_type') == other_slot.get('device_type')
                and slot.get('interface') not in (None, '')
                and slot.get('interface') == other_slot.get('interface')
                and str(slot.get('channel')) == str(other_slot.get('channel'))
            )
            if same_request or same_resolved:
                raise ValueError(
                    f"{bus_id} conflicts with {other_bus_id}; choose a different CAN device or SocketCAN interface"
                )

    def _reset_bus_slot(self, bus_id: str, reason: Optional[str] = None):
        """Reset a bus slot to its disconnected state."""
        normalized_bus_id = self._normalize_bus_id(bus_id)
        self.bus_connections[normalized_bus_id] = self._build_empty_bus_state(normalized_bus_id)
        self.bus_connections[normalized_bus_id]['connection_reason'] = reason
        self._sync_legacy_connection_state()

    def _sync_legacy_connection_state(self):
        """Keep legacy aggregate fields aligned with the multi-bus model."""
        if self._simulation_active:
            return

        connected_bus_ids = self._get_connected_bus_ids()
        claimed_bus_ids = self._get_claimed_bus_ids()
        recovering_bus_ids = self._get_recovering_bus_ids()
        primary_bus_id = self._get_primary_bus_id()

        self.is_connected = bool(connected_bus_ids)
        self._recovery_in_progress = bool(recovering_bus_ids)
        self._user_requested_disconnect = bool(claimed_bus_ids) and all(
            self.bus_connections[bus_id]['user_requested_disconnect']
            for bus_id in claimed_bus_ids
        ) if claimed_bus_ids else False
        self.message_count = sum(
            int(self.bus_connections[bus_id]['message_count'])
            for bus_id in BUS_IDS
        )

        if primary_bus_id is None:
            self.driver = None
            self.device_type = None
            self.start_time = None
            self.connection_state = 'disconnected'
            self.connection_reason = None
            return

        primary_slot = self.bus_connections[primary_bus_id]
        self.driver = primary_slot['driver']
        self.device_type = primary_slot['device_type']
        self.start_time = primary_slot['start_time']
        self.connection_state = (
            'connected' if connected_bus_ids
            else 'reconnecting' if recovering_bus_ids
            else primary_slot['connection_state']
        )
        self.connection_reason = primary_slot['connection_reason']

    def _build_bus_status_entry(self, bus_id: str) -> Dict[str, Any]:
        """Build one frontend-facing bus status payload."""
        slot = self._get_bus_slot(bus_id)
        driver_status = self._read_driver_status(bus_id) if slot['driver'] else {}
        uptime = 0.0
        if slot['start_time']:
            uptime = max(0.0, (datetime.now() - slot['start_time']).total_seconds())
        message_rate = (slot['message_count'] / uptime) if uptime > 0 else 0.0

        channel = driver_status.get('channel', slot['channel'])
        interface = driver_status.get('interface', slot['interface'])
        baudrate = driver_status.get('baudrate', slot['baudrate'])

        return {
            'bus_id': bus_id,
            'connected': bool(slot['connected']),
            'device_type': slot['device_type'].value if slot['device_type'] else None,
            'channel': channel,
            'baudrate': baudrate,
            'status': slot['connection_state'].title(),
            'interface': interface,
            'reason': slot['connection_reason'],
            'message_count': int(slot['message_count']),
            'uptime_seconds': uptime,
            'message_rate': round(message_rate, 2),
        }

    def _build_connection_status_payload(
        self,
        event_status: Optional[str] = None,
        reason: Optional[str] = None,
        bus_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build a websocket connection-status payload with aggregate and per-bus state."""
        snapshot = self.get_bus_status()
        payload = {
            "type": "connection_status",
            "status": (snapshot.get('status') or 'Disconnected').lower(),
            "timestamp": datetime.now().isoformat(),
            "connected": snapshot.get('connected', False),
            "connected_bus_count": snapshot.get('connected_bus_count', 0),
            "primary_bus_id": snapshot.get('primary_bus_id'),
            "buses": snapshot.get('buses', []),
        }

        if reason is not None:
            payload['reason'] = reason
        elif self.connection_reason is not None:
            payload['reason'] = self.connection_reason

        if event_status is not None:
            payload['event_status'] = event_status

        if bus_id is not None:
            normalized_bus_id = self._normalize_bus_id(bus_id)
            payload['bus_id'] = normalized_bus_id
            bus_snapshot = next(
                (bus for bus in snapshot.get('buses', []) if bus.get('bus_id') == normalized_bus_id),
                None
            )
            if bus_snapshot is not None:
                payload['bus_status'] = (bus_snapshot.get('status') or 'Disconnected').lower()

        return payload

    def _increment_message_count(self, bus_id: Optional[str] = None) -> int:
        """Increment aggregate or per-bus message counters."""
        if bus_id is not None and bus_id in self.bus_connections:
            slot = self.bus_connections[bus_id]
            slot['message_count'] += 1
            self.message_count += 1
            if not self._simulation_active:
                self._sync_legacy_connection_state()
            return int(slot['message_count'])

        self.message_count += 1
        return self.message_count

    def _normalize_dbc_filename(self, filename: str) -> str:
        """Return a safe filename without path segments."""
        normalized = Path(filename).name
        if not normalized or normalized != filename or normalized.startswith('.'):
            raise ValueError("Invalid DBC filename")
        return normalized

    def _load_dbc_database_from_file(self, file_path: Path) -> Optional['cantools.database.Database']:
        """Parse one DBC file if support is available."""
        if not DBC_SUPPORT:
            return None

        return cantools.database.load_file(str(file_path), strict=False)

    def _message_identity(self, message: Any) -> tuple[int, bool]:
        """Return comparable frame identity for a cantools message."""
        is_extended = bool(getattr(message, 'is_extended_frame', message.frame_id > 0x7FF))
        actual_id = message.frame_id & 0x1FFFFFFF if is_extended else message.frame_id
        return actual_id, is_extended

    def _find_message_by_frame_id(
        self,
        database: 'cantools.database.Database',
        can_id: int,
        is_extended: bool
    ) -> Optional[Any]:
        """Find a matching message while respecting standard vs extended IDs."""
        lookup_id = can_id & 0x1FFFFFFF if is_extended else can_id
        for message in database.messages:
            message_id, message_is_extended = self._message_identity(message)
            if message_id == lookup_id and message_is_extended == is_extended:
                return message
        return None

    def _find_effective_message_by_name(self, message_name: str) -> Optional[tuple[Dict[str, Any], Any]]:
        """Return the first enabled message definition with this name."""
        for entry in self.dbc_entries:
            if not entry.get('enabled') or not entry.get('database'):
                continue

            try:
                return entry, entry['database'].get_message_by_name(message_name)
            except KeyError:
                continue
        return None

    def _refresh_effective_dbc(self):
        """Maintain legacy single-DBC fields as the effective active DBC."""
        effective_entry = next(
            (entry for entry in self.dbc_entries if entry.get('enabled') and entry.get('database')),
            None
        )
        self.dbc_database = effective_entry['database'] if effective_entry else None
        self.dbc_file_path = str(effective_entry['path']) if effective_entry else None

    def _save_dbc_config(self):
        """Persist DBC ordering and enabled state."""
        payload = {
            "files": [
                {
                    "filename": entry['filename'],
                    "enabled": bool(entry.get('enabled', False))
                }
                for entry in self.dbc_entries
            ]
        }
        with open(DBC_CONFIG_FILE, 'w', encoding='utf-8') as config_file:
            json.dump(payload, config_file, indent=2)

    def _build_dbc_entry(self, filename: str, enabled: bool) -> Dict[str, Any]:
        """Create one in-memory DBC entry from disk state."""
        normalized = self._normalize_dbc_filename(filename)
        file_path = DBC_DIR / normalized
        database = None

        if file_path.exists() and DBC_SUPPORT:
            try:
                database = self._load_dbc_database_from_file(file_path)
            except Exception as e:
                print(f"[DBC] Failed to load {normalized}: {e}")

        return {
            'filename': normalized,
            'enabled': bool(enabled),
            'path': file_path,
            'database': database
        }

    def load_dbc_config(self):
        """Load persisted DBC configuration and available files from disk."""
        raw_entries: List[Dict[str, Any]] = []
        migrated_from_legacy = False

        if DBC_CONFIG_FILE.exists():
            try:
                with open(DBC_CONFIG_FILE, 'r', encoding='utf-8') as config_file:
                    payload = json.load(config_file)
                raw_entries = payload.get('files', []) if isinstance(payload, dict) else []
            except Exception as e:
                print(f"[DBC] Failed to read DBC config: {e}")

        if not raw_entries and LAST_DBC_FILE.exists():
            try:
                with open(LAST_DBC_FILE, 'r', encoding='utf-8') as legacy_file:
                    legacy_filename = legacy_file.read().strip()
                if legacy_filename:
                    raw_entries = [{'filename': legacy_filename, 'enabled': True}]
                    migrated_from_legacy = True
            except Exception as e:
                print(f"[DBC] Failed to migrate legacy DBC state: {e}")

        normalized_entries: List[Dict[str, Any]] = []
        seen_filenames = set()

        for item in raw_entries:
            if not isinstance(item, dict):
                continue

            filename = item.get('filename')
            if not isinstance(filename, str):
                continue

            try:
                normalized = self._normalize_dbc_filename(filename)
            except ValueError:
                continue

            if normalized in seen_filenames:
                continue

            seen_filenames.add(normalized)
            normalized_entries.append({
                'filename': normalized,
                'enabled': bool(item.get('enabled', False))
            })

        for file_path in sorted(DBC_DIR.glob('*.dbc')):
            if file_path.name in seen_filenames:
                continue
            normalized_entries.append({'filename': file_path.name, 'enabled': False})
            seen_filenames.add(file_path.name)

        self.dbc_entries = [
            self._build_dbc_entry(entry['filename'], entry['enabled'])
            for entry in normalized_entries
            if (DBC_DIR / entry['filename']).exists()
        ]
        self._refresh_effective_dbc()

        if migrated_from_legacy or not DBC_CONFIG_FILE.exists():
            try:
                self._save_dbc_config()
            except Exception as e:
                print(f"[DBC] Failed to persist DBC config: {e}")

    def _upload_effective_dbc_to_remote(self, bus_id: Optional[str] = None):
        """Upload the effective DBC to remote decoders when required."""
        if not self.dbc_file_path:
            return

        target_bus_ids = [self._normalize_bus_id(bus_id)] if bus_id else BUS_IDS
        for target_bus_id in target_bus_ids:
            slot = self.bus_connections[target_bus_id]
            driver = slot['driver']
            if slot['device_type'] not in (DeviceType.NETWORK, DeviceType.BLUETOOTH) or not driver:
                continue

            if not hasattr(driver, 'upload_dbc'):
                continue

            try:
                if driver.upload_dbc(self.dbc_file_path):
                    print(f"[DBC] Uploaded effective DBC to remote server for {target_bus_id}: {self.dbc_file_path}")
                else:
                    print(f"[DBC] Warning: Failed to upload effective DBC to remote server for {target_bus_id}")
            except Exception as e:
                print(f"[DBC] Warning: Remote upload failed for {target_bus_id}: {e}")

    def get_active_dbc_signature(self) -> Optional[str]:
        """Return a stable identifier for the enabled DBC set and order."""
        active_files = [entry['filename'] for entry in self.dbc_entries if entry.get('enabled')]
        if not active_files:
            return None

        joined = '|'.join(active_files)
        digest = hashlib.sha1(joined.encode('utf-8')).hexdigest()[:12]
        return f"dbcset-{digest}"

    def get_dbc_status(self) -> Dict[str, Any]:
        """Return the current multi-DBC state payload."""
        effective_filename = Path(self.dbc_file_path).name if self.dbc_file_path else None
        files = []

        for index, entry in enumerate(self.dbc_entries):
            file_path = entry['path']
            files.append({
                'filename': entry['filename'],
                'enabled': bool(entry.get('enabled', False)),
                'priority': index,
                'loaded': entry.get('database') is not None,
                'effective': bool(entry.get('enabled')) and entry['filename'] == effective_filename,
                'message_count': len(entry['database'].messages) if entry.get('database') else 0,
                'size': file_path.stat().st_size if file_path.exists() else 0,
                'modified': file_path.stat().st_mtime if file_path.exists() else 0
            })

        return {
            'loaded': self.dbc_database is not None,
            'filename': effective_filename,
            'message_count': len(self.dbc_database.messages) if self.dbc_database else 0,
            'active_signature': self.get_active_dbc_signature(),
            'active_count': sum(1 for entry in self.dbc_entries if entry.get('enabled')),
            'files': files
        }

    def register_dbc_file(self, filename: str, enabled: bool = False) -> Dict[str, Any]:
        """Add or refresh one DBC file in the ordered config."""
        normalized = self._normalize_dbc_filename(filename)
        file_path = DBC_DIR / normalized
        if not file_path.exists():
            raise FileNotFoundError(f"DBC file not found: {normalized}")

        new_entry = self._build_dbc_entry(normalized, enabled)
        for existing in self.dbc_entries:
            if existing['filename'] == normalized:
                existing['path'] = new_entry['path']
                existing['database'] = new_entry['database']
                self._refresh_effective_dbc()
                self._save_dbc_config()
                self._upload_effective_dbc_to_remote()
                return existing

        self.dbc_entries.append(new_entry)
        self._refresh_effective_dbc()
        self._save_dbc_config()
        self._upload_effective_dbc_to_remote()
        return new_entry

    def update_dbc_config(self, items: List[DBCConfigItem]) -> Dict[str, Any]:
        """Replace DBC ordering and enabled flags atomically."""
        incoming_filenames = [self._normalize_dbc_filename(item.filename) for item in items]
        current_filenames = [entry['filename'] for entry in self.dbc_entries]

        if len(set(incoming_filenames)) != len(incoming_filenames):
            raise ValueError("DBC config contains duplicate filenames")

        if set(incoming_filenames) != set(current_filenames):
            raise ValueError("DBC config update must include every known DBC file exactly once")

        item_map = {
            self._normalize_dbc_filename(item.filename): item
            for item in items
        }
        entry_map = {entry['filename']: entry for entry in self.dbc_entries}

        self.dbc_entries = []
        for filename in incoming_filenames:
            entry = entry_map[filename]
            entry['enabled'] = bool(item_map[filename].enabled)
            self.dbc_entries.append(entry)

        self._refresh_effective_dbc()
        self._save_dbc_config()
        self._upload_effective_dbc_to_remote()
        return self.get_dbc_status()

    def delete_dbc_entry(self, filename: str) -> Dict[str, Any]:
        """Remove a DBC from memory and config after the file is deleted."""
        normalized = self._normalize_dbc_filename(filename)
        self.dbc_entries = [entry for entry in self.dbc_entries if entry['filename'] != normalized]
        self._refresh_effective_dbc()
        self._save_dbc_config()
        self._upload_effective_dbc_to_remote()
        return self.get_dbc_status()

    def load_dbc_file(self, file_path: str) -> bool:
        """Legacy helper that enables a DBC and promotes it to top priority."""
        path = Path(file_path)
        if not path.exists():
            return False

        try:
            if path.parent.resolve() != DBC_DIR.resolve():
                target_path = DBC_DIR / path.name
                shutil.copy2(path, target_path)
                path = target_path

            self.register_dbc_file(path.name, enabled=True)

            promoted_entry = None
            remaining_entries = []
            for entry in self.dbc_entries:
                if entry['filename'] == path.name:
                    entry['enabled'] = True
                    promoted_entry = entry
                else:
                    remaining_entries.append(entry)

            if promoted_entry is None:
                return False

            self.dbc_entries = [promoted_entry, *remaining_entries]
            self._refresh_effective_dbc()
            self._save_dbc_config()
            self._upload_effective_dbc_to_remote()
            return True
        except Exception as e:
            print(f"DBC load error: {e}")
            return False

    def _is_driver_healthy(self, bus_id: str) -> bool:
        """Check current driver health for one bus slot."""
        slot = self._get_bus_slot(bus_id)
        driver = slot['driver']
        if not slot['connected'] or not driver:
            return False

        try:
            if hasattr(driver, 'health_check'):
                return bool(driver.health_check())

            status = driver.get_bus_status()
            return bool(status.get('connected', False))
        except Exception as e:
            print(f"[Health] Driver health check failed for {bus_id}: {e}")
            return False

    async def _run_health_monitor(self):
        """Background monitor that auto-recovers connections after sleep/wake or hardware loss."""
        print("[Health] Monitor started")
        try:
            while not self._shutdown_called:
                await asyncio.sleep(5.0)

                if self._shutdown_called:
                    break

                for bus_id in BUS_IDS:
                    slot = self.bus_connections[bus_id]
                    if slot['user_requested_disconnect']:
                        continue
                    if not slot['connected'] or not slot['driver'] or slot['recovery_in_progress']:
                        continue

                    healthy = await asyncio.to_thread(self._is_driver_healthy, bus_id)
                    if not healthy:
                        await self._handle_connection_loss(bus_id, "driver_health_check_failed")
        except asyncio.CancelledError:
            pass
        finally:
            print("[Health] Monitor stopped")

    def start_health_monitor(self):
        """Ensure health monitor task is running."""
        if self.loop and (self._health_monitor_task is None or self._health_monitor_task.done()):
            self._health_monitor_task = asyncio.create_task(self._run_health_monitor())

    async def stop_health_monitor(self):
        """Stop health monitor task."""
        if self._health_monitor_task and not self._health_monitor_task.done():
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        self._health_monitor_task = None

    async def broadcast_connection_status(
        self,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        bus_id: Optional[str] = None
    ):
        """Broadcast connection status updates to all websocket clients."""
        await self.broadcast_message(
            self._build_connection_status_payload(status, reason, bus_id)
        )

    async def _handle_connection_loss(self, bus_id: str, reason: str):
        """Retry reconnection indefinitely until hardware returns or user disconnects."""
        slot = self._get_bus_slot(bus_id)
        if slot['recovery_in_progress'] or not slot['driver']:
            return

        slot['connected'] = False
        slot['recovery_in_progress'] = True
        slot['connection_state'] = 'reconnecting'
        slot['connection_reason'] = reason
        self._sync_legacy_connection_state()
        await self.broadcast_connection_status('reconnecting', reason, bus_id)

        attempt = 0
        max_backoff = 30  # cap at 30 seconds between retries
        try:
            while not self._shutdown_called and not slot['user_requested_disconnect']:
                attempt += 1
                print(f"[Recovery] Attempt {attempt} for {bus_id}")
                success = await asyncio.to_thread(self._attempt_driver_reconnect, bus_id)
                if success:
                    slot['connected'] = True
                    slot['connection_state'] = 'connected'
                    slot['connection_reason'] = 'recovered'
                    self._sync_legacy_connection_state()
                    await self.broadcast_connection_status('connected', 'recovered', bus_id)
                    print(f"[Recovery] Connection restored for {bus_id}")
                    return

                backoff = min(2 ** min(attempt - 1, 5), max_backoff)
                print(f"[Recovery] Next retry for {bus_id} in {backoff}s")
                await asyncio.sleep(backoff)

            # User pressed disconnect while we were retrying
            if slot['user_requested_disconnect']:
                print(f"[Recovery] Stopped for {bus_id} — user requested disconnect")
        finally:
            slot['recovery_in_progress'] = False
            self._sync_legacy_connection_state()

    def _attempt_driver_reconnect(self, bus_id: str) -> bool:
        """Reconnect using driver-provided reconnect hook."""
        slot = self._get_bus_slot(bus_id)
        driver = slot['driver']
        if not driver or not hasattr(driver, 'reconnect'):
            return False

        try:
            success = bool(driver.reconnect())
            if not success:
                return False

            if hasattr(driver, 'start_receive_thread'):
                try:
                    driver.start_receive_thread(self._make_message_callback(bus_id))
                except Exception as e:
                    print(f"[Recovery] Warning starting receive thread for {bus_id}: {e}")

            slot['connected'] = True
            slot['connection_state'] = 'connected'
            slot['connection_reason'] = None
            slot['start_time'] = datetime.now()
            self._read_driver_status(bus_id)
            self._sync_legacy_connection_state()
            return True
        except Exception as e:
            print(f"[Recovery] Reconnect error for {bus_id}: {e}")
            return False

    async def shutdown(self):
        """Idempotent backend shutdown cleanup."""
        if self._shutdown_called:
            return

        self._shutdown_called = True
        await self.stop_hvc_test_mode()
        await self.stop_simulation()
        await self.stop_health_monitor()

        if self.is_connected or self._get_claimed_bus_ids():
            await asyncio.to_thread(self.disconnect)

        for ws in list(self.active_connections):
            try:
                await ws.close()
            except Exception:
                pass
        self.active_connections.clear()
    
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
                        name=dev.get('channel', f"Device {dev['index']}"),
                        description=dev.get('description', f"CANable Device {dev['index']}"),
                        available=True
                    ))
            except Exception as e:
                print(f"Error scanning CANable devices: {e}")
        
        # Network CAN devices (always show as option if driver available)
        if NETWORK_CAN_AVAILABLE:
            devices.append(DeviceInfo(
                device_type="network",
                index=0,
                name="Network CAN Server",
                description="Connect to remote CAN server via IP:Port",
                available=True
            ))
        
        # Bluetooth CAN devices (Windows only - scan for paired Bluetooth devices)
        if BLUETOOTH_CAN_AVAILABLE:
            try:
                paired_devices = get_paired_bluetooth_devices()
                for idx, device in enumerate(paired_devices):
                    devices.append(DeviceInfo(
                        device_type="bluetooth",
                        index=idx,
                        name=device['address'],
                        description=f"{device['name']} ({device['address']})",
                        available=True
                    ))
                # Always add a manual entry option
                devices.append(DeviceInfo(
                    device_type="bluetooth",
                    index=len(paired_devices),
                    name="Bluetooth CAN Server",
                    description="Connect via Bluetooth address (XX:XX:XX:XX:XX:XX)",
                    available=True
                ))
            except Exception as e:
                print(f"Error scanning Bluetooth devices: {e}")
        
        return devices
    
    def connect(
        self,
        device_type: DeviceType,
        channel: Union[str, int],
        baudrate: str,
        bus_id: Optional[str] = None
    ) -> Optional[str]:
        """Connect to a CAN device"""
        if self._simulation_active:
            print("[Connect] Refusing real hardware connect while simulation is active")
            self.connection_reason = "Simulation is active"
            return None

        target_bus_id = None
        driver = None
        
        try:
            target_bus_id = self._resolve_connect_bus_id(bus_id)
            self._assert_bus_request_available(target_bus_id, device_type, channel)
            requested_key = self._build_connection_request_key(device_type, channel)

            # Create appropriate driver
            if device_type == DeviceType.PCAN:
                if not PCAN_AVAILABLE:
                    raise Exception("PCAN driver not available")
                
                driver = PCANDriver()

                # Accept several PCAN channel formats from clients/UI.
                if isinstance(channel, int):
                    # Allow index-like values where 0 maps to USB1.
                    pcan_channel_name = f"USB{channel + 1 if channel < 1 else channel}"
                else:
                    channel_str = str(channel).strip().upper()
                    if ':' in channel_str:
                        channel_str = channel_str.split(':', 1)[0].strip()
                    if ' ' in channel_str:
                        channel_str = channel_str.split(' ', 1)[0].strip()
                    if channel_str.startswith('PCAN_USBBUS'):
                        suffix = channel_str.replace('PCAN_USBBUS', '').strip()
                        channel_str = f"USB{suffix}"
                    if channel_str.startswith('USBBUS'):
                        suffix = channel_str.replace('USBBUS', '').strip()
                        channel_str = f"USB{suffix}"
                    if channel_str.isdigit():
                        idx = int(channel_str)
                        channel_str = f"USB{idx + 1 if idx < 1 else idx}"
                    pcan_channel_name = channel_str

                try:
                    pcan_channel = PCANChannel[pcan_channel_name]
                except KeyError:
                    valid_channels = ', '.join(ch.name for ch in PCANChannel)
                    raise Exception(f"Invalid PCAN channel '{channel}'. Valid channels: {valid_channels}")

                pcan_baudrate = PCANBaudRate[baudrate]
                
                if not driver.connect(pcan_channel, pcan_baudrate):
                    driver_error = getattr(driver, 'last_error', None)
                    if driver_error:
                        raise Exception(driver_error)
                    raise Exception(f"Failed to connect PCAN channel {pcan_channel.name}")
                
            elif device_type == DeviceType.CANABLE:
                if not CANABLE_AVAILABLE:
                    raise Exception("CANable driver not available")
                
                canable_baudrate = CANableBaudRate[baudrate]
                
                # Handle both formats: "Device X: Description" or just the index number
                if isinstance(channel, str):
                    # Extract device index from "Device X: Description" format if needed
                    if channel.startswith("Device "):
                        try:
                            channel_index = int(channel.split(":")[0].split()[1])
                        except:
                            channel_index = int(channel)
                    else:
                        channel_index = int(channel)
                else:
                    channel_index = int(channel)

                canable_devices = CANableDriver().get_available_devices()
                selected_device = next(
                    (device for device in canable_devices if int(device.get('index', -1)) == channel_index),
                    None,
                )

                if selected_device and selected_device.get('interface') == 'socketcan':
                    driver = SocketCANDriver(interface_name=selected_device.get('channel'))
                    connect_target: Union[int, str] = selected_device.get('channel') or channel_index
                else:
                    driver = CANableDriver()
                    connect_target = channel_index
                
                if not driver.connect(connect_target, canable_baudrate):
                    raise Exception(f"Failed to connect CANable channel {channel_index}")
            
            elif device_type == DeviceType.NETWORK:
                if not NETWORK_CAN_AVAILABLE:
                    raise Exception("Network CAN driver not available")
                
                # Parse channel as host:port (e.g., "192.168.1.100:8080")
                if isinstance(channel, str) and ':' in channel:
                    host, port_str = channel.rsplit(':', 1)
                    port = int(port_str)
                else:
                    raise Exception("Network channel must be in format 'host:port' (e.g., '192.168.1.100:8080')")
                
                # Map baudrate string to NetworkCANBaudRate enum
                network_baudrate = NetworkCANBaudRate[baudrate]
                
                driver = NetworkCANDriver(host=host, port=port)
                
                # Test connection first
                if not driver.test_connection():
                    raise Exception("Failed to reach network CAN server")
                
                # Connect with the specified baudrate and auto-connect to server
                if not driver.connect(baudrate=network_baudrate, auto_connect_server=True):
                    raise Exception("Failed to connect network CAN driver")
            
            elif device_type == DeviceType.BLUETOOTH:
                if not BLUETOOTH_CAN_AVAILABLE:
                    raise Exception("Bluetooth CAN driver not available (requires Windows 10/11 + Python 3.9+)")
                
                # Channel format: "XX:XX:XX:XX:XX:XX" or "XX:XX:XX:XX:XX:XX:1" (address:channel)
                # Default RFCOMM channel is 1
                bt_address = str(channel).strip()
                rfcomm_channel = 1
                
                # Check if channel is specified at the end (e.g., "XX:XX:XX:XX:XX:XX:1")
                if bt_address.count(':') == 6:
                    # Has 6 colons, meaning address:channel format
                    parts = bt_address.rsplit(':', 1)
                    bt_address = parts[0]
                    try:
                        rfcomm_channel = int(parts[1])
                    except ValueError:
                        rfcomm_channel = 1
                
                driver = BluetoothCANDriver()
                
                # Connect to the Bluetooth server
                if not driver.connect(address=bt_address, channel=rfcomm_channel):
                    raise Exception("Failed to connect Bluetooth CAN driver")
            
            else:
                raise Exception(f"Unknown device type: {device_type}")
            
            # Start receive thread
            driver.start_receive_thread(self._make_message_callback(target_bus_id))

            slot = self._get_bus_slot(target_bus_id)
            slot.update({
                'connected': True,
                'driver': driver,
                'device_type': device_type,
                'channel': channel,
                'baudrate': baudrate,
                'interface': None,
                'connection_state': 'connected',
                'connection_reason': None,
                'message_count': 0,
                'start_time': datetime.now(),
                'recovery_in_progress': False,
                'user_requested_disconnect': False,
                'request_key': requested_key,
            })
            self._read_driver_status(target_bus_id)
            self._assert_unique_resolved_target(target_bus_id)
            self._sync_legacy_connection_state()
            
            # For Network/Bluetooth drivers, upload the effective DBC if one is active.
            self._upload_effective_dbc_to_remote(target_bus_id)
            
            return target_bus_id
            
        except Exception as e:
            print(f"Connection error: {e}")
            self.connection_reason = str(e)
            if driver:
                try:
                    if hasattr(driver, 'stop_receive_thread'):
                        driver.stop_receive_thread()
                except Exception:
                    pass
                try:
                    driver.disconnect()
                except Exception:
                    pass
            if target_bus_id is not None:
                self._reset_bus_slot(target_bus_id, str(e))
            return None
    
    def _disconnect_bus(self, bus_id: str) -> bool:
        """Disconnect one bus slot."""
        slot = self._get_bus_slot(bus_id)
        driver = slot['driver']
        if driver is None and not slot['recovery_in_progress']:
            return False

        device_name = slot['device_type'].value if slot['device_type'] else "unknown"
        print(f"[Disconnect] Disconnecting {bus_id} from {device_name}...")

        try:
            # Stop receive thread first if available
            if driver and hasattr(driver, 'stop_receive_thread'):
                try:
                    driver.stop_receive_thread()
                    print(f"[Disconnect] Receive thread stopped for {bus_id}")
                except Exception as e:
                    print(f"[Disconnect] Warning stopping receive thread for {bus_id}: {e}")
            
            # Disconnect from device
            if driver:
                try:
                    driver.disconnect()
                    print(f"[Disconnect] Driver disconnected for {bus_id}")
                except Exception as e:
                    print(f"[Disconnect] Warning during driver disconnect for {bus_id}: {e}")

            self._reset_bus_slot(bus_id)
            print(f"[Disconnect] Cleanup complete for {bus_id}")
            return True
        except Exception as e:
            print(f"[Disconnect] Error on {bus_id}: {e}")
            # Force cleanup even on error
            self._reset_bus_slot(bus_id, str(e))
            return False

    def disconnect(self, bus_id: Optional[str] = None) -> List[str]:
        """Disconnect one bus or all active buses."""
        if bus_id is None:
            target_bus_ids = [
                current_bus_id for current_bus_id in BUS_IDS
                if self.bus_connections[current_bus_id]['driver'] is not None
                or self.bus_connections[current_bus_id]['recovery_in_progress']
            ]
        else:
            normalized_bus_id = self._normalize_bus_id(bus_id)
            slot = self.bus_connections[normalized_bus_id]
            if slot['driver'] is None and not slot['recovery_in_progress']:
                return []
            target_bus_ids = [normalized_bus_id]

        disconnected_bus_ids = []
        for target_bus_id in target_bus_ids:
            self.bus_connections[target_bus_id]['user_requested_disconnect'] = True
            if self._disconnect_bus(target_bus_id):
                disconnected_bus_ids.append(target_bus_id)

        self._sync_legacy_connection_state()
        return disconnected_bus_ids
    
    def send_message(
        self,
        can_id: int,
        data: List[int],
        is_extended: bool = False,
        is_remote: bool = False,
        bus_id: Optional[str] = None
    ) -> bool:
        """Send a CAN message"""
        try:
            target_bus_id = self._resolve_active_bus_id(bus_id)
        except ValueError as e:
            self.connection_reason = str(e)
            return False

        slot = self._get_bus_slot(target_bus_id)
        driver = slot['driver']
        if not slot['connected'] or not driver:
            self.connection_reason = f"{target_bus_id} is not connected"
            return False
        
        try:
            data_bytes = bytes(data)
            return driver.send_message(can_id, data_bytes, is_extended, is_remote)
        except Exception as e:
            print(f"Send error: {e}")
            self.connection_reason = str(e)
            return False

    def _build_simulation_bus_status_entry(self, bus_id: str) -> Dict[str, Any]:
        """Build one frontend-facing bus status payload for synthetic test-mode buses."""
        slot = self._get_bus_slot(bus_id)
        uptime = 0.0
        if slot['start_time']:
            uptime = max(0.0, (datetime.now() - slot['start_time']).total_seconds())

        message_count = int(slot['message_count'])
        message_rate = (message_count / uptime) if uptime > 0 else 0.0
        default_channel = 'bms-fake-data' if bus_id == 'bus1' else 'master-fake-data'

        return {
            'bus_id': bus_id,
            'connected': True,
            'device_type': 'simulation',
            'channel': slot['channel'] or default_channel,
            'baudrate': slot['baudrate'] or 'SIM',
            'status': 'Connected',
            'interface': slot['interface'] or 'simulation',
            'reason': slot['connection_reason'] or 'simulation',
            'message_count': message_count,
            'uptime_seconds': uptime,
            'message_rate': round(message_rate, 2),
        }

    def _configure_simulation_bus_slots(self):
        """Expose built-in test mode as two active frontend bus slots."""
        simulation_start = self.start_time or datetime.now()
        for bus_id, channel in (('bus1', 'bms-fake-data'), ('bus2', 'master-fake-data')):
            slot = self._build_empty_bus_state(bus_id)
            slot.update({
                'connected': True,
                'channel': channel,
                'baudrate': 'SIM',
                'interface': 'simulation',
                'connection_state': 'connected',
                'connection_reason': 'simulation',
                'start_time': simulation_start,
            })
            self.bus_connections[bus_id] = slot

    def _ensure_simulation_dbc_support(self) -> bool:
        """Ensure test mode can emit both BMS traffic and master.dbc bus2 traffic."""
        requirements = {
            'BMS-Firmware-RTOS-Complete.dbc': ('BMS_Heartbeat_0', 'Current_Sensor_Data'),
            'master.dbc': self.SIM_SECONDARY_BUS_MESSAGES,
        }

        for filename, required_messages in requirements.items():
            if all(self._find_effective_message_by_name(name) for name in required_messages):
                continue

            entry = next((item for item in self.dbc_entries if item['filename'] == filename), None)
            file_path = DBC_DIR / filename
            if entry is None:
                if not file_path.exists():
                    print(f"[SIM] Missing required DBC for simulation: {filename}")
                    return False
                entry = {
                    'filename': filename,
                    'enabled': False,
                    'path': file_path,
                    'database': None,
                }
                self.dbc_entries.append(entry)

            if entry.get('database') is None:
                try:
                    entry['database'] = self._load_dbc_database_from_file(entry['path'])
                except Exception as e:
                    print(f"[SIM] Failed to load {filename}: {e}")
                    return False

            if not entry.get('enabled'):
                entry['enabled'] = True
                self._simulation_temp_enabled_dbc_files.add(filename)
                self._refresh_effective_dbc()

            if not all(self._find_effective_message_by_name(name) for name in required_messages):
                print(f"[SIM] Required simulation messages unavailable after loading {filename}")
                return False

        return True

    def _restore_simulation_dbc_state(self):
        """Undo temporary DBC enables that were only needed for simulation."""
        if not self._simulation_temp_enabled_dbc_files:
            return

        for entry in self.dbc_entries:
            if entry['filename'] in self._simulation_temp_enabled_dbc_files:
                entry['enabled'] = False

        self._simulation_temp_enabled_dbc_files.clear()
        self._refresh_effective_dbc()
    
    def get_bus_status(self) -> dict:
        """Get current bus status"""
        if self._simulation_active:
            buses = [self._build_simulation_bus_status_entry(bus_id) for bus_id in BUS_IDS]
            connected_buses = [bus for bus in buses if bus['connected']]
            total_message_count = sum(int(bus['message_count']) for bus in connected_buses)
            return {
                'connected': True,
                'connected_bus_count': len(connected_buses),
                'primary_bus_id': connected_buses[0]['bus_id'] if connected_buses else None,
                'device_type': 'simulation',
                'channel': 'bms-fake-data',
                'baudrate': 'SIM',
                'status': 'Connected',
                'interface': 'simulation',
                'message_count': total_message_count,
                'buses': buses,
            }

        buses = [self._build_bus_status_entry(bus_id) for bus_id in BUS_IDS]
        connected_buses = [bus for bus in buses if bus['connected']]
        primary_bus = connected_buses[0] if connected_buses else next(
            (bus for bus in buses if bus['status'] != 'Disconnected'),
            None
        )

        overall_status = 'Connected' if connected_buses else (
            'Reconnecting' if any(bus['status'] == 'Reconnecting' for bus in buses) else 'Disconnected'
        )

        return {
            'connected': bool(connected_buses),
            'connected_bus_count': len(connected_buses),
            'primary_bus_id': primary_bus['bus_id'] if primary_bus else None,
            'device_type': primary_bus['device_type'] if primary_bus else None,
            'channel': primary_bus['channel'] if primary_bus else None,
            'baudrate': primary_bus['baudrate'] if primary_bus else None,
            'status': overall_status,
            'interface': primary_bus['interface'] if primary_bus else None,
            'buses': buses,
        }

    def get_message_stats(self) -> Dict[str, Any]:
        """Return aggregate and per-bus message statistics."""
        if self._simulation_active:
            buses = [self._build_simulation_bus_status_entry(bus_id) for bus_id in BUS_IDS]
            connected_buses = [bus for bus in buses if bus['connected']]
            uptime = max((bus['uptime_seconds'] for bus in connected_buses), default=0.0)
            message_count = sum(int(bus['message_count']) for bus in connected_buses)
            message_rate = sum(float(bus['message_rate']) for bus in connected_buses)
            return {
                'connected': True,
                'connected_bus_count': len(connected_buses),
                'primary_bus_id': connected_buses[0]['bus_id'] if connected_buses else None,
                'message_count': message_count,
                'uptime_seconds': uptime,
                'message_rate': round(message_rate, 2),
                'buses': buses,
            }

        buses = [self._build_bus_status_entry(bus_id) for bus_id in BUS_IDS]
        connected_buses = [bus for bus in buses if bus['connected']]
        uptime = max((bus['uptime_seconds'] for bus in connected_buses), default=0.0)
        message_count = sum(int(bus['message_count']) for bus in connected_buses)
        message_rate = sum(float(bus['message_rate']) for bus in connected_buses)

        return {
            'connected': bool(connected_buses),
            'connected_bus_count': len(connected_buses),
            'primary_bus_id': connected_buses[0]['bus_id'] if connected_buses else None,
            'message_count': message_count,
            'uptime_seconds': uptime,
            'message_rate': round(message_rate, 2),
            'buses': buses,
        }

    def get_connection_health(self) -> dict:
        """Get connection health and recovery state for frontend wake handling."""
        buses = [
            {
                'bus_id': bus_id,
                'connected': slot['connected'],
                'connection_state': slot['connection_state'],
                'recovery_in_progress': slot['recovery_in_progress'],
                'reason': slot['connection_reason'],
                'device_type': slot['device_type'].value if slot['device_type'] else None,
                'channel': slot['channel'],
                'interface': slot['interface'],
            }
            for bus_id, slot in self.bus_connections.items()
        ]
        return {
            'connected': self.is_connected,
            'connection_state': self.connection_state,
            'recovery_in_progress': self._recovery_in_progress,
            'reason': self.connection_reason,
            'device_type': self.device_type.value if self.device_type else None,
            'simulation_active': self._simulation_active,
            'connected_bus_count': self.get_connected_bus_count(),
            'primary_bus_id': self._get_primary_bus_id(),
            'buses': buses,
        }

    def is_simulation_active(self) -> bool:
        """Return whether fake BMS simulation mode is active."""
        return self._simulation_active

    # ------------------------------------------------------------------
    # HVC test mode: drive synthetic BMS summary/heartbeat frames out the
    # active CAN bus so the HVC dashboard can be exercised without a full
    # battery pack attached. Unlike full simulation, this requires a real
    # CAN connection and broadcasts on top of it.
    # ------------------------------------------------------------------

    HVC_TEST_REQUIRED_MESSAGES = (
        'Cell_Temp_Summary_0',
        'BMS1_Voltage_Summary_0',
        'BMS2_Voltage_Summary_0',
        'BMS_Heartbeat_0',
    )

    SIM_TEST_OPTIONAL_MESSAGES = (
        'IO_Summary',
        'IO_Current',
        'IO_VSense',
        'BMS_State',
        'Errored_Panic',
        'SOC',
        'ACC_Summary',
        'Current_Limit',
        'PL_Signal',
        'MOBO_Heartbeat',
        'MOBO_Errors',
        'MOBO_CAN_Stats',
        'MOBO_Power_Telemetry',
        'MOBO_Current_Telemetry',
        'MOBO_Safety_Status',
        'MOBO_Relay_Status',
    )

    SIM_SECONDARY_BUS_MESSAGES = (
        'DBF_WSPD_FL',
        'DBF_WSPD_FR',
        'DBL_WSPD_BL',
        'DBR_WSPD_BR',
        'BL_BrakeTemp',
        'FR_BrakeTemp',
    )

    def get_hvc_test_mode_status(self) -> Dict[str, Any]:
        """Return current HVC test mode state and global override config."""
        return {
            'enabled': self.hvc_test_mode_enabled,
            'interval_ms': int(self.hvc_test_mode_interval_s * 1000),
            'all_modules': {
                'min_voltage_v': round(self.hvc_test_mode_config['min_voltage_mv'] / 1000.0, 3),
                'max_voltage_v': round(self.hvc_test_mode_config['max_voltage_mv'] / 1000.0, 3),
                'min_temp_c': round(self.hvc_test_mode_config['min_temp_c'], 1),
                'max_temp_c': round(self.hvc_test_mode_config['max_temp_c'], 1),
            },
            'heartbeat_errors': {
                key: int(self.hvc_test_mode_config[key])
                for key in (
                    'error_flags_byte0',
                    'error_flags_byte1',
                    'error_flags_byte2',
                    'error_flags_byte3',
                    'warning_summary',
                    'fault_count',
                )
            },
        }

    def update_hvc_test_mode_config(
        self,
        min_voltage_v: float,
        max_voltage_v: float,
        min_temp_c: float,
        max_temp_c: float,
        error_flags_byte0: int,
        error_flags_byte1: int,
        error_flags_byte2: int,
        error_flags_byte3: int,
        warning_summary: int,
        fault_count: int,
    ) -> None:
        """Persist override values used by HVC summary/heartbeat test mode."""
        self.hvc_test_mode_config = {
            'min_voltage_mv': float(min_voltage_v) * 1000.0,
            'max_voltage_mv': float(max_voltage_v) * 1000.0,
            'min_temp_c': float(min_temp_c),
            'max_temp_c': float(max_temp_c),
            'error_flags_byte0': int(error_flags_byte0) & 0xFF,
            'error_flags_byte1': int(error_flags_byte1) & 0xFF,
            'error_flags_byte2': int(error_flags_byte2) & 0xFF,
            'error_flags_byte3': int(error_flags_byte3) & 0xFF,
            'warning_summary': int(warning_summary) & 0xFF,
            'fault_count': int(fault_count) & 0xFF,
        }

    def _ensure_hvc_summary_messages_available(self) -> bool:
        """Make sure required BMS summary message definitions are loaded."""
        missing = [
            name for name in self.HVC_TEST_REQUIRED_MESSAGES
            if not self._find_effective_message_by_name(name)
        ]
        if not missing:
            return True

        if not DBC_SUPPORT:
            return False

        bms_dbc_path = DBC_DIR / 'BMS-Firmware-RTOS-Complete.dbc'
        if not bms_dbc_path.exists():
            return False
        if not self.load_dbc_file(str(bms_dbc_path)):
            return False
        return all(self._find_effective_message_by_name(name) for name in self.HVC_TEST_REQUIRED_MESSAGES)

    def _build_hvc_test_summary_signals(self, module: int) -> Dict[str, Dict[str, Union[int, float]]]:
        """Build one module's summary payloads from the configured min/max values."""
        cfg = self.hvc_test_mode_config
        temp_min = min(cfg['min_temp_c'], cfg['max_temp_c'])
        temp_max = max(cfg['min_temp_c'], cfg['max_temp_c'])
        v_min_i = int(round(min(cfg['min_voltage_mv'], cfg['max_voltage_mv'])))
        v_max_i = int(round(max(cfg['min_voltage_mv'], cfg['max_voltage_mv'])))
        v_avg_i = int(round((v_min_i + v_max_i) / 2.0))
        temp_avg = (temp_min + temp_max) / 2.0

        # Distribute fake "min/max IDs" across modules so each module's frame
        # is visually distinguishable on the dashboard.
        temp_min_id = 1 + ((module * 7) % 54)
        temp_max_id = max(temp_min_id, min(54, temp_min_id + 13))
        bms1_min_id = 1 + (module % 3)
        bms1_max_id = 7 + (module % 3)
        bms2_min_id = 10 + (module % 3)
        bms2_max_id = 16 + (module % 3)

        return {
            'temp': {
                'Min_Cell_Temp': round(temp_min, 1),
                'Max_Cell_Temp': round(temp_max, 1),
                'Avg_Cell_Temp': round(temp_avg, 1),
                'Min_Cell_Temp_ID': temp_min_id,
                'Max_Cell_Temp_ID': temp_max_id,
            },
            'voltage_1': {
                'BMS1_Voltage_Average': v_avg_i,
                'BMS1_Voltage_Min': v_min_i,
                'BMS1_Voltage_Max': v_max_i,
                'BMS1_Min_Voltage_Cell_ID': bms1_min_id,
                'BMS1_Max_Voltage_Cell_ID': bms1_max_id,
            },
            'voltage_2': {
                'BMS2_Voltage_Average': v_avg_i,
                'BMS2_Voltage_Min': v_min_i,
                'BMS2_Voltage_Max': v_max_i,
                'BMS2_Min_Voltage_Cell_ID': bms2_min_id,
                'BMS2_Max_Voltage_Cell_ID': bms2_max_id,
            },
        }

    def _build_hvc_test_heartbeat_signals(self) -> Dict[str, int]:
        """Build BMS heartbeat payload using user-configurable error bytes."""
        cfg = self.hvc_test_mode_config
        return {
            'BMS_State': 1,
            'Error_Flags_Byte0': int(cfg['error_flags_byte0']),
            'Error_Flags_Byte1': int(cfg['error_flags_byte1']),
            'Error_Flags_Byte2': int(cfg['error_flags_byte2']),
            'Error_Flags_Byte3': int(cfg['error_flags_byte3']),
            'Warning_Summary': int(cfg['warning_summary']),
            'Fault_Count': int(cfg['fault_count']),
        }

    async def _send_hvc_test_message_on_bus(
        self,
        message_name: str,
        signals: Dict[str, Union[int, float]],
        bus_id: Optional[str] = None
    ) -> bool:
        """Encode and transmit one HVC test message on the active CAN bus."""
        try:
            target_bus_id = self._resolve_active_bus_id(bus_id)
        except ValueError:
            return False

        found = self._find_effective_message_by_name(message_name)
        if not found:
            return False

        try:
            _, message = found
            payload = message.encode(signals)
            can_id, is_extended = self._message_identity(message)
            sent = await asyncio.to_thread(
                self.send_message, can_id, list(payload), is_extended, False, target_bus_id
            )
            if not sent:
                return False

            # Mirror outgoing test frames to UI clients in case the adapter
            # does not loop TX frames back on RX.
            message_data = self._build_simulated_message(can_id, payload, is_extended, target_bus_id)
            message_data['source'] = 'hvc_test_mode_tx'
            self._increment_message_count(target_bus_id)
            await self.broadcast_message(message_data)
            return True
        except Exception as e:
            print(f"[HVC TEST] Failed to send {message_name}: {e}")
            return False

    async def start_hvc_test_mode(self) -> bool:
        """Enable HVC test mode and start periodic summary transmission."""
        if self.hvc_test_mode_enabled:
            return True
        if self._simulation_active:
            return False
        if not self.is_connected:
            return False
        if not self._ensure_hvc_summary_messages_available():
            return False

        self.hvc_test_mode_enabled = True
        self._hvc_test_mode_started_monotonic = time.perf_counter()
        self._hvc_test_mode_task = asyncio.create_task(self._run_hvc_test_mode())
        return True

    async def stop_hvc_test_mode(self) -> bool:
        """Disable HVC test mode and stop periodic summary transmission."""
        self.hvc_test_mode_enabled = False
        if self._hvc_test_mode_task and not self._hvc_test_mode_task.done():
            self._hvc_test_mode_task.cancel()
            try:
                await self._hvc_test_mode_task
            except asyncio.CancelledError:
                pass
        self._hvc_test_mode_task = None
        self._hvc_test_mode_started_monotonic = None
        return True

    async def _run_hvc_test_mode(self) -> None:
        """Transmit HVC summary/heartbeat frames for all 6 modules at fixed cadence."""
        print('[HVC TEST] On-bus summary mode started')
        try:
            while self.hvc_test_mode_enabled:
                primary_bus_id = self._get_primary_bus_id()
                if not self.is_connected or primary_bus_id is None:
                    print('[HVC TEST] Stopping because CAN connection is no longer active')
                    break
                for module in range(6):
                    sigs = self._build_hvc_test_summary_signals(module)
                    await self._send_hvc_test_message_on_bus(f'Cell_Temp_Summary_{module}', sigs['temp'], primary_bus_id)
                    await self._send_hvc_test_message_on_bus(f'BMS1_Voltage_Summary_{module}', sigs['voltage_1'], primary_bus_id)
                    await self._send_hvc_test_message_on_bus(f'BMS2_Voltage_Summary_{module}', sigs['voltage_2'], primary_bus_id)
                    await self._send_hvc_test_message_on_bus(
                        f'BMS_Heartbeat_{module}', self._build_hvc_test_heartbeat_signals(), primary_bus_id
                    )
                await asyncio.sleep(self.hvc_test_mode_interval_s)
        except asyncio.CancelledError:
            pass
        finally:
            self.hvc_test_mode_enabled = False
            self._hvc_test_mode_task = None
            print('[HVC TEST] On-bus summary mode stopped')

    async def start_simulation(self) -> bool:
        """Start generating fake BMS CAN data from DBC definitions."""
        if self._simulation_active:
            return True

        if self.is_connected or self._get_claimed_bus_ids():
            # Real hardware is connected, don't mix simulation with live bus.
            return False

        if not DBC_SUPPORT:
            return False

        self._simulation_temp_enabled_dbc_files.clear()
        if not self._ensure_simulation_dbc_support():
            self._restore_simulation_dbc_state()
            return False

        self.is_connected = True
        self.device_type = None
        self.connection_state = 'connected'
        self.connection_reason = 'simulation'
        self.start_time = datetime.now()
        self.message_count = 0
        self._configure_simulation_bus_slots()
        self._simulation_active = True
        self._simulation_started_monotonic = time.perf_counter()

        self._simulation_task = asyncio.create_task(self._run_simulation())
        self._simulation_current_task = asyncio.create_task(self._run_simulated_current_sensor())
        return True

    async def stop_simulation(self) -> bool:
        """Stop fake BMS CAN data simulation."""
        if not self._simulation_active:
            return True

        self._simulation_active = False

        if self._simulation_task and not self._simulation_task.done():
            self._simulation_task.cancel()
            try:
                await self._simulation_task
            except asyncio.CancelledError:
                pass

        if self._simulation_current_task and not self._simulation_current_task.done():
            self._simulation_current_task.cancel()
            try:
                await self._simulation_current_task
            except asyncio.CancelledError:
                pass

        self._simulation_task = None
        self._simulation_current_task = None
        self._simulation_started_monotonic = None
        self._restore_simulation_dbc_state()
        for bus_id in BUS_IDS:
            self._reset_bus_slot(bus_id, 'simulation_stopped')
        self.is_connected = False
        self.connection_state = 'disconnected'
        self.connection_reason = 'simulation_stopped'
        self.device_type = None
        self.start_time = None
        self.message_count = 0
        return True

    def _build_simulated_message(
        self,
        can_id: int,
        payload: bytes,
        is_extended: bool,
        bus_id: str = 'bus1'
    ) -> dict:
        """Build a websocket message payload from simulated CAN bytes."""
        message_data = {
            'bus_id': bus_id,
            'id': can_id,
            'data': list(payload),
            'timestamp': time.time(),
            'is_extended': is_extended,
            'is_remote': False,
            'dlc': len(payload)
        }

        if self.dbc_database:
            decoded = self.decode_message(can_id, payload, is_extended)
            if decoded:
                message_data['decoded'] = decoded

        return message_data

    async def _emit_simulated_message(
        self,
        message_name: str,
        signals: Dict[str, Union[int, float]],
        bus_id: str = 'bus1'
    ) -> bool:
        """Encode and broadcast one simulated CAN message by DBC message name."""
        found = self._find_effective_message_by_name(message_name)
        if not found:
            return False

        try:
            _, message = found
            message_signal_names = {signal.name for signal in message.signals}
            filtered_signals = {
                key: value for key, value in signals.items() if key in message_signal_names
            }
            payload = message.encode(filtered_signals)
            can_id, is_extended = self._message_identity(message)
            message_data = self._build_simulated_message(can_id, payload, is_extended, bus_id)
            self._increment_message_count(bus_id)
            await self.broadcast_message(message_data)
            return True
        except Exception as e:
            print(f"[SIM] Failed to emit {message_name}: {e}")
            return False

    def _get_simulation_elapsed(self) -> float:
        """Return elapsed simulation time in seconds using monotonic clock."""
        if self._simulation_started_monotonic is None:
            return 0.0
        return max(0.0, time.perf_counter() - self._simulation_started_monotonic)

    def _build_simulated_currents(self, elapsed: float) -> tuple[float, float]:
        """Generate deterministic-but-dynamic LC/HC current values."""
        cycle_seconds = 50.0
        base_phase = (elapsed % cycle_seconds) / cycle_seconds

        if base_phase < 0.5:
            base_level = base_phase * 2.0
        else:
            base_level = (1.0 - base_phase) * 2.0

        lc_current = 5.0 + (115.0 * base_level)
        lc_current += 2.8 * math.sin((elapsed * 0.8) + 0.35)
        lc_current += random.uniform(-1.2, 1.2)
        lc_current = max(5.0, min(120.0, lc_current))

        hc_current = lc_current + (3.0 * math.sin((elapsed * 1.2) + 1.1))
        hc_current += random.uniform(-0.8, 0.8)
        hc_current = max(5.0, min(120.0, hc_current))

        return round(lc_current, 1), round(hc_current, 1)

    def _build_optional_sim_test_payloads(
        self, elapsed: float, lc_current: float, hc_current: float
    ) -> Dict[str, Dict[str, Union[int, float]]]:
        """Build synthetic payloads for optional HVC/IO/MOBO test-mode messages."""
        cycle_seconds = 36.0
        phase = (elapsed % cycle_seconds) / cycle_seconds
        wave = 0.5 + (0.5 * math.sin(2.0 * math.pi * phase))
        heartbeat_toggle = int((elapsed * 2.0) % 2.0)

        ref_temp = round(24.0 + (22.0 * wave) + random.uniform(-0.35, 0.35), 2)
        current_low_ma = int(round((-12000.0 + (24000.0 * wave)) + random.uniform(-300.0, 300.0)))
        current_high_ma = int(round(current_low_ma + random.uniform(-900.0, 900.0)))

        batt_voltage_mv = int(round(292000.0 + (98000.0 * wave) + random.uniform(-500.0, 500.0)))
        inv_voltage_mv = int(round(batt_voltage_mv - (5000.0 + (2400.0 * (1.0 - wave))) + random.uniform(-300.0, 300.0)))

        soc_percent = round(18.0 + (79.0 * wave), 2)
        soc_capacity_as = int(round(21000.0 + (13000.0 * wave)))
        soc_delta_as = int(round((wave - 0.5) * 12000.0))

        acc_volt_min_mv = int(round(3110.0 + (260.0 * wave) + random.uniform(-4.0, 4.0)))
        acc_volt_max_mv = int(round(acc_volt_min_mv + 34.0 + random.uniform(0.0, 10.0)))
        acc_temp_min_c = round(24.0 + (8.5 * wave) + random.uniform(-0.6, 0.6), 1)
        acc_temp_max_c = round(acc_temp_min_c + 4.0 + random.uniform(0.0, 2.5), 1)

        negative_current_limit_ma = int(round(150000.0 + (22000.0 * (1.0 - wave))))
        positive_current_limit_ma = int(round(210000.0 + (28000.0 * wave)))

        bms_state = 1
        if wave > 0.82:
            bms_state = 3
        elif wave < 0.12:
            bms_state = 2

        pl_signal_reason = 4 if bms_state == 2 else (1 if wave > 0.65 else 0)

        battery_voltage_v = round((12800.0 + (1400.0 * wave) + random.uniform(-50.0, 50.0)) / 1000.0, 3)
        fivev_sense = round((4950.0 + random.uniform(-35.0, 35.0)) / 1000.0, 3)
        brake_pressure_psi = round((300.0 + (1200.0 * wave) + random.uniform(-12.0, 12.0)), 1)

        lv_current = round((lc_current * 0.12) + random.uniform(-0.8, 0.8), 3)
        hc_current_mobo = round((hc_current * 0.18) + random.uniform(-0.8, 0.8), 3)
        lv_current_raw = int(round(2048 + (lv_current * 18.0)))
        lv_current_raw = max(0, min(4095, lv_current_raw))

        pump_on = 1 if wave > 0.35 else 0
        drs_on = 1 if wave > 0.75 else 0
        fans_on = 1 if wave > 0.5 else 0
        rad_on = 1 if wave > 0.58 else 0

        return {
            'IO_Summary': {
                'SDC_Closed': 1,
                'IMD_Ok': 1,
                'BMS_Fault_Ok': 1,
                'Ref_Temp_C': ref_temp,
            },
            'IO_Current': {
                'Current_Low_mA': current_low_ma,
                'Current_High_mA': current_high_ma,
            },
            'IO_VSense': {
                'Batt_Voltage_mV': batt_voltage_mv,
                'Inv_Voltage_mV': inv_voltage_mv,
            },
            'BMS_State': {
                'BMS_State': bms_state,
                'Err_RefOverTemp': 0,
                'Err_ModuleTimeout': 0,
                'Err_BattFloating': 0,
                'Err_CurrSenseFloating': 0,
                'Err_BmbError': 0,
                'Err_BmsCanError': 0,
                'Err_LvCanError': 0,
            },
            'Errored_Panic': {},
            'SOC': {
                'SOC_Percent': soc_percent,
                'SOC_Capacity_As': soc_capacity_as,
                'SOC_Delta_As': soc_delta_as,
            },
            'ACC_Summary': {
                'Acc_Volt_Min_mV': acc_volt_min_mv,
                'Acc_Volt_Max_mV': acc_volt_max_mv,
                'Acc_Temp_Min_C': acc_temp_min_c,
                'Acc_Temp_Max_C': acc_temp_max_c,
            },
            'Current_Limit': {
                'Negative_Current_Limit_mA': negative_current_limit_ma,
                'Positive_Current_Limit_mA': positive_current_limit_ma,
            },
            'PL_Signal': {
                'PL_Signal_Reason': pl_signal_reason,
            },
            'MOBO_Heartbeat': {
                'System_State': 2,
                'Heartbeat_Counter': int(elapsed * 10.0) & 0xFF,
                'Fault_Count': 0,
                'Error_Summary': 0,
                'Has_Warnings': 0,
            },
            'MOBO_Errors': {
                'Error_Flags': 0,
                'Warning_Flags': 0,
            },
            'MOBO_CAN_Stats': {
                'TX_Success': int(elapsed * 12.0) & 0xFFFF,
                'TX_Failures': 0,
                'RX_Messages': int(elapsed * 8.0) & 0xFFFF,
                'RX_Drops': 0,
            },
            'MOBO_Power_Telemetry': {
                'Battery_Voltage': battery_voltage_v,
                'FiveV_Sense': fivev_sense,
                'BSE_PSI_Rear': brake_pressure_psi,
                'LV_Current_Raw': lv_current_raw,
            },
            'MOBO_Current_Telemetry': {
                'LV_Current': lv_current,
                'HC_Current': hc_current_mobo,
                'LV_Current_Peak': round(lv_current + 1.8, 3),
                'HC_Current_Peak': round(hc_current_mobo + 2.4, 3),
            },
            'MOBO_Safety_Status': {
                'SDC1_Raw': 0,
                'SDC2_Raw': 0,
                'SDC3_Raw': 0,
                'BMS_Raw': 0,
                'BSPD_Raw': 0,
                'IMD_Raw': 0,
                'SDC1_Debounced': 0,
                'SDC2_Debounced': 0,
                'SDC3_Debounced': 0,
                'BMS_Debounced': 0,
                'BSPD_Debounced': 0,
                'IMD_Debounced': 0,
                'SDC1_Latched': 0,
                'SDC2_Latched': 0,
                'SDC3_Latched': 0,
                'BMS_Latched': 0,
                'BSPD_Latched': 0,
                'IMD_Latched': 0,
            },
            'MOBO_Relay_Status': {
                'Pump_Commanded': pump_on,
                'DRS_Commanded': drs_on,
                'Fans_Commanded': fans_on,
                'Radiator_Fans_Commanded': rad_on,
                'Pump_Actual': pump_on,
                'DRS_Actual': drs_on,
                'Fans_Actual': fans_on,
                'Radiator_Fans_Actual': rad_on,
                'Pump_State': 2 if pump_on else 0,
                'DRS_State': 2 if drs_on else 0,
                'Fans_State': 2 if fans_on else 0,
                'Radiator_Fans_State': 2 if rad_on else 0,
                'Acc_Fans_Active': 0,
                'Acc_Fans_Phase': 0,
                'Ms_Since_Cmd': int((elapsed * 1000.0) % 5000.0),
            },
        }

    def _build_secondary_bus_sim_test_payloads(self, elapsed: float) -> Dict[str, Dict[str, Union[int, float]]]:
        """Build synthetic wheel-speed and brake-temperature traffic for bus2 using master.dbc."""
        speed_wave = 0.5 + (0.5 * math.sin((elapsed * 0.42) - 0.45))
        brake_wave = 0.5 + (0.5 * math.sin((elapsed * 0.18) - 1.1))

        front_base_rpm = 180.0 + (1350.0 * speed_wave)
        rear_base_rpm = front_base_rpm * (1.01 + (0.015 * math.sin((elapsed * 0.27) + 0.8)))
        steering_delta = 18.0 * math.sin((elapsed * 0.65) + 0.35)
        rear_diff = 11.0 * math.sin((elapsed * 0.58) - 0.9)

        wheel_rpms = {
            'DBF_WSPD_FL': max(0.0, front_base_rpm - steering_delta + random.uniform(-4.0, 4.0)),
            'DBF_WSPD_FR': max(0.0, front_base_rpm + steering_delta + random.uniform(-4.0, 4.0)),
            'DBL_WSPD_BL': max(0.0, rear_base_rpm - rear_diff + random.uniform(-4.0, 4.0)),
            'DBR_WSPD_BR': max(0.0, rear_base_rpm + rear_diff + random.uniform(-4.0, 4.0)),
        }

        brake_front_base = 68.0 + (155.0 * brake_wave)
        brake_rear_base = 60.0 + (126.0 * brake_wave)

        payloads: Dict[str, Dict[str, Union[int, float]]] = {}
        for message_name, rpm in wheel_rpms.items():
            avg_delta_us = int(max(800, round(60_000_000.0 / max(1.0, rpm * 48.0))))
            payloads[message_name] = {
                f'{message_name}_Valid': 1,
                f'{message_name}_Timeout': 0,
                f'{message_name}_Avg_Delta': avg_delta_us,
                f'{message_name}_RPM': round(rpm),
            }

        payloads['BL_BrakeTemp'] = {
            'BL_BrakeTemp_Ch1': round(brake_rear_base + 7.0 + random.uniform(-1.6, 1.6), 1),
            'BL_BrakeTemp_Ch2': round(brake_rear_base + 3.5 + random.uniform(-1.4, 1.4), 1),
            'BL_BrakeTemp_Ch3': round(brake_rear_base - 2.0 + random.uniform(-1.2, 1.2), 1),
            'BL_BrakeTemp_Ch4': round(brake_rear_base + 1.5 + random.uniform(-1.3, 1.3), 1),
        }
        payloads['FR_BrakeTemp'] = {
            'FR_BrakeTemp_Ch1': round(brake_front_base + 9.0 + random.uniform(-1.8, 1.8), 1),
            'FR_BrakeTemp_Ch2': round(brake_front_base + 4.0 + random.uniform(-1.5, 1.5), 1),
            'FR_BrakeTemp_Ch3': round(brake_front_base - 3.5 + random.uniform(-1.2, 1.2), 1),
            'FR_BrakeTemp_Ch4': round(brake_front_base + 2.5 + random.uniform(-1.4, 1.4), 1),
        }

        return payloads

    async def _run_simulated_current_sensor(self):
        """Emit Current_Sensor_Data at a fixed 10 ms cadence while simulation is active."""
        try:
            if not self._find_effective_message_by_name("Current_Sensor_Data"):
                return

            emit_interval_s = 0.01
            next_emit = time.perf_counter()

            while self._simulation_active:
                elapsed = self._get_simulation_elapsed()
                lc_current, hc_current = self._build_simulated_currents(elapsed)

                await self._emit_simulated_message(
                    "Current_Sensor_Data",
                    {
                        "LC_Current": lc_current,
                        "HC_Current": hc_current,
                        "Reserved_4": 0,
                        "Reserved_5": 0,
                        "Reserved_6": 0,
                        "Reserved_7": 0
                    },
                    bus_id='bus1'
                )

                next_emit += emit_interval_s
                sleep_for = next_emit - time.perf_counter()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                else:
                    # If delayed by scheduler load, skip ahead to preserve ~10 ms cadence.
                    missed_intervals = int((-sleep_for) // emit_interval_s) + 1
                    next_emit += missed_intervals * emit_interval_s
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass

    async def _run_simulation(self):
        """Main fake-data loop with rise/fall wave and center-lag thermal/electrical gradients."""
        print("[SIM] BMS simulation started")

        # Simulation bounds requested by user.
        temp_min = 20.0
        temp_max = 60.0
        voltage_min = 3200.0
        voltage_max = 4200.0

        cycle_seconds = 50.0  # One full rise-and-fall cycle.
        optional_messages_available = {
            name: bool(self._find_effective_message_by_name(name))
            for name in self.SIM_TEST_OPTIONAL_MESSAGES
        }
        secondary_bus_messages_available = {
            name: bool(self._find_effective_message_by_name(name))
            for name in self.SIM_SECONDARY_BUS_MESSAGES
        }

        def normalized_triangle(phase: float) -> tuple[float, bool]:
            """Return (0..1 value, rising_phase)."""
            phase = phase % 1.0
            if phase < 0.5:
                return phase * 2.0, True
            return (1.0 - phase) * 2.0, False

        def center_closeness(local_index: int, max_index: int, center_idx: float) -> float:
            """1.0 at center, 0.0 at far edges."""
            half_span = max(center_idx, max_index - center_idx)
            if half_span <= 0:
                return 0.0
            return max(0.0, 1.0 - (abs(local_index - center_idx) / half_span))

        def phase_response(closeness: float, rising: bool) -> float:
            """Middle cells 7-13 heat slower and cool first/faster."""
            if rising:
                # Center lags while heating.
                return 1.0 - (0.42 * closeness)
            # Center leads while cooling.
            return 1.0 + (0.55 * closeness)

        def hotspot_curve(x: float, center: float, width: float) -> float:
            """Smooth 0..1 bump used to build non-uniform local hot/cold regions."""
            if width <= 0:
                return 0.0
            normalized = (x - center) / width
            return max(0.0, 1.0 - (normalized * normalized))

        # Persistent per-thermistor profile so readings are varied, not a flat gradient.
        temp_gain = [0.82 + random.uniform(-0.08, 0.18) for _ in range(336)]
        temp_phase_offset = [random.uniform(-0.09, 0.09) for _ in range(336)]
        temp_sensor_bias = [random.uniform(-1.6, 1.8) for _ in range(336)]
        temp_jitter_amp = [0.15 + random.uniform(0.0, 0.45) for _ in range(336)]

        # Cache actual DBC signal names per temperature message so ambient renames are handled.
        temp_message_signal_names: Dict[str, set[str]] = {}
        for module in range(6):
            temp_module_base = module * 56
            for temp_group in range(14):
                temp_start = temp_module_base + (temp_group * 4)
                temp_end = temp_start + 3
                message_name = f"Cell_Temp_{temp_start}_{temp_end}"
                try:
                    msg = self.dbc_database.get_message_by_name(message_name)
                    temp_message_signal_names[message_name] = {sig.name for sig in msg.signals}
                except Exception:
                    temp_message_signal_names[message_name] = set()

        # Build module-local hotspot maps (different regions warm/cool at different rates).
        module_hotspot_profiles: List[List[float]] = []
        for _ in range(6):
            hotspot_centers = [
                random.uniform(6.0, 20.0),
                random.uniform(24.0, 36.0),
                random.uniform(38.0, 52.0)
            ]
            hotspot_strengths = [
                random.uniform(1.0, 2.8),
                random.uniform(-1.1, 1.7),
                random.uniform(0.9, 2.5)
            ]
            hotspot_widths = [
                random.uniform(4.0, 8.0),
                random.uniform(3.0, 7.0),
                random.uniform(4.5, 9.0)
            ]

            profile: List[float] = []
            for local_idx in range(56):
                value = 0.0
                for center, strength, width in zip(hotspot_centers, hotspot_strengths, hotspot_widths):
                    value += strength * hotspot_curve(float(local_idx), center, width)
                profile.append(value)
            module_hotspot_profiles.append(profile)

        start_time = time.time()

        try:
            while self._simulation_active:
                elapsed = time.time() - start_time
                base_phase = (elapsed % cycle_seconds) / cycle_seconds
                base_level, is_rising = normalized_triangle(base_phase)

                for module in range(6):
                    temp_module_base = module * 56
                    voltage_module_base = module * 18

                    # Slight pack-level gradient so modules are not identical.
                    module_temp_offset = (module - 2.5) * 0.8
                    module_voltage_offset = (module - 2.5) * 18.0

                    # 14 temperature frames per module, 4 temperatures each.
                    for temp_group in range(14):
                        start_idx = temp_module_base + (temp_group * 4)
                        temp_start = temp_module_base + (temp_group * 4)
                        temp_end = temp_start + 3
                        temp_message_name = f"Cell_Temp_{temp_start}_{temp_end}"
                        signal_name_set = temp_message_signal_names.get(temp_message_name, set())
                        signal_payload: Dict[str, float] = {}
                        for offset in range(4):
                            thermistor_idx = start_idx + offset
                            local_temp_idx = thermistor_idx - temp_module_base  # 0..55

                            # Map thermistor position into a pseudo 18-cell span to mirror cell 7-13 behavior.
                            pseudo_cell_idx = int(round((local_temp_idx / 55.0) * 17.0))
                            center_factor = center_closeness(pseudo_cell_idx, 17, 9.0)
                            response = phase_response(center_factor, is_rising)

                            # Add per-sensor phase skew and gain for richer thermal behavior.
                            local_phase = (base_phase + temp_phase_offset[thermistor_idx]) % 1.0
                            local_level, _ = normalized_triangle(local_phase)
                            effective_level = min(1.0, max(0.0, local_level * response * temp_gain[thermistor_idx]))

                            temp_value = temp_min + ((temp_max - temp_min) * effective_level)

                            # Hotspots intensify while heating and fade during cooling.
                            hotspot_scale = 0.35 + (1.15 * base_level if is_rising else 0.55 * base_level)
                            hotspot_value = module_hotspot_profiles[module][local_temp_idx] * hotspot_scale

                            # Mixed-frequency ripple to avoid smooth/linear appearance.
                            thermal_wave = (
                                0.6 * math.sin((elapsed * 0.45) + (local_temp_idx * 0.31) + (module * 0.9)) +
                                0.35 * math.sin((elapsed * 0.9) + (local_temp_idx * 0.11) + (module * 1.7))
                            )

                            temp_value += module_temp_offset
                            temp_value += temp_sensor_bias[thermistor_idx]
                            temp_value += hotspot_value
                            temp_value += thermal_wave
                            temp_value += random.uniform(-temp_jitter_amp[thermistor_idx], temp_jitter_amp[thermistor_idx])
                            temp_value = max(temp_min, min(temp_max, temp_value))

                            default_name = f"Temp_{thermistor_idx:03d}"
                            ambient1_name = f"Ambient_Temp_1_{thermistor_idx:03d}"
                            ambient2_name = f"Ambient_Temp_2_{thermistor_idx:03d}"

                            # Use the exact signal name from DBC for the last two channels.
                            if local_temp_idx == 54 and ambient1_name in signal_name_set:
                                signal_name = ambient1_name
                            elif local_temp_idx == 55 and ambient2_name in signal_name_set:
                                signal_name = ambient2_name
                            elif default_name in signal_name_set or not signal_name_set:
                                signal_name = default_name
                            elif ambient1_name in signal_name_set:
                                signal_name = ambient1_name
                            elif ambient2_name in signal_name_set:
                                signal_name = ambient2_name
                            else:
                                signal_name = default_name

                            signal_payload[signal_name] = round(temp_value, 1)

                        await self._emit_simulated_message(
                            temp_message_name,
                            signal_payload,
                            bus_id='bus1'
                        )

                    # 6 cell-voltage frames per module, 3 voltages each.
                    for voltage_group in range(6):
                        start_idx = voltage_module_base + (voltage_group * 3)
                        signal_payload: Dict[str, int] = {}
                        for offset in range(3):
                            cell_idx = start_idx + offset
                            local_cell_idx = cell_idx - voltage_module_base  # 0..17

                            # Center cells (7-13 -> roughly local 6..12) lag on rise and cool first.
                            center_factor = center_closeness(local_cell_idx, 17, 9.0)
                            response = phase_response(center_factor, is_rising)

                            # Add slight phase spread across pack so gradients are visible.
                            local_phase = (base_phase + (local_cell_idx / 18.0) * 0.08) % 1.0
                            local_level, _ = normalized_triangle(local_phase)
                            effective_level = min(1.0, max(0.0, local_level * response))

                            voltage_value = voltage_min + ((voltage_max - voltage_min) * effective_level)
                            voltage_value += module_voltage_offset + random.uniform(-2.0, 2.0)
                            voltage_value = max(voltage_min, min(voltage_max, voltage_value))

                            signal_payload[f"Cell_{cell_idx + 1:03d}_Voltage"] = int(round(voltage_value))

                        cell_start = 1 + voltage_module_base + (voltage_group * 3)
                        cell_end = cell_start + 2
                        await self._emit_simulated_message(
                            f"Cell_Voltage_{cell_start}_{cell_end}",
                            signal_payload,
                            bus_id='bus1'
                        )

                    await self._emit_simulated_message(
                        f"BMS_Heartbeat_{module}",
                        {
                            "BMS_State": 1,
                            "Error_Flags_Byte0": 0,
                            "Error_Flags_Byte1": 0,
                            "Error_Flags_Byte2": 0,
                            "Error_Flags_Byte3": 0,
                            "Warning_Summary": 0,
                            "Fault_Count": 0
                        },
                        bus_id='bus1'
                    )

                elapsed_for_optional = self._get_simulation_elapsed()
                lc_current, hc_current = self._build_simulated_currents(elapsed_for_optional)
                optional_payloads = self._build_optional_sim_test_payloads(
                    elapsed_for_optional, lc_current, hc_current
                )
                for message_name, payload in optional_payloads.items():
                    if optional_messages_available.get(message_name):
                        await self._emit_simulated_message(message_name, payload, bus_id='bus1')

                secondary_bus_payloads = self._build_secondary_bus_sim_test_payloads(elapsed_for_optional)
                for message_name, payload in secondary_bus_payloads.items():
                    if secondary_bus_messages_available.get(message_name):
                        await self._emit_simulated_message(message_name, payload, bus_id='bus2')

                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[SIM] Simulation loop crashed: {e}")
            self._simulation_active = False
        finally:
            print("[SIM] BMS simulation stopped")
    
    def get_dbc_messages(self) -> List[dict]:
        """Get effective message list from enabled DBC files."""
        if not self.dbc_entries:
            return []

        messages = []
        seen_frame_keys = set()

        for entry in self.dbc_entries:
            if not entry.get('enabled') or not entry.get('database'):
                continue

            for msg in entry['database'].messages:
                try:
                    actual_id, is_extended = self._message_identity(msg)
                    frame_key = (actual_id, is_extended)
                    if frame_key in seen_frame_keys:
                        continue
                    seen_frame_keys.add(frame_key)

                    signals = []
                    for signal in msg.signals:
                        choices_dict = {}
                        if signal.choices:
                            choices_dict = {int(k): str(v) for k, v in signal.choices.items()}

                        multiplexer_signal = getattr(signal, 'multiplexer_signal', None)
                        if hasattr(multiplexer_signal, 'name'):
                            multiplexer_signal = multiplexer_signal.name

                        multiplexer_ids = getattr(signal, 'multiplexer_ids', None)
                        if multiplexer_ids is None:
                            multiplexer_id = getattr(signal, 'multiplexer_id', None)
                            if multiplexer_id is not None:
                                multiplexer_ids = [multiplexer_id]

                        if multiplexer_ids is not None:
                            multiplexer_ids = [int(v) for v in sorted(multiplexer_ids)]

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
                            'choices': choices_dict,
                            'is_multiplexer': bool(getattr(signal, 'is_multiplexer', False)),
                            'multiplexer_signal': multiplexer_signal,
                            'multiplexer_ids': multiplexer_ids
                        })

                    msg_length = msg.length if msg.length is not None else 8

                    messages.append({
                        'name': msg.name,
                        'frame_id': actual_id,
                        'is_extended': is_extended,
                        'dlc': msg_length,
                        'length': msg_length,
                        'signal_count': len(signals),
                        'signals': signals,
                        'source_dbc': entry['filename']
                    })
                except Exception as e:
                    print(f"Error processing message {msg.name}: {e}")
                    continue
        
        return messages
    
    def decode_message(self, can_id: int, data: bytes, is_extended: bool = False) -> Optional[dict]:
        """Decode a CAN message using the first matching enabled DBC."""
        if not self.dbc_entries:
            print(f"[DECODE] No DBC database loaded")
            return None

        for entry in self.dbc_entries:
            if not entry.get('enabled') or not entry.get('database'):
                continue

            try:
                message = self._find_message_by_frame_id(entry['database'], can_id, is_extended)
                if not message:
                    continue

                decoded = message.decode(data)
                signals = {}
                for key, value in decoded.items():
                    signal = message.get_signal_by_name(key)

                    if hasattr(value, 'name') and value.name is not None:
                        display_value = value.name
                        raw_value = value.value
                    elif hasattr(value, 'value'):
                        display_value = value.value
                        raw_value = value.value
                    else:
                        display_value = value
                        raw_value = value

                    signal_info = {
                        'value': display_value,
                    }

                    if isinstance(display_value, str) and isinstance(raw_value, (int, float)):
                        signal_info['raw'] = raw_value

                    if signal.unit:
                        signal_info['unit'] = signal.unit
                    if signal.scale != 1:
                        signal_info['scale'] = signal.scale
                    if signal.offset != 0:
                        signal_info['offset'] = signal.offset
                    if signal.minimum is not None:
                        signal_info['min'] = signal.minimum
                    if signal.maximum is not None:
                        signal_info['max'] = signal.maximum

                    signals[key] = signal_info

                return {
                    'message_name': message.name,
                    'signals': signals,
                    'source_dbc': entry['filename']
                }
            except Exception as e:
                print(f"[DECODE] Decode error in {entry['filename']}: can_id=0x{can_id:X}, error={e}")

        print(f"[DECODE] Message not found in enabled DBCs: can_id=0x{can_id:X}, is_extended={is_extended}")
        return None
    
    def _make_message_callback(self, bus_id: str):
        """Bind one driver's receive callback to a bus slot."""
        def _callback(msg):
            self._on_message_received(msg, bus_id=bus_id)
        return _callback

    def _on_message_received(self, msg, bus_id: Optional[str] = None):
        """Callback for received CAN messages - broadcasts to all WebSocket clients
        
        This is called from the driver's receive thread, so we need to schedule
        the async broadcast on the main event loop.
        """
        target_bus_id = bus_id if bus_id in self.bus_connections else None
        message_count = self._increment_message_count(target_bus_id)
        received_at = time.time()
        
        # Convert message to JSON-serializable format
        message_data = {
            'bus_id': target_bus_id,
            'id': msg.id,
            'data': list(msg.data),
            'timestamp': msg.timestamp,
            'received_at': received_at,
            'is_extended': msg.is_extended,
            'is_remote': msg.is_remote,
            'dlc': msg.dlc
        }
        
        # Debug: Print first few messages
        if message_count <= 5:
            print(f"[RX][{target_bus_id or 'unknown'}] Message #{message_count}: ID=0x{msg.id:X}, Extended={msg.is_extended}, DLC={msg.dlc}, Data={msg.data.hex()}")
        
        # Check for server-decoded data (Network driver with DBC loaded on server)
        if hasattr(msg, 'server_decoded') and msg.server_decoded:
            # Use server-decoded data - convert signals list to dict format
            server_decoded = msg.server_decoded
            if server_decoded.get('message_name') or server_decoded.get('signals'):
                signals = {}
                if server_decoded.get('signals'):
                    for sig in server_decoded['signals']:
                        if isinstance(sig, dict):
                            sig_name = sig.get('name', 'unknown')
                            # Preserve full signal info including value, unit, and any other metadata
                            signal_info = {
                                'value': sig.get('value', 0)
                            }
                            # Add unit if present
                            if sig.get('unit'):
                                signal_info['unit'] = sig['unit']
                            # Add raw value if present (for enum values)
                            if 'raw' in sig:
                                signal_info['raw'] = sig['raw']
                            signals[sig_name] = signal_info
                
                message_data['decoded'] = {
                    'message_name': server_decoded.get('message_name'),
                    'signals': signals
                }
                if message_count <= 5:
                    print(f"[RX] Server-decoded: {server_decoded.get('message_name')}")
        # Fallback to local DBC decoding if no server-decoded data
        elif self.dbc_database:
            decoded = self.decode_message(msg.id, msg.data, msg.is_extended)
            if decoded:
                message_data['decoded'] = decoded
        else:
            if message_count <= 2:
                print(f"[RX] No DBC database available for decoding")
        
        # Schedule broadcast on the event loop (if available)
        if self.loop and self.loop.is_running():
            if message_count <= 5:
                print(f"[RX] Broadcasting to {len(self.active_connections)} clients, loop running: {self.loop.is_running()}")
            asyncio.run_coroutine_threadsafe(
                self.broadcast_message(message_data),
                self.loop
            )
        else:
            if message_count <= 5:
                print(f"[RX] NOT broadcasting - loop={self.loop}, running={self.loop.is_running() if self.loop else 'N/A'}")
    
    async def broadcast_message(self, message: dict):
        """Broadcast message to all connected WebSocket clients"""
        disconnected = []
        
        for connection in list(self.active_connections):
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
        self.websocket_last_seen[websocket] = time.monotonic()
        print(f"[WS] WebSocket connected, total clients: {len(self.active_connections)}")

    def touch_websocket_connection(self, websocket: WebSocket):
        """Record the latest activity timestamp for a WebSocket connection."""
        if websocket in self.active_connections:
            self.websocket_last_seen[websocket] = time.monotonic()
    
    def remove_websocket_connection(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        removed = False
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            removed = True
        self.websocket_last_seen.pop(websocket, None)
        if removed:
            print(f"[WS] WebSocket disconnected, remaining clients: {len(self.active_connections)}")


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


def get_transmit_list_path(dbc_context: str) -> Path:
    """Return a stable JSON path for a transmit-list context string."""
    digest = hashlib.sha1(dbc_context.encode('utf-8')).hexdigest()[:16]
    return TRANSMIT_LISTS_DIR / f"{digest}_transmit_list.json"


def cleanup_on_exit():
    """Cleanup handler called on program exit."""
    print("\n[Cleanup] Performing cleanup on exit...")
    if backend.is_connected or backend._get_claimed_bus_ids():
        try:
            backend.disconnect()
            print("[Cleanup] Disconnected successfully")
        except Exception as e:
            print(f"[Cleanup] Error during disconnect: {e}")


# Register cleanup handler
atexit.register(cleanup_on_exit)


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
    connected_bus_id = backend.connect(
        request.device_type,
        request.channel,
        request.baudrate,
        request.bus_id,
    )
    
    if connected_bus_id:
        status = backend.get_bus_status()
        bus_status = next(
            (bus for bus in status['buses'] if bus['bus_id'] == connected_bus_id),
            {}
        )
        await backend.broadcast_connection_status('connected', 'connected_via_api', connected_bus_id)
        return ConnectionResponse(
            success=True,
            message="Connected successfully",
            bus_id=connected_bus_id,
            connected_bus_count=status['connected_bus_count'],
            device_type=bus_status.get('device_type') or request.device_type.value,
            channel=bus_status.get('channel', request.channel),
            baudrate=bus_status.get('baudrate', request.baudrate)
        )
    else:
        detail = backend.connection_reason or "Failed to connect to device"
        raise HTTPException(status_code=500, detail=detail)


@app.post("/disconnect", response_model=DisconnectionResponse)
async def disconnect(request: Optional[DisconnectionRequest] = None):
    """Disconnect from CAN device"""
    target_bus_id = request.bus_id if request else None
    if backend.is_simulation_active():
        await backend.stop_simulation()
        await backend.broadcast_connection_status('disconnected', 'simulation_stopped')
        return DisconnectionResponse(
            success=True,
            message="Simulation stopped",
            disconnected_bus_ids=['simulation'],
            connected_bus_count=0,
        )

    if backend.hvc_test_mode_enabled:
        await backend.stop_hvc_test_mode()

    if not backend.is_connected and not backend._recovery_in_progress and not backend._get_claimed_bus_ids():
        raise HTTPException(status_code=400, detail="Not connected to any device")

    disconnected_bus_ids = backend.disconnect(target_bus_id)

    if disconnected_bus_ids:
        for disconnected_bus_id in disconnected_bus_ids:
            await backend.broadcast_connection_status('disconnected', 'disconnected_via_api', disconnected_bus_id)

        message = (
            f"Disconnected {disconnected_bus_ids[0]} successfully"
            if len(disconnected_bus_ids) == 1
            else "Disconnected all buses successfully"
        )
        return DisconnectionResponse(
            success=True,
            message=message,
            bus_id=disconnected_bus_ids[0] if len(disconnected_bus_ids) == 1 else None,
            disconnected_bus_ids=disconnected_bus_ids,
            connected_bus_count=backend.get_connected_bus_count(),
        )

    raise HTTPException(status_code=500, detail="Failed to disconnect")


@app.get("/status", response_model=BusStatusResponse)
async def get_status():
    """Get current bus status"""
    status = backend.get_bus_status()
    return BusStatusResponse(**status)


@app.get("/health")
async def get_health():
    """Get backend connection health state for wake/sleep recovery UX."""
    return backend.get_connection_health()


@app.post("/shutdown")
async def shutdown_backend():
    """Gracefully disconnect hardware so launcher can terminate process safely."""
    await backend.shutdown()
    return {"success": True, "message": "Backend shutdown cleanup complete"}


@app.post("/send", response_model=CANMessageResponse)
async def send_message(request: CANMessageRequest):
    """Send a CAN message"""
    if not backend.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to any device")

    try:
        target_bus_id = backend.resolve_target_bus_id(request.bus_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    success = backend.send_message(
        request.can_id,
        request.data,
        request.is_extended,
        request.is_remote,
        target_bus_id,
    )
    
    if success:
        return CANMessageResponse(
            success=True,
            message="Message sent successfully",
            bus_id=target_bus_id,
        )
    else:
        detail = backend.connection_reason or "Failed to send message"
        raise HTTPException(status_code=500, detail=detail)


@app.post("/dbc/upload", response_model=DBCLoadResponse)
async def upload_dbc(file: UploadFile = File(...)):
    """Upload a DBC file and register it in the ordered list as disabled by default."""
    if not DBC_SUPPORT:
        raise HTTPException(status_code=400, detail="DBC support not available (install cantools)")
    
    # Validate file extension
    if not file.filename.endswith('.dbc'):
        raise HTTPException(status_code=400, detail="File must have .dbc extension")
    
    try:
        # Save the uploaded file
        filename = backend._normalize_dbc_filename(file.filename)
        file_path = DBC_DIR / filename
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)

        entry = backend.register_dbc_file(filename, enabled=False)
        message_count = len(entry['database'].messages) if entry.get('database') else 0
        return DBCLoadResponse(
            success=True,
            message=f"DBC file '{filename}' uploaded successfully. Enable it to use it for decoding.",
            file_path=str(file_path),
            message_count=message_count
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@app.get("/dbc/current", response_model=DBCConfigResponse)
async def get_current_dbc():
    """Get information about the current effective DBC state and full ordered list."""
    return DBCConfigResponse(**backend.get_dbc_status())


@app.get("/dbc/list", response_model=DBCConfigResponse)
async def list_dbc_files():
    """List all uploaded DBC files with ordering, enabled state, and load status."""
    return DBCConfigResponse(**backend.get_dbc_status())


@app.get("/dbc/config", response_model=DBCConfigResponse)
async def get_dbc_config():
    """Return the full multi-DBC config for the frontend manager."""
    return DBCConfigResponse(**backend.get_dbc_status())


@app.post("/dbc/config", response_model=DBCConfigResponse)
async def update_dbc_config(request: DBCConfigUpdateRequest):
    """Update DBC priority ordering and enabled state atomically."""
    try:
        return DBCConfigResponse(**backend.update_dbc_config(request.files))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/dbc/delete/{filename}")
async def delete_dbc_file(filename: str):
    """Delete a DBC file"""
    # Validate filename to prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    normalized_filename = backend._normalize_dbc_filename(filename)
    file_path = DBC_DIR / normalized_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()

        status = backend.delete_dbc_entry(normalized_filename)

        return {
            "success": True,
            "message": f"File '{normalized_filename}' deleted",
            "dbc": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


@app.post("/dbc/load", response_model=DBCLoadResponse)
async def load_dbc(request: DBCLoadRequest):
    """Legacy endpoint: enable a DBC and promote it to top priority."""
    if not DBC_SUPPORT:
        raise HTTPException(status_code=400, detail="DBC support not available (install cantools)")
    
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="DBC file not found")
    
    success = backend.load_dbc_file(request.file_path)
    
    if success:
        message_count = len(backend.dbc_database.messages) if backend.dbc_database else 0
        return DBCLoadResponse(
            success=True,
            message="DBC file enabled and moved to highest priority",
            file_path=request.file_path,
            message_count=message_count
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to load DBC file")


@app.get("/dbc/messages", response_model=DBCMessagesResponse)
async def get_dbc_messages():
    """Get effective message list from enabled DBC files."""
    if not backend.dbc_database:
        raise HTTPException(status_code=400, detail="No DBC file loaded")
    
    messages = backend.get_dbc_messages()
    return DBCMessagesResponse(success=True, messages=messages)


@app.get("/stats")
async def get_stats():
    """Get message statistics"""
    return backend.get_message_stats()


@app.post("/simulation/start")
async def start_simulation():
    """Start fake BMS telemetry stream for UI testing."""
    success = await backend.start_simulation()
    if not success:
        raise HTTPException(status_code=400, detail="Unable to start simulation (real device may be connected or DBC unavailable)")

    await backend.broadcast_connection_status('connected', 'simulation_started')
    return {"success": True, "message": "Simulation started"}


@app.post("/simulation/stop")
async def stop_simulation():
    """Stop fake BMS telemetry stream."""
    success = await backend.stop_simulation()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to stop simulation")

    await backend.broadcast_connection_status('disconnected', 'simulation_stopped')
    return {"success": True, "message": "Simulation stopped"}


@app.get("/simulation/status")
async def simulation_status():
    """Get current simulation mode status."""
    return {
        "active": backend.is_simulation_active()
    }


# ============================================================================
# HVC Test Mode Endpoints
# ============================================================================

@app.get("/hvc/test_mode/status")
async def get_hvc_test_mode_status():
    """Return HVC summary test mode state and global override values."""
    return backend.get_hvc_test_mode_status()


@app.post("/hvc/test_mode/toggle")
async def set_hvc_test_mode_toggle(request: HVCTestModeToggleRequest):
    """Enable or disable backend-driven HVC summary test mode."""
    if request.enabled:
        success = await backend.start_hvc_test_mode()
        if not success:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unable to enable HVC test mode (requires active CAN "
                    "connection and BMS-Firmware-RTOS-Complete.dbc loaded)"
                ),
            )
    else:
        await backend.stop_hvc_test_mode()
    return backend.get_hvc_test_mode_status()


@app.post("/hvc/test_mode/config")
async def set_hvc_test_mode_config(request: HVCTestModeConfigRequest):
    """Update all-module HVC summary and heartbeat overrides used by test mode."""
    if not (2.5 <= request.min_voltage_v <= 4.3):
        raise HTTPException(status_code=422, detail="min_voltage_v must be between 2.5 and 4.3")
    if not (2.5 <= request.max_voltage_v <= 4.3):
        raise HTTPException(status_code=422, detail="max_voltage_v must be between 2.5 and 4.3")
    if not (20.0 <= request.min_temp_c <= 80.0):
        raise HTTPException(status_code=422, detail="min_temp_c must be between 20 and 80")
    if not (20.0 <= request.max_temp_c <= 80.0):
        raise HTTPException(status_code=422, detail="max_temp_c must be between 20 and 80")
    if request.min_voltage_v > request.max_voltage_v:
        raise HTTPException(status_code=422, detail="min_voltage_v must be <= max_voltage_v")
    if request.min_temp_c > request.max_temp_c:
        raise HTTPException(status_code=422, detail="min_temp_c must be <= max_temp_c")

    for key in (
        'error_flags_byte0', 'error_flags_byte1', 'error_flags_byte2',
        'error_flags_byte3', 'warning_summary', 'fault_count',
    ):
        value = getattr(request, key)
        if not (0 <= value <= 255):
            raise HTTPException(status_code=422, detail=f"{key} must be between 0 and 255")

    backend.update_hvc_test_mode_config(
        request.min_voltage_v,
        request.max_voltage_v,
        request.min_temp_c,
        request.max_temp_c,
        request.error_flags_byte0,
        request.error_flags_byte1,
        request.error_flags_byte2,
        request.error_flags_byte3,
        request.warning_summary,
        request.fault_count,
    )
    return backend.get_hvc_test_mode_status()


# ============================================================================
# Transmit List Endpoints
# ============================================================================

@app.post("/transmit_list/save")
async def save_transmit_list(request: SaveTransmitListRequest):
    """Save transmit list for the current DBC context."""
    try:
        json_path = get_transmit_list_path(request.dbc_file)
        
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
    """Load transmit list for the current DBC context."""
    try:
        json_path = get_transmit_list_path(dbc_file)
        
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
        signals_dict = json.loads(signals)

        resolved_message = backend._find_effective_message_by_name(message_name)
        if not resolved_message:
            raise KeyError(message_name)

        _, message = resolved_message
        
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
    # Store the current event loop so the receive thread can schedule async tasks
    if backend.loop is None:
        backend.loop = asyncio.get_event_loop()
    
    await backend.add_websocket_connection(websocket)

    # Inform the new client of the current CAN connection state so it can
    # render the correct UI immediately (e.g. during an ongoing reconnect).
    try:
        await websocket.send_json(backend._build_connection_status_payload())
    except Exception:
        pass

    try:
        while True:
            # Keep connection alive and handle any client messages
            data = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=backend.websocket_idle_timeout_seconds,
            )
            backend.touch_websocket_connection(websocket)
            # Echo back for heartbeat
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now().isoformat()})
    except asyncio.TimeoutError:
        print(
            f"[WS] Closing idle WebSocket after "
            f"{backend.websocket_idle_timeout_seconds:.0f}s without client activity"
        )
        backend.remove_websocket_connection(websocket)
        try:
            await websocket.close(code=1001, reason="client heartbeat timeout")
        except Exception:
            pass
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
    
    # Set the event loop for the backend so messages can be broadcast
    # even before the first WebSocket connection
    backend.loop = asyncio.get_running_loop()
    print("[OK] Event loop initialized for CAN message broadcasting")
    backend.start_health_monitor()

    try:
        backend.load_dbc_config()
        status = backend.get_dbc_status()
        print(
            f"[OK] Loaded DBC config: {len(status['files'])} file(s), "
            f"{status['active_count']} active, effective={status['filename']}"
        )
    except Exception as e:
        print(f"[ERROR] Error loading DBC config: {e}")
    
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler - ensures clean disconnection"""
    print("\n" + "=" * 60)
    print("SHUTTING DOWN SERVER")
    print("=" * 60)
    
    await backend.shutdown()
    
    print("[Shutdown] Backend stopped")
    print("=" * 60)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the backend server"""
    # Note: reload=False for stability when launched from start.py
    # For development, run directly: python api.py --reload
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
    args = parser.parse_args()
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
