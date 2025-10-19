# DBC File Format Guide for Extended CAN IDs

## Complete Reference for AI-Assisted DBC File Generation

---

## Table of Contents
1. [Overview](#overview)
2. [Critical Rules](#critical-rules)
3. [Extended CAN ID Encoding](#extended-can-id-encoding)
4. [File Structure](#file-structure)
5. [Message Definition Format](#message-definition-format)
6. [Signal Definition Format](#signal-definition-format)
7. [Attributes and Metadata](#attributes-and-metadata)
8. [Common Mistakes to Avoid](#common-mistakes-to-avoid)
9. [Validation Checklist](#validation-checklist)
10. [Complete Example](#complete-example)

---

## Overview

A DBC (CAN Database) file is a text-based format that defines:
- CAN message IDs and names
- Signal definitions (bits, scaling, units)
- Node/ECU definitions
- Attributes and metadata
- Value tables for enumerations

This guide focuses on **Extended 29-bit CAN IDs** using the **Bit 31 Flag Method**.

---

## Critical Rules

### Rule 1: Extended CAN ID Encoding
**FOR EXTENDED (29-BIT) CAN IDs:**
```
DBC_Frame_ID = Actual_29bit_CAN_ID | 0x80000000
```

**ALWAYS** set bit 31 (0x80000000) in the frame ID to indicate extended format.

### Rule 2: Decimal Conversion Formula
```python
# Convert hex CAN ID to DBC decimal ID
actual_can_id = 0x08F00300  # Your actual 29-bit CAN ID
dbc_decimal_id = actual_can_id | 0x80000000  # Set bit 31

# Example:
# 0x08F00300 | 0x80000000 = 0x88F00300 = 2297430784 (decimal)
```

### Rule 3: Cantools Behavior
- **cantools library** automatically **strips bit 31** when parsing
- Your code must add bit 31 back when decoding: `lookup_id = can_id | 0x80000000`
- The DBC file stores IDs **with bit 31 set**, cantools exposes them **without bit 31**

### Rule 4: Standard vs Extended Format
```
Standard (11-bit):  0x000 to 0x7FF (0-2047)
Extended (29-bit):  0x00000000 to 0x1FFFFFFF (0-536870911)
DBC Extended:       Add 0x80000000 to extended IDs
```

---

## Extended CAN ID Encoding

### Why Bit 31?
The DBC file format was designed for 11-bit standard CAN IDs. To support 29-bit extended IDs, the convention is:
- **Bit 31 = 0**: Standard 11-bit CAN ID
- **Bit 31 = 1**: Extended 29-bit CAN ID

### Conversion Table

| Description | Hex | Decimal | Notes |
|-------------|-----|---------|-------|
| Actual CAN ID | 0x08F00000 | 149946368 | What hardware sees |
| DBC File ID | 0x88F00000 | 2297430016 | With bit 31 set |
| Bit 31 mask | 0x80000000 | 2147483648 | The extended flag |
| **Formula** | `actual \| 0x80000000` | `actual + 2147483648` | Conversion |

### Python Conversion Examples

```python
# Converting actual CAN IDs to DBC format
can_ids = {
    'Heartbeat': 0x08F00300,
    'Temperature': 0x08F00000,
    'Status': 0x08F00301,
    'Config': 0x08F00F00,
}

dbc_ids = {}
for name, can_id in can_ids.items():
    dbc_id = can_id | 0x80000000
    print(f"{name:15s}: 0x{can_id:08X} -> 0x{dbc_id:08X} ({dbc_id})")
    dbc_ids[name] = dbc_id

# Output:
# Heartbeat      : 0x08F00300 -> 0x88F00300 (2297430784)
# Temperature    : 0x08F00000 -> 0x88F00000 (2297430016)
# Status         : 0x08F00301 -> 0x88F00301 (2297430785)
# Config         : 0x08F00F00 -> 0x88F00F00 (2297433856)
```

### Decoding in Application Code

```python
import cantools

# Load DBC file
db = cantools.database.load_file('my_file.dbc')

# Receive CAN message
msg = can_bus.recv()  # msg.arbitration_id = 0x08F00300

# cantools strips bit 31, so we must add it back for lookup
if msg.is_extended_id:
    lookup_id = msg.arbitration_id | 0x80000000
else:
    lookup_id = msg.arbitration_id

# Decode using the lookup_id
decoded = db.decode_message(lookup_id, msg.data)
```

---

## File Structure

### 1. Header Section
```dbc
VERSION ""

NS_ : 
	NS_DESC_
	CM_
	BA_DEF_
	BA_
	VAL_
	CAT_DEF_
	CAT_
	FILTER
	BA_DEF_DEF_
	EV_DATA_
	ENVVAR_DATA_
	SGTYPE_
	SGTYPE_VAL_
	BA_DEF_SGTYPE_
	BA_SGTYPE_
	SIG_TYPE_REF_
	VAL_TABLE_
	SIG_GROUP_
	SIG_VALTYPE_
	SIGTYPE_VALTYPE_
	BO_TX_BU_
	BA_DEF_REL_
	BA_REL_
	BA_SGTYPE_REL_
	SG_MUL_VAL_

BS_:
```

### 2. Node/ECU Definitions
```dbc
BU_: ECU_Name1 ECU_Name2 ECU_Name3
```

**Rules:**
- Space-separated list
- No special characters except underscore
- Names must be unique

### 3. Attribute Definitions
```dbc
BA_DEF_ BO_  "VFrameFormat" ENUM  "StandardCAN","ExtendedCAN";
BA_DEF_ BO_  "GenMsgCycleTime" INT 0 10000;
BA_DEF_DEF_  "VFrameFormat" "StandardCAN";
BA_DEF_DEF_  "GenMsgCycleTime" 0;
```

---

## Message Definition Format

### Basic Syntax
```dbc
BO_ <Frame_ID> <Message_Name>: <DLC> <Transmitter>
 SG_ <Signal_Name> : <Start_Bit>|<Bit_Length>@<Byte_Order><Value_Type> (<Factor>,<Offset>) [<Min>|<Max>] "<Unit>" <Receiver1>,<Receiver2>
```

### Field Breakdown

#### Frame_ID (DECIMAL)
- **Must be decimal**, not hex
- For extended IDs: `actual_can_id | 0x80000000`
- Example: `2297430784` (which is 0x88F00300)

#### Message_Name
- Alphanumeric and underscore only
- Must be unique
- Example: `BMS_Heartbeat`, `Motor_Speed_CMD`

#### DLC (Data Length Code)
- Number of bytes: `0` to `8`
- Classic CAN max: `8`
- CAN-FD can be higher (not covered here)

#### Transmitter
- Name of ECU/node that sends this message
- Must match name in `BU_` definition
- Can be `Vector__XXX` for unknown

### Example Message
```dbc
BO_ 2297430784 BMS_Heartbeat: 8 BMS_Controller
 SG_ BMS_State : 0|8@1+ (1,0) [0|7] "" CAN_Receiver
 SG_ Error_Flags : 8|16@1+ (1,0) [0|65535] "" CAN_Receiver
 SG_ Temperature : 24|16@1- (0.1,-40) [-40|125] "degC" CAN_Receiver
```

**This defines:**
- Message ID: 0x88F00300 (extended, actual CAN ID 0x08F00300)
- Name: BMS_Heartbeat
- Size: 8 bytes
- Sender: BMS_Controller
- 3 signals defined

---

## Signal Definition Format

### Signal Syntax Components

```
SG_ Signal_Name : Start_Bit|Bit_Length@Byte_Order Value_Type (Factor,Offset) [Min|Max] "Unit" Receivers
```

### Start_Bit
- Bit position where signal starts (0-63 for 8-byte message)
- **Bit 0** = LSB of first byte (byte 0)
- **Bit numbering depends on byte order**

### Byte Order
- `@1` or `@1+`: **Little Endian** (Intel format) - most common
- `@0` or `@0+`: **Big Endian** (Motorola format)

### Value Type
- `+`: **Unsigned** (always positive)
- `-`: **Signed** (two's complement, can be negative)

### Factor and Offset
Used to convert raw integer to physical value:
```
Physical_Value = (Raw_Value × Factor) + Offset
```

**Examples:**
```dbc
(1,0)      # No scaling, raw value = physical value
(0.1,0)    # Divide by 10: raw 235 = 23.5
(0.01,-40) # Scale and offset: raw 1500 = (1500 × 0.01) - 40 = -25.0
(2,-100)   # Multiply and offset: raw 150 = (150 × 2) - 100 = 200
```

### Min and Max
- `[Min|Max]`: Valid range of physical values
- Used for validation
- Example: `[-40|125]` for temperature in Celsius

### Unit
- String in quotes: `"degC"`, `"km/h"`, `"A"`, `""`
- Empty string `""` for dimensionless

### Receivers
- Comma-separated list of ECUs that receive this signal
- Example: `CAN_Host,Logger,Display`

---

## Signal Layout Examples

### Example 1: Simple Unsigned Byte
```dbc
SG_ Status : 0|8@1+ (1,0) [0|255] "" Receiver
```
- Bits 0-7 (byte 0)
- Unsigned 8-bit
- No scaling
- Range: 0-255

### Example 2: Temperature (Signed, Scaled)
```dbc
SG_ Temperature : 16|16@1- (0.1,0) [-40|125] "degC" Receiver
```
- Bits 16-31 (bytes 2-3)
- Signed 16-bit (two's complement)
- Scale by 0.1 (raw value 235 = 23.5°C)
- Range: -40°C to 125°C

### Example 3: Multi-byte Little Endian
```dbc
SG_ Timestamp : 32|32@1+ (1,0) [0|4294967295] "ms" Receiver
```
- Bits 32-63 (bytes 4-7)
- Unsigned 32-bit
- Little endian
- Range: 0 to 4,294,967,295 ms

### Example 4: Bitfield Flags
```dbc
SG_ Flag_A : 0|1@1+ (1,0) [0|1] "" Receiver
SG_ Flag_B : 1|1@1+ (1,0) [0|1] "" Receiver
SG_ Flag_C : 2|1@1+ (1,0) [0|1] "" Receiver
SG_ Reserved : 3|5@1+ (1,0) [0|31] "" Receiver
```
- Individual bits as separate signals
- Byte 0: `[Flag_A, Flag_B, Flag_C, Reserved(5 bits)]`

---

## Attributes and Metadata

### VFrameFormat Attribute
**CRITICAL:** Mark each extended message with VFrameFormat attribute:

```dbc
BA_ "VFrameFormat" BO_ 2297430784 1;
```

- `BO_` indicates this is a message attribute
- `2297430784` is the message ID (decimal)
- `1` means ExtendedCAN (0 = StandardCAN)

### Message Cycle Time
```dbc
BA_ "GenMsgCycleTime" BO_ 2297430784 1000;
```
- Transmission period in milliseconds
- `1000` = sent every 1 second

### Comments
```dbc
CM_ BO_ 2297430784 "Heartbeat message transmitted every 1 second with system status";
CM_ SG_ 2297430784 BMS_State "0=INIT, 1=IDLE, 2=CHARGING, 3=DISCHARGING, 4=ERROR";
```

### Value Tables (Enumerations)
```dbc
VAL_ 2297430784 BMS_State 0 "INIT" 1 "IDLE" 2 "CHARGING" 3 "DISCHARGING" 4 "BALANCING" 5 "ERROR" 6 "SHUTDOWN" 7 "RESERVED";
```

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Using Hex Instead of Decimal
```dbc
BO_ 0x88F00300 BMS_Heartbeat: 8 BMS_Controller  # WRONG!
```
✅ **Correct:**
```dbc
BO_ 2297430784 BMS_Heartbeat: 8 BMS_Controller
```

### ❌ Mistake 2: Wrong Bit 31 Calculation
```dbc
# WRONG - Forgot to set bit 31
BO_ 149946368 BMS_Heartbeat: 8 BMS_Controller  # This is 0x08F00300
```
✅ **Correct:**
```dbc
# Must add 0x80000000
BO_ 2297430016 BMS_Heartbeat: 8 BMS_Controller  # This is 0x88F00300
```

### ❌ Mistake 3: Incorrect Decimal Calculation
```python
# WRONG calculation
0x08F00300 = 149946368
149946368 + 0x80000000 = 2297430016  # This is WRONG!

# The hex changes, not just addition!
```
✅ **Correct:**
```python
# Correct bitwise OR
0x08F00300 | 0x80000000 = 0x88F00300 = 2297430784
```

### ❌ Mistake 4: Forgetting VFrameFormat Attribute
```dbc
BO_ 2297430784 BMS_Heartbeat: 8 BMS_Controller
# Missing: BA_ "VFrameFormat" BO_ 2297430784 1;
```

### ❌ Mistake 5: Signal Bit Overlap
```dbc
SG_ Signal_A : 0|16@1+ (1,0) [0|65535] "" Receiver  # Bits 0-15
SG_ Signal_B : 8|16@1+ (1,0) [0|65535] "" Receiver  # Bits 8-23 - OVERLAPS!
```

### ❌ Mistake 6: Signal Exceeds Message Length
```dbc
BO_ 2297430784 BMS_Status: 4 BMS_Controller  # 4 bytes = 32 bits
 SG_ Data : 0|64@1+ (1,0) [0|999999] "" Receiver  # 64 bits - TOO BIG!
```

### ❌ Mistake 7: Duplicate Message IDs
```dbc
BO_ 2297430784 Message_A: 8 ECU1
BO_ 2297430784 Message_B: 8 ECU2  # DUPLICATE ID!
```

---

## Validation Checklist

Before finalizing your DBC file, verify:

- [ ] **All extended IDs have bit 31 set** (0x80000000)
- [ ] **All IDs are in decimal format**, not hex
- [ ] **Decimal values match hex with bit 31**: `0x88F00300 = 2297430784`
- [ ] **No duplicate message IDs**
- [ ] **All node names in messages exist in BU_ line**
- [ ] **Signal bits don't overlap within same message**
- [ ] **Signal bits don't exceed message DLC** (DLC×8 bits)
- [ ] **VFrameFormat attribute set for all extended messages**
- [ ] **Factor/offset calculations are correct**
- [ ] **Min/Max ranges are in physical units** (after scaling)
- [ ] **Value tables reference valid message IDs**
- [ ] **Comments reference valid message/signal IDs**

### Automated Validation Script

```python
import cantools

def validate_dbc_file(dbc_path, expected_ids):
    """
    Validate DBC file against expected CAN IDs.
    
    Args:
        dbc_path: Path to DBC file
        expected_ids: Dict of {name: actual_can_id_hex}
    """
    db = cantools.database.load_file(dbc_path)
    
    print(f"Validating: {dbc_path}")
    print("="*70)
    
    errors = []
    
    for name, expected_can_id in expected_ids.items():
        try:
            msg = db.get_message_by_name(name)
            
            # cantools strips bit 31, so we check without it
            if msg.frame_id != expected_can_id:
                errors.append(
                    f"❌ {name}: Expected 0x{expected_can_id:08X}, "
                    f"got 0x{msg.frame_id:08X}"
                )
            else:
                print(f"✅ {name}: 0x{msg.frame_id:08X}")
                
        except KeyError:
            errors.append(f"❌ {name}: Message not found in DBC")
    
    if errors:
        print("\nERRORS FOUND:")
        for error in errors:
            print(error)
        return False
    else:
        print("\n✅ All validations passed!")
        return True

# Usage
expected = {
    'BMS_Heartbeat': 0x08F00300,
    'BMS_Temperature': 0x08F00000,
    'BMS_Status': 0x08F00301,
}

validate_dbc_file('my_file.dbc', expected)
```

---

## Complete Example

### Scenario: BMS with Module-Based CAN IDs

**CAN ID Structure:**
```
Bits 28-24: Priority (0x08)
Bits 23-16: Message Type (0xF0 = BMS)
Bits 15-12: Module ID (0-15)
Bits 11-8:  Message Group
Bits 7-0:   Message Index
```

**Module 0 Messages:**
- Heartbeat: 0x08F00300 (no module offset)
- Temperature: 0x08F00000
- Status: 0x08F00301

**Module 1 Messages:** (add 0x1000 for module ID 1)
- Heartbeat: 0x08F01300
- Temperature: 0x08F01000
- Status: 0x08F01301

### Complete DBC File

```dbc
VERSION ""

// ==============================================================================
// BMS FIRMWARE DBC FILE
// ==============================================================================
// Extended CAN IDs: DBC_ID = actual_29bit_id | 0x80000000
// 
// CAN ID STRUCTURE:
//   Bits 28-24: Priority (0x08)
//   Bits 23-16: Message Type (0xF0 = BMS data)
//   Bits 15-12: Module ID (0-15)
//   Bits 11-8:  Message Group (0=temps, 3=status)
//   Bits 7-0:   Message Index
//
// CONVERSION FORMULA:
//   Python: dbc_id = can_id | 0x80000000
//   Example: 0x08F00300 | 0x80000000 = 0x88F00300 = 2297430784
// ==============================================================================

NS_ : 
	NS_DESC_
	CM_
	BA_DEF_
	BA_
	VAL_
	CAT_DEF_
	CAT_
	FILTER
	BA_DEF_DEF_
	EV_DATA_
	ENVVAR_DATA_
	SGTYPE_
	SGTYPE_VAL_
	BA_DEF_SGTYPE_
	BA_SGTYPE_
	SIG_TYPE_REF_
	VAL_TABLE_
	SIG_GROUP_
	SIG_VALTYPE_
	SIGTYPE_VALTYPE_
	BO_TX_BU_
	BA_DEF_REL_
	BA_REL_
	BA_SGTYPE_REL_
	SG_MUL_VAL_

BS_:

BU_: BMS_Module_0 BMS_Module_1 CAN_Host

BA_DEF_ BO_  "VFrameFormat" ENUM  "StandardCAN","ExtendedCAN";
BA_DEF_ BO_  "GenMsgCycleTime" INT 0 10000;
BA_DEF_DEF_  "VFrameFormat" "StandardCAN";
BA_DEF_DEF_  "GenMsgCycleTime" 0;

// Module 0 - Heartbeat (0x08F00300 | 0x80000000 = 0x88F00300 = 2297430784)
BO_ 2297430784 BMS_Mod0_Heartbeat: 8 BMS_Module_0
 SG_ BMS_State : 0|8@1+ (1,0) [0|7] "" CAN_Host
 SG_ Error_Flags_Byte0 : 8|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Error_Flags_Byte1 : 16|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Error_Flags_Byte2 : 24|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Error_Flags_Byte3 : 32|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Warning_Summary : 40|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Fault_Count : 48|16@1+ (1,0) [0|65535] "" CAN_Host

// Module 0 - Status (0x08F00301 | 0x80000000 = 0x88F00301 = 2297430785)
BO_ 2297430785 BMS_Mod0_Status: 8 BMS_Module_0
 SG_ RX_Message_Count : 0|16@1+ (1,0) [0|65535] "" CAN_Host
 SG_ TX_Success_Count : 16|16@1+ (1,0) [0|65535] "" CAN_Host
 SG_ TX_Error_Count : 32|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Bus_Off_Count : 40|8@1+ (1,0) [0|255] "" CAN_Host

// Module 0 - Temperature (0x08F00000 | 0x80000000 = 0x88F00000 = 2297430016)
BO_ 2297430016 BMS_Mod0_Temperature: 8 BMS_Module_0
 SG_ Temp_000 : 0|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_001 : 16|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_002 : 32|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_003 : 48|16@1- (0.1,0) [-40|125] "degC" CAN_Host

// Module 1 - Heartbeat (0x08F01300 | 0x80000000 = 0x88F01300 = 2297434880)
BO_ 2297434880 BMS_Mod1_Heartbeat: 8 BMS_Module_1
 SG_ BMS_State : 0|8@1+ (1,0) [0|7] "" CAN_Host
 SG_ Error_Flags_Byte0 : 8|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Error_Flags_Byte1 : 16|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Error_Flags_Byte2 : 24|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Error_Flags_Byte3 : 32|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Warning_Summary : 40|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Fault_Count : 48|16@1+ (1,0) [0|65535] "" CAN_Host

// Module 1 - Status (0x08F01301 | 0x80000000 = 0x88F01301 = 2297434881)
BO_ 2297434881 BMS_Mod1_Status: 8 BMS_Module_1
 SG_ RX_Message_Count : 0|16@1+ (1,0) [0|65535] "" CAN_Host
 SG_ TX_Success_Count : 16|16@1+ (1,0) [0|65535] "" CAN_Host
 SG_ TX_Error_Count : 32|8@1+ (1,0) [0|255] "" CAN_Host
 SG_ Bus_Off_Count : 40|8@1+ (1,0) [0|255] "" CAN_Host

// Module 1 - Temperature (0x08F01000 | 0x80000000 = 0x88F01000 = 2297434112)
BO_ 2297434112 BMS_Mod1_Temperature: 8 BMS_Module_1
 SG_ Temp_000 : 0|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_001 : 16|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_002 : 32|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_003 : 48|16@1- (0.1,0) [-40|125] "degC" CAN_Host

// Comments
CM_ BO_ 2297430784 "Module 0 heartbeat - system status and error flags, sent every 1 second";
CM_ SG_ 2297430784 BMS_State "BMS State: 0=INIT, 1=IDLE, 2=CHARGING, 3=DISCHARGING, 4=BALANCING, 5=ERROR, 6=SHUTDOWN";
CM_ SG_ 2297430784 Error_Flags_Byte0 "Temperature error flags (bit 0=over temp, bit 1=under temp, bit 2=sensor fault)";
CM_ BO_ 2297430016 "Module 0 temperature readings - each value is temperature × 10 (0.1°C resolution), 0x8000 = invalid";

// Attributes
BA_ "VFrameFormat" BO_ 2297430784 1;
BA_ "VFrameFormat" BO_ 2297430785 1;
BA_ "VFrameFormat" BO_ 2297430016 1;
BA_ "VFrameFormat" BO_ 2297434880 1;
BA_ "VFrameFormat" BO_ 2297434881 1;
BA_ "VFrameFormat" BO_ 2297434112 1;

BA_ "GenMsgCycleTime" BO_ 2297430784 1000;
BA_ "GenMsgCycleTime" BO_ 2297430785 1000;
BA_ "GenMsgCycleTime" BO_ 2297430016 1000;
BA_ "GenMsgCycleTime" BO_ 2297434880 1000;
BA_ "GenMsgCycleTime" BO_ 2297434881 1000;
BA_ "GenMsgCycleTime" BO_ 2297434112 1000;

// Value tables
VAL_ 2297430784 BMS_State 0 "INIT" 1 "IDLE" 2 "CHARGING" 3 "DISCHARGING" 4 "BALANCING" 5 "ERROR" 6 "SHUTDOWN" 7 "RESERVED";
VAL_ 2297434880 BMS_State 0 "INIT" 1 "IDLE" 2 "CHARGING" 3 "DISCHARGING" 4 "BALANCING" 5 "ERROR" 6 "SHUTDOWN" 7 "RESERVED";
```

---

## AI Generation Prompt Template

When requesting AI to generate a DBC file, provide this structure:

```
Generate a DBC file for the following CAN messages using extended 29-bit IDs:

CRITICAL REQUIREMENTS:
1. All frame IDs MUST be in DECIMAL format
2. For extended IDs, use formula: DBC_ID = (CAN_ID | 0x80000000)
3. Add VFrameFormat attribute for each extended message
4. No duplicate message IDs
5. Signals must not overlap or exceed message DLC

CAN ID STRUCTURE:
[Describe your bit layout]

MESSAGES:
Message Name: [Name]
CAN ID (hex): 0x[8 digits]
DLC: [bytes]
Transmitter: [node name]
Signals:
  - Signal_Name: Byte [X], Bits [Y-Z], Type: [Unsigned/Signed], Scaling: [factor, offset], Unit: [unit], Range: [min-max]
  [repeat for each signal]

[Repeat for each message]

NODES:
- [Node1]
- [Node2]

ENUMERATIONS:
Message: [Message_Name], Signal: [Signal_Name]
  0: [Value_0_Name]
  1: [Value_1_Name]
  [etc.]
```

---

## Tools and Resources

### Recommended Tools
- **cantools** (Python): DBC parsing and message encoding/decoding
- **CANdb++ / Vector CANalyzer**: Professional DBC editing
- **PCAN-View**: Free CAN bus viewer with DBC support
- **Kvaser Database Editor**: Free DBC editor

### Online Calculators
```python
# Quick conversion calculator
def can_to_dbc_decimal(can_id_hex_string):
    """Convert hex CAN ID to DBC decimal"""
    can_id = int(can_id_hex_string, 16)
    dbc_id = can_id | 0x80000000
    print(f"CAN ID:  0x{can_id:08X} ({can_id})")
    print(f"DBC ID:  0x{dbc_id:08X} ({dbc_id})")
    return dbc_id

# Usage
can_to_dbc_decimal("0x08F00300")
```

---

## Summary

**Key Takeaways:**
1. **Always set bit 31** for extended CAN IDs: `dbc_id = can_id | 0x80000000`
2. **Use decimal values** in BO_ lines, not hex
3. **Verify calculations** with Python or calculator
4. **Add VFrameFormat attribute** for each extended message
5. **Test with cantools** to ensure proper parsing
6. **Validate** against your actual CAN traffic

**Golden Rule:**
```python
DBC_Frame_ID = Actual_CAN_ID | 0x80000000
```

This document should be used as the definitive reference when generating or validating DBC files for extended CAN IDs.

---

**Document Version:** 1.0  
**Last Updated:** October 18, 2025  
**Author:** AI Assistant  
**License:** Public Domain
