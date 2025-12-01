import requests
import json
import time

BASE_URL = 'http://localhost:5000/api'

def login(username, password):
    response = requests.post(f'{BASE_URL}/login', json={
        'username': username,
        'password': password
    })
    if response.status_code != 200:
        print(f"Login failed for {username}: {response.text}")
        return None
    return response.json()['access_token']

def get_staff_id(token):
    response = requests.get(f'{BASE_URL}/me', headers={'Authorization': f'Bearer {token}'})
    if response.status_code != 200:
        print(f"Failed to get user info: {response.text}")
        return None
    return response.json()['id']

def create_registry_file(token, staff_id):
    # Create a file and assign it to the staff user (owner_id)
    data = {
        'file_name': 'ROUTING TEST FILE',
        'category': 'Personal',
        'employment_type': 'Permanent',
        'owner_id': staff_id
    }
    response = requests.post(f'{BASE_URL}/registry/files', json=data, headers={'Authorization': f'Bearer {token}'})
    if response.status_code != 201:
        print(f"Failed to create file: {response.text}")
        return None
    return response.json()['file_id']

def activate_file(registry_token, staff_token, file_id):
    # Staff requests activation
    response = requests.post(f'{BASE_URL}/staff/files/{file_id}/request-activation', 
                             json={'request_reason': 'Need to create doc'},
                             headers={'Authorization': f'Bearer {staff_token}'})
    if response.status_code != 200:
        print(f"Failed to request activation: {response.text}")
        return False

    # Registry approves
    # First get request ID
    response = requests.get(f'{BASE_URL}/registry/activation-requests', headers={'Authorization': f'Bearer {registry_token}'})
    requests_list = response.json()
    request_id = next((r['id'] for r in requests_list if r['file_id'] == file_id), None)
    
    if not request_id:
        print("Activation request not found")
        return False
        
    response = requests.put(f'{BASE_URL}/registry/activation-requests/{request_id}/approve', headers={'Authorization': f'Bearer {registry_token}'})
    if response.status_code != 200:
        print(f"Failed to approve activation: {response.text}")
        return False
        
    return True

def create_document(token, file_id):
    data = {
        'file_id': file_id,
        'title': 'Routing Test Doc',
        'type': 'Minute',
        'content': 'This is a test document for routing.'
    }
    response = requests.post(f'{BASE_URL}/documents', json=data, headers={'Authorization': f'Bearer {token}'})
    if response.status_code != 201:
        print(f"Failed to create document: {response.text}")
        return None
    return response.json()['document_id']

def route_document(token, doc_id):
    data = {
        'target_role': 'HOD',
        'comment': 'Please review this.'
    }
    url = f'{BASE_URL}/documents/{doc_id}/route'
    print(f"DEBUG: Calling URL: {url}")
    response = requests.post(url, json=data, headers={'Authorization': f'Bearer {token}'})
    if response.status_code != 200:
        print(f"Failed to route document: {response.status_code} {response.text}")
        return False
    print(f"Route response: {response.json()}")
    return True

def main():
    print("Starting Routing Verification...")
    
    # 1. Login Staff
    staff_token = login('staff_user', 'password123')
    if not staff_token: return
    staff_id = get_staff_id(staff_token)
    print("Staff logged in.")

    # 2. Login Registry
    registry_token = login('registry_user', 'password123')
    if not registry_token: return
    print("Registry logged in.")

    # 3. Create File (Registry)
    file_id = create_registry_file(registry_token, staff_id)
    if not file_id: return
    print(f"File created: {file_id}")

    # 4. Activate File
    if not activate_file(registry_token, staff_token, file_id): return
    print("File activated.")

    # 5. Create Document (Staff)
    doc_id = create_document(staff_token, file_id)
    if not doc_id: return
    print(f"Document created: {doc_id}")

    # 6. Route Document (Staff -> HOD)
    # Note: This assumes an HOD exists in the staff's department. 
    # If not, it might fail or route to department head.
    if route_document(staff_token, doc_id):
        print("SUCCESS: Document routed to HOD.")
    else:
        print("FAILURE: Could not route document.")

if __name__ == '__main__':
    main()
