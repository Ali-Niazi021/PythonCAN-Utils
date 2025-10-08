"""
PythonCAN GUI Application with Integrated Firmware Flasher
==========================================================
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
CAN_HOST_ID = 0x701
CAN_BOOTLOADER_ID = 0x700

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
    Main GUI application for PCAN Explorer with integrated firmware flasher.
    """
    
    def __init__(self):
        """Initialize the GUI application."""
        self.driver = PCANDriver()
        self.is_connected = False
        self.message_data: Dict[int, dict] = {}
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
        self.flash_log = []
        
        # Thermistor monitoring
        self.thermistor_temps = [None] * 8  # Store latest temps for channels 0-7
        self.thermistor_text_tags = []  # GUI text element tags
        self.thermistor_adc_tags = []   # ADC value text tags
        
        # Statistics
        self.total_messages = 0
        self.start_time = None
        
    def setup_gui(self):
        """Set up the DearPyGUI interface with tabs."""
        dpg.create_context()
        
        # Set up fonts
        with dpg.font_registry():
            default_font = dpg.add_font("C:\\Windows\\Fonts\\segoeui.ttf", 16)
            mono_font = dpg.add_font("C:\\Windows\\Fonts\\consola.ttf", 14)
        
        # Main window
        with dpg.window(label="PCAN Explorer & Flasher", tag="main_window", width=1250, height=850):
            
            # Connection Panel (always visible)
            with dpg.group(horizontal=True):
                dpg.add_text("Connection Settings", color=(100, 200, 255))
            
            dpg.add_separator()
            
            with dpg.group(horizontal=True):
                dpg.add_text("Channel:")
                self.channel_combo = dpg.add_combo(
                    items=[channel.name for channel in PCANChannel],
                    default_value="USB1",
                    width=120
                )
                
                dpg.add_text(" Baud:")
                self.baudrate_combo = dpg.add_combo(
                    items=[br.name for br in PCANBaudRate],
                    default_value="BAUD_500K",
                    width=130
                )
                
                dpg.add_text(" ")
                self.connect_button = dpg.add_button(
                    label="Connect",
                    callback=self._toggle_connection,
                    width=100,
                    height=28
                )
                
                dpg.add_text(" ")
                self.status_text = dpg.add_text("Disconnected", color=(255, 100, 100))
            
            dpg.add_separator()
            
            # Tab Bar
            with dpg.tab_bar():
                
                # ===== CAN EXPLORER TAB =====
                with dpg.tab(label="CAN Explorer"):
                    self._setup_explorer_tab()
                
                # ===== THERMISTOR MONITOR TAB =====
                with dpg.tab(label="Thermistor Monitor"):
                    self._setup_thermistor_tab()
                
                # ===== FIRMWARE FLASHER TAB =====
                with dpg.tab(label="Firmware Flasher"):
                    self._setup_flasher_tab()
        
        # Setup viewport
        dpg.create_viewport(
            title="PCAN Explorer & STM32 Flasher",
            width=1270,
            height=900,
            min_width=900,
            min_height=600
        )
        
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_window", True)
        dpg.bind_font(default_font)
    
    def _setup_explorer_tab(self):
        """Setup the CAN Explorer tab content."""
        # DBC Status
        with dpg.group(horizontal=True):
            dpg.add_text("DBC File:")
            self.dbc_status_text = dpg.add_text("No DBC loaded", color=(200, 200, 100))
            dpg.add_text("  ")
            dpg.add_button(label="Load DBC", callback=self._load_dbc_file, width=100, height=25)
        
        dpg.add_separator()
        
        # Send Message Panel
        with dpg.collapsing_header(label="Send CAN Message", default_open=True):
            with dpg.group(horizontal=True):
                dpg.add_text("ID (Hex):")
                dpg.add_input_text(tag="can_id_input", default_value="123", width=90)
                
                dpg.add_text(" Data (Hex):")
                dpg.add_input_text(tag="data_input", default_value="01 02 03 04", width=220)
                
                dpg.add_checkbox(label="Ext", tag="extended_checkbox", default_value=False)
                dpg.add_checkbox(label="RTR", tag="remote_checkbox", default_value=False)
                
                dpg.add_button(label="Send", callback=self._send_message, width=80, height=28)
        
        dpg.add_separator()
        
        # Statistics
        with dpg.group(horizontal=True):
            dpg.add_text("Statistics:", color=(100, 255, 100))
            self.stats_text = dpg.add_text("Total: 0 | Unique IDs: 0 | Rate: 0 msg/s")
        
        dpg.add_separator()
        
        # Message Table Controls
        with dpg.group(horizontal=True):
            dpg.add_text("Received Messages", color=(100, 200, 255))
            dpg.add_text("     ")
            dpg.add_button(label="Clear", callback=self._clear_messages, width=80, height=25)
            dpg.add_button(label="Export CSV", callback=self._export_messages, width=100, height=25)
        
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
            height=500
        ):
            dpg.add_table_column(label="CAN ID", width_fixed=True, init_width_or_weight=90)
            dpg.add_table_column(label="Name", width_fixed=True, init_width_or_weight=110)
            dpg.add_table_column(label="Type", width_fixed=True, init_width_or_weight=50)
            dpg.add_table_column(label="DLC", width_fixed=True, init_width_or_weight=45)
            dpg.add_table_column(label="Data", width_fixed=True, init_width_or_weight=200)
            dpg.add_table_column(label="Decoded Signals", width_fixed=False, init_width_or_weight=250)
            dpg.add_table_column(label="Count", width_fixed=True, init_width_or_weight=60)
            dpg.add_table_column(label="Last RX", width_fixed=True, init_width_or_weight=110)
            dpg.add_table_column(label="Period", width_fixed=True, init_width_or_weight=70)
    
    def _setup_thermistor_tab(self):
        """Setup the Thermistor Monitor tab content."""
        dpg.add_text("8-Channel Thermistor Temperature Monitor", color=(100, 255, 200))
        dpg.add_text("Displays real-time temperature readings from all 8 thermistor channels", color=(150, 150, 150))
        dpg.add_separator()
        
        # Temperature Display Grid
        dpg.add_text("Temperature Readings (0.1°C resolution):", color=(200, 200, 255))
        dpg.add_spacing(count=2)
        
        # Create 2x4 grid for 8 channels
        for row in range(2):
            with dpg.group(horizontal=True):
                for col in range(4):
                    channel = row * 4 + col
                    
                    with dpg.child_window(width=280, height=120, border=True):
                        dpg.add_text(f"Channel {channel}", color=(255, 200, 100))
                        dpg.add_separator()
                        
                        # Temperature value (large text)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Temp:", color=(180, 180, 180))
                            temp_tag = f"therm_temp_{channel}"
                            dpg.add_text("---.-- °C", tag=temp_tag, color=(100, 255, 100))
                            self.thermistor_text_tags.append(temp_tag)
                        
                        # ADC raw value
                        with dpg.group(horizontal=True):
                            dpg.add_text("ADC:", color=(180, 180, 180))
                            adc_tag = f"therm_adc_{channel}"
                            dpg.add_text("---- counts", tag=adc_tag, color=(150, 150, 255))
                            self.thermistor_adc_tags.append(adc_tag)
                        
                        # Status/age indicator
                        dpg.add_text("Last: Never", tag=f"therm_time_{channel}", color=(150, 150, 150))
        
        dpg.add_separator()
        dpg.add_spacing(count=2)
        
        # Statistics and controls
        with dpg.group(horizontal=True):
            dpg.add_text("Statistics:", color=(100, 200, 255))
            dpg.add_text("Active Channels: 0/8 | Min: --°C | Max: --°C | Avg: --°C", 
                        tag="therm_stats", color=(200, 200, 200))
        
        dpg.add_spacing(count=2)
        
        # Control buttons
        with dpg.group(horizontal=True):
            dpg.add_button(label="Clear History", callback=self._clear_thermistor_data, width=120, height=30)
            dpg.add_button(label="Export Temps CSV", callback=self._export_thermistor_data, width=140, height=30)
            dpg.add_checkbox(label="Auto-scroll", tag="therm_autoscroll", default_value=True)
        
        dpg.add_separator()
        dpg.add_text("Note: Temperature data comes from CAN messages 0x710-0x713 (Thermistor_Pair_0 through Thermistor_Pair_3)", 
                    color=(150, 150, 150), wrap=1150)
    
    def _setup_flasher_tab(self):
        """Setup the Firmware Flasher tab content."""
        dpg.add_text("STM32L432 CAN Bootloader Firmware Flasher", color=(255, 200, 100))
        dpg.add_separator()
        
        # File Selection
        with dpg.group(horizontal=True):
            dpg.add_text("Firmware File:")
            self.flash_file_text = dpg.add_text("No file selected", color=(200, 200, 200))
            dpg.add_text("  ")
            dpg.add_button(label="Browse...", callback=self._select_firmware_file, width=100, height=28)
        
        dpg.add_separator()
        
        # Flash Controls
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Erase Flash",
                callback=self._flash_erase,
                width=120,
                height=35,
                tag="erase_button"
            )
            dpg.add_button(
                label="Flash Firmware",
                callback=self._flash_firmware,
                width=140,
                height=35,
                tag="flash_button"
            )
            dpg.add_button(
                label="Verify Flash",
                callback=self._flash_verify,
                width=120,
                height=35,
                tag="verify_button"
            )
            dpg.add_button(
                label="Jump to App",
                callback=self._flash_jump,
                width=120,
                height=35,
                tag="jump_button"
            )
        
        dpg.add_separator()
        
        # Progress Bar
        with dpg.group():
            dpg.add_text("Progress:")
            self.flash_progress_bar = dpg.add_progress_bar(default_value=0.0, width=-1, height=25)
            self.flash_status_text = dpg.add_text("Ready", color=(200, 200, 200))
        
        dpg.add_separator()
        
        # Flash Log
        dpg.add_text("Flash Log:", color=(100, 255, 100))
        with dpg.child_window(border=True, height=450, tag="flash_log_window"):
            dpg.add_text("Ready to flash firmware...", tag="flash_log_text", wrap=1150)
    
    # ============================================================================
    # Connection Methods
    # ============================================================================
    
    def _toggle_connection(self):
        """Connect or disconnect from PCAN device."""
        if not self.is_connected:
            channel_name = dpg.get_value(self.channel_combo)
            baudrate_name = dpg.get_value(self.baudrate_combo)
            
            channel = PCANChannel[channel_name]
            baudrate = PCANBaudRate[baudrate_name]
            
            # Connect to PCAN device
            if self.driver.connect(channel, baudrate):
                self.is_connected = True
                self.start_time = datetime.now()
                dpg.set_item_label(self.connect_button, "Disconnect")
                dpg.set_value(self.status_text, f"Connected: {channel_name} @ {baudrate_name}")
                dpg.configure_item(self.status_text, color=(100, 255, 100))
                
                # Start receiving messages
                self.driver.start_receive_thread(self._on_message_received)
                
                # Disable controls
                dpg.configure_item(self.channel_combo, enabled=False)
                dpg.configure_item(self.baudrate_combo, enabled=False)
            else:
                self._show_popup("Connection Failed", "Failed to connect to PCAN device.")
        else:
            # Disconnect
            self.driver.disconnect()
            self.is_connected = False
            dpg.set_item_label(self.connect_button, "Connect")
            dpg.set_value(self.status_text, "Disconnected")
            dpg.configure_item(self.status_text, color=(255, 100, 100))
            
            # Enable controls
            dpg.configure_item(self.channel_combo, enabled=True)
            dpg.configure_item(self.baudrate_combo, enabled=True)
    
    # ============================================================================
    # CAN Explorer Methods
    # ============================================================================
    
    def _load_dbc_file(self):
        """Load a DBC file."""
        if not DBC_SUPPORT:
            self._show_popup("DBC Not Available", "cantools library not installed.")
            return
        
        def file_selected(sender, app_data):
            file_path = app_data['file_path_name']
            try:
                self.dbc_database = cantools.database.load_file(file_path)
                self.dbc_file_path = file_path
                filename = os.path.basename(file_path)
                dpg.set_value(self.dbc_status_text, f"Loaded: {filename}")
                dpg.configure_item(self.dbc_status_text, color=(100, 255, 100))
            except Exception as e:
                self._show_popup("DBC Load Failed", f"Error: {str(e)}")
        
        with dpg.file_dialog(directory_selector=False, show=True, callback=file_selected,
                           default_filename="*.dbc", width=700, height=400):
            dpg.add_file_extension(".dbc", color=(150, 255, 150, 255))
    
    def _decode_message(self, can_id: int, data: bytes) -> Optional[str]:
        """Decode CAN message using DBC."""
        if not self.dbc_database:
            return None
        try:
            message = self.dbc_database.get_message_by_frame_id(can_id)
            decoded = message.decode(data)
            signal_strs = []
            
            for signal_name, value in decoded.items():
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
                
                # Format numeric values
                if isinstance(value, float):
                    # Use appropriate precision based on scale
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
        except Exception as e:
            # Return None if decode fails (message not in DBC or decode error)
            return None
    
    def _get_message_name(self, can_id: int) -> Optional[str]:
        """Get message name from DBC."""
        if not self.dbc_database:
            return None
        try:
            return self.dbc_database.get_message_by_frame_id(can_id).name
        except:
            return None
    
    def _on_message_received(self, msg: CANMessage):
        """Callback for received CAN messages."""
        # Check if this is a flash response
        if self.flash_in_progress and msg.id == CAN_BOOTLOADER_ID:
            self.flash_response_data = msg.data
            self.flash_response_event.set()
        
        # Check if this is thermistor data and update display
        self._update_thermistor_data(msg.id, msg.data)
        
        # Update message table
        with self.message_lock:
            self.total_messages += 1
            current_time = datetime.now()
            
            decoded_signals = self._decode_message(msg.id, msg.data)
            message_name = self._get_message_name(msg.id)
            
            if msg.id in self.message_data:
                data = self.message_data[msg.id]
                data['count'] += 1
                if data['last_time']:
                    period_ms = (current_time - data['last_time']).total_seconds() * 1000
                    data['period_ms'] = round(period_ms, 1)
                data['last_time'] = current_time
                data['last_timestamp'] = current_time.strftime("%H:%M:%S.%f")[:-3]
                data['data'] = msg.data
                data['dlc'] = msg.dlc
                data['decoded'] = decoded_signals
                data['name'] = message_name if message_name else ""
            else:
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
    
    def _update_message_table(self):
        """Update the message table display."""
        with self.message_lock:
            existing_rows = dpg.get_item_children("message_table", slot=1)
            
            for can_id, data in sorted(self.message_data.items()):
                data_hex = ' '.join([f'{b:02X}' for b in data['data']])
                decoded_str = data.get('decoded', '') or ''
                message_name = data.get('name', '') or ''
                
                if data['row_tag'] is None or data['row_tag'] not in existing_rows:
                    with dpg.table_row(parent="message_table") as row_tag:
                        dpg.add_text(f"0x{data['id']:X}", tag=f"id_{can_id}")
                        dpg.add_text(message_name, tag=f"name_{can_id}")
                        dpg.add_text(data['type'], tag=f"type_{can_id}")
                        dpg.add_text(str(data['dlc']), tag=f"dlc_{can_id}")
                        dpg.add_text(data_hex, tag=f"data_{can_id}")
                        dpg.add_text(decoded_str, tag=f"decoded_{can_id}", wrap=250)
                        dpg.add_text(str(data['count']), tag=f"count_{can_id}")
                        dpg.add_text(data['last_timestamp'], tag=f"time_{can_id}")
                        dpg.add_text(f"{data['period_ms']:.1f}", tag=f"period_{can_id}")
                        data['row_tag'] = row_tag
                else:
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
                dpg.set_value(self.stats_text, 
                            f"Total: {self.total_messages} | Unique IDs: {unique_ids} | Rate: {rate:.1f} msg/s")
    
    def _send_message(self):
        """Send a CAN message."""
        if not self.is_connected:
            self._show_popup("Not Connected", "Please connect first.")
            return
        
        try:
            can_id_str = dpg.get_value("can_id_input").strip()
            can_id = int(can_id_str, 16)
            
            data_str = dpg.get_value("data_input").strip()
            data_bytes = bytes.fromhex(data_str.replace(" ", ""))
            
            is_extended = dpg.get_value("extended_checkbox")
            is_remote = dpg.get_value("remote_checkbox")
            
            self.driver.send_message(can_id, data_bytes, is_extended, is_remote)
        except Exception as e:
            self._show_popup("Send Failed", f"Error: {str(e)}")
    
    def _clear_messages(self):
        """Clear message table."""
        with self.message_lock:
            self.message_data.clear()
            self.total_messages = 0
            self.start_time = datetime.now()
            children = dpg.get_item_children("message_table", slot=1)
            for child in children:
                dpg.delete_item(child)
            dpg.set_value(self.stats_text, "Total: 0 | Unique IDs: 0 | Rate: 0 msg/s")
    
    def _export_messages(self):
        """Export messages to CSV."""
        if not self.message_data:
            self._show_popup("No Data", "No messages to export.")
            return
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"can_messages_{timestamp}.csv"
            
            with open(filename, 'w') as f:
                f.write("CAN_ID,Name,Type,DLC,Data,Decoded,Count,Last_RX,Period_ms\n")
                with self.message_lock:
                    for can_id, data in sorted(self.message_data.items()):
                        data_hex = ''.join([f'{b:02X}' for b in data['data']])
                        decoded = (data.get('decoded', '') or '').replace(',', ';')
                        f.write(f"0x{data['id']:X},{data.get('name','')},{data['type']},"
                              f"{data['dlc']},{data_hex},\"{decoded}\","
                              f"{data['count']},{data['last_timestamp']},{data['period_ms']:.1f}\n")
            
            self._show_popup("Export Success", f"Saved: {filename}")
        except Exception as e:
            self._show_popup("Export Failed", f"Error: {str(e)}")
    
    # ============================================================================
    # Thermistor Monitor Methods
    # ============================================================================
    
    def _update_thermistor_data(self, can_id: int, data: bytes):
        """Update thermistor display from incoming CAN messages."""
        # Use the existing DBC decoder to get signal values
        if not self.dbc_database:
            return
        
        try:
            # Decode the message using DBC
            message = self.dbc_database.get_message_by_frame_id(can_id)
            decoded = message.decode(data)
            
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Thermistor_Pair_0 (0x710/1808) - Channels 0 and 1
            if can_id == 0x710:
                if 'Temp_Ch0' in decoded:
                    self._update_single_thermistor(0, decoded['Temp_Ch0'], current_time)
                if 'Temp_Ch1' in decoded:
                    self._update_single_thermistor(1, decoded['Temp_Ch1'], current_time)
            
            # Thermistor_Pair_1 (0x711/1809) - Channels 2 and 3
            elif can_id == 0x711:
                if 'Temp_Ch2' in decoded:
                    self._update_single_thermistor(2, decoded['Temp_Ch2'], current_time)
                if 'Temp_Ch3' in decoded:
                    self._update_single_thermistor(3, decoded['Temp_Ch3'], current_time)
            
            # Thermistor_Pair_2 (0x712/1810) - Channels 4 and 5
            elif can_id == 0x712:
                if 'Temp_Ch4' in decoded:
                    self._update_single_thermistor(4, decoded['Temp_Ch4'], current_time)
                if 'Temp_Ch5' in decoded:
                    self._update_single_thermistor(5, decoded['Temp_Ch5'], current_time)
            
            # Thermistor_Pair_3 (0x713/1811) - Channels 6 and 7
            elif can_id == 0x713:
                if 'Temp_Ch6' in decoded:
                    self._update_single_thermistor(6, decoded['Temp_Ch6'], current_time)
                if 'Temp_Ch7' in decoded:
                    self._update_single_thermistor(7, decoded['Temp_Ch7'], current_time)
            
            # ADC_Raw_0_3 (0x720/1824) - Channels 0-3
            elif can_id == 0x720:
                for i in range(4):
                    adc_signal = f'ADC_Ch{i}'
                    if adc_signal in decoded and i < len(self.thermistor_adc_tags):
                        dpg.set_value(self.thermistor_adc_tags[i], f"{int(decoded[adc_signal])} counts")
            
            # ADC_Raw_4_7 (0x721/1825) - Channels 4-7
            elif can_id == 0x721:
                for i in range(4):
                    adc_signal = f'ADC_Ch{i+4}'
                    if adc_signal in decoded and (i+4) < len(self.thermistor_adc_tags):
                        dpg.set_value(self.thermistor_adc_tags[i+4], f"{int(decoded[adc_signal])} counts")
            
        except Exception as e:
            # Message not in DBC or decode error - silently ignore
            pass
    
    def _update_single_thermistor(self, channel: int, temp: float, time_str: str):
        """Update a single thermistor channel display."""
        if channel >= 8:
            return
        
        # Update stored value
        self.thermistor_temps[channel] = temp
        
        # Update GUI
        if channel < len(self.thermistor_text_tags):
            temp_color = self._get_temp_color(temp)
            dpg.set_value(self.thermistor_text_tags[channel], f"{temp:.1f} °C")
            dpg.configure_item(self.thermistor_text_tags[channel], color=temp_color)
            dpg.set_value(f"therm_time_{channel}", f"Last: {time_str}")
        
        # Update statistics
        self._update_thermistor_stats()
    
    def _decode_thermistor_pair(self, data: bytes, base_channel: int):
        """Decode a thermistor pair message and update display."""
        # REMOVED - now using DBC decoder directly
        pass
    
    def _decode_adc_values(self, data: bytes, base_channel: int):
        """Decode ADC raw values and update display."""
        # REMOVED - now using DBC decoder directly
        pass
    
    def _get_temp_color(self, temp: float):
        """Get color for temperature display based on value."""
        if temp < -50:
            return (100, 100, 255)  # Very cold - blue
        elif temp < 0:
            return (100, 200, 255)  # Cold - light blue
        elif temp < 25:
            return (100, 255, 100)  # Normal - green
        elif temp < 50:
            return (255, 255, 100)  # Warm - yellow
        elif temp < 85:
            return (255, 200, 100)  # Hot - orange
        else:
            return (255, 100, 100)  # Very hot - red
    
    def _update_thermistor_stats(self):
        """Update thermistor statistics display."""
        valid_temps = [t for t in self.thermistor_temps if t is not None]
        
        if not valid_temps:
            stats_text = "Active Channels: 0/8 | Min: --°C | Max: --°C | Avg: --°C"
        else:
            active = len(valid_temps)
            min_temp = min(valid_temps)
            max_temp = max(valid_temps)
            avg_temp = sum(valid_temps) / len(valid_temps)
            stats_text = f"Active Channels: {active}/8 | Min: {min_temp:.1f}°C | Max: {max_temp:.1f}°C | Avg: {avg_temp:.1f}°C"
        
        dpg.set_value("therm_stats", stats_text)
    
    def _clear_thermistor_data(self):
        """Clear all thermistor data."""
        self.thermistor_temps = [None] * 8
        
        for i in range(8):
            if i < len(self.thermistor_text_tags):
                dpg.set_value(self.thermistor_text_tags[i], "---.-- °C")
                dpg.configure_item(self.thermistor_text_tags[i], color=(100, 255, 100))
                dpg.set_value(f"therm_time_{i}", "Last: Never")
            
            if i < len(self.thermistor_adc_tags):
                dpg.set_value(self.thermistor_adc_tags[i], "---- counts")
        
        self._update_thermistor_stats()
    
    def _export_thermistor_data(self):
        """Export current thermistor temperatures to CSV."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"thermistor_temps_{timestamp}.csv"
            
            with open(filename, 'w') as f:
                f.write("Channel,Temperature_degC,Status\n")
                for i in range(8):
                    temp = self.thermistor_temps[i]
                    if temp is not None:
                        f.write(f"{i},{temp:.1f},Active\n")
                    else:
                        f.write(f"{i},,No Data\n")
            
            self._show_popup("Export Success", f"Saved: {filename}")
        except Exception as e:
            self._show_popup("Export Failed", f"Error: {str(e)}")
    
    # ============================================================================
    # Firmware Flasher Methods
    # ============================================================================
    
    def _select_firmware_file(self):
        """Select firmware .bin file."""
        def file_selected(sender, app_data):
            file_path = app_data['file_path_name']
            self.flash_firmware_path = file_path
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            dpg.set_value(self.flash_file_text, f"{filename} ({file_size} bytes)")
            dpg.configure_item(self.flash_file_text, color=(100, 255, 100))
            self._log_flash(f"Selected: {filename} ({file_size} bytes)")
        
        with dpg.file_dialog(directory_selector=False, show=True, callback=file_selected,
                           default_filename="*.bin", width=700, height=400):
            dpg.add_file_extension(".bin", color=(255, 150, 150, 255))
    
    def _log_flash(self, message: str):
        """Add message to flash log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.flash_log.append(log_entry)
        log_text = "\n".join(self.flash_log[-100:])  # Keep last 100 lines
        dpg.set_value("flash_log_text", log_text)
    
    def _wait_for_response(self, timeout: float = RESPONSE_TIMEOUT) -> Optional[bytes]:
        """Wait for bootloader response."""
        self.flash_response_event.clear()
        if self.flash_response_event.wait(timeout):
            return self.flash_response_data
        return None
    
    def _send_command(self, cmd: int, data: bytes = b'') -> bool:
        """Send command to bootloader."""
        msg_data = bytes([cmd]) + data
        msg_data = msg_data + b'\x00' * (8 - len(msg_data))  # Pad to 8 bytes
        return self.driver.send_message(CAN_HOST_ID, msg_data[:8])
    
    def _send_command_list(self, cmd: int, data_list: list = []) -> bool:
        """Send command to bootloader with data as list."""
        msg_data = [cmd] + data_list
        msg_data = msg_data + [0x00] * (8 - len(msg_data))  # Pad to 8 bytes
        return self.driver.send_message(CAN_HOST_ID, bytes(msg_data[:8]))
    
    def _flash_erase(self):
        """Erase flash memory."""
        if not self.is_connected:
            self._show_popup("Not Connected", "Please connect to PCAN first.")
            return
        
        threading.Thread(target=self._flash_erase_thread, daemon=True).start()
    
    def _flash_erase_thread(self):
        """Erase flash thread."""
        try:
            self.flash_in_progress = True
            dpg.set_value(self.flash_status_text, "Erasing flash...")
            dpg.configure_item(self.flash_status_text, color=(255, 200, 100))
            self._log_flash("Starting flash erase...")
            
            # Send erase command
            if not self._send_command(CMD_ERASE_FLASH):
                raise Exception("Failed to send erase command")
            
            # Wait for response
            response = self._wait_for_response(ERASE_TIMEOUT)
            if response and response[0] == RESP_ACK:
                dpg.set_value(self.flash_status_text, "Erase complete!")
                dpg.configure_item(self.flash_status_text, color=(100, 255, 100))
                self._log_flash("✓ Flash erased successfully")
            else:
                raise Exception("Erase failed or timeout")
                
        except Exception as e:
            dpg.set_value(self.flash_status_text, f"Error: {str(e)}")
            dpg.configure_item(self.flash_status_text, color=(255, 100, 100))
            self._log_flash(f"✗ Error: {str(e)}")
        finally:
            self.flash_in_progress = False
    
    def _flash_firmware(self):
        """Flash firmware to device."""
        if not self.is_connected:
            self._show_popup("Not Connected", "Please connect to PCAN first.")
            return
        
        if not self.flash_firmware_path:
            self._show_popup("No File", "Please select a firmware file first.")
            return
        
        threading.Thread(target=self._flash_firmware_thread, daemon=True).start()
    
    def _flash_firmware_thread(self):
        """Flash firmware thread."""
        try:
            self.flash_in_progress = True
            
            # Read firmware file
            with open(self.flash_firmware_path, 'rb') as f:
                firmware_data = f.read()
            
            # Pad to 4-byte boundary
            if len(firmware_data) % 4 != 0:
                padding = 4 - (len(firmware_data) % 4)
                firmware_data += b'\xFF' * padding
            
            total_bytes = len(firmware_data)
            self._log_flash(f"Flashing {total_bytes} bytes...")
            
            # IMPORTANT: Erase flash first!
            self._log_flash("Step 1: Erasing flash...")
            dpg.set_value(self.flash_status_text, "Erasing flash...")
            dpg.configure_item(self.flash_status_text, color=(255, 200, 100))
            
            if not self._send_command(CMD_ERASE_FLASH):
                raise Exception("Failed to send erase command")
            
            response = self._wait_for_response(ERASE_TIMEOUT)
            if not response or response[0] != RESP_ACK:
                raise Exception("Flash erase failed")
            
            self._log_flash("✓ Flash erased successfully")
            time.sleep(0.1)
            
            # Set address - use MSB first (big-endian)
            self._log_flash("Step 2: Setting write address...")
            addr_bytes = [
                (APP_START_ADDRESS >> 24) & 0xFF,
                (APP_START_ADDRESS >> 16) & 0xFF,
                (APP_START_ADDRESS >> 8) & 0xFF,
                APP_START_ADDRESS & 0xFF
            ]
            
            if not self._send_command_list(CMD_SET_ADDRESS, addr_bytes):
                raise Exception("Failed to send set address command")
            
            response = self._wait_for_response()
            if not response or response[0] != RESP_ACK:
                error_code = response[1] if response and len(response) > 1 else 0
                error_desc = ERROR_DESCRIPTIONS.get(error_code, f"Error {error_code}")
                raise Exception(f"Address setting failed: {error_desc}")
            
            self._log_flash(f"✓ Address set to 0x{APP_START_ADDRESS:08X}")
            time.sleep(0.05)
            
            # Write data in 4-byte chunks
            self._log_flash(f"Step 3: Writing {total_bytes} bytes...")
            dpg.set_value(self.flash_status_text, "Writing firmware...")
            dpg.configure_item(self.flash_status_text, color=(100, 200, 255))
            bytes_written = 0
            for offset in range(0, total_bytes, WRITE_CHUNK_SIZE):
                chunk = firmware_data[offset:offset + WRITE_CHUNK_SIZE]
                
                # Send write command: [CMD_WRITE_DATA] [0x04] [byte0] [byte1] [byte2] [byte3]
                cmd_data = [0x04] + list(chunk)
                if not self._send_command_list(CMD_WRITE_DATA, cmd_data):
                    raise Exception(f"Failed to send chunk at offset {offset}")
                
                # Wait for ACK - bootloader must acknowledge each write
                response = self._wait_for_response(1.0)  # 1 second timeout
                
                if not response:
                    raise Exception(f"No response from bootloader at offset {offset}")
                
                if response[0] == RESP_ACK:
                    # Success, continue
                    pass
                elif response[0] == RESP_NACK:
                    error_code = response[1] if len(response) > 1 else 0
                    error_desc = ERROR_DESCRIPTIONS.get(error_code, f"Error {error_code}")
                    raise Exception(f"Write failed at {offset}: {error_desc}")
                else:
                    raise Exception(f"Unexpected response at {offset}: 0x{response[0]:02X}")
                
                bytes_written += len(chunk)
                
                # Update progress
                progress = bytes_written / total_bytes
                dpg.set_value(self.flash_progress_bar, progress)
                dpg.set_value(self.flash_status_text, 
                            f"Writing: {bytes_written}/{total_bytes} bytes ({progress*100:.1f}%)")
                
                # Every 256 bytes, log progress
                if offset % 256 == 0:
                    self._log_flash(f"Written: {bytes_written}/{total_bytes} bytes")
                
                time.sleep(0.002)  # Small delay between chunks
            
            dpg.set_value(self.flash_status_text, "Flash complete!")
            dpg.configure_item(self.flash_status_text, color=(100, 255, 100))
            self._log_flash(f"✓ Successfully flashed {total_bytes} bytes")
            
        except Exception as e:
            dpg.set_value(self.flash_status_text, f"Error: {str(e)}")
            dpg.configure_item(self.flash_status_text, color=(255, 100, 100))
            self._log_flash(f"✗ Error: {str(e)}")
        finally:
            self.flash_in_progress = False
    
    def _flash_verify(self):
        """Verify flashed firmware."""
        self._show_popup("Verify", "Verify feature coming soon...")
    
    def _flash_jump(self):
        """Jump to application."""
        if not self.is_connected:
            self._show_popup("Not Connected", "Please connect first.")
            return
        
        try:
            self.flash_in_progress = True
            self._send_command(CMD_JUMP_TO_APP)
            self._log_flash("Jump to application command sent")
            time.sleep(0.5)
            self.flash_in_progress = False
        except Exception as e:
            self._log_flash(f"Error: {str(e)}")
            self.flash_in_progress = False
    
    # ============================================================================
    # Utility Methods
    # ============================================================================
    
    def _show_popup(self, title: str, message: str):
        """Show popup message."""
        popup_id = f"popup_{id(message)}"
        with dpg.window(label=title, modal=True, show=True, tag=popup_id,
                       pos=[400, 300], width=400, height=150):
            dpg.add_text(message)
            dpg.add_separator()
            dpg.add_button(label="OK", width=100, callback=lambda: dpg.delete_item(popup_id))
    
    def run(self):
        """Run the GUI application."""
        self.setup_gui()
        
        # Main render loop
        while dpg.is_dearpygui_running():
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
