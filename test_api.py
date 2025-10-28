"""Quick test script to check the /dbc/messages endpoint"""
import requests
import json

try:
    response = requests.get('http://localhost:8000/dbc/messages')
    print(f"Status Code: {response.status_code}")
    print(f"\nResponse:")
    data = response.json()
    print(json.dumps(data, indent=2))
    
    if 'messages' in data:
        print(f"\n✓ Found {len(data['messages'])} messages")
        if len(data['messages']) > 0:
            print(f"\nFirst message:")
            print(json.dumps(data['messages'][0], indent=2))
except Exception as e:
    print(f"Error: {e}")
