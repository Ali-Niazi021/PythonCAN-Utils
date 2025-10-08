"""
PythonCAN GUI Application
=========================
A PCAN-Explorer-like application built with DearPyGUI.
Allows connection to PCAN-USB adapters, sending/receiving CAN messages.
Supports DBC file loading for automatic message decoding.
Includes integrated STM32 bootloader firmware flashing.

Author: GitHub Copilot
Date: October 8, 2025
"""

import dearpygui.dearpygui as dpg
from PCAN_Driver import PCANDriver, PCANChannel, PCANBaudRate, CANMessage
from typing import Dict, Optional, Callable
from datetime import datetime
import threading
import os
import time
from pathlib import Path

# Optional: DBC file support
try:
    import cantools
    DBC_SUPPORT = True
except ImportError:
    DBC_SUPPORT = False
    print("Warning: cantools not installed. DBC file support disabled.")
    print("Install with: pip install cantools")


# ============================================================================
# Bootloader Protocol Constants
# ============================================================================

# CAN IDs
CAN_HOST_ID = 0x701          # PC sends commands to this ID
CAN_BOOTLOADER_ID = 0x700    # Bootloader responds from this ID

# Commands
CMD_ERASE_FLASH = 0x01
CMD_WRITE_FLASH = 0x02
CMD_READ_FLASH = 0x03
CMD_JUMP_TO_APP = 0x04
CMD_GET_STATUS = 0x05
CMD_SET_ADDRESS = 0x06
CMD_WRITE_DATA = 0x07

# Responses
RESP_ACK = 0x10
RESP_NACK = 0x11
RESP_ERROR = 0x12
RESP_BUSY = 0x13
RESP_READY = 0x14
RESP_DATA = 0x15

# Error Codes
ERR_NONE = 0x00
ERR_INVALID_COMMAND = 0x01
ERR_INVALID_ADDRESS = 0x02
ERR_FLASH_ERASE_FAILED = 0x03
ERR_FLASH_WRITE_FAILED = 0x04
ERR_INVALID_DATA_LENGTH = 0x05
ERR_NO_VALID_APP = 0x06
ERR_TIMEOUT = 0x07

# Memory Configuration
APP_START_ADDRESS = 0x08008000
APP_MAX_SIZE = 224 * 1024  # 224 KB

# Timing
RESPONSE_TIMEOUT = 1.0
ERASE_TIMEOUT = 15.0
WRITE_CHUNK_SIZE = 4

ERROR_DESCRIPTIONS = {
    ERR_NONE: "No error",
    ERR_INVALID_COMMAND: "Invalid command",
    ERR_INVALID_ADDRESS: "Invalid address",
    ERR_FLASH_ERASE_FAILED: "Flash erase failed",
    ERR_FLASH_WRITE_FAILED: "Flash write failed",
    ERR_INVALID_DATA_LENGTH: "Invalid data length",
    ERR_NO_VALID_APP: "No valid application",
    ERR_TIMEOUT: "Operation timeout"
}


class PCANExplorerGUI:
    """
    Main GUI application for PCAN Explorer.
    Provides a graphical interface to interact with PCAN-USB adapters.
    """
    
    def __init__(self):
        """Initialize the GUI application."""
        self.driver = PCANDriver()
        self.is_connected = False
        self.message_data: Dict[int, dict] = {}  # Store messages by CAN ID
        self.message_lock = threading.Lock()
        
        # DBC database support
        self.dbc_database: Optional[cantools.database.Database] = None if DBC_SUPPORT else None
        self.dbc_file_path: Optional[str] = None
        
        # Flash-related variables
        self.flash_firmware_path: Optional[str] = None
        self.flash_in_progress = False
        self.flash_response_data: Optional[bytes] = None
        self.flash_response_event = threading.Event()
        
        # GUI element tags
        self.channel_combo = None
        self.baudrate_combo = None
        self.connect_button = None
        self.status_text = None
        self.message_table = None
        self.stats_text = None
        self.dbc_status_text = None
        
        # Flash tab GUI elements
        self.flash_file_text = None
        self.flash_progress_bar = None
        self.flash_status_text = None
        self.flash_log_text = None
        
        # Statistics
        self.total_messages = 0
        self.start_time = None
        
    def setup_gui(self):
        """Set up the DearPyGUI interface."""
        dpg.create_context()
        
        # Set up fonts for better readability
        with dpg.font_registry():
            default_font = dpg.add_font("C:\\Windows\\Fonts\\segoeui.ttf", 16)
            mono_font = dpg.add_font("C:\\Windows\\Fonts\\consola.ttf", 14)
        
        # Main window
        with dpg.window(label="PCAN Explorer", tag="main_window", width=1200, height=800):
            
            # Connection Panel
            with dpg.group(horizontal=True):
                dpg.add_text("Connection Settings", color=(100, 200, 255))
            
            dpg.add_separator()
            
            with dpg.group(horizontal=True):
                dpg.add_text("Channel:")
                self.channel_combo = dpg.add_combo(
                    items=[channel.name for channel in PCANChannel],
                    default_value="USB1",
                    width=150,
                    callback=self._on_channel_change
                )
                
                dpg.add_text("  Baud Rate:")
                self.baudrate_combo = dpg.add_combo(
                    items=[br.name for br in PCANBaudRate],
                    default_value="BAUD_500K",
                    width=150
                )
                
                dpg.add_text("  ")
                self.connect_button = dpg.add_button(
                    label="Connect",
                    callback=self._toggle_connection,
                    width=120,
                    height=30
                )
                
                dpg.add_text("  ")
                dpg.add_button(
                    label="Scan Devices",
                    callback=self._scan_devices,
                    width=120,
                    height=30
                )
            
            # Status Bar
            with dpg.group(horizontal=True):
                dpg.add_text("Status:")
                self.status_text = dpg.add_text(
                    "Disconnected",
                    color=(255, 100, 100)
                )
                
                dpg.add_text("     DBC:")
                self.dbc_status_text = dpg.add_text(
                    "No DBC file loaded",
                    color=(200, 200, 100)
                )
                
                dpg.add_text("     ")
                dpg.add_button(
                    label="Load DBC",
                    callback=self._load_dbc_file,
                    width=100,
                    height=25
                )
                
                if self.dbc_file_path:
                    dpg.add_button(
                        label="Clear DBC",
                        callback=self._clear_dbc_file,
                        width=100,
                        height=25
                    )
            
            dpg.add_separator()
            
            # Message Transmission Panel
            with dpg.collapsing_header(label="Send CAN Message", default_open=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("CAN ID (Hex):")
                    can_id_input = dpg.add_input_text(
                        tag="can_id_input",
                        default_value="123",
                        width=100,
                        hint="e.g., 123"
                    )
                    
                    dpg.add_text("  Data (Hex):")
                    data_input = dpg.add_input_text(
                        tag="data_input",
                        default_value="01 02 03 04 05 06 07 08",
                        width=250,
                        hint="e.g., 01 02 03 04"
                    )
                    
                    dpg.add_checkbox(
                        label="Extended ID",
                        tag="extended_checkbox",
                        default_value=False
                    )
                    
                    dpg.add_checkbox(
                        label="Remote Frame",
                        tag="remote_checkbox",
                        default_value=False
                    )
                    
                    dpg.add_button(
                        label="Send",
                        callback=self._send_message,
                        width=100,
                        height=30
                    )
            
            dpg.add_separator()
            
            # Statistics Panel
            with dpg.group(horizontal=True):
                dpg.add_text("Statistics:", color=(100, 255, 100))
                self.stats_text = dpg.add_text("Total Messages: 0 | Unique IDs: 0 | Rate: 0 msg/s")
            
            dpg.add_separator()
            
            # Message Table Controls
            with dpg.group(horizontal=True):
                dpg.add_text("Received Messages", color=(100, 200, 255))
                dpg.add_text("     ")
                dpg.add_button(
                    label="Clear Table",
                    callback=self._clear_messages,
                    width=120,
                    height=25
                )
                dpg.add_button(
                    label="Export to CSV",
                    callback=self._export_messages,
                    width=120,
                    height=25
                )
            
            # Message Table
            with dpg.table(
                tag="message_table",
                header_row=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                borders_outerH=True,
                borders_innerV=True,
                borders_innerH=True,
                borders_outerV=True,
                scrollY=True,
                height=450
            ):
                dpg.add_table_column(label="CAN ID", width_fixed=True, init_width_or_weight=100)
                dpg.add_table_column(label="Name", width_fixed=True, init_width_or_weight=120)
                dpg.add_table_column(label="Type", width_fixed=True, init_width_or_weight=60)
                dpg.add_table_column(label="DLC", width_fixed=True, init_width_or_weight=50)
                dpg.add_table_column(label="Data", width_fixed=True, init_width_or_weight=220)
                dpg.add_table_column(label="Decoded Signals", width_fixed=False, init_width_or_weight=300)
                dpg.add_table_column(label="Count", width_fixed=True, init_width_or_weight=70)
                dpg.add_table_column(label="Last Received", width_fixed=True, init_width_or_weight=120)
                dpg.add_table_column(label="Period (ms)", width_fixed=True, init_width_or_weight=90)
        
        # Set up viewport
        dpg.create_viewport(
            title="PCAN Explorer - Python CAN Utility",
            width=1220,
            height=850,
            min_width=800,
            min_height=600
        )
        
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_window", True)
        dpg.bind_font(default_font)
    
    def _on_channel_change(self, sender, app_data):
        """Handle channel selection change."""
        pass
    
    def _load_dbc_file(self):
        """Load a DBC file for message decoding."""
        if not DBC_SUPPORT:
            self._show_popup("DBC Support Not Available", 
                           "cantools library is not installed.\n\n"
                           "Install with: pip install cantools")
            return
        
        # File dialog callback
        def file_selected(sender, app_data):
            file_path = app_data['file_path_name']
            
            try:
                # Load DBC database
                self.dbc_database = cantools.database.load_file(file_path)
                self.dbc_file_path = file_path
                
                # Update status
                filename = os.path.basename(file_path)
                dpg.set_value(self.dbc_status_text, f"Loaded: {filename}")
                dpg.configure_item(self.dbc_status_text, color=(100, 255, 100))
                
                # Show success message
                num_messages = len(self.dbc_database.messages)
                self._show_popup("DBC Loaded", 
                               f"Successfully loaded DBC file:\n{filename}\n\n"
                               f"Messages defined: {num_messages}")
                
            except Exception as e:
                self._show_popup("DBC Load Failed", 
                               f"Failed to load DBC file:\n\n{str(e)}")
        
        # Show file dialog
        with dpg.file_dialog(
            directory_selector=False,
            show=True,
            callback=file_selected,
            default_filename="*.dbc",
            width=700,
            height=400
        ):
            dpg.add_file_extension(".dbc", color=(150, 255, 150, 255))
            dpg.add_file_extension(".*")
    
    def _clear_dbc_file(self):
        """Clear the loaded DBC file."""
        self.dbc_database = None
        self.dbc_file_path = None
        dpg.set_value(self.dbc_status_text, "No DBC file loaded")
        dpg.configure_item(self.dbc_status_text, color=(200, 200, 100))
    
    def _decode_message(self, can_id: int, data: bytes) -> Optional[str]:
        """
        Decode a CAN message using the loaded DBC database.
        
        Args:
            can_id: CAN message ID
            data: Raw message data bytes
            
        Returns:
            Decoded signal string or None if no DBC or message not found
        """
        if not self.dbc_database:
            return None
        
        try:
            # Find message by ID
            message = self.dbc_database.get_message_by_frame_id(can_id)
            
            # Decode the message - cantools handles endianness automatically
            decoded = message.decode(data)
            
            # Format decoded signals
            signal_strs = []
            for signal_name, value in decoded.items():
                # Get signal definition for unit info
                signal = message.get_signal_by_name(signal_name)
                unit = signal.unit if signal.unit else ""
                
                # Check if this signal has value table (enum)
                if signal.choices:
                    # Try to map the value to a choice name
                    try:
                        choice_name = signal.choices.get(int(value))
                        if choice_name:
                            signal_strs.append(f"{signal_name}: {choice_name}")
                            continue
                    except:
                        pass
                
                # Format numeric values with appropriate precision
                if isinstance(value, float):
                    # Use appropriate precision based on scale factor
                    if signal.scale >= 1.0:
                        value_str = f"{value:.1f}"
                    elif signal.scale >= 0.1:
                        value_str = f"{value:.2f}"
                    elif signal.scale >= 0.01:
                        value_str = f"{value:.2f}"
                    else:
                        value_str = f"{value:.3f}"
                elif isinstance(value, int):
                    value_str = str(value)
                else:
                    value_str = str(value)
                
                # Add unit if present
                if unit:
                    signal_strs.append(f"{signal_name}: {value_str} {unit}")
                else:
                    signal_strs.append(f"{signal_name}: {value_str}")
            
            return " | ".join(signal_strs)
            
        except (KeyError, cantools.database.errors.DecodeError):
            # Message not found in DBC or decode error
            return None
    
    def _get_message_name(self, can_id: int) -> Optional[str]:
        """
        Get message name from DBC database.
        
        Args:
            can_id: CAN message ID
            
        Returns:
            Message name or None if not found
        """
        if not self.dbc_database:
            return None
        
        try:
            message = self.dbc_database.get_message_by_frame_id(can_id)
            return message.name
        except KeyError:
            return None
    
    def _scan_devices(self):
        """Scan for available PCAN devices."""
        devices = self.driver.get_available_devices()
        
        if not devices:
            self._show_popup("No Devices Found", "No PCAN devices detected.\nPlease connect your PCAN-USB adapter.")
        else:
            device_list = "\n".join([
                f"• {dev['channel']}: {'OCCUPIED' if dev['occupied'] else 'AVAILABLE'}"
                for dev in devices
            ])
            self._show_popup("Available Devices", f"Found {len(devices)} device(s):\n\n{device_list}")
    
    def _toggle_connection(self):
        """Connect or disconnect from PCAN device."""
        if not self.is_connected:
            # Connect
            channel_name = dpg.get_value(self.channel_combo)
            baudrate_name = dpg.get_value(self.baudrate_combo)
            
            channel = PCANChannel[channel_name]
            baudrate = PCANBaudRate[baudrate_name]
            
            # Connect to PCAN device
            if self.driver.connect(channel, baudrate):
                self.is_connected = True
                self.start_time = datetime.now()
                dpg.set_item_label(self.connect_button, "Disconnect")
                dpg.set_value(self.status_text, f"Connected to {channel_name} at {baudrate_name}")
                dpg.configure_item(self.status_text, color=(100, 255, 100))
                
                # Start receiving messages
                self.driver.start_receive_thread(self._on_message_received)
                
                # Disable channel/baudrate selection
                dpg.configure_item(self.channel_combo, enabled=False)
                dpg.configure_item(self.baudrate_combo, enabled=False)
            else:
                self._show_popup("Connection Failed", "Failed to connect to PCAN device.\nPlease check device and try again.")
        else:
            # Disconnect
            self.driver.disconnect()
            self.is_connected = False
            dpg.set_item_label(self.connect_button, "Connect")
            dpg.set_value(self.status_text, "Disconnected")
            dpg.configure_item(self.status_text, color=(255, 100, 100))
            
            # Enable channel/baudrate selection
            dpg.configure_item(self.channel_combo, enabled=True)
            dpg.configure_item(self.baudrate_combo, enabled=True)
    
    def _on_message_received(self, msg: CANMessage):
        """
        Callback for received CAN messages.
        Updates the message table with new messages or increments counter for existing IDs.
        """
        with self.message_lock:
            self.total_messages += 1
            current_time = datetime.now()
            
            # Try to decode message using DBC
            decoded_signals = self._decode_message(msg.id, msg.data)
            message_name = self._get_message_name(msg.id)
            
            if msg.id in self.message_data:
                # Message ID already exists - update it
                data = self.message_data[msg.id]
                data['count'] += 1
                
                # Calculate period (time between messages)
                if data['last_time']:
                    period_ms = (current_time - data['last_time']).total_seconds() * 1000
                    data['period_ms'] = round(period_ms, 1)
                
                data['last_time'] = current_time
                data['last_timestamp'] = current_time.strftime("%H:%M:%S.%f")[:-3]
                data['data'] = msg.data  # Update with latest data
                data['dlc'] = msg.dlc
                data['decoded'] = decoded_signals
                data['name'] = message_name if message_name else ""
                
            else:
                # New message ID
                msg_type = "EXT" if msg.is_extended else "STD"
                if msg.is_remote:
                    msg_type += "-R"
                
                self.message_data[msg.id] = {
                    'id': msg.id,
                    'name': message_name if message_name else "",
                    'type': msg_type,
                    'dlc': msg.dlc,
                    'data': msg.data,
                    'decoded': decoded_signals,
                    'count': 1,
                    'last_timestamp': current_time.strftime("%H:%M:%S.%f")[:-3],
                    'last_time': current_time,
                    'period_ms': 0.0,
                    'row_tag': None
                }
            
            # Update GUI (must be done in main thread, so we'll do it in update loop)
    
    def _update_message_table(self):
        """Update the message table with current data."""
        with self.message_lock:
            # Get all existing rows
            existing_rows = dpg.get_item_children("message_table", slot=1)
            
            # Update or create rows for each message
            for can_id, data in sorted(self.message_data.items()):
                data_hex = ' '.join([f'{b:02X}' for b in data['data']])
                decoded_str = data.get('decoded', '') or ''
                message_name = data.get('name', '') or ''
                
                if data['row_tag'] is None or data['row_tag'] not in existing_rows:
                    # Create new row
                    with dpg.table_row(parent="message_table") as row_tag:
                        dpg.add_text(f"0x{data['id']:X}", tag=f"id_{can_id}")
                        dpg.add_text(message_name, tag=f"name_{can_id}")
                        dpg.add_text(data['type'], tag=f"type_{can_id}")
                        dpg.add_text(str(data['dlc']), tag=f"dlc_{can_id}")
                        dpg.add_text(data_hex, tag=f"data_{can_id}")
                        dpg.add_text(decoded_str, tag=f"decoded_{can_id}", wrap=300)
                        dpg.add_text(str(data['count']), tag=f"count_{can_id}")
                        dpg.add_text(data['last_timestamp'], tag=f"time_{can_id}")
                        dpg.add_text(f"{data['period_ms']:.1f}", tag=f"period_{can_id}")
                        data['row_tag'] = row_tag
                else:
                    # Update existing row
                    dpg.set_value(f"name_{can_id}", message_name)
                    dpg.set_value(f"type_{can_id}", data['type'])
                    dpg.set_value(f"dlc_{can_id}", str(data['dlc']))
                    dpg.set_value(f"data_{can_id}", data_hex)
                    dpg.set_value(f"decoded_{can_id}", decoded_str)
                    dpg.set_value(f"count_{can_id}", str(data['count']))
                    dpg.set_value(f"time_{can_id}", data['last_timestamp'])
                    dpg.set_value(f"period_{can_id}", f"{data['period_ms']:.1f}")
            
            # Update statistics
            unique_ids = len(self.message_data)
            if self.start_time:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                rate = self.total_messages / elapsed if elapsed > 0 else 0
                dpg.set_value(
                    self.stats_text,
                    f"Total Messages: {self.total_messages} | Unique IDs: {unique_ids} | Rate: {rate:.1f} msg/s"
                )
    
    def _send_message(self):
        """Send a CAN message."""
        if not self.is_connected:
            self._show_popup("Not Connected", "Please connect to a PCAN device first.")
            return
        
        try:
            # Get CAN ID
            can_id_str = dpg.get_value("can_id_input").strip()
            can_id = int(can_id_str, 16)
            
            # Get data bytes
            data_str = dpg.get_value("data_input").strip()
            data_bytes = bytes.fromhex(data_str.replace(" ", ""))
            
            # Get flags
            is_extended = dpg.get_value("extended_checkbox")
            is_remote = dpg.get_value("remote_checkbox")
            
            # Send message
            if self.driver.send_message(can_id, data_bytes, is_extended, is_remote):
                # Visual feedback - briefly change button color or show success
                pass
            else:
                self._show_popup("Send Failed", "Failed to send CAN message.")
                
        except ValueError as e:
            self._show_popup("Invalid Input", f"Invalid CAN ID or data format.\n\nError: {str(e)}")
        except Exception as e:
            self._show_popup("Error", f"An error occurred:\n\n{str(e)}")
    
    def _clear_messages(self):
        """Clear the message table."""
        with self.message_lock:
            self.message_data.clear()
            self.total_messages = 0
            self.start_time = datetime.now()
            
            # Clear table
            children = dpg.get_item_children("message_table", slot=1)
            for child in children:
                dpg.delete_item(child)
            
            # Reset statistics
            dpg.set_value(self.stats_text, "Total Messages: 0 | Unique IDs: 0 | Rate: 0 msg/s")
    
    def _export_messages(self):
        """Export messages to CSV file."""
        if not self.message_data:
            self._show_popup("No Data", "No messages to export.")
            return
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"can_messages_{timestamp}.csv"
            
            with open(filename, 'w') as f:
                # Write header
                f.write("CAN_ID,Message_Name,Type,DLC,Data,Decoded_Signals,Count,Last_Received,Period_ms\n")
                
                # Write data
                with self.message_lock:
                    for can_id, data in sorted(self.message_data.items()):
                        data_hex = ''.join([f'{b:02X}' for b in data['data']])
                        message_name = data.get('name', '')
                        decoded = data.get('decoded', '') or ''
                        # Escape any commas in decoded signals
                        decoded = decoded.replace(',', ';')
                        
                        f.write(f"0x{data['id']:X},{message_name},{data['type']},{data['dlc']},{data_hex},"
                               f"\"{decoded}\",{data['count']},{data['last_timestamp']},{data['period_ms']:.1f}\n")
            
            self._show_popup("Export Success", f"Messages exported to:\n{filename}")
            
        except Exception as e:
            self._show_popup("Export Failed", f"Failed to export messages:\n\n{str(e)}")
    
    def _show_popup(self, title: str, message: str):
        """Show a popup message."""
        with dpg.window(label=title, modal=True, show=True, tag=f"popup_{id(message)}", 
                       pos=[400, 300], width=400, height=200):
            dpg.add_text(message)
            dpg.add_separator()
            dpg.add_button(
                label="OK",
                width=100,
                callback=lambda: dpg.delete_item(f"popup_{id(message)}")
            )
    
    def run(self):
        """Run the GUI application."""
        self.setup_gui()
        
        # Main render loop
        while dpg.is_dearpygui_running():
            # Update message table
            if self.is_connected:
                self._update_message_table()
            
            dpg.render_dearpygui_frame()
        
        # Cleanup
        if self.is_connected:
            self.driver.disconnect()
        
        dpg.destroy_context()


def main():
    """Main entry point."""
    app = PCANExplorerGUI()
    app.run()


if __name__ == "__main__":
    main()
