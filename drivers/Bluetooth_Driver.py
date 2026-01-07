"""
Bluetooth CAN Driver for Windows
================================
Native Windows Bluetooth SPP driver using socket.AF_BLUETOOTH.
Connects to TREVCAN-Explorer-Server via Bluetooth RFCOMM.

Requirements:
    - Windows 10/11 with Bluetooth
    - Python 3.9+ (native Bluetooth socket support)
    - Device must be paired first via Windows Bluetooth settings

Author: GitHub Copilot
Date: January 2026
"""

import socket
import json
import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable, List, Dict, Any
import subprocess
import re

# Check if Bluetooth sockets are available
BLUETOOTH_AVAILABLE = False
try:
    # Test if AF_BLUETOOTH is available (Windows 10/11 with Python 3.9+)
    test_socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, 3)
    test_socket.close()
    BLUETOOTH_AVAILABLE = True
except (AttributeError, OSError):
    pass


@dataclass
class CANMessage:
    """CAN message structure matching the main driver interface."""
    timestamp: float
    arbitration_id: int
    is_extended_id: bool
    is_remote_frame: bool
    dlc: int
    data: bytes
    channel: str = "bluetooth"
    server_decoded: Optional[Dict[str, Any]] = None  # Decoded data from server


def get_paired_bluetooth_devices() -> List[Dict[str, str]]:
    """
    Get list of paired Bluetooth devices from Windows.
    Uses PowerShell to query the registry for paired devices.
    
    Returns:
        List of dicts with 'name' and 'address' keys
    """
    devices = []
    
    try:
        # PowerShell command to get paired Bluetooth devices
        ps_cmd = '''
        Get-ChildItem -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\BTHPORT\\Parameters\\Devices" -ErrorAction SilentlyContinue | ForEach-Object {
            $addr = $_.PSChildName
            $name = (Get-ItemProperty -Path $_.PSPath -Name "Name" -ErrorAction SilentlyContinue).Name
            if ($name) {
                # Convert name from byte array to string
                $nameStr = [System.Text.Encoding]::UTF8.GetString($name).TrimEnd([char]0)
                # Format address with colons
                $formattedAddr = ($addr -replace '(.{2})', '$1:').TrimEnd(':')
                Write-Output "$formattedAddr|$nameStr"
            }
        }
        '''
        
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        for line in result.stdout.strip().split('\n'):
            if '|' in line:
                addr, name = line.strip().split('|', 1)
                if addr and name:
                    devices.append({
                        'address': addr.upper(),
                        'name': name
                    })
                    
    except Exception as e:
        print(f"[Bluetooth] Error getting paired devices: {e}")
    
    return devices


class BluetoothCANDriver:
    """
    Bluetooth CAN driver using native Windows Bluetooth sockets.
    Connects to TREVCAN-Explorer-Server via RFCOMM.
    """
    
    # Bluetooth RFCOMM protocol number
    BTPROTO_RFCOMM = 3
    
    def __init__(self):
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._receive_thread: Optional[threading.Thread] = None
        self._stop_receive = False
        self._message_callback: Optional[Callable[[CANMessage], None]] = None
        self._response_buffer = ""
        self._pending_responses: List[dict] = []
        self._response_lock = threading.Lock()
        self._address = ""
        self._channel = 1
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @staticmethod
    def list_devices() -> List[Dict[str, str]]:
        """Get list of paired Bluetooth devices."""
        return get_paired_bluetooth_devices()
    
    def connect(self, address: str, channel: int = 1, timeout: float = 10.0) -> bool:
        """
        Connect to Bluetooth CAN server.
        
        Args:
            address: Bluetooth MAC address (XX:XX:XX:XX:XX:XX)
            channel: RFCOMM channel (default 1)
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected successfully
        """
        if self._connected:
            print("[Bluetooth] Already connected")
            return True
        
        if not BLUETOOTH_AVAILABLE:
            print("[Bluetooth] Native Bluetooth sockets not available")
            print("[Bluetooth] Requires Windows 10/11 with Python 3.9+")
            return False
        
        # Validate and normalize address format
        address = address.strip().upper()
        if not re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', address):
            print(f"[Bluetooth] Invalid address format: {address}")
            print("[Bluetooth] Expected format: XX:XX:XX:XX:XX:XX")
            return False
        
        self._address = address
        self._channel = channel
        
        try:
            print(f"[Bluetooth] Connecting to {address} channel {channel}...")
            
            # Create Bluetooth RFCOMM socket
            self._socket = socket.socket(
                socket.AF_BLUETOOTH,
                socket.SOCK_STREAM,
                self.BTPROTO_RFCOMM
            )
            self._socket.settimeout(timeout)
            self._socket.connect((address, channel))
            
            self._connected = True
            self._stop_receive = False
            
            # Start receive thread
            self._receive_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True,
                name="BluetoothReceive"
            )
            self._receive_thread.start()
            
            # Socket connected successfully - we're good
            print(f"[Bluetooth] Connected to {address}")
            
            return True
                
        except OSError as e:
            error_msgs = {
                10061: "Connection refused - is the server running?",
                10060: "Connection timed out - is device in range and paired?",
                10050: "Bluetooth adapter not available",
                10051: "Network unreachable - check Bluetooth is enabled",
            }
            msg = error_msgs.get(e.errno, str(e))
            print(f"[Bluetooth] Connection failed: {msg}")
            self._socket = None
            return False
        except Exception as e:
            print(f"[Bluetooth] Connection failed: {e}")
            if self._socket:
                try:
                    self._socket.close()
                except:
                    pass
            self._socket = None
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from server."""
        if not self._connected:
            return True
        
        print("[Bluetooth] Disconnecting...")
        
        # Try to unsubscribe first
        try:
            self._send_command("unsubscribe", timeout=1.0)
        except:
            pass
        
        self._stop_receive = True
        self._connected = False
        
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        
        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=2.0)
        
        print("[Bluetooth] Disconnected")
        return True
    
    def stop_receive_thread(self) -> bool:
        """
        Stop the background receive thread.
        Required for API compatibility with other drivers.
        
        Returns:
            True if thread stopped successfully, False otherwise.
        """
        if not self._receive_thread or not self._receive_thread.is_alive():
            return False
        
        self._stop_receive = True
        self._receive_thread.join(timeout=2.0)
        
        if self._receive_thread.is_alive():
            print("[Bluetooth] Warning: Receive thread did not stop cleanly")
            return False
        
        self._receive_thread = None
        self._message_callback = None
        print("[Bluetooth] Receive thread stopped")
        return True
    
    def __del__(self):
        """Destructor to ensure cleanup on garbage collection."""
        try:
            if self._connected:
                self.disconnect()
        except:
            pass
    
    def _receive_loop(self):
        """Background thread to receive data from server."""
        while not self._stop_receive and self._connected:
            try:
                self._socket.settimeout(0.5)
                data = self._socket.recv(8192)
                
                if not data:
                    break
                
                self._response_buffer += data.decode('utf-8', errors='ignore')
                
                # Process complete lines
                while '\n' in self._response_buffer:
                    line, self._response_buffer = self._response_buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self._handle_response(line)
                        
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop_receive:
                    print(f"[Bluetooth] Receive error: {e}")
                break
        
        if self._connected:
            self._connected = False
            print("[Bluetooth] Connection lost")
    
    def _handle_response(self, line: str):
        """Handle a received JSON response line."""
        try:
            response = json.loads(line)
            
            # Check if this is a streaming message event
            if response.get("event") == "messages":
                msg_count = response.get("count", len(response.get("messages", [])))
                if msg_count > 0:
                    print(f"[Bluetooth] Received {msg_count} streaming messages")
                self._process_messages(response.get("messages", []))
            else:
                # Regular command response
                with self._response_lock:
                    self._pending_responses.append(response)
                    
        except json.JSONDecodeError:
            print(f"[Bluetooth] Invalid JSON received: {line[:100]}")
    
    def _process_messages(self, messages: List[dict]):
        """Process received CAN messages and call callback."""
        if not self._message_callback:
            return
        
        for msg_data in messages:
            try:
                can_msg = self._parse_message(msg_data)
                if can_msg:
                    self._message_callback(can_msg)
            except Exception as e:
                print(f"[Bluetooth] Error processing message: {e}")
    
    def _parse_message(self, msg_data: dict) -> Optional[CANMessage]:
        """Parse server message format into CANMessage."""
        try:
            # Parse ID
            arb_id = msg_data.get("id", 0)
            if isinstance(arb_id, str):
                arb_id = int(arb_id, 16) if arb_id.startswith("0x") else int(arb_id)
            
            # Parse data
            data_hex = msg_data.get("data_hex", "") or msg_data.get("data", "")
            if isinstance(data_hex, str):
                data_hex = data_hex.replace(" ", "")
                data = bytes.fromhex(data_hex) if data_hex else b''
            elif isinstance(data_hex, list):
                data = bytes(data_hex)
            else:
                data = b''
            
            # Build decoded info dict if present
            server_decoded = None
            if msg_data.get("message_name") or msg_data.get("signals"):
                server_decoded = {
                    "message_name": msg_data.get("message_name", "Unknown"),
                    "signals": msg_data.get("signals", {})
                }
            
            return CANMessage(
                timestamp=msg_data.get("timestamp", time.time()),
                arbitration_id=arb_id,
                is_extended_id=msg_data.get("is_extended", arb_id > 0x7FF),
                is_remote_frame=msg_data.get("is_remote", False),
                dlc=len(data),
                data=data,
                channel="bluetooth",
                server_decoded=server_decoded
            )
        except Exception as e:
            print(f"[Bluetooth] Parse error: {e}")
            return None
    
    def _send_command(self, cmd: str, params: dict = None, timeout: float = 5.0) -> dict:
        """Send command to server and wait for response."""
        if not self._connected or not self._socket:
            return {"success": False, "error": "Not connected"}
        
        command = {"cmd": cmd}
        if params:
            command["params"] = params
        
        # Clear pending responses
        with self._response_lock:
            self._pending_responses.clear()
        
        try:
            message = json.dumps(command) + '\n'
            self._socket.send(message.encode('utf-8'))
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        # Wait for response
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._response_lock:
                if self._pending_responses:
                    return self._pending_responses.pop(0)
            time.sleep(0.01)
        
        return {"success": False, "error": "Timeout waiting for response"}
    
    def send_message(self, arbitration_id: int, data: bytes, 
                     is_extended: bool = False, is_remote: bool = False) -> bool:
        """
        Send a CAN message via the server.
        
        Args:
            arbitration_id: CAN message ID
            data: Message data bytes
            is_extended: Extended ID flag
            is_remote: Remote frame flag
            
        Returns:
            True if sent successfully
        """
        if not self._connected:
            return False
        
        params = {
            "id": arbitration_id,
            "data": list(data),
            "extended": is_extended,
            "remote": is_remote
        }
        
        response = self._send_command("send_message", params, timeout=2.0)
        return response.get("success", False)
    
    def start_receive_thread(self, callback: Callable[[CANMessage], None]) -> bool:
        """
        Start receiving messages with callback.
        The receive thread is already running after connect(),
        this sets the callback and subscribes to message stream.
        """
        self._message_callback = callback
        
        # Now that callback is set, subscribe to message stream
        if self._connected:
            try:
                sub_response = self._send_command("subscribe", timeout=3.0)
                if sub_response.get("success"):
                    print("[Bluetooth] Subscribed to message stream")
                else:
                    print(f"[Bluetooth] Subscribe response: {sub_response}")
            except Exception as e:
                print(f"[Bluetooth] Subscribe error: {e}")
        
        return self._connected
    
    def upload_dbc(self, dbc_path: str) -> bool:
        """
        Upload DBC file content to server for decoding.
        
        Args:
            dbc_path: Path to DBC file
            
        Returns:
            True if uploaded successfully
        """
        if not self._connected:
            return False
        
        try:
            with open(dbc_path, 'r', encoding='utf-8', errors='ignore') as f:
                dbc_content = f.read()
            
            response = self._send_command("load_dbc", {
                "filename": dbc_path.split('/')[-1].split('\\')[-1],
                "content": dbc_content
            }, timeout=10.0)
            
            if response.get("success"):
                print(f"[Bluetooth] DBC uploaded: {dbc_path}")
                return True
            else:
                print(f"[Bluetooth] DBC upload failed: {response.get('error', 'Unknown')}")
                return False
                
        except Exception as e:
            print(f"[Bluetooth] DBC upload error: {e}")
            return False
    
    def get_status(self) -> dict:
        """Get server status."""
        return self._send_command("get_status")
    
    def get_bus_status(self) -> dict:
        """
        Get the current status of the Bluetooth CAN connection.
        Required for API compatibility with other drivers.
        
        Returns:
            Dictionary containing connection status information.
        """
        if not self._connected:
            return {'connected': False, 'error': 'Not connected'}
        
        status = {
            'connected': True,
            'channel': f'bluetooth:{self._address}',
            'address': self._address,
            'rfcomm_channel': self._channel,
            'status': 'OK'
        }
        
        # Try to get server status
        try:
            server_status = self._send_command("get_status", timeout=2.0)
            if server_status.get("success"):
                status['server_status'] = server_status
        except:
            pass
        
        return status
    
    def get_messages(self, count: int = 100) -> dict:
        """Get recent messages from server buffer."""
        return self._send_command("get_messages", {"count": count})
    
    def unload_dbc(self) -> bool:
        """Unload DBC file from server."""
        if not self._connected:
            return False
        response = self._send_command("unload_dbc", timeout=3.0)
        return response.get("success", False)
    
    def clear_messages(self) -> bool:
        """Clear message buffer on server."""
        if not self._connected:
            return False
        response = self._send_command("clear_messages", timeout=3.0)
        return response.get("success", False)
    
    def send_batch(self, messages: list) -> bool:
        """Send multiple CAN messages in a batch."""
        if not self._connected:
            return False
        response = self._send_command("send_batch", {"messages": messages}, timeout=5.0)
        return response.get("success", False)
