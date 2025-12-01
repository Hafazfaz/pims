"""Workflow state machine helper: allowed transitions and validation.
This module provides can_transition() which validates whether an actor
may move a workflow from current_status -> requested_status and whether
a comment is required.
"""

transitions = {
    'submitted': ['acknowledged', 'pending', 'escalated'],
    'acknowledged': ['pending', 'escalated'],
    'pending': ['approved', 'rejected', 'escalated'],
    'approved': ['archived', 'escalated'],
    'rejected': ['submitted', 'escalated'],
    'escalated': ['pending', 'approved', 'archived'],
}


def can_transition(actor_role, actor_id, receiver_id, current_status, requested_status, comment):
    """Return dict {ok:bool, type:<'forbidden'|'invalid'|'comment_required'|'ok'>, message:str}

    actor_role: role name string (e.g., 'HOD', 'Admin', 'Staff')
    actor_id: integer id of actor
    receiver_id: integer id of the workflow's assigned receiver
    current_status: existing status string
    requested_status: desired status string
    comment: provided comment (or None)
    """
    # no-op if same status
    if requested_status == current_status:
        return {'ok': True}

    # Admin may perform any transition
    if actor_role == 'Admin':
        # still require comment for specific actions
        if requested_status in ('rejected', 'escalated') and not comment:
            return {'ok': False, 'type': 'comment_required', 'message': 'Comment required for this transition'}
        return {'ok': True}

    # validate allowed transitions
    allowed = transitions.get(current_status, [])
    if requested_status not in allowed:
        return {'ok': False, 'type': 'invalid', 'message': f'Invalid transition: {current_status} -> {requested_status}'}

    # role-specific rules
    # Acknowledge: only the receiver can acknowledge
    if requested_status == 'acknowledged':
        if actor_id != receiver_id:
            return {'ok': False, 'type': 'forbidden', 'message': 'Only assigned receiver can acknowledge'}
        return {'ok': True}

    # Approve/Reject: only HOD (receiver) can do this (except Admin handled earlier)
    if requested_status in ('approved', 'rejected'):
        if actor_role != 'HOD' and actor_id != receiver_id:
            return {'ok': False, 'type': 'forbidden', 'message': 'Only HOD or assigned receiver can approve/reject'}
        if requested_status == 'rejected' and not comment:
            return {'ok': False, 'type': 'comment_required', 'message': 'Comment required for rejection'}
        return {'ok': True}

    # Escalate: HOD or receiver can escalate, but comment required
    if requested_status == 'escalated':
        if actor_role not in ('HOD', 'Admin') and actor_id != receiver_id:
            return {'ok': False, 'type': 'forbidden', 'message': 'Only HOD, Admin, or receiver can escalate'}
        if not comment:
            return {'ok': False, 'type': 'comment_required', 'message': 'Comment required for escalation'}
        return {'ok': True}

    # For other transitions (pending, archived, submitted resubmit), allow if actor is receiver or HOD
    if actor_id == receiver_id or actor_role == 'HOD':
        return {'ok': True}

    return {'ok': False, 'type': 'forbidden', 'message': 'Actor is not permitted to perform this transition'}
