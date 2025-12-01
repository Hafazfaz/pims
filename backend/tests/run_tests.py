"""Simple test runner for workflow validation without pytest.
Run: python backend/tests/run_tests.py
"""
import sys, os
# Ensure project root is on sys.path so 'backend' package can be imported when running this script directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.workflow import can_transition

def run_case(name, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except AssertionError as e:
        print(f"FAIL: {name} -> {e}")
        return False

def test_hod_can_approve_pending():
    res = can_transition('HOD', actor_id=10, receiver_id=10, current_status='pending', requested_status='approved', comment='Looks good')
    assert res['ok'] is True

def test_non_receiver_cannot_approve():
    res = can_transition('Staff', actor_id=11, receiver_id=10, current_status='pending', requested_status='approved', comment='')
    assert res['ok'] is False and res['type'] == 'forbidden'

def test_admin_can_approve_without_being_receiver():
    res = can_transition('Admin', actor_id=2, receiver_id=10, current_status='pending', requested_status='approved', comment='')
    assert res['ok'] is True

def test_reject_requires_comment():
    res = can_transition('HOD', actor_id=10, receiver_id=10, current_status='pending', requested_status='rejected', comment='')
    assert res['ok'] is False and res['type'] == 'comment_required'

def test_acknowledge_by_receiver():
    res = can_transition('Staff', actor_id=20, receiver_id=20, current_status='submitted', requested_status='acknowledged', comment='')
    assert res['ok'] is True

def main():
    cases = [
        ("hod_can_approve_pending", test_hod_can_approve_pending),
        ("non_receiver_cannot_approve", test_non_receiver_cannot_approve),
        ("admin_can_approve", test_admin_can_approve_without_being_receiver),
        ("reject_requires_comment", test_reject_requires_comment),
        ("acknowledge_by_receiver", test_acknowledge_by_receiver),
    ]
    ok = True
    for name, fn in cases:
        res = run_case(name, fn)
        ok = ok and res
    if ok:
        print("All tests passed")
        sys.exit(0)
    else:
        print("Some tests failed")
        sys.exit(2)

if __name__ == '__main__':
    main()
