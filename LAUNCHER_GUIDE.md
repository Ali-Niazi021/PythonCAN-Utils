# 🚀 CAN Explorer Launcher

## Overview
A simple, one-command launcher script that starts both backend and frontend servers and opens your browser automatically.

## Usage

### Windows

**Option 1: Double-click**
- Simply double-click `start.bat` in File Explorer
- Everything starts automatically!

**Option 2: Command line**
```cmd
python start.py
```

### Linux / macOS

**Option 1: Shell script**
```bash
chmod +x start.sh  # First time only
./start.sh
```

**Option 2: Python directly**
```bash
python3 start.py
```

## What It Does

### 1. Prerequisites Check ✅
- Verifies Node.js is installed
- Verifies npm is installed
- Shows version numbers

### 2. Dependency Installation 📦
- Checks if frontend dependencies are installed
- Runs `npm install` if needed (first time only)
- Subsequent runs skip this step

### 3. Server Startup 🚀
- **Backend Server**: Starts on port 8000
  - API: http://localhost:8000
  - Docs: http://localhost:8000/docs
  - Runs in a new console window (Windows) or background (Linux/Mac)

- **Frontend Server**: Starts on port 3001
  - App: http://localhost:3001
  - Runs in a new console window (Windows) or background (Linux/Mac)

### 4. Browser Launch 🌐
- Waits 8 seconds for servers to initialize
- Automatically opens http://localhost:3001 in your default browser

## Features

### Colored Terminal Output
- **Green**: Success messages
- **Blue**: URLs and information
- **Yellow**: Warnings and wait messages
- **Red**: Errors
- **Purple**: Headers

### Error Handling
- Checks for Node.js before starting
- Provides helpful error messages
- Shows installation links if prerequisites missing

### Cross-Platform
- Works on Windows, Linux, and macOS
- Automatically detects platform
- Uses appropriate process creation methods

## Requirements

### Must Have
- **Python 3.7+**: For running the launcher
- **Node.js 14+**: For the React frontend
- **npm**: Usually comes with Node.js

### Auto-Installed
- All Python backend dependencies (already in requirements.txt)
- All npm frontend dependencies (installed on first run)

## Configuration

### Change Frontend Port
The launcher is configured to use port 3001. To change it:

**Edit `start.py`, line ~90:**
```python
env['PORT'] = '3001'  # Change to your desired port
```

**Edit browser URL, line ~127:**
```python
open_browser("http://localhost:3001", delay=8)  # Update port here too
```

### Change Backend Port
Backend port is configured in `webserver/backend/api.py` at the bottom:
```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # Change port here
```

### Adjust Startup Delay
If your computer is slow and needs more time:

**Edit `start.py`, line ~127:**
```python
open_browser("http://localhost:3001", delay=8)  # Increase delay (seconds)
```

## Troubleshooting

### "Node.js is not installed"
**Solution**: Install Node.js from https://nodejs.org/
- Download the LTS version
- Run the installer
- Restart your terminal
- Try again

### "npm is not installed"
**Solution**: npm should come with Node.js
- Reinstall Node.js
- Make sure to check "npm package manager" during installation

### Frontend dependencies fail to install
**Solution**: 
```bash
cd webserver/frontend
npm cache clean --force
npm install
```

### Servers don't start
**Solution**:
- Check if ports 8000 and 3001 are already in use
- Close other applications using those ports
- Or change the ports (see Configuration above)

### Browser doesn't open
**Solution**:
- Manually navigate to http://localhost:3001
- The servers are still running even if browser doesn't auto-open

### Windows: "Python is not recognized"
**Solution**:
- Add Python to your PATH
- Or use full path: `C:\Python312\python.exe start.py`

## Stopping the Servers

### Windows
- Find the two console windows that opened
- Close them OR press Ctrl+C in each window

### Linux/Mac
- Press Ctrl+C in the terminal where you ran start.py
- Or find the processes:
  ```bash
  ps aux | grep python
  ps aux | grep node
  kill <PID>
  ```

## Files

### `start.py` (Main Launcher)
- Python script with all the logic
- Cross-platform compatibility
- Colored terminal output
- Error handling

### `start.bat` (Windows Shortcut)
- Simple batch file
- Just runs `python start.py`
- For users who prefer double-clicking

### `start.sh` (Linux/Mac Shortcut)
- Simple shell script
- Just runs `python3 start.py`
- Make executable with `chmod +x start.sh`

## Advanced Usage

### Run without opening browser
Edit `start.py` and comment out this line:
```python
# open_browser("http://localhost:3001", delay=8)
```

### Keep terminal open on error
The script automatically pauses on errors.
On Windows, `start.bat` has a `pause` command at the end.

### Run in current terminal (no new windows)
Edit `start.py` and remove `creationflags=subprocess.CREATE_NEW_CONSOLE` for Windows.

## Benefits

✅ **One command** - No need to remember multiple steps  
✅ **Automatic setup** - Installs dependencies if needed  
✅ **Cross-platform** - Works on Windows, Linux, Mac  
✅ **User-friendly** - Colored output, clear messages  
✅ **Error handling** - Helpful error messages with solutions  
✅ **Fast** - Reuses installed dependencies on subsequent runs  
✅ **Convenient** - Opens browser automatically  

## Example Output

```
============================================================
CAN Explorer Launcher
============================================================

📋 Checking prerequisites...
✓ Node.js version: v22.20.0
✓ npm version: 10.9.3
✓ Frontend dependencies already installed

============================================================
Starting Servers
============================================================

🚀 Starting backend server...
✓ Backend server started (PID: 12345)
   Backend URL: http://localhost:8000
   API Docs: http://localhost:8000/docs

🚀 Starting frontend server...
✓ Frontend server starting (PID: 12346)
   Frontend URL: http://localhost:3001

⏱️  Waiting 8 seconds for servers to start...
🌐 Opening browser at http://localhost:3001

============================================================
All Services Running
============================================================
✓ Backend: http://localhost:8000
✓ Frontend: http://localhost:3001

💡 Both servers are running in separate windows.
   Close those windows or press Ctrl+C to stop the servers.

🎉 CAN Explorer is ready to use!

Press Ctrl+C to exit...
```

---

**That's it!** Just run `python start.py` and you're ready to go! 🚀
