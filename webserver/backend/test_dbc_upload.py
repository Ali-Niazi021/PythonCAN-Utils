"""
Test DBC Upload Feature
========================
Quick test to verify DBC file upload functionality.
"""

import requests
import os
from pathlib import Path

API_URL = "http://localhost:8000"

def test_dbc_upload():
    """Test uploading a DBC file"""
    print("=" * 60)
    print("Testing DBC Upload Feature")
    print("=" * 60)
    
    # Path to test DBC file
    dbc_file = Path(__file__).parent.parent.parent / "bootloader" / "STM32L432_Bootloader.dbc"
    
    if not dbc_file.exists():
        print(f"✗ Test DBC file not found: {dbc_file}")
        return False
    
    print(f"✓ Found test DBC file: {dbc_file.name}")
    
    # Upload the DBC file
    print("\n1. Uploading DBC file...")
    try:
        with open(dbc_file, 'rb') as f:
            files = {'file': (dbc_file.name, f, 'application/octet-stream')}
            response = requests.post(f"{API_URL}/dbc/upload", files=files)
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Upload successful!")
            print(f"   - Message: {data.get('message')}")
            print(f"   - File path: {data.get('file_path')}")
            print(f"   - Messages in DBC: {data.get('message_count')}")
        else:
            print(f"   ✗ Upload failed: {response.status_code}")
            print(f"   - Error: {response.text}")
            return False
    except Exception as e:
        print(f"   ✗ Upload error: {e}")
        return False
    
    # Check current DBC status
    print("\n2. Checking current DBC status...")
    try:
        response = requests.get(f"{API_URL}/dbc/current")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status retrieved")
            print(f"   - Loaded: {data.get('loaded')}")
            print(f"   - Filename: {data.get('filename')}")
            print(f"   - Message count: {data.get('message_count')}")
        else:
            print(f"   ✗ Status check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Status error: {e}")
        return False
    
    # List all DBC files
    print("\n3. Listing uploaded DBC files...")
    try:
        response = requests.get(f"{API_URL}/dbc/list")
        if response.status_code == 200:
            data = response.json()
            files = data.get('files', [])
            print(f"   ✓ Found {len(files)} file(s):")
            for file_info in files:
                size_kb = file_info['size'] / 1024
                print(f"   - {file_info['filename']} ({size_kb:.1f} KB)")
        else:
            print(f"   ✗ List failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ List error: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ All DBC upload tests passed!")
    print("=" * 60)
    print("\nNOTE: The DBC file will be auto-loaded on next server restart.")
    print(f"Stored in: webserver/backend/dbc_files/")
    return True

if __name__ == "__main__":
    try:
        success = test_dbc_upload()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
