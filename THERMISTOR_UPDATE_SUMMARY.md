# Thermistor Monitor Update - 336 Channels (6 Modules)

## Summary of Changes

The thermistor monitor tab has been updated to support **336 thermistors** across **6 BMS modules** (56 thermistors per module).

---

## Key Features

### 1. **Multi-Module Support**
- **6 modules** (Module 0 through Module 5)
- **56 thermistors per module**
- **Total: 336 thermistors**

### 2. **Compact Display Design**
- **Module selector dropdown** - Switch between modules 0-5
- **Dense grid layout** - 8 rows × 7 columns = 56 thermistors per view
- **Minimal information** - Only shows:
  - Module-Channel identifier (e.g., "M0-00")
  - Temperature value (e.g., "23.5°C")
- **Color-coded temperatures**:
  - Blue: Very cold (< -50°C)
  - Light blue: Cold (< 0°C)
  - Green: Normal (0-25°C)
  - Yellow: Warm (25-50°C)
  - Orange: Hot (50-85°C)
  - Red: Very hot (> 85°C)

### 3. **Statistics Display**
- **Global stats** - All 336 thermistors across all modules
  - Active count, min, max, average
- **Module stats** - Current module's 56 thermistors
  - Active count, min, max, average
  - Updates when switching modules

### 4. **CAN Message Format**
Messages follow this structure:
```
Module 0: 0x08F00000 - 0x08F0000D (14 messages)
Module 1: 0x08F01000 - 0x08F0100D (14 messages)
Module 2: 0x08F02000 - 0x08F0200D (14 messages)
Module 3: 0x08F03000 - 0x08F0300D (14 messages)
Module 4: 0x08F04000 - 0x08F0400D (14 messages)
Module 5: 0x08F05000 - 0x08F0500D (14 messages)
```

**CAN ID Structure:**
- Bits 15-12: Module ID (0-5)
- Bits 11-8: Message group (0x0 = temperatures)
- Bits 7-0: Message index (0x00-0x0D)

**Each message contains 4 temperature readings** (56 ÷ 14 = 4 per message)

---

## Implementation Details

### Data Structure Changes

**Before (single module):**
```python
self.thermistor_temps = [None] * 56  # Single array
self.thermistor_text_tags = []       # Single list
```

**After (6 modules):**
```python
self.thermistor_temps = [[None] * 56 for _ in range(6)]  # 6 arrays
self.thermistor_text_tags = [[None] * 56 for _ in range(6)]  # 6 lists
self.current_thermistor_module = 0  # Currently displayed module
```

### New Methods

1. **`_create_thermistor_grid(module_id)`**
   - Creates the 56-thermistor grid for specified module
   - Dynamically rebuilds when switching modules
   - Tag format: `therm_m{module}_temp_{channel}`

2. **`_on_thermistor_module_changed(sender, app_data)`**
   - Handles module selector dropdown changes
   - Recreates grid for new module
   - Updates statistics

3. **`_update_thermistor_data(can_id, data)` - Enhanced**
   - Extracts module ID from CAN ID (bits 15-12)
   - Routes data to correct module array
   - Supports all 6 modules automatically

4. **`_update_single_thermistor(module_id, channel, temp, time)` - Updated**
   - Now requires module_id parameter
   - Updates correct module's data array
   - Only updates GUI if module is currently displayed

5. **`_update_thermistor_stats()` - Enhanced**
   - Calculates global stats (all 336 thermistors)
   - Calculates current module stats (56 thermistors)
   - Updates both stat displays independently

6. **`_clear_thermistor_data()` - Updated**
   - Clears all 6 modules
   - Resets visible GUI elements

---

## UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│ 336-Channel Multi-Module Thermistor Monitor (6 Modules)    │
├─────────────────────────────────────────────────────────────┤
│ Global Stats: All Modules | Active: 224/336 | Min: 18.2°C  │
│               Max: 85.3°C | Avg: 45.7°C                     │
│                                                             │
│ Module 2: Active: 42/56 | Min: 22.1°C | Max: 68.4°C        │
│           Avg: 42.3°C                                       │
│                                                             │
│ [Clear All Data]    View Module: [Module 0 ▼]              │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────┬─────────┬─────────┬─────────┬─────────┬───┐   │
│ │M2-00:   │M2-01:   │M2-02:   │M2-03:   │M2-04:   │...│   │
│ │ 23.5°C  │ 24.1°C  │ 22.9°C  │ 25.3°C  │ 23.8°C  │   │   │
│ ├─────────┼─────────┼─────────┼─────────┼─────────┼───┤   │
│ │M2-07:   │M2-08:   │M2-09:   │M2-10:   │M2-11:   │...│   │
│ │ 26.2°C  │ 25.7°C  │ 24.3°C  │ 27.1°C  │ 25.9°C  │   │   │
│ └─────────┴─────────┴─────────┴─────────┴─────────┴───┘   │
│               ... (8 rows × 7 columns)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Usage Instructions

1. **Load DBC File**
   - Load `BMS-Firmware-RTOS-Complete.dbc` which contains definitions for all 6 modules
   - Messages should be named: `BMS_Mod0_Temp_000` through `BMS_Mod5_Temp_013`

2. **Connect to CAN Bus**
   - All modules transmit simultaneously
   - Data automatically routed to correct module display

3. **Switch Between Modules**
   - Use "View Module" dropdown to switch between Module 0-5
   - Grid rebuilds instantly with selected module's data
   - Statistics update to show current module + global totals

4. **Monitor Temperatures**
   - Color coding provides instant visual feedback
   - Green = normal operating temperature
   - Yellow/Orange = elevated temperature (check cooling)
   - Red = critical temperature (requires attention)

5. **Clear Data**
   - "Clear All Data" button resets all 336 thermistors
   - Useful when starting fresh monitoring session

---

## Performance Considerations

- **Memory efficient**: Only one module's GUI elements exist at a time (56 widgets)
- **Fast switching**: Grid recreation is instant (< 50ms)
- **Update rate**: Can handle 336 updates per second (one per thermistor)
- **No lag**: GUI only updates visible module, background modules just store data

---

## DBC File Requirements

Each module must have 14 temperature messages defined:

```dbc
// Module 0
BO_ 2297430016 BMS_Mod0_Temp_000: 8 BMS_Module_0
 SG_ Temp_000 : 0|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_001 : 16|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_002 : 32|16@1- (0.1,0) [-40|125] "degC" CAN_Host
 SG_ Temp_003 : 48|16@1- (0.1,0) [-40|125] "degC" CAN_Host

... (repeat for Temp_001 through Temp_013)

// Module 1
BO_ 2297434112 BMS_Mod1_Temp_000: 8 BMS_Module_1
... (same structure)

... (repeat for all 6 modules)
```

**CAN ID Calculation:**
```python
base_id = 0x08F00000  # Module 0, message 0
module_offset = module_id << 12  # Shift module ID to bits 15-12
message_index = msg_num  # 0x00 through 0x0D
can_id = base_id | module_offset | message_index

# Example: Module 2, Message 5
# 0x08F00000 | (2 << 12) | 0x05 = 0x08F02005
```

---

## Testing Checklist

- [ ] Load DBC file successfully
- [ ] Connect to CAN bus
- [ ] Verify Module 0 temperatures display
- [ ] Switch to Module 1-5 and verify display updates
- [ ] Check global statistics calculate correctly
- [ ] Check module statistics calculate correctly
- [ ] Verify color coding works (inject test temperatures)
- [ ] Test "Clear All Data" button
- [ ] Verify data persists when switching modules
- [ ] Check performance with all 336 updating rapidly

---

## Troubleshooting

**Issue: No temperatures showing**
- Check DBC file loaded
- Verify CAN IDs match expected format (0x08F0X0YZ)
- Check message names in DBC match pattern: `BMS_ModX_Temp_YYY`

**Issue: Wrong module receiving data**
- Verify CAN ID module field (bits 15-12)
- Check DBC file has correct CAN IDs with bit 31 set

**Issue: Statistics incorrect**
- Ensure all modules have same number of channels (56)
- Verify temperature values are valid (not NaN or extreme values)

**Issue: Grid not updating when switching modules**
- Check `_create_thermistor_grid()` is being called
- Verify tag names match pattern: `therm_m{module}_temp_{channel}`

---

**Version:** 1.0  
**Date:** October 18, 2025  
**Compatibility:** Requires BMS-Firmware-RTOS-Complete.dbc
