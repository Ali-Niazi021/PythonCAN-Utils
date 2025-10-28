#!/usr/bin/env python3
"""
CAN Explorer Launcher
=====================
Simple script to start both backend and frontend servers and open the browser.
Manages all processes and automatically cleans up on exit.

Usage: python start.py
"""

import subprocess
import sys
import os
import time
import webbrowser
import signal
import atexit
from pathlib import Path

# Global process list for cleanup
processes = []

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_colored(message, color=Colors.OKGREEN):
    """Print colored message"""
    print(f"{color}{message}{Colors.ENDC}")

def print_header(message):
    """Print header"""
    print("\n" + "=" * 60)
    print_colored(message, Colors.HEADER + Colors.BOLD)
    print("=" * 60)

def cleanup_processes():
    """Kill all spawned processes"""
    global processes
    if processes:
        print_colored("\n🧹 Cleaning up processes...", Colors.WARNING)
        for proc_info in processes:
            try:
                proc = proc_info['process']
                name = proc_info['name']
                
                if proc.poll() is None:  # Process is still running
                    print_colored(f"  ⏹️  Stopping {name}...", Colors.OKCYAN)
                    
                    if sys.platform == 'win32':
                        # Windows: Kill the entire process tree
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                                     capture_output=True,
                                     shell=True)
                    else:
                        # Linux/Mac: Send SIGTERM
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    
                    print_colored(f"  ✓ {name} stopped", Colors.OKGREEN)
            except Exception as e:
                print_colored(f"  ⚠️  Error stopping {name}: {e}", Colors.WARNING)
        
        processes.clear()
        print_colored("✓ All processes cleaned up", Colors.OKGREEN)

# Register cleanup function
atexit.register(cleanup_processes)

# Handle Ctrl+C gracefully
def signal_handler(sig, frame):
    """Handle interrupt signal"""
    print_colored("\n\n👋 Shutting down gracefully...", Colors.WARNING)
    cleanup_processes()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
if sys.platform == 'win32':
    signal.signal(signal.SIGBREAK, signal_handler)

def check_node_installed():
    """Check if Node.js is installed"""
    try:
        result = subprocess.run(['node', '--version'], 
                              capture_output=True, 
                              text=True, 
                              shell=True)
        if result.returncode == 0:
            print_colored(f"✓ Node.js version: {result.stdout.strip()}", Colors.OKGREEN)
            return True
        return False
    except FileNotFoundError:
        return False

def check_npm_installed():
    """Check if npm is installed"""
    try:
        result = subprocess.run(['npm', '--version'], 
                              capture_output=True, 
                              text=True, 
                              shell=True)
        if result.returncode == 0:
            print_colored(f"✓ npm version: {result.stdout.strip()}", Colors.OKGREEN)
            return True
        return False
    except FileNotFoundError:
        return False

def install_frontend_dependencies():
    """Install frontend dependencies if needed"""
    frontend_dir = Path(__file__).parent / "webserver" / "frontend"
    node_modules = frontend_dir / "node_modules"
    
    if not node_modules.exists():
        print_colored("📦 Installing frontend dependencies (this may take a few minutes)...", Colors.WARNING)
        try:
            # Run npm install silently
            subprocess.run(['npm', 'install'], 
                         cwd=str(frontend_dir), 
                         shell=True, 
                         check=True,
                         capture_output=True)
            print_colored("✓ Frontend dependencies installed", Colors.OKGREEN)
            return True
        except subprocess.CalledProcessError as e:
            print_colored(f"✗ Failed to install frontend dependencies", Colors.FAIL)
            print_colored(f"  Error: {e.stderr.decode() if e.stderr else 'Unknown error'}", Colors.FAIL)
            return False
    else:
        print_colored("✓ Frontend dependencies already installed", Colors.OKGREEN)
        return True

def start_backend():
    """Start the backend server"""
    global processes
    print_colored("\n🚀 Starting backend server...", Colors.OKCYAN)
    backend_dir = Path(__file__).parent / "webserver" / "backend"
    
    # Start backend in a new console window (visible for debugging)
    if sys.platform == 'win32':
        # Windows - show console window for visibility
        backend_process = subprocess.Popen(
            [sys.executable, 'api.py'],
            cwd=str(backend_dir),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    else:
        # Linux/Mac
        backend_process = subprocess.Popen(
            [sys.executable, 'api.py'],
            cwd=str(backend_dir)
        )
    
    processes.append({'process': backend_process, 'name': 'Backend'})
    
    print_colored("✓ Backend server started (PID: {})".format(backend_process.pid), Colors.OKGREEN)
    print_colored("   Backend URL: http://localhost:8000", Colors.OKBLUE)
    print_colored("   API Docs: http://localhost:8000/docs", Colors.OKBLUE)
    
    return backend_process

def start_frontend():
    """Start the frontend development server"""
    global processes
    print_colored("\n🚀 Starting frontend server...", Colors.OKCYAN)
    frontend_dir = Path(__file__).parent / "webserver" / "frontend"
    
    # Set environment variable for port 3001
    env = os.environ.copy()
    env['PORT'] = '3001'
    env['BROWSER'] = 'none'  # Prevent npm from opening browser automatically
    
    # Start frontend in a new console window (visible for debugging)
    if sys.platform == 'win32':
        # Windows - show console window for visibility
        frontend_process = subprocess.Popen(
            ['cmd', '/c', 'npm', 'start'],
            cwd=str(frontend_dir),
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    else:
        # Linux/Mac
        frontend_process = subprocess.Popen(
            ['npm', 'start'],
            cwd=str(frontend_dir),
            env=env
        )
    
    processes.append({'process': frontend_process, 'name': 'Frontend'})
    
    print_colored("✓ Frontend server starting (PID: {})".format(frontend_process.pid), Colors.OKGREEN)
    print_colored("   Frontend URL: http://localhost:3001", Colors.OKBLUE)
    
    return frontend_process

def open_browser(url, delay=5):
    """Open browser after a delay"""
    print_colored(f"\n⏱️  Waiting {delay} seconds for servers to start...", Colors.WARNING)
    time.sleep(delay)
    print_colored(f"🌐 Opening browser at {url}", Colors.OKCYAN)
    webbrowser.open(url)

def main():
    """Main function"""
    print_header("CAN Explorer Launcher")
    
    # Check prerequisites
    print_colored("\n📋 Checking prerequisites...", Colors.OKCYAN)
    
    if not check_node_installed():
        print_colored("✗ Node.js is not installed!", Colors.FAIL)
        print_colored("  Please install Node.js from: https://nodejs.org/", Colors.WARNING)
        sys.exit(1)
    
    if not check_npm_installed():
        print_colored("✗ npm is not installed!", Colors.FAIL)
        print_colored("  npm should be installed with Node.js", Colors.WARNING)
        sys.exit(1)
    
    # Install frontend dependencies if needed
    if not install_frontend_dependencies():
        print_colored("\n✗ Failed to install dependencies. Exiting.", Colors.FAIL)
        cleanup_processes()
        sys.exit(1)
    
    # Start servers
    print_header("Starting Servers")
    
    try:
        backend_process = start_backend()
        time.sleep(2)  # Give backend a moment to start
        
        frontend_process = start_frontend()
        
        # Open browser
        open_browser("http://localhost:3001", delay=8)
        
        print_header("All Services Running")
        print_colored("✓ Backend: http://localhost:8000", Colors.OKGREEN)
        print_colored("✓ Frontend: http://localhost:3001", Colors.OKGREEN)
        print_colored("\n💡 Servers are running in separate console windows.", Colors.OKCYAN)
        print_colored("   Close this window or press Ctrl+C to stop everything.", Colors.OKCYAN)
        print_colored("\n🎉 CAN Explorer is ready to use!", Colors.OKGREEN + Colors.BOLD)
        
        # Keep script alive and monitor processes
        print_colored("\n⏳ Monitoring services (Press Ctrl+C to exit)...", Colors.WARNING)
        
        try:
            while True:
                # Check if processes are still running
                for proc_info in processes:
                    if proc_info['process'].poll() is not None:
                        print_colored(f"\n⚠️  {proc_info['name']} has stopped unexpectedly!", Colors.FAIL)
                        cleanup_processes()
                        sys.exit(1)
                time.sleep(2)
        except KeyboardInterrupt:
            print_colored("\n\n👋 Shutting down gracefully...", Colors.WARNING)
            cleanup_processes()
            
    except Exception as e:
        print_colored(f"\n✗ Error starting servers: {e}", Colors.FAIL)
        cleanup_processes()
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\n👋 Cancelled by user", Colors.WARNING)
        cleanup_processes()
        sys.exit(0)
