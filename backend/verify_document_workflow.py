import requests
import json
import time

BASE_URL = 'http://localhost:5000/api'

def print_step(step):
    print(f"\n{'='*60}\n{step}\n{'='*60}")

def login(username, password):
    print(f"Logging in as {username}...")
    response = requests.post(f'{BASE_URL}/login', json={'username': username, 'password': password})
    if response.status_code == 200:
        token = response.json()['access_token']
        print(f"SUCCESS: Logged in. Token: {token[:20]}...")
        return token
    else:
        print(f"FAILED: Login failed. {response.text}")
        return None

def test_full_document_workflow():
    # 0. Get Staff ID
    print_step("0. Get Staff ID")
    staff_token = login('testuser', 'Test@123')
    if not staff_token: return
    
    # We need to decode token or fetch profile to get ID. 
    # Let's fetch profile.
    staff_headers = {'Authorization': f'Bearer {staff_token}'}
    response = requests.get(f'{BASE_URL}/me', headers=staff_headers) # Assuming /me exists? 
    # If /me doesn't exist, we might need another way. 
    # Let's check if /me exists. It was used in staff-dashboard.js.
    if response.status_code == 200:
        staff_id = response.json()['id']
        print(f"Staff ID: {staff_id}")
    else:
        print("FAILED: Could not get staff profile.")
        return

    # 1. Registry Login & Create File
    print_step("1. Registry: Create File")
    registry_token = login('registry_officer', 'Registry@2025')
    if not registry_token: return
    registry_headers = {'Authorization': f'Bearer {registry_token}'}

    file_data = {
        'file_name': f'DOC TEST FILE {int(time.time())}',
        'category': 'Personal',
        'employment_type': 'Permanent',
        'owner_id': staff_id,
        'second_level_auth': False
    }
    response = requests.post(f'{BASE_URL}/registry/files', json=file_data, headers=registry_headers)
    if response.status_code != 201:
        print(f"FAILED: Create file failed. {response.text}")
        return
    
    file_info = response.json()
    file_id = file_info['file_id']
    print(f"SUCCESS: File Created. ID: {file_id}")

    # 2. Staff Login & Request Activation
    print_step("2. Staff: Request Activation")
    staff_token = login('testuser', 'Test@123')
    if not staff_token: return
    staff_headers = {'Authorization': f'Bearer {staff_token}'}

    req_data = {'request_reason': 'Need to add documents'}
    response = requests.post(f'{BASE_URL}/staff/files/{file_id}/request-activation', json=req_data, headers=staff_headers)
    if response.status_code != 201:
        print(f"FAILED: Activation request failed. {response.text}")
        return
    print("SUCCESS: Activation requested.")

    # 3. Registry: Approve Activation
    print_step("3. Registry: Approve Activation")
    # Get request ID
    response = requests.get(f'{BASE_URL}/registry/activation-requests', headers=registry_headers)
    requests_list = response.json()
    target_request = next((r for r in requests_list if r['file_id'] == file_id), None)
    
    if not target_request:
        print("FAILED: Request not found.")
        return
    
    req_id = target_request['id']
    response = requests.put(f'{BASE_URL}/registry/activation-requests/{req_id}/approve', headers=registry_headers)
    if response.status_code != 200:
        print(f"FAILED: Approval failed. {response.text}")
        return
    print("SUCCESS: File Activated.")

    # 4. Staff: Create Document
    print_step("4. Staff: Create Document")
    doc_data = {
        'file_id': file_id,
        'title': f'Test Minute {int(time.time())}',
        'type': 'minute',
        'content': 'This is a test minute sheet content.'
    }
    
    response = requests.post(f'{BASE_URL}/documents', json=doc_data, headers=staff_headers)
    if response.status_code == 201:
        doc_info = response.json()
        doc_id = doc_info['document_id']
        print(f"SUCCESS: Document Created. ID: {doc_id}")
    else:
        print(f"FAILED: Create document failed. {response.text}")
        return

    # 5. Verify Document Listing
    print_step("5. Verify Document Listing")
    response = requests.get(f'{BASE_URL}/files/{file_id}/documents', headers=staff_headers)
    if response.status_code == 200:
        docs = response.json()
        found = any(d['id'] == doc_id for d in docs)
        if found:
            print(f"SUCCESS: Document {doc_id} found in file {file_id}.")
        else:
            print(f"FAILED: Document {doc_id} NOT found in list.")
            print("Docs found:", docs)
    else:
        print(f"FAILED: Get documents failed. {response.text}")

if __name__ == "__main__":
    try:
        test_full_document_workflow()
    except Exception as e:
        print(f"ERROR: {e}")
