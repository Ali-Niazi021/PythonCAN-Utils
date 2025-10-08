# DBC File Support - PythonCAN-GUI

## Overview

The PythonCAN-GUI now supports loading **DBC (CAN Database)** files for automatic decoding of CAN messages. This allows you to see human-readable signal values instead of just raw hex data.

---

## Installation

### Install Required Library

```bash
pip install cantools
```

Or install all requirements:

```bash
pip install -r requirements.txt
```

---

## Features

### 1. **Load DBC Files**
- Click the "Load DBC" button in the GUI
- Select your `.dbc` file
- The GUI will automatically decode all matching messages

### 2. **Automatic Message Decoding**
- Messages defined in the DBC are automatically decoded
- Signal names, values, and units are displayed in the "Decoded Signals" column
- Message names appear in the "Name" column

### 3. **Real-Time Updates**
- Decoded values update in real-time as new messages arrive
- Works seamlessly with existing message monitoring

### 4. **Export with Decoded Data**
- CSV exports now include both raw and decoded data
- Useful for data analysis and debugging

---

## Using DBC Files

### Step 1: Create or Obtain a DBC File

**Option A: Use the Template**
- See `DBC_TEMPLATE_GUIDE.md` for complete instructions
- Use `example_bootloader.dbc` as a reference

**Option B: Create Your Own**
Follow the guide in `DBC_TEMPLATE_GUIDE.md` to create a custom DBC file for your CAN network.

### Step 2: Load in GUI

1. **Launch the GUI**:
   ```bash
   python PythonCAN-GUI.py
   ```

2. **Click "Load DBC"** button in the status bar

3. **Select your `.dbc` file**

4. **Success!** You should see:
   - Green status text showing the loaded file name
   - Number of messages defined in the DBC

### Step 3: View Decoded Messages

Once connected to PCAN and receiving messages:

- **Name Column**: Shows message name from DBC (e.g., "EngineStatus")
- **Decoded Signals Column**: Shows all signals with values and units
  - Example: `EngineRPM: 2500.00 RPM | VehicleSpeed: 65.50 km/h | Gear: Third`

---

## Example Workflow

### Example: Bootloader Messages

Using `example_bootloader.dbc`:

1. **Load the DBC file** via the GUI

2. **Connect to PCAN**

3. **Send a bootloader command** (CAN ID 0x701):
   ```
   ID: 701
   Data: 05 00 00 00 00 00 00 00
   ```

4. **See decoded output**:
   ```
   Name: Host_TX
   Decoded: CommandType: CMD_GET_STATUS | Address: 0
   ```

5. **Receive bootloader response** (CAN ID 0x700):
   ```
   Name: Bootloader_TX
   Decoded: ResponseType: READY | ErrorCode: ERR_NONE | State: IDLE
   ```

---

## DBC File Format Quick Reference

### Basic Structure

```dbc
VERSION ""

NS_ : ...

BS_:

BU_: Node1 Node2

BO_ [CAN_ID] [MessageName]: [DLC] [Transmitter]
 SG_ [SignalName] : [StartBit]|[Length]@[ByteOrder][Type] ([Factor],[Offset]) [[Min]|[Max]] "[Unit]"  [Receivers]

VAL_ [CAN_ID] [SignalName] [Value] "[Description]" ;
```

### Signal Syntax

```
SG_ SignalName : StartBit|Length@ByteOrder DataType (Factor,Offset) [Min|Max] "Unit"  Receivers
```

**Parameters:**
- **StartBit**: Bit position (0-63)
- **Length**: Number of bits
- **ByteOrder**: `1` = Little-endian, `0` = Big-endian
- **DataType**: `+` = Unsigned, `-` = Signed
- **Factor**: Multiplier (e.g., 0.1)
- **Offset**: Added after multiplication (e.g., -40)
- **Unit**: Engineering unit (e.g., "RPM", "°C")

**Formula:**
```
Physical_Value = (Raw_Value × Factor) + Offset
```

---

## Creating a Custom DBC File

### Step-by-Step Example

**Scenario:** Temperature sensor on CAN ID 0x100

**Raw Message:**
- ID: 0x100
- Data: `1C 00 64 00 00 00 00 00`
- Byte 0: Temperature (28°C, with -40 offset → raw value = 68)
- Byte 2: Humidity (100%)

**DBC Definition:**

```dbc
VERSION ""

NS_ : 
    NS_DESC_
    CM_
    BA_DEF_
    BA_
    VAL_

BS_:

BU_: Sensor Controller

BO_ 256 TemperatureSensor: 8 Sensor
 SG_ Temperature : 0|8@1+ (1,-40) [-40|215] "degC"  Controller
 SG_ Humidity : 16|8@1+ (1,0) [0|100] "%"  Controller

CM_ SG_ 256 Temperature "Ambient temperature reading";
CM_ SG_ 256 Humidity "Relative humidity percentage";
```

**Result in GUI:**
```
Name: TemperatureSensor
Decoded: Temperature: 28.00 degC | Humidity: 100.00 %
```

---

## Troubleshooting

### "cantools not installed"

**Problem:** DBC support is disabled

**Solution:**
```bash
pip install cantools
```

### "DBC Load Failed"

**Problem:** Invalid DBC file format

**Solutions:**
- Check DBC syntax (see `DBC_TEMPLATE_GUIDE.md`)
- Validate with online DBC checker
- Check for missing semicolons or quotes

### "No decoded signals shown"

**Problem:** Message ID not defined in DBC

**Solutions:**
- Verify CAN ID matches DBC definition (decimal vs hex)
- Check that message is in the loaded DBC file
- Ensure DBC was loaded successfully (check status bar)

### "Decode error"

**Problem:** Data length mismatch or signal definition error

**Solutions:**
- Verify DLC matches DBC definition
- Check signal bit positions don't exceed data length
- Verify byte order (little/big endian)

---

## Advanced Features

### Multiple DBC Files

To work with multiple CAN networks:
1. Create separate DBC files for each network
2. Load the appropriate DBC when connecting to different devices
3. Use "Clear DBC" to unload and switch files

### Value Tables (Enumerations)

For signals with discrete states:

```dbc
VAL_ 512 CurrentGear 0 "Neutral" 1 "First" 2 "Second" 3 "Third" ;
```

Result:
```
CurrentGear: First (instead of CurrentGear: 1)
```

### Complex Signal Types

**Signed integers:**
```dbc
SG_ SteeringAngle : 0|16@1- (0.1,0) [-180|180] "deg"  Controller
```

**Multi-byte little-endian:**
```dbc
SG_ Timestamp : 0|32@1+ (1,0) [0|4294967295] "ms"  Controller
```

---

## File Locations

- **Template & Guide**: `DBC_TEMPLATE_GUIDE.md`
- **Example DBC**: `example_bootloader.dbc`
- **Requirements**: `requirements.txt`

---

## Benefits

✅ **Human-readable** - See "EngineRPM: 2500 RPM" instead of "00 10"  
✅ **Automatic conversion** - No manual calculation needed  
✅ **Unit display** - Clear engineering units (°C, km/h, etc.)  
✅ **Enumeration support** - Text labels instead of numbers  
✅ **Industry standard** - Compatible with CANalyzer, PCAN-View, etc.  
✅ **Time-saving** - Define once, decode forever  

---

## Tips

1. **Start simple** - Begin with basic messages, add complexity later
2. **Test incrementally** - Load DBC, verify one message at a time
3. **Document everything** - Use comments (`CM_`) liberally
4. **Use realistic ranges** - Set appropriate min/max values
5. **Share DBCs** - Export and share with your team

---

## Next Steps

1. ✅ Install cantools: `pip install cantools`
2. ✅ Read `DBC_TEMPLATE_GUIDE.md`
3. ✅ Create your first DBC file
4. ✅ Load it in the GUI
5. ✅ Enjoy automatic decoding!

**Happy decoding! 🚗📊**
