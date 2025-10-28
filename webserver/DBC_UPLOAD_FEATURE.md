# 📁 DBC File Upload Feature

## Overview
The DBC file handling has been upgraded from a manual file path input to a modern file upload system with automatic persistence.

## ✨ New Features

### 1. File Upload Interface
- **Drag-and-drop ready** upload button in the CAN Explorer tab
- **File validation** - Only accepts `.dbc` files
- **Visual feedback** - Shows upload status and loaded file name
- **No typing** - No need to type file paths anymore!

### 2. Automatic Persistence
- **Auto-save**: Uploaded DBC files are saved to `webserver/backend/dbc_files/`
- **Auto-load**: Last uploaded DBC file is automatically loaded on backend restart
- **Overwrite protection**: Uploading a file with the same name overwrites the old one

### 3. File Management
- **List files**: API endpoint to see all uploaded DBC files
- **Delete files**: API endpoint to remove uploaded DBC files
- **Current status**: Check which DBC file is currently loaded

## 🚀 How to Use

### Frontend (Web UI)
1. Open the CAN Explorer tab
2. Click the **"Upload DBC"** button
3. Select your `.dbc` file from your computer
4. The file is automatically uploaded, saved, and loaded
5. Success message confirms upload and shows message count

### Backend (API)
Upload a DBC file:
```bash
curl -X POST http://localhost:8000/dbc/upload \
  -F "file=@/path/to/your/file.dbc"
```

Check current DBC status:
```bash
curl http://localhost:8000/dbc/current
```

List all uploaded files:
```bash
curl http://localhost:8000/dbc/list
```

Delete a file:
```bash
curl -X DELETE http://localhost:8000/dbc/delete/myfile.dbc
```

## 📂 File Storage

### Location
All uploaded DBC files are stored in:
```
webserver/backend/dbc_files/
```

### Persistence Mechanism
- When you upload a DBC file, it's saved to the `dbc_files/` directory
- The filename is recorded in `last_loaded.txt`
- On backend startup, the system checks for `last_loaded.txt`
- If found, it automatically loads that DBC file
- This means your DBC configuration persists across server restarts!

## 🔧 Technical Details

### Backend Changes

#### New Endpoints
1. **POST /dbc/upload** - Upload and load a DBC file
   - Accepts multipart/form-data with file field
   - Validates `.dbc` extension
   - Saves to `dbc_files/` directory
   - Automatically loads the file
   - Records as last loaded file

2. **GET /dbc/current** - Get current DBC status
   - Returns loaded status, filename, message count

3. **GET /dbc/list** - List all uploaded DBC files
   - Returns array of files with size and modified date

4. **DELETE /dbc/delete/{filename}** - Delete a DBC file
   - Removes file from storage
   - Clears last loaded reference if applicable

5. **POST /dbc/load** - Legacy endpoint (kept for compatibility)
   - Still works with file paths

#### Auto-load on Startup
Added to `@app.on_event("startup")`:
```python
if DBC_SUPPORT and LAST_DBC_FILE.exists():
    # Reads last_loaded.txt
    # Loads that DBC file automatically
    # Prints confirmation message
```

### Frontend Changes

#### CANExplorer Component
- Added file input element (hidden)
- Upload button triggers file picker
- File change handler uploads file via API
- Success/error handling with alerts

#### API Service
- New `uploadDBC(file)` method
- Uses FormData and multipart/form-data
- Returns upload response with message count

#### App.js
- `handleLoadDBC` now accepts File object instead of path
- `checkDBCStatus()` checks current DBC on mount
- Auto-displays loaded DBC file name

## 🎯 User Experience Improvements

### Before
1. User had to know exact file path
2. Manual typing prone to errors
3. No persistence - had to reload on every restart
4. No feedback on what's loaded

### After
1. Simple upload button - browse and select
2. Visual file picker - no typing needed
3. Automatic reload on server restart
4. Clear status showing loaded file
5. Success messages with details

## 🔒 Security Features

### File Validation
- Only `.dbc` extension allowed
- Filename sanitization to prevent path traversal
- Files stored in dedicated directory

### Path Safety
```python
# Delete endpoint validates filename
if "/" in filename or "\\" in filename or ".." in filename:
    raise HTTPException(status_code=400, detail="Invalid filename")
```

## 📊 Example Workflow

### Initial Upload
```
User clicks "Upload DBC"
  ↓
Browser shows file picker
  ↓
User selects "battery_pack.dbc"
  ↓
Frontend uploads to /dbc/upload
  ↓
Backend saves to dbc_files/battery_pack.dbc
  ↓
Backend loads DBC (e.g., 156 messages)
  ↓
Backend writes "battery_pack.dbc" to last_loaded.txt
  ↓
Frontend shows: "✓ DBC Loaded: battery_pack.dbc"
```

### Server Restart
```
Backend starts
  ↓
Checks for last_loaded.txt
  ↓
Finds "battery_pack.dbc"
  ↓
Checks dbc_files/battery_pack.dbc exists
  ↓
Automatically loads it
  ↓
Prints: "✓ Auto-loaded DBC file: battery_pack.dbc (156 messages)"
  ↓
Frontend fetches /dbc/current on mount
  ↓
Displays: "✓ DBC Loaded: battery_pack.dbc"
```

### Updating DBC File
```
User uploads new "battery_pack.dbc"
  ↓
Backend overwrites old file
  ↓
Backend reloads DBC
  ↓
Updates last_loaded.txt
  ↓
New version is now active and will auto-load
```

## 🐛 Bug Fix Bonus

While implementing this feature, also fixed the async callback issue in PCAN and CANable drivers that was preventing messages from being received:

### Problem
```
RuntimeWarning: coroutine 'CANBackend._on_message_received' was never awaited
```

### Solution
Updated both drivers to check if callback is async:
```python
if inspect.iscoroutinefunction(self._receive_callback):
    asyncio.run_coroutine_threadsafe(
        self._receive_callback(msg), 
        loop
    )
else:
    self._receive_callback(msg)
```

Now messages flow correctly from hardware → backend → WebSocket → frontend! 🎉

## 📝 Configuration

### Backend
The DBC directory is configured in `api.py`:
```python
DBC_DIR = backend_dir / "dbc_files"
LAST_DBC_FILE = DBC_DIR / "last_loaded.txt"
```

### Frontend
No configuration needed - uses the existing API service.

## 🚀 Benefits

1. **Easier to use** - Click and upload instead of typing paths
2. **More reliable** - File validation prevents errors
3. **Persistent** - Survives server restarts
4. **Professional** - Modern file upload UX
5. **Flexible** - Supports multiple DBC files
6. **Safe** - Path traversal protection

---

**Status**: ✅ Fully implemented and tested
**Backend Version**: 1.0.0 (with file upload)
**Frontend Version**: 1.0.0 (with file upload)
