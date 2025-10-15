#!/usr/bin/env python3
"""
STM32L432 CAN Bootloader Flash Script - 4-Byte Chunk Method
===========================================================
Optimized for 4-byte chunks that align perfectly with STM32 flash requirements.
Flash application firmware to STM32L432 via CAN bus and verify by reading back.

Usage:
    python Flash_Application.py application.bin [--device pcan] [--channel USB1]
    python Flash_Application.py application.bin [--device canable] [--channel COM3]

Requirements:
    - PCAN_Driver.py or CANable_Driver.py (CAN driver modules)
    - python-can library
    - PCAN-USB adapter or CANable device

Author: GitHub Copilot
Date: October 10, 2025
"""

import sys
import time
import argparse
from pathlib import Path
from typing import Optional, Tuple, Union
from dataclasses import dataclass

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
    print("Error: No CAN driver modules found in drivers/ directory")
    print("Please ensure PCAN_Driver.py or CANable_Driver.py exists")
    sys.exit(1)


# ============================================================================
# Bootloader Protocol Constants
# ============================================================================

# CAN IDs (29-bit Extended IDs)
CAN_HOST_ID = 0x18000701          # PC sends commands to this ID (Extended)
CAN_BOOTLOADER_ID = 0x18000700    # Bootloader responds from this ID (Extended)

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
PERMANENT_STORAGE_SIZE = 0x4000         # 16KB reserved for permanent data
PERMANENT_STORAGE_ADDRESS = 0x0803C000  # Last 16KB of flash (256KB - 16KB)
APP_END_ADDRESS = 0x0803BFFF            # Application ends before permanent storage
APP_MAX_SIZE = 0x34000                  # 208 KB (APPLICATION_END - APPLICATION_START + 1)

# Timing
RESPONSE_TIMEOUT = 1.0       # Normal response timeout (seconds)
ERASE_TIMEOUT = 15.0         # Flash erase timeout (seconds)
WRITE_CHUNK_SIZE = 4         # Write 4 bytes per CAN message (bootloader buffers 2 chunks for 8-byte flash write)


# ============================================================================
# Error Code Descriptions
# ============================================================================

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


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class BootloaderStatus:
    """Bootloader status information"""
    state: int
    error: int
    bytes_written: int
    
    def __str__(self):
        states = ['IDLE', 'ERASING', 'WRITING', 'READING', 'VERIFYING', 'JUMPING']
        state_name = states[self.state] if self.state < len(states) else 'UNKNOWN'
        error_desc = ERROR_DESCRIPTIONS.get(self.error, f'Unknown error {self.error}')
        return f"State: {state_name}, Error: {error_desc}, Bytes Written: {self.bytes_written}"


# ============================================================================
# CAN Bootloader Flash Class
# ============================================================================

class CANBootloaderFlash:
    """
    Main class for flashing firmware via CAN bootloader.
    Supports both PCAN and CANable devices.
    """
    
    def __init__(self, device_type: str = 'pcan', channel: Union[str, 'PCANChannel', int] = None):
        """
        Initialize the CAN flasher.
        
        Args:
            device_type: 'pcan' or 'canable'
            channel: PCAN channel (e.g., PCANChannel.USB1) or CANable device index (int, e.g., 0, 1, 2)
        """
        self.device_type = device_type.lower()
        
        if self.device_type == 'pcan':
            if not PCAN_AVAILABLE:
                raise ImportError("PCAN driver not available")
            self.driver = PCANDriver()
            self.channel = channel if channel else PCANChannel.USB1
        elif self.device_type == 'canable':
            if not CANABLE_AVAILABLE:
                raise ImportError("CANable driver not available")
            self.driver = CANableDriver()
            self.channel = channel if channel is not None else 0  # Default to first device
        else:
            raise ValueError(f"Unknown device type: {device_type}")
        
        self.connected = False
        self.verbose = True
        
    def connect(self) -> bool:
        """
        Connect to CAN device and initialize CAN communication.
        
        Returns:
            True if connection successful
        """
        print(f"\n{'='*60}")
        print(f"Connecting to {self.device_type.upper()} device...")
        print(f"{'='*60}")
        
        # Connect based on device type
        if self.device_type == 'pcan':
            # Connect to PCAN at 500 kbps (bootloader baud rate)
            if not self.driver.connect(self.channel, PCANBaudRate.BAUD_500K):
                print(f"✗ Failed to connect to PCAN device on {self.channel.name}")
                return False
        elif self.device_type == 'canable':
            # Connect to CANable at 500 kbps (bootloader baud rate)
            if not self.driver.connect(self.channel, CANableBaudRate.BAUD_500K):
                print(f"✗ Failed to connect to CANable device on {self.channel}")
                return False
        
        self.connected = True
        
        # Clear receive queue
        self.driver.clear_receive_queue()
        
        print("✓ Connected successfully")
        
        # Wait for bootloader READY message
        self.wait_for_bootloader_ready()
        
        print()
        return True
    
    def disconnect(self):
        """Disconnect from PCAN device."""
        if self.connected:
            self.driver.disconnect()
            self.connected = False
    
    def send_command(self, command: int, data: list) -> bool:
        """
        Send a command to the bootloader.
        
        Args:
            command: Command byte
            data: List of data bytes (will be padded to 8 bytes)
        
        Returns:
            True if sent successfully
        """
        # Prepare message (pad to 8 bytes)
        msg_data = [command] + data
        while len(msg_data) < 8:
            msg_data.append(0x00)
        
        # Send to bootloader using 29-bit extended ID
        return self.driver.send_message(CAN_HOST_ID, bytes(msg_data[:8]), is_extended=True)
    
    def wait_response(self, timeout: float = RESPONSE_TIMEOUT):
        """
        Wait for a response from bootloader.
        
        Args:
            timeout: Maximum time to wait in seconds
        
        Returns:
            CANMessage if received, None if timeout
        """
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            msg = self.driver.read_message(timeout=0.1)
            
            if msg and msg.id == CAN_BOOTLOADER_ID:
                return msg
        
        return None
    
    def wait_for_bootloader_ready(self, timeout: float = 3.0) -> bool:
        """
        Wait for bootloader READY message on startup.
        According to BUILD_AND_FLASH_INSTRUCTIONS.md:
        - Bootloader sends READY message on power-up
        - CAN ID: 0x700
        - Data: 0x14 0x01 0x00 ... (READY + version)
        
        Args:
            timeout: Maximum time to wait for READY message
            
        Returns:
            True if READY message received
        """
        if self.verbose:
            print("Waiting for bootloader READY message...")
        
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            msg = self.driver.read_message(timeout=0.1)
            
            if msg and msg.id == CAN_BOOTLOADER_ID:
                if len(msg.data) > 0 and msg.data[0] == RESP_READY:
                    version = msg.data[1] if len(msg.data) > 1 else 0
                    if self.verbose:
                        print(f"✓ Bootloader READY (version: {version})")
                    return True
        
        if self.verbose:
            print("⚠ No READY message received (bootloader may already be running)")
        return False
    
    def get_status(self) -> Optional[BootloaderStatus]:
        """
        Get bootloader status.
        
        Returns:
            BootloaderStatus object or None if failed
        """
        if self.verbose:
            print("Getting bootloader status...")
        
        # Send GET_STATUS command
        if not self.send_command(CMD_GET_STATUS, []):
            return None
        
        # Wait for response
        resp = self.wait_response()
        if not resp or len(resp.data) < 7:
            if self.verbose:
                print("✗ No response or invalid response")
            return None
        
        # Parse response
        if resp.data[0] == RESP_DATA:
            status = BootloaderStatus(
                state=resp.data[1],
                error=resp.data[2],
                bytes_written=(resp.data[3] << 24) | (resp.data[4] << 16) | 
                              (resp.data[5] << 8) | resp.data[6]
            )
            if self.verbose:
                print(f"✓ {status}")
            return status
        
        return None
    
    def erase_flash(self) -> bool:
        """
        Erase application flash area.
        
        Returns:
            True if erase successful
        """
        print("\n" + "="*60)
        print("Erasing flash memory...")
        print("="*60)
        print("This may take several seconds...")
        
        # Send ERASE command
        if not self.send_command(CMD_ERASE_FLASH, []):
            print("✗ Failed to send erase command")
            return False
        
        # Wait for ACK (with longer timeout)
        resp = self.wait_response(timeout=ERASE_TIMEOUT)
        
        if not resp:
            print("✗ Erase timeout (no response)")
            return False
        
        if resp.data[0] == RESP_ACK:
            print("✓ Flash erased successfully\n")
            return True
        elif resp.data[0] == RESP_NACK:
            error_code = resp.data[1] if len(resp.data) > 1 else 0
            error_desc = ERROR_DESCRIPTIONS.get(error_code, f"Error {error_code}")
            print(f"✗ Erase failed: {error_desc}")
            return False
        else:
            print(f"✗ Unexpected response: 0x{resp.data[0]:02X}")
            return False
    
    def set_address(self, address: int) -> bool:
        """
        Set write address pointer.
        
        Args:
            address: Flash address to set
        
        Returns:
            True if successful
        """
        if self.verbose:
            print(f"Setting address to 0x{address:08X}...")
        
        # Prepare address bytes (MSB first)
        addr_bytes = [
            (address >> 24) & 0xFF,
            (address >> 16) & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF
        ]
        
        # Send SET_ADDRESS command
        if not self.send_command(CMD_SET_ADDRESS, addr_bytes):
            return False
        
        # Wait for ACK
        resp = self.wait_response()
        
        if not resp:
            if self.verbose:
                print("✗ No response")
            return False
        
        if resp.data[0] == RESP_ACK:
            if self.verbose:
                print("✓ Address set")
            return True
        elif resp.data[0] == RESP_NACK:
            error_code = resp.data[1] if len(resp.data) > 1 else 0
            error_desc = ERROR_DESCRIPTIONS.get(error_code, f"Error {error_code}")
            if self.verbose:
                print(f"✗ Failed: {error_desc}")
            return False
        
        return False
    
    def write_4bytes(self, data: bytes) -> bool:
        """
        Write exactly 4 bytes to flash.
        Bootloader buffers two 4-byte chunks before writing 8 bytes to flash.
        
        Args:
            data: Exactly 4 bytes to write
            
        Returns:
            True if write successful
        """
        if len(data) != 4:
            raise ValueError(f"Must write exactly 4 bytes, got {len(data)}")
        
        # Build command: [CMD] [0x04] [byte0] [byte1] [byte2] [byte3]
        cmd_data = [0x04] + list(data)
        
        # Send WRITE_DATA command
        if not self.send_command(CMD_WRITE_DATA, cmd_data):
            return False
        
        # Wait for ACK
        resp = self.wait_response()
        
        if not resp:
            if self.verbose:
                print(f"\n⚠ No response from bootloader for write (timeout)")
                print(f"  Data attempted: {data.hex().upper()}")
            return False
        
        if resp.data[0] == RESP_ACK:
            return True
        elif resp.data[0] == RESP_NACK:
            error_code = resp.data[1] if len(resp.data) > 1 else 0
            error_desc = ERROR_DESCRIPTIONS.get(error_code, f'Unknown error {error_code}')
            print(f"\n✗ Write NACK received: {error_desc}")
            print(f"  Data attempted: {data.hex().upper()}")
            print(f"  Error code: 0x{error_code:02X}")
            return False
        else:
            print(f"\n⚠ Unexpected response from bootloader: 0x{resp.data[0]:02X}")
            print(f"  Expected RESP_ACK (0x{RESP_ACK:02X}) or RESP_NACK (0x{RESP_NACK:02X})")
            print(f"  Full response: {resp.data.hex().upper()}")
            return False
    
    def read_data(self, address: int, length: int) -> Optional[bytes]:
        """
        Read data from flash.
        
        Args:
            address: Flash address
            length: Number of bytes to read (max 7)
            
        Returns:
            Read data or None if failed
        """
        if length == 0 or length > 7:
            if self.verbose:
                print(f"\n⚠ Invalid read length: {length} (must be 1-7)")
            return None
        
        # Build command: [CMD] [addr3] [addr2] [addr1] [addr0] [length]
        addr_bytes = [
            (address >> 24) & 0xFF,
            (address >> 16) & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF,
            length
        ]
        
        if not self.send_command(CMD_READ_FLASH, addr_bytes):
            if self.verbose:
                print(f"\n⚠ Failed to send read command for address 0x{address:08X}")
            return None
        
        msg = self.wait_response()
        if not msg:
            if self.verbose:
                print(f"\n⚠ No response from bootloader for read at 0x{address:08X}")
            return None
        
        if len(msg.data) == 0:
            if self.verbose:
                print(f"\n⚠ Empty response from bootloader for read at 0x{address:08X}")
            return None
        
        if msg.data[0] == RESP_DATA:
            # Data starts at byte 1
            read_bytes = bytes(msg.data[1:1+length])
            if len(read_bytes) != length:
                if self.verbose:
                    print(f"\n⚠ Read length mismatch: requested {length}, got {len(read_bytes)}")
            return read_bytes
        elif msg.data[0] == RESP_NACK:
            error_code = msg.data[1] if len(msg.data) > 1 else 0
            error_desc = ERROR_DESCRIPTIONS.get(error_code, f"Error {error_code}")
            if self.verbose:
                print(f"\n⚠ Read failed at 0x{address:08X}: {error_desc}")
            return None
        else:
            if self.verbose:
                print(f"\n⚠ Unexpected response: 0x{msg.data[0]:02X} for read at 0x{address:08X}")
            return None
    
    @staticmethod
    def pad_to_4byte_boundary(data: bytes) -> bytes:
        """
        Pad data to 4-byte boundary (and therefore 8-byte boundary).
        
        Args:
            data: Original firmware data
            
        Returns:
            Padded data (length is multiple of 4)
        """
        padding_needed = (4 - len(data) % 4) % 4
        if padding_needed > 0:
            data = data + b'\xFF' * padding_needed
        return data
    
    def write_firmware(self, firmware_data: bytes) -> bool:
        """
        Write complete firmware to flash using 4-byte chunks.
        
        Args:
            firmware_data: Complete firmware binary (will be padded to 4-byte boundary)
        
        Returns:
            True if write successful
        """
        print("\n" + "="*60)
        print("Writing firmware...")
        print("="*60)
        
        total_bytes = len(firmware_data)
        chunk_size = WRITE_CHUNK_SIZE  # 4 bytes per message
        
        print(f"Total size: {total_bytes} bytes ({total_bytes/1024:.2f} KB)")
        print(f"Chunk size: {chunk_size} bytes per CAN message")
        print("Bootloader buffers 2 chunks (8 bytes) before writing to flash")
        print()
        
        # Set initial address
        if not self.set_address(APP_START_ADDRESS):
            print("✗ Failed to set initial address")
            return False
        
        # Write data in 4-byte chunks
        start_time = time.time()
        last_progress = -1
        bytes_written = 0
        
        while bytes_written < total_bytes:
            # Get next 4-byte chunk
            chunk_end = min(bytes_written + chunk_size, total_bytes)
            chunk = firmware_data[bytes_written:chunk_end]
            
            # Ensure exactly 4 bytes (pad if needed for last chunk)
            if len(chunk) < 4:
                chunk = chunk + b'\xFF' * (4 - len(chunk))
            
            # Write 4-byte chunk
            if not self.write_4bytes(chunk):
                print(f"\n\n{'='*60}")
                print("✗ WRITE FAILED")
                print("="*60)
                print(f"Failed at offset: 0x{bytes_written:08X} ({bytes_written} bytes)")
                print(f"Flash address: 0x{APP_START_ADDRESS + bytes_written:08X}")
                print(f"Progress: {bytes_written}/{total_bytes} bytes ({bytes_written*100//total_bytes}%)")
                print(f"\nFailed chunk data:")
                print(f"  Hex: {chunk.hex().upper()}")
                print(f"  Decimal: {' '.join(f'{b:3d}' for b in chunk)}")
                print(f"\nDebugging information:")
                print(f"  Device type: {self.device_type.upper()}")
                print(f"  Channel: {self.channel}")
                print(f"  Bytes successfully written: {bytes_written}")
                print(f"\nPossible causes:")
                print(f"  1. Communication timeout with bootloader")
                print(f"  2. Flash write protection enabled")
                print(f"  3. Invalid flash address")
                print(f"  4. CAN bus error or disconnection")
                print(f"  5. Bootloader busy or in error state")
                print(f"\nSuggested actions:")
                print(f"  1. Reset the device and try again")
                print(f"  2. Check CAN bus connection and termination")
                print(f"  3. Verify bootloader is running (check for READY message)")
                print(f"  4. Try erasing flash before writing")
                return False
            
            bytes_written += len(chunk) if chunk_end != total_bytes or len(chunk) == 4 else (chunk_end - bytes_written)
            
            # Update progress every 128 bytes (32 messages)
            progress = int((bytes_written * 100) / total_bytes)
            if bytes_written % 128 == 0 or bytes_written >= total_bytes:
                if progress != last_progress:
                    elapsed = time.time() - start_time
                    speed = bytes_written / elapsed / 1024 if elapsed > 0 else 0
                    eta = (total_bytes - bytes_written) / (bytes_written / elapsed) if elapsed > 0 and bytes_written > 0 else 0
                    print(f"Progress: {progress:3d}% [{bytes_written}/{total_bytes} bytes] "
                          f"Speed: {speed:.1f} KB/s ETA: {eta:.1f}s", end='\r')
                    last_progress = progress
        
        elapsed = time.time() - start_time
        avg_speed = total_bytes / elapsed / 1024 if elapsed > 0 else 0
        print(f"\n\n✓ Firmware written successfully!")
        print(f"  Total time: {elapsed:.1f}s")
        print(f"  Average speed: {avg_speed:.1f} KB/s\n")
        
        return True
    
    def verify_flash(self, expected_data: bytes) -> bool:
        """
        Verify flashed data by reading back and comparing.
        
        Args:
            expected_data: Expected binary data
            
        Returns:
            True if verification successful
        """
        print("\n" + "="*60)
        print("Verifying flash contents...")
        print("="*60)
        
        address = APP_START_ADDRESS
        bytes_verified = 0
        chunk_size = 4  # Read 4 bytes at a time for consistency with write
        
        start_time = time.time()
        last_progress = -1
        mismatch_count = 0
        first_mismatch_addr = None
        
        while bytes_verified < len(expected_data):
            # Read chunk
            remaining = len(expected_data) - bytes_verified
            read_size = min(chunk_size, remaining)
            
            read_data = self.read_data(address, read_size)
            
            if read_data is None:
                print(f"\n\n{'='*60}")
                print("✗ VERIFICATION FAILED - READ ERROR")
                print("="*60)
                print(f"Failed to read data at address: 0x{address:08X}")
                print(f"Bytes verified so far: {bytes_verified}/{len(expected_data)} ({bytes_verified*100//len(expected_data)}%)")
                print(f"Offset in file: 0x{bytes_verified:08X} ({bytes_verified} bytes)")
                print("\nPossible causes:")
                print("  1. Communication timeout with bootloader")
                print("  2. Invalid flash address")
                print("  3. Bootloader not responding")
                print(f"  4. CAN bus issue (check connection)")
                return False
            
            # Compare
            expected_chunk = expected_data[bytes_verified:bytes_verified + read_size]
            
            if read_data != expected_chunk:
                # Detailed mismatch analysis
                if first_mismatch_addr is None:
                    first_mismatch_addr = address
                mismatch_count += 1
                
                print(f"\n\n{'='*60}")
                print("✗ VERIFICATION FAILED - DATA MISMATCH")
                print("="*60)
                print(f"Mismatch detected at flash address: 0x{address:08X}")
                print(f"File offset: 0x{bytes_verified:08X} ({bytes_verified} bytes)")
                print(f"Progress: {bytes_verified}/{len(expected_data)} bytes ({bytes_verified*100//len(expected_data)}%)")
                print(f"\nChunk size: {read_size} bytes")
                print(f"\nExpected data: {expected_chunk.hex().upper()}")
                print(f"  Binary: {' '.join(f'{b:08b}' for b in expected_chunk)}")
                print(f"  Decimal: {' '.join(f'{b:3d}' for b in expected_chunk)}")
                print(f"  ASCII: {''.join(chr(b) if 32 <= b < 127 else '.' for b in expected_chunk)}")
                
                print(f"\nActual data:   {read_data.hex().upper()}")
                print(f"  Binary: {' '.join(f'{b:08b}' for b in read_data)}")
                print(f"  Decimal: {' '.join(f'{b:3d}' for b in read_data)}")
                print(f"  ASCII: {''.join(chr(b) if 32 <= b < 127 else '.' for b in read_data)}")
                
                # Bit-level diff
                print(f"\nBit differences:")
                for i in range(len(expected_chunk)):
                    if i < len(read_data):
                        if expected_chunk[i] != read_data[i]:
                            xor_val = expected_chunk[i] ^ read_data[i]
                            print(f"  Byte {i}: Expected 0x{expected_chunk[i]:02X}, Got 0x{read_data[i]:02X}, XOR: 0x{xor_val:02X} (bits differ: {bin(xor_val)})")
                
                # Context: show surrounding addresses
                print(f"\nContext (surrounding flash memory):")
                context_start = max(address - 16, APP_START_ADDRESS)
                context_end = min(address + 16, APP_START_ADDRESS + len(expected_data))
                print(f"  Addresses 0x{context_start:08X} to 0x{context_end:08X}")
                print(f"  Current mismatch is at 0x{address:08X}")
                
                # Read a larger chunk for context
                try:
                    before_offset = max(0, bytes_verified - 8)
                    after_offset = min(len(expected_data), bytes_verified + read_size + 8)
                    context_expected = expected_data[before_offset:after_offset]
                    print(f"\nExpected context ({len(context_expected)} bytes from file offset 0x{before_offset:08X}):")
                    print(f"  {context_expected.hex().upper()}")
                except:
                    pass
                
                print(f"\nDebugging information:")
                print(f"  Device type: {self.device_type.upper()}")
                print(f"  Channel: {self.channel}")
                print(f"  Total firmware size: {len(expected_data)} bytes ({len(expected_data)/1024:.2f} KB)")
                print(f"  Bytes written successfully: {bytes_verified}")
                print(f"  Write may have been interrupted or corrupted")
                
                print(f"\nSuggested actions:")
                print(f"  1. Re-flash the firmware (erase + write again)")
                print(f"  2. Check CAN bus wiring and termination")
                print(f"  3. Verify power supply is stable")
                print(f"  4. Try reducing flash speed (increase delay)")
                print(f"  5. Check for electromagnetic interference")
                
                return False
            
            bytes_verified += read_size
            address += read_size
            
            # Update progress every 128 bytes
            progress = int((bytes_verified * 100) / len(expected_data))
            if bytes_verified % 128 == 0 or bytes_verified >= len(expected_data):
                if progress != last_progress:
                    elapsed = time.time() - start_time
                    speed = bytes_verified / elapsed / 1024 if elapsed > 0 else 0
                    print(f"Verifying: {progress:3d}% [{bytes_verified}/{len(expected_data)} bytes] "
                          f"Speed: {speed:.1f} KB/s", end='\r')
                    last_progress = progress
        
        elapsed = time.time() - start_time
        print(f"\n\n✓ Verification successful ({bytes_verified} bytes)")
        print(f"  Total time: {elapsed:.1f}s")
        print(f"  All {bytes_verified} bytes match expected data")
        print(f"  Flash integrity confirmed!\n")
        
        return True
    
    def jump_to_application(self) -> bool:
        """
        Command bootloader to jump to application.
        
        Returns:
            True if command sent successfully
        """
        print("\n" + "="*60)
        print("Jumping to application...")
        print("="*60)
        
        # Send JUMP command
        if not self.send_command(CMD_JUMP_TO_APP, []):
            print("✗ Failed to send jump command")
            return False
        
        # Wait for ACK (bootloader may not respond if it successfully jumps)
        resp = self.wait_response(timeout=0.5)
        
        if resp:
            if resp.data[0] == RESP_ACK:
                print("✓ Application started\n")
                return True
            elif resp.data[0] == RESP_NACK:
                error_code = resp.data[1] if len(resp.data) > 1 else 0
                error_desc = ERROR_DESCRIPTIONS.get(error_code, f"Error {error_code}")
                print(f"✗ Jump failed: {error_desc}")
                return False
        else:
            # No response might mean bootloader successfully jumped
            print("✓ Command sent (bootloader may have jumped)\n")
            return True
        
        return False
    
    def flash_firmware(self, firmware_path: Path, verify: bool = True, 
                      jump: bool = True) -> bool:
        """
        Complete firmware flashing process.
        
        Args:
            firmware_path: Path to .bin file
            verify: Verify by reading back after writing (default: True)
            jump: Jump to application after flashing (default: True)
        
        Returns:
            True if flashing successful
        """
        # Read firmware file
        print(f"\n{'='*60}")
        print(f"Loading firmware: {firmware_path.name}")
        print(f"{'='*60}")
        
        try:
            firmware_data = firmware_path.read_bytes()
            original_size = len(firmware_data)
            
            # Pad to 4-byte boundary (ensures 8-byte alignment)
            firmware_data = self.pad_to_4byte_boundary(firmware_data)
            
            print(f"✓ Loaded {original_size} bytes ({original_size/1024:.2f} KB)")
            if len(firmware_data) != original_size:
                print(f"  Padded to {len(firmware_data)} bytes (4-byte aligned)\n")
            else:
                print()
        except Exception as e:
            print(f"✗ Failed to read firmware file: {e}")
            return False
        
        # Validate size
        if len(firmware_data) > APP_MAX_SIZE:
            print(f"✗ Firmware too large ({len(firmware_data)} bytes > {APP_MAX_SIZE} bytes)")
            return False
        
        # Get initial status
        status = self.get_status()
        if not status:
            print("⚠ Warning: Could not get bootloader status")
            print("  Continuing anyway...\n")
        
        # Erase flash
        if not self.erase_flash():
            return False
        
        # Write firmware
        if not self.write_firmware(firmware_data):
            return False
        
        # Verify by reading back
        if verify:
            if not self.verify_flash(firmware_data):
                print("⚠ Warning: Flash verification failed")
                return False
        
        # Jump to application
        if jump:
            if not self.jump_to_application():
                print("⚠ Warning: Jump command may have failed")
        
        return True


# ============================================================================
# Main Function
# ============================================================================

def main():
    """Main entry point for the script."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Flash firmware to STM32L432 via CAN bootloader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Using PCAN (default)
  python Flash_Application.py application.bin
  python Flash_Application.py application.bin --device pcan --channel USB1
  
  # Using CANable (specify device index)
  python Flash_Application.py application.bin --device canable --channel 0
  python Flash_Application.py application.bin --device canable --channel 1
  
  # Additional options
  python Flash_Application.py application.bin --no-verify
  python Flash_Application.py application.bin --no-jump
  python Flash_Application.py application.bin --status-only
        '''
    )
    
    parser.add_argument('firmware', type=str, nargs='?',
                       help='Path to firmware .bin file')
    parser.add_argument('--device', type=str, default='pcan',
                       choices=['pcan', 'canable'],
                       help='CAN adapter type (default: pcan)')
    parser.add_argument('--channel', type=str, default=None,
                       help='PCAN channel (e.g., USB1) or CANable device index (e.g., 0, 1, 2)')
    parser.add_argument('--verify', action='store_true', default=True,
                       help='Verify by reading back after flashing (default: enabled)')
    parser.add_argument('--no-verify', action='store_false', dest='verify',
                       help='Skip read-back verification')
    parser.add_argument('--jump', action='store_true', default=True,
                       help='Jump to application after flashing (default: enabled)')
    parser.add_argument('--no-jump', action='store_false', dest='jump',
                       help='Stay in bootloader after flashing')
    parser.add_argument('--status-only', action='store_true',
                       help='Only get bootloader status and exit')
    parser.add_argument('--list-devices', action='store_true',
                       help='List available CAN devices and exit')
    
    args = parser.parse_args()
    
    # Print banner
    print("\n" + "="*60)
    print("STM32L432 CAN Bootloader Flash Tool")
    print("="*60)
    print(f"Version: 1.0")
    print(f"Date: October 10, 2025")
    print("="*60 + "\n")
    
    # Determine device type and channel
    device_type = args.device.lower()
    
    # Set default channel based on device type
    if args.channel:
        channel = args.channel
    else:
        if device_type == 'pcan':
            channel = 'USB1'  # Default PCAN channel
        else:
            channel = '0'  # Default CANable device index
    
    # List devices if requested
    if args.list_devices:
        if device_type == 'pcan':
            if not PCAN_AVAILABLE:
                print("✗ PCAN driver not available")
                return 1
            driver = PCANDriver()
            print("Scanning for PCAN devices...\n")
            devices = driver.get_available_devices()
            
            if not devices:
                print("✗ No PCAN devices found")
                return 1
            
            print(f"Found {len(devices)} device(s):\n")
            for dev in devices:
                status = "OCCUPIED" if dev['occupied'] else "AVAILABLE"
                print(f"  {dev['channel']:10s} : {status}")
        
        elif device_type == 'canable':
            if not CANABLE_AVAILABLE:
                print("✗ CANable driver not available")
                return 1
            driver = CANableDriver()
            print("Scanning for CANable devices (USB)...\n")
            devices = driver.get_available_devices()
            
            if not devices:
                print("✗ No CANable/gs_usb devices found")
                print("\nMake sure:")
                print("  1. CANable is connected via USB")
                print("  2. Device has candleLight firmware")
                print("  3. libusb-1.0.dll is in the project directory (Windows)")
                return 1
            
            print(f"Found {len(devices)} CANable/gs_usb device(s):\n")
            for dev in devices:
                print(f"  [Index {dev['index']}] {dev['description']}")
                print(f"      VID: 0x{dev['vid']:04X}, PID: 0x{dev['pid']:04X}")
                print(f"      Serial: {dev['serial_number']}")
                print()
        
        print()
        return 0
    
    # Check firmware file
    if not args.status_only and not args.firmware:
        parser.print_help()
        return 1
    
    if args.firmware:
        firmware_path = Path(args.firmware)
        if not firmware_path.exists():
            print(f"✗ Error: Firmware file not found: {firmware_path}")
            return 1
    
    # Create flasher instance
    try:
        if device_type == 'pcan':
            if not PCAN_AVAILABLE:
                print("✗ Error: PCAN driver not available")
                print("  Please ensure PCAN_Driver.py is in the drivers/ directory")
                return 1
            pcan_channel = PCANChannel[channel] if channel in [c.name for c in PCANChannel] else PCANChannel.USB1
            flasher = CANBootloaderFlash(device_type='pcan', channel=pcan_channel)
        else:  # canable
            if not CANABLE_AVAILABLE:
                print("✗ Error: CANable driver not available")
                print("  Please ensure CANable_Driver.py is in the drivers/ directory")
                return 1
            # Convert channel to integer
            try:
                channel_index = int(channel)
            except ValueError:
                print(f"✗ Error: Invalid CANable channel index: {channel}")
                print("  Expected an integer (0, 1, 2, ...) representing device index")
                print("  Use --list-devices to see available devices")
                return 1
            flasher = CANBootloaderFlash(device_type='canable', channel=channel_index)
    except Exception as e:
        print(f"✗ Error creating flasher: {e}")
        return 1
    
    try:
        # Connect to CAN device
        if not flasher.connect():
            return 1
        
        # Status only mode
        if args.status_only:
            status = flasher.get_status()
            return 0 if status else 1
        
        # Flash firmware
        print(f"Firmware file: {firmware_path}")
        print(f"Device type:   {device_type.upper()}")
        print(f"Channel/Port:  {channel}")
        print(f"Read-back verify: {'Yes' if args.verify else 'No'}")
        print(f"Jump to app:   {'Yes' if args.jump else 'No'}")
        
        success = flasher.flash_firmware(
            firmware_path,
            verify=args.verify,
            jump=args.jump
        )
        
        if success:
            print("\n" + "="*60)
            print("✓ FLASHING COMPLETED SUCCESSFULLY!")
            print("="*60 + "\n")
            return 0
        else:
            print("\n" + "="*60)
            print("✗ FLASHING FAILED")
            print("="*60 + "\n")
            return 1
    
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        return 1
    
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Always disconnect
        flasher.disconnect()


if __name__ == '__main__':
    sys.exit(main())
