"""
Test if registry routes are accessible
"""
import requests

# Test the endpoint directly
try:
    # First, login to get token
    login_response = requests.post('http://localhost:5000/api/login', json={
        'username': 'registry_officer',
        'password': 'Registry@2025'
    })
    
    if login_response.status_code == 200:
        token = login_response.json()['access_token']
        print(f"✓ Login successful, token received")
        
        # Try to access activation requests
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get('http://localhost:5000/api/registry/activation-requests', headers=headers)
        
        print(f"\nGET /api/registry/activation-requests")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        if response.status_code == 200:
            print(f"✓ Endpoint working! Requests: {response.json()}")
        else:
            print(f"✗ Endpoint failed")
    else:
        print(f"✗ Login failed: {login_response.status_code}")
        print(f"Response: {login_response.text}")
        
except Exception as e:
    print(f"Error: {e}")
