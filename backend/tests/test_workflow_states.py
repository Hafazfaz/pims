import pytest

from backend.workflow import can_transition


def test_hod_can_approve_pending():
    res = can_transition('HOD', actor_id=10, receiver_id=10, current_status='pending', requested_status='approved', comment='Looks good')
    assert res['ok'] is True


def test_non_receiver_cannot_approve():
    res = can_transition('Staff', actor_id=11, receiver_id=10, current_status='pending', requested_status='approved', comment='')
    assert res['ok'] is False
    assert res['type'] == 'forbidden'


def test_admin_can_approve_without_being_receiver():
    res = can_transition('Admin', actor_id=2, receiver_id=10, current_status='pending', requested_status='approved', comment='')
    assert res['ok'] is True


def test_reject_requires_comment():
    res = can_transition('HOD', actor_id=10, receiver_id=10, current_status='pending', requested_status='rejected', comment='')
    assert res['ok'] is False
    assert res['type'] == 'comment_required'


def test_acknowledge_by_receiver():
    res = can_transition('Staff', actor_id=20, receiver_id=20, current_status='submitted', requested_status='acknowledged', comment='')
    assert res['ok'] is True
