"""
PythonCAN GUI Application
==========================
A PCAN-Explorer-like application built with DearPyGUI.
Allows connection to PCAN-USB or CANable adapters, sending/receiving CAN messages.
Supports DBC file loading for automatic message decoding.

Author: GitHub Copilot
Date: October 10, 2025
"""

import dearpygui.dearpygui as dpg
import sys
import argparse
from typing import Dict, Optional, Callable, Union
from datetime import datetime
import threading
import os
import time
from pathlib import Path
import json

# Import both drivers
try:
    from drivers.PCAN_Driver import PCANDriver, PCANChannel, PCANBaudRate, CANMessage as PCANMessage
    PCAN_AVAILABLE = True
except ImportError:
    PCAN_AVAILABLE = False
    print("Warning: PCAN_Driver.py not found")

try:
    from drivers.CANable_Driver import CANableDriver, CANableBaudRate, CANMessage as CANableMessage
    CANABLE_AVAILABLE = True
except ImportError:
    CANABLE_AVAILABLE = False
    print("Warning: CANable_Driver.py not found")

if not PCAN_AVAILABLE and not CANABLE_AVAILABLE:
    print("Error: No CAN driver modules found")
    print("Please ensure PCAN_Driver.py or CANable_Driver.py exists in drivers/ directory")
    sys.exit(1)

# Optional: DBC file support
try:
    import cantools
    DBC_SUPPORT = True
except ImportError:
    DBC_SUPPORT = False
    print("Warning: cantools not installed. DBC file support disabled.")
    print("Install with: pip install cantools")


class PCANExplorerGUI:
    """
    Main GUI application for PCAN/CANable Explorer.
    """
    
    # Configuration file path
    CONFIG_FILE = Path.home() / ".pythoncan_gui_config.json"
    
    def __init__(self, device_type: str = None, channel: Union[str, 'PCANChannel'] = None):
        """Initialize the GUI application.
        
        Args:
            device_type: 'pcan' or 'canable' (None = use config)
            channel: Default channel/port to use (None = use config)
        """
        # Load saved configuration
        config = self._load_config_static()
        self.config = config
        
        # Priority: command line args > config > defaults
        if device_type is not None:
            self.device_type = device_type.lower()
            print(f"Using device_type from command line: {self.device_type}")
        else:
            self.device_type = config.get('device_type', 'pcan')
            print(f"Using device_type from config: {self.device_type} (config: {config})")
        
        if channel is not None:
            self.default_channel = channel
            print(f"Using channel from command line: {self.default_channel}")
        else:
            self.default_channel = config.get('channel')
            print(f"Using channel from config: {self.default_channel}")
        
        # Create appropriate driver
        if self.device_type == 'pcan':
            if not PCAN_AVAILABLE:
                raise ImportError("PCAN driver not available")
            self.driver = PCANDriver()
        elif self.device_type == 'canable':
            if not CANABLE_AVAILABLE:
                raise ImportError("CANable driver not available")
            self.driver = CANableDriver()
        else:
            raise ValueError(f"Unknown device type: {device_type}")
        
        self.is_connected = False
        self.message_data: Dict[int, dict] = {}
        self.message_lock = threading.Lock()
        
        # Track expanded rows for signal display
        self.expanded_rows: set = set()
        
        # Send messages table data
        self.send_messages: list = []  # List of messages to send
        self.send_messages_lock = threading.Lock()
        self.selected_send_row = None
        
        # GUI initialization state
        self.gui_initializing = True  # Flag to prevent saving during initialization
        
        # DBC database support
        self.dbc_database: Optional[cantools.database.Database] = None if DBC_SUPPORT else None
        self.dbc_file_path: Optional[str] = None
        
        # GUI element tags
        self.channel_combo = None
        self.baudrate_combo = None
        self.connect_button = None
        self.status_text = None
        self.message_table = None
        self.stats_text = None
        self.dbc_status_text = None
        
        # Thermistor monitoring - 6 modules × 56 thermistors = 336 total
        self.thermistor_temps = [[None] * 56 for _ in range(6)]  # [module][channel]
        self.thermistor_text_tags = [[None] * 56 for _ in range(6)]  # GUI text element tags per module
        self.current_thermistor_module = 0  # Currently displayed module (0-5)
        
        # Cell voltage monitoring - 6 modules × 18 cells = 108 total
        self.cell_voltages = [[None] * 18 for _ in range(6)]  # [module][cell] - Store latest voltages (in mV)
        self.stack_voltage = None  # Total stack voltage (in mV)
        self.cell_voltage_text_tags = [[None] * 18 for _ in range(6)]  # GUI text element tags per module
        
        # Statistics
        self.total_messages = 0
        self.start_time = None
    
    @staticmethod
    def _load_config_static() -> dict:
        """Load configuration from JSON file (static version for __init__)."""
        try:
            config_file = Path.home() / ".pythoncan_gui_config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
        return {}
    
    def _load_config(self) -> dict:
        """Load configuration from JSON file."""
        return self._load_config_static()
    
    def _save_config(self):
        """Save current configuration to JSON file."""
        try:
            # Get current channel value from combo box
            channel_value = dpg.get_value(self.channel_combo) if self.channel_combo else None
            
            config = {
                'device_type': self.device_type,
                'channel': channel_value,
                'baudrate': dpg.get_value(self.baudrate_combo) if self.baudrate_combo else 'BAUD_500K',
                'dbc_file': self.dbc_file_path
            }
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"Config saved: {config}")
        except Exception as e:
            print(f"Warning: Could not save config: {e}")
    
    def _get_channel_string(self) -> Optional[str]:
        """Get the current channel as a string for saving."""
        if self.device_type == 'pcan':
            if hasattr(self.driver, '_channel') and self.driver._channel:
                return self.driver._channel.name
        else:  # canable
            if hasattr(self.driver, '_device_index'):
                return str(self.driver._device_index)
        return None
    
    def setup_gui(self):
        """Set up the DearPyGUI interface with tabs."""
        dpg.create_context()
        
        # Set up modern color theme with vibrant gradients
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                # Modern dark theme with cyan/purple gradient accents
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (18, 18, 24, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (24, 24, 32, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (80, 70, 120, 180))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (35, 35, 48, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (50, 50, 68, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (65, 60, 85, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (25, 25, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (40, 35, 60, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgCollapsed, (20, 20, 35, 255))
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, (25, 25, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (24, 24, 32, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (100, 80, 140, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (120, 100, 160, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, (140, 120, 180, 255))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (100, 200, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (100, 180, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (120, 200, 255, 255))
                # Vibrant gradient buttons (cyan to purple)
                dpg.add_theme_color(dpg.mvThemeCol_Button, (70, 100, 180, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (90, 130, 220, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (110, 150, 240, 255))
                # Headers with purple tint
                dpg.add_theme_color(dpg.mvThemeCol_Header, (80, 60, 140, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (100, 80, 170, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (120, 100, 190, 255))
                # Separators with gradient feel
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (90, 80, 130, 200))
                dpg.add_theme_color(dpg.mvThemeCol_SeparatorHovered, (120, 100, 160, 255))
                dpg.add_theme_color(dpg.mvThemeCol_SeparatorActive, (140, 120, 180, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ResizeGrip, (80, 100, 180, 200))
                dpg.add_theme_color(dpg.mvThemeCol_ResizeGripHovered, (100, 130, 220, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ResizeGripActive, (120, 150, 240, 255))
                # Tabs with gradient colors
                dpg.add_theme_color(dpg.mvThemeCol_Tab, (50, 50, 85, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (90, 120, 200, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, (70, 100, 180, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocused, (35, 35, 60, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, (50, 50, 85, 255))
                # Table colors with better contrast
                dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg, (45, 45, 75, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderStrong, (90, 80, 130, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, (60, 55, 85, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, (0, 0, 0, 0))
                dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (100, 90, 140, 15))
                # Text colors with better readability
                dpg.add_theme_color(dpg.mvThemeCol_Text, (240, 240, 250, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (140, 140, 160, 255))
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (30, 30, 48, 245))
                
                # Enhanced style adjustments for modern look
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 10)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 10, 8)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 8)
                dpg.add_theme_style(dpg.mvStyleVar_IndentSpacing, 22)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 16)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 14)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 12)
        
        dpg.bind_theme(global_theme)
        
        # Set up fonts
        with dpg.font_registry():
            default_font = dpg.add_font("C:\\Windows\\Fonts\\segoeui.ttf", 16)
            mono_font = dpg.add_font("C:\\Windows\\Fonts\\consola.ttf", 14)
        
        # Main window
        device_name = "PCAN/CANable" if PCAN_AVAILABLE and CANABLE_AVAILABLE else self.device_type.upper()
        with dpg.window(label=f"{device_name} Explorer", tag="main_window", width=1250, height=850):
            
            # Connection Panel (always visible)
            with dpg.group(horizontal=True):
                dpg.add_text("Connection Settings", color=(140, 200, 255))  # Vibrant cyan-blue for headers
            
            dpg.add_separator()
            
            with dpg.group(horizontal=True):
                # Device Type selector (if both available)
                if PCAN_AVAILABLE and CANABLE_AVAILABLE:
                    dpg.add_text("Device:")
                    dpg.add_combo(
                        items=['PCAN', 'CANable'],
                        default_value=self.device_type.upper(),
                        width=100,
                        tag="device_type_combo",
                        callback=self._on_device_type_changed
                    )
                
                dpg.add_text("Channel:")
                
                # Populate channel combo based on device type
                if self.device_type == 'pcan':
                    channel_items = [channel.name for channel in PCANChannel]
                    # Use saved channel or command line arg or default
                    if self.default_channel and hasattr(self.default_channel, 'name'):
                        default_channel = self.default_channel.name
                    elif self.default_channel and isinstance(self.default_channel, str):
                        default_channel = self.default_channel
                    elif 'channel' in self.config and self.config['channel']:
                        default_channel = self.config['channel']
                    else:
                        default_channel = "USB1"
                else:
                    # For CANable, get available devices and show indices
                    try:
                        canable_devices = self.driver.get_available_devices()
                        if canable_devices:
                            channel_items = [f"Device {dev['index']}: {dev['description']}" for dev in canable_devices]
                            # Try to match saved channel
                            saved_idx = self.config.get('channel', '0') if self.default_channel is None else str(self.default_channel)
                            default_channel = None
                            for item in channel_items:
                                if item.startswith(f"Device {saved_idx}:"):
                                    default_channel = item
                                    break
                            if not default_channel:
                                default_channel = channel_items[0] if channel_items else "Device 0"
                        else:
                            channel_items = ["Device 0", "Device 1", "Device 2"]
                            saved_idx = self.config.get('channel', '0') if self.default_channel is None else str(self.default_channel)
                            default_channel = f"Device {saved_idx}"
                    except:
                        channel_items = ["Device 0", "Device 1", "Device 2"]
                        saved_idx = self.config.get('channel', '0') if self.default_channel is None else str(self.default_channel)
                        default_channel = f"Device {saved_idx}"
                
                self.channel_combo = dpg.add_combo(
                    items=channel_items,
                    default_value=default_channel,
                    width=200,
                    tag="channel_combo"
                )
                
                dpg.add_text(" Baud:")
                
                # Baud rate combo (same for both)
                baudrate_items = [br.name for br in (PCANBaudRate if self.device_type == 'pcan' else CANableBaudRate)]
                default_baudrate = self.config.get('baudrate', 'BAUD_500K')
                self.baudrate_combo = dpg.add_combo(
                    items=baudrate_items,
                    default_value=default_baudrate,
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
                self.status_text = dpg.add_text("Disconnected", color=(255, 100, 120))  # Vibrant coral-red for disconnected
            
            dpg.add_separator()
            
            # Tab Bar
            with dpg.tab_bar():
                
                # ===== CAN EXPLORER TAB =====
                with dpg.tab(label="CAN Explorer"):
                    self._setup_explorer_tab()
                
                # ===== THERMISTOR MONITOR TAB =====
                with dpg.tab(label="Thermistor Monitor"):
                    self._setup_thermistor_tab()
                
                # ===== CELL VOLTAGE MONITOR TAB =====
                with dpg.tab(label="Cell Voltage Monitor"):
                    self._setup_cell_voltage_tab()
        
        # Setup viewport
        dpg.create_viewport(
            title=f"{device_name} Explorer",
            width=1270,
            height=900,
            min_width=900,
            min_height=600
        )
        
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_window", True)
        dpg.bind_font(default_font)
        
        # Auto-load saved DBC file if it exists
        self._auto_load_dbc()
        
        # GUI initialization complete - now allow saving config on changes
        self.gui_initializing = False
    
    def _auto_load_dbc(self):
        """Automatically load the last used DBC file if it exists."""
        if not DBC_SUPPORT:
            return
        
        saved_dbc = self.config.get('dbc_file')
        if saved_dbc and os.path.exists(saved_dbc):
            try:
                self._load_dbc_file_path(saved_dbc)
                print(f"Auto-loaded DBC file: {saved_dbc}")
            except Exception as e:
                print(f"Could not auto-load DBC file: {e}")
    
    def _setup_explorer_tab(self):
        """Setup the CAN Explorer tab content with Send and Receive sections."""
        # DBC Status at top
        with dpg.group(horizontal=True):
            dpg.add_text("DBC File:")
            self.dbc_status_text = dpg.add_text("No DBC loaded", color=(255, 200, 100))
            dpg.add_text("  ")
            dpg.add_button(label="Load DBC", callback=self._load_dbc_file, width=100, height=25)
        
        dpg.add_separator()
        
        # Send section as collapsing header
        with dpg.collapsing_header(label="Send CAN Messages", default_open=False):
            self._setup_send_section()
        
        dpg.add_separator()
        
        # Receive section as collapsing header
        with dpg.collapsing_header(label="Receive CAN Messages", default_open=True):
            self._setup_receive_section()
    
    def _setup_send_section(self):
        """Setup the Send CAN Messages section."""
        dpg.add_text("CAN Message Transmitter", color=(140, 200, 255))
        dpg.add_text("Select a message from the list and use the buttons to send, edit, or remove it.", 
                    color=(180, 190, 220))
        dpg.add_spacing(count=1)
        
        # Controls
        with dpg.group(horizontal=True):
            dpg.add_button(label="Add from DBC", callback=self._show_add_dbc_message_dialog, width=120, height=30)
            dpg.add_button(label="Add Custom", callback=self._show_add_custom_message_dialog, width=120, height=30)
            dpg.add_button(label="Send Selected", callback=self._send_selected_message, width=120, height=30)
            dpg.add_button(label="Edit Selected", callback=self._edit_send_message, width=120, height=30)
            dpg.add_button(label="Remove Selected", callback=self._remove_send_message, width=130, height=30)
            dpg.add_button(label="Clear All", callback=self._clear_send_messages, width=100, height=30)
        
        dpg.add_separator()
        
        # Send Messages List and Details
        with dpg.group(horizontal=True):
            # Left side: Message list
            with dpg.child_window(border=True, width=400, height=250):
                dpg.add_text("Message Library:", color=(140, 200, 255))
                dpg.add_listbox(
                    tag="send_messages_listbox",
                    items=[],
                    num_items=10,
                    callback=self._on_send_message_selected,
                    width=-1
                )
            
            # Right side: Message details
            with dpg.child_window(border=True, width=-1, height=250):
                dpg.add_text("Message Details:", color=(140, 200, 255))
                dpg.add_separator()
                with dpg.group(tag="send_message_details"):
                    dpg.add_text("No message selected", color=(180, 190, 220))
    
    def _setup_receive_section(self):
        """Setup the Receive CAN Messages section."""
        # Statistics
        with dpg.group(horizontal=True):
            dpg.add_text("Statistics:", color=(100, 255, 200))
            self.stats_text = dpg.add_text("Total: 0 | Unique IDs: 0 | Rate: 0 msg/s")
        
        dpg.add_separator()
        
        # Message Table Controls
        with dpg.group(horizontal=True):
            dpg.add_text("Received Messages", color=(140, 200, 255))
            dpg.add_text("     ")
            dpg.add_button(label="Clear", callback=self._clear_messages, width=80, height=25)
        
        dpg.add_spacing(count=1)
        
        # Message Table (dynamic height - fills remaining space)
        with dpg.child_window(border=True, autosize_x=True, autosize_y=True):
            with dpg.table(
                tag="message_table",
                header_row=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                borders_outerH=True,
                borders_innerV=True,
                borders_innerH=True,
                borders_outerV=True,
                scrollY=True
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
                dpg.add_table_column(label="Last RX", width_fixed=True, init_width_or_weight=110)
                dpg.add_table_column(label="Period", width_fixed=True, init_width_or_weight=70)
    
    def _setup_thermistor_tab(self):
        """Setup the Thermistor Monitor tab content - 336 thermistors (6 modules × 56)."""
        dpg.add_text("336-Channel Multi-Module Thermistor Monitor (All Modules)", color=(140, 220, 255))
        dpg.add_text("Real-time temperature readings from 6 BMS modules, 56 channels each (0.1°C resolution)", 
                    color=(160, 170, 180))
        dpg.add_separator()
        
        # Global statistics
        with dpg.group(horizontal=True):
            dpg.add_text("Global Stats:", color=(140, 200, 255))
            dpg.add_text("All Modules | Active: 0/336 | Min: --°C | Max: --°C | Avg: --°C", 
                        tag="therm_global_stats", color=(200, 210, 230))
        
        # Controls
        with dpg.group(horizontal=True):
            dpg.add_button(label="Clear All Data", callback=self._clear_thermistor_data, width=120, height=25)
        
        dpg.add_separator()
        dpg.add_spacing(count=1)
        
        # Temperature Display Grid - ALL 336 thermistors (6 modules)
        # Compact layout: 14 columns (2 per module) × 56 rows
        with dpg.child_window(border=True, autosize_x=True, autosize_y=True, tag="therm_display_container"):
            self._create_all_thermistors_grid()
        
        dpg.add_separator()
        dpg.add_text("Note: Module IDs extracted from bits 15-12 of CAN ID (0x08F0X0YZ format)", 
                    color=(160, 170, 180), wrap=1150)
    
    def _setup_cell_voltage_tab(self):
        """Setup the Cell Voltage Monitor tab content."""
        dpg.add_text("108-Cell Multi-Module Battery Voltage Monitor (All Modules)", color=(140, 220, 255))
        dpg.add_text("Real-time voltage monitoring for 6 modules × 18 cells = 108 total cells (1mV resolution)", 
                    color=(180, 190, 220))
        dpg.add_separator()
        
        # Global statistics
        with dpg.group(horizontal=True):
            dpg.add_text("Global Stats:", color=(140, 200, 255))
            dpg.add_text("Active: 0/108 | Stack: ---.--- V | Min: -.--- V | Max: -.--- V | Avg: -.--- V | Delta: -.--- V", 
                        tag="cell_stats", color=(220, 220, 255))
        
        # Controls
        with dpg.group(horizontal=True):
            dpg.add_button(label="Clear All Data", callback=self._clear_cell_voltage_data, width=120, height=25)
            dpg.add_button(label="Export CSV", callback=self._export_cell_voltage_data, width=120, height=25)
        
        dpg.add_separator()
        dpg.add_spacing(count=1)
        
        # Voltage Display Grid - ALL 108 cells in compact table
        # Layout: 6 columns (one per module) × 18 rows (one per cell)
        with dpg.child_window(border=True, autosize_x=True, autosize_y=True, tag="cell_voltage_display_container"):
            self._create_all_cells_grid()
        
        dpg.add_separator()
        dpg.add_text("Note: Cell voltage data from CAN messages (Cell_X_Voltage signals for 6 modules)", 
                    color=(160, 170, 180), wrap=1150)
    
    def _create_all_cells_grid(self):
        """Create a table showing all 108 cells (6 modules × 18 cells) in a compact grid.
        
        Layout: 6 columns (one per module) × 18 rows (one per cell)
        Similar to thermistor display
        """
        # Create table with 6 columns (one per module)
        with dpg.table(header_row=True, borders_innerH=True, borders_innerV=True, 
                      borders_outerH=True, borders_outerV=True, scrollY=True, height=600):
            # Headers: Module 0 through Module 5
            for module_id in range(6):
                dpg.add_table_column(label=f"Module {module_id}", width_fixed=True, init_width_or_weight=200)
            
            # Create 18 rows (one per cell in each module)
            for cell_idx in range(18):
                with dpg.table_row():
                    # Each column shows one module's cell
                    for module_id in range(6):
                        with dpg.table_cell():
                            with dpg.group(horizontal=True):
                                dpg.add_text(f"C{cell_idx+1:02d}:", color=(160, 170, 200))
                                voltage_tag = f"cell_m{module_id}_v_{cell_idx}"
                                dpg.add_text("-.---- V", tag=voltage_tag, color=(100, 255, 180))
                                
                                # Store tag reference
                                if self.cell_voltage_text_tags[module_id][cell_idx] is None:
                                    self.cell_voltage_text_tags[module_id][cell_idx] = voltage_tag

    
    # ============================================================================
    # Connection Methods
    # ============================================================================
    
    def _on_device_type_changed(self, sender, app_data):
        """Handle device type change."""
        if self.is_connected:
            self._show_popup("Cannot Change", "Please disconnect before changing device type.")
            return
        
        new_device = app_data.lower()
        
        # Update driver
        if new_device == 'pcan':
            self.driver = PCANDriver()
            channel_items = [channel.name for channel in PCANChannel]
            default_channel = "USB1"
            baudrate_items = [br.name for br in PCANBaudRate]
        else:
            self.driver = CANableDriver()
            # Get available CANable devices
            try:
                canable_devices = self.driver.get_available_devices()
                if canable_devices:
                    channel_items = [f"Device {dev['index']}: {dev['description']}" for dev in canable_devices]
                    default_channel = channel_items[0]
                else:
                    channel_items = ["Device 0", "Device 1", "Device 2"]
                    default_channel = "Device 0"
            except:
                channel_items = ["Device 0", "Device 1", "Device 2"]
                default_channel = "Device 0"
            baudrate_items = [br.name for br in CANableBaudRate]
        
        self.device_type = new_device
        
        # Update channel combo
        dpg.configure_item("channel_combo", items=channel_items, default_value=default_channel)
        
        # Update baudrate combo
        dpg.configure_item(self.baudrate_combo, items=baudrate_items, default_value="BAUD_500K")
        
        # Only save config if not initializing (user manually changed device type)
        if not self.gui_initializing:
            self._save_config()
    
    def _toggle_connection(self):
        """Connect or disconnect from CAN device."""
        if not self.is_connected:
            channel_name = dpg.get_value(self.channel_combo)
            baudrate_name = dpg.get_value(self.baudrate_combo)
            
            # Connect based on device type
            if self.device_type == 'pcan':
                channel = PCANChannel[channel_name]
                baudrate = PCANBaudRate[baudrate_name]
            else:  # canable
                # Extract device index from "Device X: Description" format
                try:
                    if channel_name.startswith("Device "):
                        channel_index = int(channel_name.split(":")[0].split()[1])
                    else:
                        channel_index = 0
                except:
                    channel_index = 0
                
                channel = channel_index
                baudrate = CANableBaudRate[baudrate_name]
            
            # Connect to device
            if self.driver.connect(channel, baudrate):
                self.is_connected = True
                self.start_time = datetime.now()
                dpg.set_item_label(self.connect_button, "Disconnect")
                dpg.set_value(self.status_text, f"Connected: {self.device_type.upper()} {channel_name} @ {baudrate_name}")
                dpg.configure_item(self.status_text, color=(120, 220, 150))  # Soft green for connected
                
                # Start receiving messages
                self.driver.start_receive_thread(self._on_message_received)
                
                # Save connection settings
                self._save_config()
                
                # Disable controls
                dpg.configure_item(self.channel_combo, enabled=False)
                dpg.configure_item(self.baudrate_combo, enabled=False)
                if dpg.does_item_exist("device_type_combo"):
                    dpg.configure_item("device_type_combo", enabled=False)
            else:
                self._show_popup("Connection Failed", f"Failed to connect to {self.device_type.upper()} device.")
        else:
            # Disconnect
            if self.driver.disconnect():
                self.is_connected = False
                dpg.set_item_label(self.connect_button, "Connect")
                dpg.set_value(self.status_text, "Disconnected")
                dpg.configure_item(self.status_text, color=(255, 120, 120))  # Soft red for disconnected
                
                # Enable controls
                dpg.configure_item(self.channel_combo, enabled=True)
                dpg.configure_item(self.baudrate_combo, enabled=True)
                if dpg.does_item_exist("device_type_combo"):
                    dpg.configure_item("device_type_combo", enabled=True)
            else:
                self._show_popup("Disconnect Failed", "Failed to properly disconnect from device.")
    
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
            self._load_dbc_file_path(file_path)
        
        with dpg.file_dialog(directory_selector=False, show=True, callback=file_selected,
                           default_filename="*.dbc", width=700, height=400):
            dpg.add_file_extension(".dbc", color=(150, 255, 150, 255))
    
    def _load_dbc_file_path(self, file_path: str):
        """Load a DBC file from a specific path."""
        try:
            # Load with strict=False to allow extended 29-bit CAN IDs without validation errors
            self.dbc_database = cantools.database.load_file(file_path, strict=False)
            self.dbc_file_path = file_path
            filename = os.path.basename(file_path)
            dpg.set_value(self.dbc_status_text, f"Loaded: {filename}")
            dpg.configure_item(self.dbc_status_text, color=(120, 220, 150))  # Soft green for success
            
            # Debug: Print first few messages in DBC
            print(f"\n[DEBUG] DBC loaded successfully: {filename}")
            print(f"[DEBUG] Total messages in DBC: {len(self.dbc_database.messages)}")
            print(f"[DEBUG] First 5 messages:")
            for i, msg in enumerate(self.dbc_database.messages[:5]):
                print(f"  {msg.name}: ID=0x{msg.frame_id:X} ({msg.frame_id})")
            
            # Save config with new DBC path (only if not initializing)
            if not self.gui_initializing:
                self._save_config()
        except Exception as e:
            # Don't show popup during auto-load, just update status
            dpg.set_value(self.dbc_status_text, f"Load failed: {filename if 'filename' in locals() else 'file'}")
            dpg.configure_item(self.dbc_status_text, color=(255, 140, 100))  # Orange for error
            print(f"Warning: Could not load DBC file {file_path}: {e}")
    
    def _decode_message(self, can_id: int, data: bytes, is_extended: bool = False) -> Optional[dict]:
        """Decode CAN message using DBC.
        
        Returns:
            Dictionary with 'summary' (str) and 'signals' (list of tuples) or None
        """
        if not self.dbc_database:
            return None
        try:
            # For extended IDs, add bit 31 to match DBC storage format
            # DBC files store extended IDs with 0x80000000 flag set
            lookup_id = can_id | 0x80000000 if is_extended else can_id
            print(f"[DEBUG] Decoding: can_id=0x{can_id:X}, is_extended={is_extended}, lookup_id=0x{lookup_id:X}")
            
            message = self.dbc_database.get_message_by_frame_id(lookup_id)
            decoded = message.decode(data)
            signals = []
            
            for signal_name, value in decoded.items():
                signal = message.get_signal_by_name(signal_name)
                unit = signal.unit if signal.unit else ""
                
                # Check if this signal has value table (enum)
                if signal.choices:
                    # Try to map the value to a choice name
                    try:
                        choice_name = signal.choices.get(int(value))
                        if choice_name:
                            signals.append((signal_name, choice_name, ""))
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
                
                # Store signal name, value, and unit
                signals.append((signal_name, value_str, unit))
            
            # Create summary
            summary = f"{len(signals)} signal{'s' if len(signals) != 1 else ''}"
            
            return {
                'summary': summary,
                'signals': signals
            }
        except Exception as e:
            # Debug: print exception (remove after testing)
            if is_extended and can_id == 0x18FF0000:
                print(f"DEBUG: Decode failed for 0x{can_id:08X}: {type(e).__name__}: {str(e)}")
            # Return None if decode fails (message not in DBC or decode error)
            return None
    
    def _get_message_name(self, can_id: int, is_extended: bool = False) -> Optional[str]:
        """Get message name from DBC."""
        if not self.dbc_database:
            return None
        try:
            # For extended IDs, add bit 31 to match DBC storage format
            lookup_id = can_id | 0x80000000 if is_extended else can_id
            return self.dbc_database.get_message_by_frame_id(lookup_id).name
        except:
            return None
    
    def _on_message_received(self, msg):
        """Callback for received CAN messages."""
        # Check if this is thermistor data and update display
        self._update_thermistor_data(msg.id, msg.data)
        
        # Check if this is cell voltage data and update display
        self._update_cell_voltage_data(msg.id, msg.data)
        
        # Update message table
        with self.message_lock:
            self.total_messages += 1
            current_time = datetime.now()

            decoded_info = self._decode_message(msg.id, msg.data, msg.is_extended)
            message_name = self._get_message_name(msg.id, msg.is_extended)
            
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
                data['decoded_info'] = decoded_info
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
                    'decoded_info': decoded_info,
                    'count': 1,
                    'last_timestamp': current_time.strftime("%H:%M:%S.%f")[:-3],
                    'last_time': current_time,
                    'period_ms': 0.0,
                    'row_tag': None
                }
    
    def _toggle_row_expansion(self, sender, app_data, user_data):
        """Toggle signal expansion for a row."""
        can_id = user_data
        if can_id in self.expanded_rows:
            self.expanded_rows.remove(can_id)
        else:
            self.expanded_rows.add(can_id)
        self._update_message_table()
    
    def _update_message_table(self):
        """Update the message table display."""
        with self.message_lock:
            existing_rows = dpg.get_item_children("message_table", slot=1)
            
            for can_id, data in sorted(self.message_data.items()):
                data_hex = ' '.join([f'{b:02X}' for b in data['data']])
                
                # Handle decoded signals display
                decoded_info = data.get('decoded_info')
                message_name = data.get('name', '') or ''
                
                if decoded_info:
                    # Check if this row is expanded
                    if can_id in self.expanded_rows:
                        # Show full signal list
                        decoded_lines = []
                        for sig_name, sig_value, sig_unit in decoded_info['signals']:
                            if sig_unit:
                                decoded_lines.append(f"{sig_name}: {sig_value} {sig_unit}")
                            else:
                                decoded_lines.append(f"{sig_name}: {sig_value}")
                        decoded_str = "\n".join(decoded_lines)
                        button_label = "-"  # Minus when expanded (collapse)
                    else:
                        # Show summary only
                        decoded_str = decoded_info['summary']
                        button_label = "+"  # Plus when collapsed (expand)
                else:
                    decoded_str = ""
                    button_label = ""
                
                if data['row_tag'] is None or data['row_tag'] not in existing_rows:
                    with dpg.table_row(parent="message_table") as row_tag:
                        # Format CAN ID with 8 digits for extended IDs, variable for standard
                        can_id_str = f"0x{data['id']:08X}" if data['type'].startswith('EXT') else f"0x{data['id']:X}"
                        dpg.add_text(can_id_str, tag=f"id_{can_id}")
                        dpg.add_text(message_name, tag=f"name_{can_id}")
                        dpg.add_text(data['type'], tag=f"type_{can_id}")
                        dpg.add_text(str(data['dlc']), tag=f"dlc_{can_id}")
                        dpg.add_text(data_hex, tag=f"data_{can_id}")
                        
                        # Decoded signals cell with expand/collapse button
                        with dpg.group(horizontal=True, tag=f"decoded_group_{can_id}"):
                            if decoded_info:
                                dpg.add_button(
                                    label=button_label,
                                    callback=self._toggle_row_expansion,
                                    user_data=can_id,
                                    width=25,
                                    height=20,
                                    tag=f"expand_btn_{can_id}"
                                )
                            dpg.add_text(decoded_str, tag=f"decoded_{can_id}", wrap=220)
                        
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
                    
                    # Update expand button if it exists
                    if decoded_info and dpg.does_item_exist(f"expand_btn_{can_id}"):
                        dpg.configure_item(f"expand_btn_{can_id}", label=button_label)
            
            # Update statistics
            unique_ids = len(self.message_data)
            if self.start_time:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                rate = self.total_messages / elapsed if elapsed > 0 else 0
                dpg.set_value(self.stats_text, 
                            f"Total: {self.total_messages} | Unique IDs: {unique_ids} | Rate: {rate:.1f} msg/s")
    
    def _clear_messages(self):
        """Clear message table."""
        with self.message_lock:
            self.message_data.clear()
            self.expanded_rows.clear()
            self.total_messages = 0
            self.start_time = datetime.now()
            children = dpg.get_item_children("message_table", slot=1)
            for child in children:
                dpg.delete_item(child)
            dpg.set_value(self.stats_text, "Total: 0 | Unique IDs: 0 | Rate: 0 msg/s")
    
    # ============================================================================
    # Send Message Methods
    # ============================================================================
    
    def _on_send_message_selected(self, sender, app_data):
        """Handle selection in send messages listbox."""
        # Find the index of the selected message
        selected_label = app_data
        print(f"[DEBUG] Listbox selection callback: '{selected_label}'")
        
        if not selected_label:
            self.selected_send_row = None
            self._update_send_message_details()
            return
        
        # Find which message was selected
        with self.send_messages_lock:
            for idx, msg in enumerate(self.send_messages):
                msg_type = "EXT" if msg['is_extended'] else "STD"
                label = f"{msg['name']} (0x{msg['can_id']:X} {msg_type}) - Sent: {msg['sent_count']}"
                if label == selected_label:
                    self.selected_send_row = idx
                    print(f"[DEBUG] Selected message index: {idx}, name: {msg['name']}")
                    self._update_send_message_details()
                    
                    # Check for double-click to send
                    if dpg.is_mouse_button_double_clicked(dpg.mvMouseButton_Left):
                        print(f"[DEBUG] Double-click detected, sending message")
                        self._send_selected_message()
                    break
    
    def _update_send_message_details(self):
        """Update the message details panel."""
        try:
            # Clear existing details
            if dpg.does_item_exist("send_message_details"):
                children = dpg.get_item_children("send_message_details", slot=1)
                for child in children:
                    dpg.delete_item(child)
            
            if self.selected_send_row is None or self.selected_send_row >= len(self.send_messages):
                dpg.add_text("No message selected", color=(180, 190, 220), parent="send_message_details")
            else:
                with self.send_messages_lock:
                    msg = self.send_messages[self.selected_send_row]
                    
                    msg_type = "EXT" if msg['is_extended'] else "STD"
                    if msg['is_remote']:
                        msg_type += "-R"
                    
                    data_hex = ' '.join([f'{b:02X}' for b in msg['data']])
                    
                    dpg.add_text(f"Name: {msg['name']}", color=(100, 255, 200), parent="send_message_details")
                    dpg.add_text(f"CAN ID: 0x{msg['can_id']:X}", color=(220, 220, 255), parent="send_message_details")
                    dpg.add_text(f"Type: {msg_type}", color=(220, 220, 255), parent="send_message_details")
                    dpg.add_text(f"DLC: {msg['dlc']}", color=(220, 220, 255), parent="send_message_details")
                    dpg.add_text(f"Data: {data_hex}", color=(220, 220, 255), parent="send_message_details")
                    dpg.add_text(f"Sent Count: {msg['sent_count']}", color=(220, 220, 255), parent="send_message_details")
                    dpg.add_separator(parent="send_message_details")
                    dpg.add_text("Signals:", color=(140, 200, 255), parent="send_message_details")
                    
                    if msg['signal_values'] and msg['dbc_message']:
                        try:
                            for sig_name, sig_value in msg['signal_values'].items():
                                signal = msg['dbc_message'].get_signal_by_name(sig_name)
                                if signal.choices and int(sig_value) in signal.choices:
                                    value_str = signal.choices[int(sig_value)]
                                    dpg.add_text(f"  {sig_name} = {sig_value} ({value_str})", color=(220, 220, 255), parent="send_message_details")
                                else:
                                    dpg.add_text(f"  {sig_name} = {sig_value}", color=(220, 220, 255), parent="send_message_details")
                        except Exception as e:
                            dpg.add_text(f"  Error displaying signals: {e}", color=(255, 100, 120), parent="send_message_details")
                    else:
                        dpg.add_text("  No signals (custom message)", color=(180, 190, 220), parent="send_message_details")
        except Exception as e:
            print(f"[ERROR] Failed to update message details: {e}")
            # Try to at least show an error message
            try:
                dpg.add_text(f"Error: {e}", color=(255, 100, 100), parent="send_message_details")
            except:
                pass
    
    def _show_add_dbc_message_dialog(self):
        """Show dialog to add a message from DBC file."""
        if not self.dbc_database:
            self._show_popup("No DBC File", "Please load a DBC file first.")
            return
        
        # Create popup window
        if dpg.does_item_exist("add_dbc_msg_window"):
            dpg.delete_item("add_dbc_msg_window")
        
        with dpg.window(label="Add Message from DBC", modal=True, tag="add_dbc_msg_window",
                       width=500, height=400, pos=(400, 200)):
            dpg.add_text("Select a message from the DBC file:", color=(140, 200, 255))
            dpg.add_separator()
            
            # List all messages
            message_names = [msg.name for msg in self.dbc_database.messages]
            dpg.add_listbox(items=message_names, tag="dbc_message_selector", 
                           num_items=15, width=480)
            
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add Message", callback=self._add_dbc_message_confirmed, 
                              width=120, height=30)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item("add_dbc_msg_window"),
                              width=100, height=30)
    
    def _add_dbc_message_confirmed(self):
        """Add the selected DBC message to send table."""
        selected_name = dpg.get_value("dbc_message_selector")
        if not selected_name:
            return
        
        try:
            message = self.dbc_database.get_message_by_name(selected_name)
            
            # Create default signal values (all zeros)
            signal_values = {}
            for signal in message.signals:
                # Use default value or 0
                if signal.choices and 0 in signal.choices:
                    signal_values[signal.name] = 0
                else:
                    signal_values[signal.name] = 0
            
            # Encode the message with default values
            data = message.encode(signal_values)
            
            # Determine if extended ID
            is_extended = message.frame_id > 0x7FF
            actual_id = message.frame_id & 0x1FFFFFFF if is_extended else message.frame_id
            
            send_msg = {
                'name': message.name,
                'can_id': actual_id,
                'is_extended': is_extended,
                'is_remote': False,
                'dlc': len(data),
                'data': data,
                'signal_values': signal_values,
                'dbc_message': message,
                'sent_count': 0,
                'row_tag': None
            }
            
            with self.send_messages_lock:
                self.send_messages.append(send_msg)
                # Select the newly added message
                self.selected_send_row = len(self.send_messages) - 1
            
            self._update_send_messages_table()
            dpg.delete_item("add_dbc_msg_window")
            
        except Exception as e:
            self._show_popup("Add Failed", f"Error: {str(e)}")
    
    def _show_add_custom_message_dialog(self):
        """Show dialog to add a custom message."""
        if dpg.does_item_exist("add_custom_msg_window"):
            dpg.delete_item("add_custom_msg_window")
        
        with dpg.window(label="Add Custom Message", modal=True, tag="add_custom_msg_window",
                       width=450, height=300, pos=(400, 250)):
            dpg.add_text("Create a custom CAN message:", color=(140, 200, 255))
            dpg.add_separator()
            
            dpg.add_text("Message Name:")
            dpg.add_input_text(tag="custom_msg_name", default_value="Custom_Message", width=400)
            
            dpg.add_text("CAN ID (Hex):")
            dpg.add_input_text(tag="custom_msg_id", default_value="123", width=150)
            
            dpg.add_text("Data (Hex, space separated):")
            dpg.add_input_text(tag="custom_msg_data", default_value="00 00 00 00 00 00 00 00", width=400)
            
            dpg.add_checkbox(label="Extended ID", tag="custom_msg_ext", default_value=False)
            dpg.add_checkbox(label="Remote Frame", tag="custom_msg_rtr", default_value=False)
            
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add Message", callback=self._add_custom_message_confirmed,
                              width=120, height=30)
                dpg.add_button(label="Cancel", callback=lambda: dpg.delete_item("add_custom_msg_window"),
                              width=100, height=30)
    
    def _add_custom_message_confirmed(self):
        """Add the custom message to send table."""
        try:
            name = dpg.get_value("custom_msg_name").strip()
            can_id_str = dpg.get_value("custom_msg_id").strip()
            can_id = int(can_id_str, 16)
            data_str = dpg.get_value("custom_msg_data").strip()
            data = bytes.fromhex(data_str.replace(" ", ""))
            is_extended = dpg.get_value("custom_msg_ext")
            is_remote = dpg.get_value("custom_msg_rtr")
            
            send_msg = {
                'name': name,
                'can_id': can_id,
                'is_extended': is_extended,
                'is_remote': is_remote,
                'dlc': len(data),
                'data': data,
                'signal_values': None,
                'dbc_message': None,
                'sent_count': 0,
                'row_tag': None
            }
            
            with self.send_messages_lock:
                self.send_messages.append(send_msg)
                # Select the newly added message
                self.selected_send_row = len(self.send_messages) - 1
            
            self._update_send_messages_table()
            dpg.delete_item("add_custom_msg_window")
            
        except Exception as e:
            self._show_popup("Add Failed", f"Error: {str(e)}")
    
    def _edit_send_message(self):
        """Edit the selected send message."""
        if self.selected_send_row is None or self.selected_send_row >= len(self.send_messages):
            self._show_popup("No Selection", "Please select a message to edit.")
            return
        
        msg = self.send_messages[self.selected_send_row]
        
        # If it's a DBC message, show signal editor
        if msg['dbc_message']:
            self._show_signal_editor_dialog(self.selected_send_row)
        else:
            # Show custom message editor
            self._show_edit_custom_message_dialog(self.selected_send_row)
    
    def _show_signal_editor_dialog(self, msg_index):
        """Show dialog to edit signal values for a DBC message."""
        msg = self.send_messages[msg_index]
        dbc_msg = msg['dbc_message']
        
        if dpg.does_item_exist("signal_editor_window"):
            dpg.delete_item("signal_editor_window")
        
        with dpg.window(label=f"Edit Signals - {msg['name']}", modal=True, 
                       tag="signal_editor_window", width=600, height=500, pos=(350, 150)):
            dpg.add_text(f"Message: {msg['name']} (0x{msg['can_id']:X})", color=(140, 200, 255))
            dpg.add_separator()
            
            # Create input for each signal
            with dpg.child_window(height=350, border=True):
                for signal in dbc_msg.signals:
                    with dpg.group():
                        dpg.add_text(f"{signal.name}:", color=(200, 210, 240))
                        
                        # Show unit and range info
                        info_text = f"  Range: {signal.minimum} to {signal.maximum}"
                        if signal.unit:
                            info_text += f" {signal.unit}"
                        dpg.add_text(info_text, color=(170, 180, 210))
                        
                        current_value = msg['signal_values'].get(signal.name, 0)
                        
                        # If signal has choices (value table), use combo box
                        if signal.choices:
                            choices_list = [f"{v}: {name}" for v, name in signal.choices.items()]
                            # Find current selection
                            default_choice = f"{int(current_value)}: {signal.choices.get(int(current_value), 'Unknown')}"
                            dpg.add_combo(items=choices_list, default_value=default_choice,
                                         tag=f"signal_input_{signal.name}", width=400)
                        else:
                            # Numeric input
                            dpg.add_input_float(tag=f"signal_input_{signal.name}", 
                                              default_value=float(current_value), width=200,
                                              step=signal.scale)
                        
                        dpg.add_spacing(count=1)
            
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Apply Changes", 
                              callback=lambda: self._apply_signal_changes(msg_index),
                              width=120, height=30)
                dpg.add_button(label="Cancel",
                              callback=lambda: dpg.delete_item("signal_editor_window"),
                              width=100, height=30)
            
            # Store msg_index for callback
            dpg.set_item_user_data("signal_editor_window", msg_index)
    
    def _apply_signal_changes(self, msg_index):
        """Apply edited signal values and re-encode message."""
        try:
            msg = self.send_messages[msg_index]
            dbc_msg = msg['dbc_message']
            
            # Read all signal values from inputs
            new_signal_values = {}
            for signal in dbc_msg.signals:
                tag = f"signal_input_{signal.name}"
                if signal.choices:
                    # Parse "value: name" format
                    combo_value = dpg.get_value(tag)
                    value = int(combo_value.split(":")[0])
                    new_signal_values[signal.name] = value
                else:
                    new_signal_values[signal.name] = dpg.get_value(tag)
            
            # Re-encode message with new values
            new_data = dbc_msg.encode(new_signal_values)
            
            # Update message
            msg['signal_values'] = new_signal_values
            msg['data'] = new_data
            msg['dlc'] = len(new_data)
            
            self._update_send_messages_table()
            dpg.delete_item("signal_editor_window")
            
        except Exception as e:
            self._show_popup("Update Failed", f"Error: {str(e)}")
    
    def _show_edit_custom_message_dialog(self, msg_index):
        """Show dialog to edit a custom message."""
        msg = self.send_messages[msg_index]
        
        if dpg.does_item_exist("edit_custom_msg_window"):
            dpg.delete_item("edit_custom_msg_window")
        
        data_hex = ' '.join([f'{b:02X}' for b in msg['data']])
        
        with dpg.window(label="Edit Custom Message", modal=True, tag="edit_custom_msg_window",
                       width=450, height=300, pos=(400, 250)):
            dpg.add_text("Edit custom CAN message:", color=(140, 200, 255))
            dpg.add_separator()
            
            dpg.add_text("Message Name:")
            dpg.add_input_text(tag="edit_msg_name", default_value=msg['name'], width=400)
            
            dpg.add_text("CAN ID (Hex):")
            dpg.add_input_text(tag="edit_msg_id", default_value=f"{msg['can_id']:X}", width=150)
            
            dpg.add_text("Data (Hex, space separated):")
            dpg.add_input_text(tag="edit_msg_data", default_value=data_hex, width=400)
            
            dpg.add_checkbox(label="Extended ID", tag="edit_msg_ext", default_value=msg['is_extended'])
            dpg.add_checkbox(label="Remote Frame", tag="edit_msg_rtr", default_value=msg['is_remote'])
            
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Save Changes", 
                              callback=lambda: self._save_custom_message_edits(msg_index),
                              width=120, height=30)
                dpg.add_button(label="Cancel",
                              callback=lambda: dpg.delete_item("edit_custom_msg_window"),
                              width=100, height=30)
    
    def _save_custom_message_edits(self, msg_index):
        """Save edits to custom message."""
        try:
            msg = self.send_messages[msg_index]
            
            msg['name'] = dpg.get_value("edit_msg_name").strip()
            msg['can_id'] = int(dpg.get_value("edit_msg_id").strip(), 16)
            data_str = dpg.get_value("edit_msg_data").strip()
            msg['data'] = bytes.fromhex(data_str.replace(" ", ""))
            msg['dlc'] = len(msg['data'])
            msg['is_extended'] = dpg.get_value("edit_msg_ext")
            msg['is_remote'] = dpg.get_value("edit_msg_rtr")
            
            self._update_send_messages_table()
            dpg.delete_item("edit_custom_msg_window")
            
        except Exception as e:
            self._show_popup("Save Failed", f"Error: {str(e)}")
    
    def _remove_send_message(self):
        """Remove selected message from send table."""
        if self.selected_send_row is None or self.selected_send_row >= len(self.send_messages):
            self._show_popup("No Selection", "Please select a message to remove.")
            return
        
        with self.send_messages_lock:
            self.send_messages.pop(self.selected_send_row)
        
        self.selected_send_row = None
        self._update_send_messages_table()
    
    def _clear_send_messages(self):
        """Clear all send messages."""
        with self.send_messages_lock:
            self.send_messages.clear()
        
        self.selected_send_row = None
        self._update_send_messages_table()
    
    def _send_selected_message(self):
        """Send the currently selected message."""
        print(f"[DEBUG] Send button clicked, selected_send_row: {self.selected_send_row}, total messages: {len(self.send_messages)}")
        
        if self.selected_send_row is None or self.selected_send_row >= len(self.send_messages):
            self._show_popup("No Selection", "Please select a message to send.")
            return
            
        if not self.is_connected:
            self._show_popup("Not Connected", "Please connect to CAN device first.")
            return
        
        try:
            msg = self.send_messages[self.selected_send_row]
            print(f"[DEBUG] Sending message: {msg['name']}, ID: 0x{msg['can_id']:X}")
            self.driver.send_message(msg['can_id'], msg['data'], msg['is_extended'], msg['is_remote'])
            
            # Increment sent count
            msg['sent_count'] += 1
            print(f"[DEBUG] Message sent successfully, count: {msg['sent_count']}")
            self._update_send_messages_table()
            
        except Exception as e:
            print(f"[DEBUG] Send failed: {e}")
            self._show_popup("Send Failed", f"Error: {str(e)}")
    
    def _update_send_messages_table(self):
        """Update the send messages listbox display."""
        # Store the current selection index before updating
        current_selection_idx = self.selected_send_row
        
        # Build list of message names with IDs
        message_labels = []
        with self.send_messages_lock:
            for idx, msg in enumerate(self.send_messages):
                msg_type = "EXT" if msg['is_extended'] else "STD"
                label = f"{msg['name']} (0x{msg['can_id']:X} {msg_type}) - Sent: {msg['sent_count']}"
                message_labels.append(label)
        
        # Update listbox
        if dpg.does_item_exist("send_messages_listbox"):
            # Temporarily disable callback to prevent triggering during update
            dpg.configure_item("send_messages_listbox", items=message_labels, callback=None)
            
            # Restore selection if valid
            if current_selection_idx is not None and current_selection_idx < len(message_labels):
                dpg.set_value("send_messages_listbox", message_labels[current_selection_idx])
            
            # Re-enable callback
            dpg.configure_item("send_messages_listbox", callback=self._on_send_message_selected)
            
            # Update details panel
            self._update_send_message_details()
    
    
    # ============================================================================
    # Thermistor Monitor Methods
    # ============================================================================
    
    def _create_all_thermistors_grid(self):
        """Create a single grid showing all 336 thermistors from all 6 modules.
        
        Layout: 6 modules horizontally, 56 channels vertically
        Creates a 56-row table with 6 columns (one per module)
        """
        # Create table with headers for each module
        with dpg.table(header_row=True, borders_innerH=True, borders_innerV=True, 
                      borders_outerH=True, borders_outerV=True, scrollY=True):
            # Headers: Module 0 through Module 5
            for module_id in range(6):
                dpg.add_table_column(label=f"Module {module_id}", width_fixed=True, init_width_or_weight=160)
            
            # Create 56 rows (one per channel)
            for channel in range(56):
                with dpg.table_row():
                    # Each column shows one module's thermistor
                    for module_id in range(6):
                        with dpg.table_cell():
                            with dpg.group(horizontal=True):
                                dpg.add_text(f"Ch{channel:02d}:", color=(160, 170, 200))
                                temp_tag = f"therm_m{module_id}_temp_{channel}"
                                dpg.add_text("--.-°C", tag=temp_tag, color=(100, 255, 180))
                                
                                # Store tag reference
                                if self.thermistor_text_tags[module_id][channel] is None:
                                    self.thermistor_text_tags[module_id][channel] = temp_tag
    
    def _create_thermistor_grid(self, module_id: int):
        """Legacy method - now creates all thermistors grid."""
        # This method is kept for compatibility but now just creates the full grid
        self._create_all_thermistors_grid()
    
    def _on_thermistor_module_changed(self, sender, app_data):
        """Handle module selector change - NOT USED in all-in-one view."""
        pass  # No longer needed since we show all modules
    
    def _update_thermistor_data(self, can_id: int, data: bytes):
        """Update thermistor display from incoming CAN messages.
        
        Handles messages from all 6 modules:
        Module 0: 0x08F00000-0x08F0000D (Temps 0-55)
        Module 1: 0x08F01000-0x08F0100D (Temps 56-111)
        Module 2: 0x08F02000-0x08F0200D (Temps 112-167)
        Module 3: 0x08F03000-0x08F0300D (Temps 168-223)
        Module 4: 0x08F04000-0x08F0400D (Temps 224-279)
        Module 5: 0x08F05000-0x08F0500D (Temps 280-335)
        
        CAN ID Format: 0x08F0XYZZ
          Bits 15-12 (X): Module ID (0-5)
          Bits 11-8  (Y): Message group (0 = temps)
          Bits 7-0   (ZZ): Message index (00-0D)
        
        Signal naming in DBC: Temp_XXX where XXX is absolute thermistor number (0-335)
        """
        # Use the existing DBC decoder to get signal values
        if not self.dbc_database:
            return

        try:
            # For extended IDs, add bit 31 to match DBC storage format
            lookup_id = can_id | 0x80000000 if True else can_id  # Assume all thermistor messages are extended
            message = self.dbc_database.get_message_by_frame_id(lookup_id)
            decoded = message.decode(data)
            
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Extract module ID from CAN ID (bits 15-12)
            # Example: 0x08F02005 -> bits 15-12 = 0x2 (module 2)
            module_id = (can_id >> 12) & 0x0F
            
            if module_id > 5:
                return  # Invalid module ID
            
            # Check if this is a temperature message (group 0x0, indices 0x00-0x0D)
            msg_index = can_id & 0xFF
            
            if msg_index <= 0x0D:  # Temperature messages (14 messages, 0x00-0x0D)
                # DBC uses ABSOLUTE thermistor numbering (0-335)
                # Calculate the absolute base for this message
                absolute_base = (module_id * 56) + (msg_index * 4)
                
                # Process each temperature signal in the message (4 per message)
                for i in range(4):
                    absolute_therm_num = absolute_base + i
                    
                    # Channel within this module (0-55)
                    channel = (msg_index * 4) + i
                    if channel >= 56:
                        continue
                    
                    # Signal name in DBC is absolute: Temp_XXX (0-335)
                    signal_name = f'Temp_{absolute_therm_num:03d}'
                    
                    if signal_name in decoded:
                        temp_value = decoded[signal_name]
                        self._update_single_thermistor(module_id, channel, temp_value, current_time)
                    else:
                        # Try alternate patterns if absolute naming doesn't work
                        for pattern in [f'Temp_{channel:03d}', f'Temp_Therm_{channel}', f'Temp_{i}']:
                            if pattern in decoded:
                                temp_value = decoded[pattern]
                                self._update_single_thermistor(module_id, channel, temp_value, current_time)
                                break
            
        except Exception as e:
            # Message not in DBC or decode error - silently ignore
            pass
    
    def _update_single_thermistor(self, module_id: int, channel: int, temp: float, time_str: str):
        """Update a single thermistor channel display.
        
        Args:
            module_id: Module number (0-5)
            channel: Channel number within module (0-55)
            temp: Temperature value in degrees C
            time_str: Timestamp string
        """
        if module_id >= 6 or channel >= 56:
            return
        
        # Update stored value
        self.thermistor_temps[module_id][channel] = temp
        
        # Update GUI - only if this module is currently displayed
        temp_tag = f"therm_m{module_id}_temp_{channel}"
        if dpg.does_item_exist(temp_tag):
            temp_color = self._get_temp_color(temp)
            dpg.set_value(temp_tag, f"{temp:.1f}°C")
            dpg.configure_item(temp_tag, color=temp_color)
        
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
            return (120, 160, 255)  # Very cold - blue
        elif temp < 0:
            return (140, 200, 255)  # Cold - light blue
        elif temp < 25:
            return (120, 220, 150)  # Normal - soft green
        elif temp < 50:
            return (240, 220, 120)  # Warm - yellow
        elif temp < 85:
            return (255, 180, 100)  # Hot - orange
        else:
            return (255, 120, 120)  # Very hot - soft red
    
    def _update_thermistor_stats(self):
        """Update thermistor statistics display for all modules."""
        # Global stats (all modules)
        all_temps = []
        module_counts = [0] * 6  # Count active thermistors per module
        
        for module_id in range(6):
            module_temps = [t for t in self.thermistor_temps[module_id] if t is not None]
            all_temps.extend(module_temps)
            module_counts[module_id] = len(module_temps)
        
        if not all_temps:
            global_stats = "All Modules | Active: 0/336 | Min: --°C | Max: --°C | Avg: --°C"
        else:
            active_global = len(all_temps)
            min_global = min(all_temps)
            max_global = max(all_temps)
            avg_global = sum(all_temps) / len(all_temps)
            
            # Include per-module active counts
            module_str = " | ".join([f"M{i}:{module_counts[i]}" for i in range(6)])
            global_stats = (f"Active: {active_global}/336 ({module_str}) | "
                          f"Min: {min_global:.1f}°C | Max: {max_global:.1f}°C | Avg: {avg_global:.1f}°C")
        
        dpg.set_value("therm_global_stats", global_stats)
    
    def _clear_thermistor_data(self):
        """Clear all thermistor data from all modules."""
        # Clear stored data
        self.thermistor_temps = [[None] * 56 for _ in range(6)]
        
        # Clear all visible tags (all modules now visible)
        for module_id in range(6):
            for channel in range(56):
                temp_tag = f"therm_m{module_id}_temp_{channel}"
                if dpg.does_item_exist(temp_tag):
                    dpg.set_value(temp_tag, "--.-°C")
                    dpg.configure_item(temp_tag, color=(120, 220, 150))
        
        self._update_thermistor_stats()
    
    
    # ============================================================================
    # Cell Voltage Monitor Methods
    # ============================================================================
    
    def _update_cell_voltage_data(self, can_id: int, data: bytes):
        """Update cell voltage display from incoming CAN messages."""
        # Use the existing DBC decoder to get signal values
        if not self.dbc_database:
            return

        try:
            # Decode the message using DBC - cantools auto-detects if extended
            message = self.dbc_database.get_message_by_frame_id(can_id)
            decoded = message.decode(data)
            
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Cell voltage messages for 6 modules × 18 cells
            # Assuming messages follow pattern: Module_X_Cell_Voltages_Y_Z
            # where X is module (0-5) and Y-Z indicates which cells (e.g., 1-6, 7-12, 13-18)
            # Each message carries voltages for 6 cells (3 messages per module)
            
            # Parse cell voltage messages dynamically based on signal names
            # Look for signals like "Cell_1_Voltage", "Cell_2_Voltage", etc.
            for signal_name, signal_value in decoded.items():
                if signal_name.startswith('Cell_') and signal_name.endswith('_Voltage'):
                    try:
                        # Extract cell number from signal name (e.g., "Cell_5_Voltage" -> 5)
                        parts = signal_name.split('_')
                        if len(parts) >= 3:
                            cell_num_global = int(parts[1])  # Global cell number (1-108)
                            
                            # Map global cell number to module and cell index
                            # Cells 1-18 -> Module 0, Cells 19-36 -> Module 1, etc.
                            module_id = (cell_num_global - 1) // 18
                            cell_idx = (cell_num_global - 1) % 18
                            
                            if 0 <= module_id < 6 and 0 <= cell_idx < 18:
                                self._update_single_cell_voltage(module_id, cell_idx, signal_value, current_time)
                    except (ValueError, IndexError):
                        pass  # Skip malformed signal names
            
            # Legacy support: BQ76952 messages (if still present)
            # BQ76952_Stack_Voltage (0x731/1841)
            if can_id == 0x731:
                if 'Stack_Voltage' in decoded:
                    self.stack_voltage = decoded['Stack_Voltage']  # in mV
            
            # BQ76952_Cell_Voltages_1_4 (0x732/1842) - Cells 1-4 (Module 0, Cells 0-3)
            elif can_id == 0x732:
                for i in range(1, 5):
                    key = f'Cell_{i}_Voltage'
                    if key in decoded:
                        module_id = 0
                        cell_idx = i - 1
                        self._update_single_cell_voltage(module_id, cell_idx, decoded[key], current_time)
            
            # BQ76952_Cell_Voltages_5_8 (0x733/1843) - Cells 5-8 (Module 0, Cells 4-7)
            elif can_id == 0x733:
                for i in range(5, 9):
                    key = f'Cell_{i}_Voltage'
                    if key in decoded:
                        module_id = 0
                        cell_idx = i - 1
                        self._update_single_cell_voltage(module_id, cell_idx, decoded[key], current_time)
            
            # BQ76952_Cell_Voltages_9_12 (0x734/1844) - Cells 9-12 (Module 0, Cells 8-11)
            elif can_id == 0x734:
                for i in range(9, 13):
                    key = f'Cell_{i}_Voltage'
                    if key in decoded:
                        module_id = 0
                        cell_idx = i - 1
                        self._update_single_cell_voltage(module_id, cell_idx, decoded[key], current_time)
            
            # BQ76952_Cell_Voltages_13_16 (0x735/1845) - Cells 13-16 (Module 0, Cells 12-15)
            elif can_id == 0x735:
                for i in range(13, 17):
                    key = f'Cell_{i}_Voltage'
                    if key in decoded:
                        module_id = 0
                        cell_idx = i - 1
                        self._update_single_cell_voltage(module_id, cell_idx, decoded[key], current_time)
            
        except Exception as e:
            # Message not in DBC or decode error - silently ignore
            pass
    
    def _update_single_cell_voltage(self, module_id: int, cell_idx: int, voltage_mv: float, time_str: str):
        """Update a single cell voltage display.
        
        Args:
            module_id: Module ID (0-5)
            cell_idx: Cell index within module (0-17)
            voltage_mv: Voltage in millivolts
            time_str: Timestamp string (not displayed in compact view)
        """
        if module_id < 0 or module_id >= 6 or cell_idx < 0 or cell_idx >= 18:
            return
        
        # Update stored value
        self.cell_voltages[module_id][cell_idx] = voltage_mv
        
        voltage_v = voltage_mv / 1000.0
        
        # Update GUI
        voltage_tag = f"cell_m{module_id}_v_{cell_idx}"
        dpg.set_value(voltage_tag, f"{voltage_v:.4f} V")
        
        # Color based on voltage level
        cell_color = self._get_cell_voltage_color(voltage_v)
        dpg.configure_item(voltage_tag, color=cell_color)
        
        # Update statistics
        self._update_cell_voltage_stats()
    
    def _get_cell_voltage_color(self, voltage: float):
        """Get color for cell voltage display based on value."""
        if voltage < 2.5:
            return (255, 0, 0)      # Critical low - bright red
        elif voltage < 3.0:
            return (255, 100, 100)  # Very low - red
        elif voltage < 3.3:
            return (255, 200, 100)  # Low - orange
        elif voltage < 4.2:
            return (100, 255, 100)  # Normal - green
        elif voltage < 4.3:
            return (255, 255, 100)  # High - yellow
        else:
            return (255, 100, 255)  # Very high - magenta
    
    def _update_cell_voltage_stats(self):
        """Update cell voltage statistics display for all 108 cells across 6 modules."""
        # Flatten all cell voltages
        valid_voltages = []
        for module in self.cell_voltages:
            for v in module:
                if v is not None:
                    valid_voltages.append(v)
        
        # Calculate stack voltage from sum of cells
        stack_v = sum(valid_voltages) / 1000.0 if valid_voltages else 0.0
        
        if not valid_voltages:
            stats_text = "Active: 0/108 | Stack: ---.--- V | Min: -.--- V | Max: -.--- V | Avg: -.--- V | Delta: -.--- V"
        else:
            active = len(valid_voltages)
            min_v = min(valid_voltages) / 1000.0
            max_v = max(valid_voltages) / 1000.0
            avg_v = sum(valid_voltages) / len(valid_voltages) / 1000.0
            delta_v = (max_v - min_v)
            stats_text = f"Active: {active}/108 | Stack: {stack_v:.3f} V | Min: {min_v:.4f} V | Max: {max_v:.4f} V | Avg: {avg_v:.4f} V | Delta: {delta_v:.4f} V"
        
        dpg.set_value("cell_stats", stats_text)
    
    def _clear_cell_voltage_data(self):
        """Clear all cell voltage data for all 108 cells."""
        self.cell_voltages = [[None] * 18 for _ in range(6)]
        self.stack_voltage = None
        
        # Clear individual cells for all modules
        for module_id in range(6):
            for cell_idx in range(18):
                voltage_tag = f"cell_m{module_id}_v_{cell_idx}"
                dpg.set_value(voltage_tag, "-.---- V")
                dpg.configure_item(voltage_tag, color=(100, 255, 180))  # Vibrant mint green
        
        self._update_cell_voltage_stats()
    
    def _export_cell_voltage_data(self):
        """Export current cell voltages to CSV for all 108 cells."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cell_voltages_{timestamp}.csv"
            
            with open(filename, 'w') as f:
                f.write("Module,Cell_Index,Cell_Label,Voltage_V,Voltage_mV,Status\n")
                
                # Calculate stack voltage
                valid_voltages = []
                for module in self.cell_voltages:
                    for v in module:
                        if v is not None:
                            valid_voltages.append(v)
                
                stack_v = sum(valid_voltages) / 1000.0 if valid_voltages else 0.0
                stack_mv = sum(valid_voltages) if valid_voltages else 0.0
                
                # Stack voltage summary
                f.write(f"ALL,ALL,Stack,{stack_v:.3f},{stack_mv:.0f},Active\n")
                f.write("\n")
                
                # Individual cells for each module
                for module_id in range(6):
                    for cell_idx in range(18):
                        voltage_mv = self.cell_voltages[module_id][cell_idx]
                        cell_label = f"M{module_id}_C{cell_idx+1}"
                        if voltage_mv is not None:
                            voltage_v = voltage_mv / 1000.0
                            f.write(f"{module_id},{cell_idx},{cell_label},{voltage_v:.4f},{voltage_mv:.0f},Active\n")
                        else:
                            f.write(f"{module_id},{cell_idx},{cell_label},,,No Data\n")
            
            self._show_popup("Export Success", f"Saved: {filename}")
        except Exception as e:
            self._show_popup("Export Failed", f"Error: {str(e)}")
    
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
    """Main entry point with command-line argument support."""
    parser = argparse.ArgumentParser(
        description='PythonCAN GUI Explorer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Using PCAN (default)
  python GUI_Master.py
  python GUI_Master.py --device pcan --channel USB1
  
  # Using CANable (specify device index)
  python GUI_Master.py --device canable --channel 0
  python GUI_Master.py --device canable --channel 1
        '''
    )
    
    parser.add_argument('--device', type=str, default=None,
                       choices=['pcan', 'canable'],
                       help='CAN adapter type (default: from config or pcan)')
    parser.add_argument('--channel', type=str, default=None,
                       help='PCAN channel (e.g., USB1) or CANable device index (e.g., 0, 1, 2)')
    
    args = parser.parse_args()
    
    # Load config to check for saved preferences
    config = PCANExplorerGUI._load_config_static()
    
    # Use command-line args if provided, otherwise use config, otherwise use defaults
    if args.device:
        device_type = args.device.lower()
    else:
        device_type = config.get('device_type', 'pcan')
    
    # Validate device availability
    if device_type == 'pcan' and not PCAN_AVAILABLE:
        print("Error: PCAN driver not available")
        print("Please ensure PCAN_Driver.py exists in drivers/ directory")
        sys.exit(1)
    
    if device_type == 'canable' and not CANABLE_AVAILABLE:
        print("Error: CANable driver not available")
        print("Please ensure CANable_Driver.py exists in drivers/ directory")
        sys.exit(1)
    
    # Set channel - use command-line arg if provided, otherwise let __init__ use config
    if args.channel:
        channel = args.channel
    else:
        channel = None  # Let __init__ use config value
    
    # Convert PCAN channel string to enum if needed
    if device_type == 'pcan' and isinstance(channel, str):
        try:
            channel = PCANChannel[channel]
        except KeyError:
            print(f"Error: Invalid PCAN channel: {channel}")
            print(f"Available channels: {[c.name for c in PCANChannel]}")
            sys.exit(1)
    
    # Convert CANable channel string to integer if needed
    if device_type == 'canable' and isinstance(channel, str):
        try:
            channel = int(channel)
        except ValueError:
            print(f"Error: Invalid CANable channel index: {channel}")
            print(f"Expected an integer (0, 1, 2, ...) representing device index")
            sys.exit(1)
    
    # Create and run GUI
    app = PCANExplorerGUI(device_type=device_type, channel=channel)
    app.run()


if __name__ == "__main__":
    main()
