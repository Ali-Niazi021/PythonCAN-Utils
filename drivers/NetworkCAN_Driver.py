"""
Network CAN Driver Module
=========================
A Python driver for connecting to remote CAN servers over HTTP.
This module provides a network interface to CAN bus hardware running
the TREVCAN-Explorer-Server or compatible HTTP CAN servers.

Author: GitHub Copilot
Date: December 29, 2025
"""

from dataclasses import dataclass
from typing import Optional, List, Callable, Dict, Any
import time
import threading
import requests
from enum import Enum


class NetworkCANBaudRate(Enum):
    """Standard CAN baud rates (matches server expectations)"""
    BAUD_1M = 1000000
    BAUD_800K = 800000
    BAUD_500K = 500000
    BAUD_250K = 250000
    BAUD_125K = 125000
    BAUD_100K = 100000
    BAUD_50K = 50000
    BAUD_20K = 20000
    BAUD_10K = 10000


@dataclass
class CANMessage:
    """
    Represents a CAN message with all relevant information.
    """
    id: int
    data: bytes
    timestamp: float = 0.0
    is_extended: bool = False
    is_remote: bool = False
    dlc: int = 0

    def __post_init__(self):
        if self.dlc == 0:
            self.dlc = len(self.data)


class NetworkCANDriver:
    """
    Network CAN Driver for connecting to remote CAN HTTP servers.
    
    This driver communicates with a CAN server over HTTP, allowing
    CAN bus access over a network connection.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8080):
        self._host: str = host
        self._port: int = port
        self._base_url: str = f"http://{host}:{port}"
        self._connected: bool = False
        self._receive_thread: Optional[threading.Thread] = None
        self._receive_callback: Optional[Callable[[CANMessage], None]] = None
        self._stop_receive: bool = False
        self._session: Optional[requests.Session] = None
        self._poll_interval: float = 0.05  # 50ms polling interval
        self._last_timestamp: float = 0.0
        self._server_info: Dict[str, Any] = {}
        
    def test_connection(self, timeout: float = 3.0) -> bool:
        """
        Test if the CAN server is reachable.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if server is reachable
        """
        try:
            response = requests.get(f"{self._base_url}/", timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                print(f"[NetworkCAN] Server reachable: {data.get('name', 'Unknown')}")
                return True
            else:
                print(f"[NetworkCAN] Server returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print(f"[NetworkCAN] Cannot connect to {self._base_url}")
            return False
        except requests.exceptions.Timeout:
            print(f"[NetworkCAN] Connection timed out")
            return False
        except Exception as e:
            print(f"[NetworkCAN] Error: {e}")
            return False
    
    def get_server_devices(self) -> List[Dict]:
        """
        Get list of CAN devices available on the remote server.
        
        Returns:
            List of device info dictionaries
        """
        try:
            response = requests.get(f"{self._base_url}/api/devices", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data.get('devices', [])
            return []
        except Exception as e:
            print(f"[NetworkCAN] Error getting devices: {e}")
            return []
    
    def get_server_status(self) -> Dict[str, Any]:
        """
        Get current status of the remote CAN server.
        
        Returns:
            Status dictionary
        """
        try:
            response = requests.get(f"{self._base_url}/api/status", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data.get('status', {})
            return {}
        except Exception as e:
            print(f"[NetworkCAN] Error getting status: {e}")
            return {}
    
    def connect(self, channel: int = 0, baudrate: NetworkCANBaudRate = NetworkCANBaudRate.BAUD_500K,
                auto_connect_server: bool = True) -> bool:
        """
        Connect to the remote CAN server.
        
        Args:
            channel: CAN channel on the remote server (default 0)
            baudrate: CAN baudrate
            auto_connect_server: If True, also connect the server to its CAN hardware
            
        Returns:
            True if connection successful
        """
        if self._connected:
            print("[NetworkCAN] Already connected")
            return False
        
        self._session = requests.Session()
        
        try:
            # Test server reachability
            response = self._session.get(f"{self._base_url}/", timeout=5.0)
            if response.status_code != 200:
                print(f"[NetworkCAN] Server not responding correctly")
                return False
            
            self._server_info = response.json()
            print(f"[NetworkCAN] Connected to server: {self._server_info.get('name', 'Unknown')}")
            
            # Check if server is already connected to CAN hardware
            status_response = self._session.get(f"{self._base_url}/api/status", timeout=5.0)
            if status_response.status_code == 200:
                status = status_response.json()
                if status.get('success') and status.get('status', {}).get('connected'):
                    print("[NetworkCAN] Server already connected to CAN bus")
                    self._connected = True
                    return True
            
            # Connect server to CAN hardware if requested
            if auto_connect_server:
                baudrate_name = baudrate.name if isinstance(baudrate, NetworkCANBaudRate) else baudrate
                connect_data = {
                    'channel': channel,
                    'baudrate': baudrate_name
                }
                
                connect_response = self._session.post(
                    f"{self._base_url}/api/connect",
                    json=connect_data,
                    timeout=10.0
                )
                
                if connect_response.status_code == 200:
                    result = connect_response.json()
                    if result.get('success'):
                        print(f"[NetworkCAN] Server connected to CAN bus: {result.get('message', '')}")
                        self._connected = True
                        return True
                    else:
                        print(f"[NetworkCAN] Server connect failed: {result.get('error', 'Unknown error')}")
                        return False
                else:
                    print(f"[NetworkCAN] Server connect request failed: {connect_response.status_code}")
                    return False
            
            self._connected = True
            return True
            
        except requests.exceptions.ConnectionError as e:
            print(f"[NetworkCAN] Connection error: {e}")
            return False
        except Exception as e:
            print(f"[NetworkCAN] Error: {e}")
            return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from the remote CAN server.
        
        Returns:
            True if disconnection successful
        """
        if not self._connected:
            return False
        
        self.stop_receive_thread()
        
        try:
            if self._session:
                # Optionally disconnect server from CAN hardware
                # (commented out - let server manage its own connection)
                # self._session.post(f"{self._base_url}/api/disconnect", timeout=5.0)
                self._session.close()
                self._session = None
        except Exception as e:
            print(f"[NetworkCAN] Disconnect error: {e}")
        
        self._connected = False
        self._base_url = None
        print("[NetworkCAN] Disconnected from server")
        return True
    
    def send_message(self, can_id: int, data: bytes, 
                     is_extended: bool = False, is_remote: bool = False) -> bool:
        """
        Send a CAN message through the remote server.
        
        Args:
            can_id: CAN arbitration ID
            data: Message data bytes
            is_extended: Use extended (29-bit) ID
            is_remote: Remote transmission request
            
        Returns:
            True if message sent successfully
        """
        if not self._connected or not self._session:
            print("[NetworkCAN] Not connected")
            return False
        
        try:
            # Format ID as hex string for server
            id_str = f"0x{can_id:X}"
            
            message_data = {
                'id': id_str,
                'data': list(data),
                'is_extended': is_extended
            }
            
            response = self._session.post(
                f"{self._base_url}/api/messages",
                json=message_data,
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('success', False)
            else:
                print(f"[NetworkCAN] Send failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[NetworkCAN] Send error: {e}")
            return False
    
    def _receive_loop(self):
        """Background thread for polling messages from the server."""
        print("[NetworkCAN] Receive thread started")
        error_count = 0
        max_errors = 10
        
        while not self._stop_receive and self._connected:
            try:
                # Poll for new messages
                response = self._session.get(
                    f"{self._base_url}/api/messages",
                    params={'count': 100},
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        messages = data.get('messages', [])
                        
                        for msg_data in messages:
                            # Skip messages we've already seen
                            timestamp = msg_data.get('timestamp', 0)
                            if timestamp <= self._last_timestamp:
                                continue
                            
                            self._last_timestamp = timestamp
                            
                            # Parse message data
                            msg_id = msg_data.get('id', 0)
                            
                            # Handle data - could be in different formats
                            raw_data = msg_data.get('data', [])
                            if isinstance(raw_data, str):
                                # Hex string format
                                raw_data = bytes.fromhex(raw_data.replace(' ', ''))
                            else:
                                raw_data = bytes(raw_data)
                            
                            # Also try data_hex if data not available
                            if not raw_data and msg_data.get('data_hex'):
                                raw_data = bytes.fromhex(msg_data['data_hex'].replace(' ', ''))
                            
                            is_extended = msg_data.get('is_extended', msg_id > 0x7FF)
                            
                            # Create CAN message
                            can_msg = CANMessage(
                                id=msg_id,
                                data=raw_data,
                                timestamp=timestamp,
                                is_extended=is_extended,
                                is_remote=msg_data.get('is_remote', False),
                                dlc=msg_data.get('dlc', len(raw_data))
                            )
                            
                            # Call callback
                            if self._receive_callback:
                                try:
                                    self._receive_callback(can_msg)
                                except Exception as e:
                                    print(f"[NetworkCAN] Callback error: {e}")
                        
                        error_count = 0  # Reset error count on success
                else:
                    error_count += 1
                    
            except requests.exceptions.Timeout:
                error_count += 1
            except requests.exceptions.ConnectionError:
                error_count += 1
                print("[NetworkCAN] Connection lost")
                if error_count >= max_errors:
                    break
            except Exception as e:
                error_count += 1
                print(f"[NetworkCAN] Receive error: {e}")
            
            if error_count >= max_errors:
                print(f"[NetworkCAN] Too many errors ({error_count}), stopping receive")
                break
            
            # Wait before next poll
            time.sleep(self._poll_interval)
        
        print("[NetworkCAN] Receive thread stopped")
    
    def start_receive_thread(self, callback: Callable[[CANMessage], None]) -> bool:
        """
        Start background thread for receiving messages.
        
        Args:
            callback: Function to call for each received message
            
        Returns:
            True if thread started successfully
        """
        if not self._connected:
            print("[NetworkCAN] Not connected")
            return False
        
        if self._receive_thread and self._receive_thread.is_alive():
            print("[NetworkCAN] Receive thread already running")
            return False
        
        self._receive_callback = callback
        self._stop_receive = False
        self._last_timestamp = time.time()  # Only get new messages from now
        
        # Clear the message buffer on the server before starting
        try:
            self._session.delete(f"{self._base_url}/api/messages", timeout=5.0)
        except:
            pass
        
        self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._receive_thread.start()
        
        return True
    
    def stop_receive_thread(self):
        """Stop the background receive thread."""
        self._stop_receive = True
        
        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=2.0)
        
        self._receive_thread = None
        self._receive_callback = None
    
    def get_bus_status(self) -> dict:
        """
        Get current bus/connection status.
        
        Returns:
            Status dictionary
        """
        if not self._connected or not self._session:
            return {'connected': False}
        
        try:
            response = self._session.get(f"{self._base_url}/api/status", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    status = data.get('status', {})
                    return {
                        'connected': True,
                        'server_connected': status.get('connected', False),
                        'mode': status.get('mode', 'unknown'),
                        'buffer_size': status.get('buffer_size', 0),
                        'interface': 'network',
                        'server_url': self._base_url
                    }
        except Exception as e:
            print(f"[NetworkCAN] Status error: {e}")
        
        return {'connected': self._connected, 'interface': 'network'}
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._connected
    
    @property
    def server_url(self) -> Optional[str]:
        """Get the current server URL."""
        return self._base_url
