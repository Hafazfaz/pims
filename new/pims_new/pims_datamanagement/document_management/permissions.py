"""
Central permission/policy rules for document management.

All role-based checks should be defined here as plain functions.
Views import and call these instead of duplicating logic inline.
"""
from django.utils import timezone
from django.db.models import Q


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def get_staff(user):
    return getattr(user, "staff", None)


def is_registry(user):
    staff = get_staff(user)
    return user.is_superuser or (staff is not None and staff.is_registry)


def is_hod(user):
    staff = get_staff(user)
    return staff is not None and staff.is_hod


def is_unit_manager(user):
    staff = get_staff(user)
    return staff is not None and staff.is_unit_manager


def is_supervisor(user):
    staff = get_staff(user)
    return staff is not None and staff.is_effective_supervisor


def is_executive(user):
    staff = get_staff(user)
    return staff is not None and (staff.is_md or staff.is_executive)


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------

def can_create_file(user):
    """Only registry staff can create files."""
    return is_registry(user)


def can_view_file(user, file):
    """Who can open the file detail page."""
    if user.is_superuser or is_registry(user) or is_executive(user):
        return True
    staff = get_staff(user)
    if not staff:
        return False
    if file.owner == staff or file.current_location == staff:
        return True
    if file.file_type == "policy":
        if (is_hod(user) or is_unit_manager(user)) and file.department == staff.department:
            return True
    if file.file_type == "personal" and is_hod(user) and file.owner and file.owner.department == staff.department:
        return True
    # Approved access request
    from document_management.models import FileAccessRequest
    return FileAccessRequest.objects.filter(
        file=file, requested_by=user, status="approved"
    ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()


def can_activate_file(user, file):
    """Registry can activate any pending/inactive file."""
    return is_registry(user) and file.status in ("inactive", "pending_activation")


def can_close_file(user, file):
    return is_registry(user) and file.status == "active"


def can_archive_file(user, file):
    return is_registry(user) and file.status == "closed"


def can_send_file(user, file):
    """
    Sending a file (dispatching) is DISABLED — only documents are dispatched.
    Kept as a no-op so existing references don't break.
    """
    return False


# ---------------------------------------------------------------------------
# Document permissions
# ---------------------------------------------------------------------------

def can_add_document(user, file):
    """Registry or current custodian with RW access can add documents."""
    if not file.status == "active":
        return False
    if file.is_in_active_chain:
        return False
    if is_registry(user):
        return True
    staff = get_staff(user)
    if not staff or file.current_location != staff:
        return False
    from document_management.models import FileAccessRequest
    return FileAccessRequest.objects.filter(
        file=file, requested_by=user, status="approved", access_type="read_write"
    ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()


def can_dispatch_document(user, file):
    """
    Who can dispatch (send) a document from a file.
    Registry can dispatch to anyone.
    Other custodians follow the chain-of-command rules.
    File must be active.
    """
    if file.status != "active":
        return False
    if file.is_in_active_chain:
        return False
    if is_registry(user):
        return True
    staff = get_staff(user)
    return staff is not None and file.current_location == staff


def can_delete_document(user, document):
    """Only the uploader or registry can delete a document."""
    return is_registry(user) or document.uploaded_by == user


def can_view_document_content(user):
    """
    Who can view the actual contents of documents (minute_content, attachments).
    Only HODs, Supervisors, Executives, and MD — NOT registry or general staff.
    """
    if user.is_superuser:
        return True
    staff = get_staff(user)
    if not staff:
        return False
    return staff.is_hod or staff.is_effective_supervisor or staff.is_executive or staff.is_md


def can_view_document(user, document):
    """
    Who can view a document's detail page.
    Only HODs, Supervisors, and Executives can view document contents.
    Registry and general staff cannot view document contents.
    """
    if not can_view_file(user, document.file):
        return False
    return can_view_document_content(user)


# ---------------------------------------------------------------------------
# Dispatch recipient rules
# ---------------------------------------------------------------------------

def get_dispatch_recipients(user, file):
    """
    Returns a Staff queryset of valid recipients for dispatching a document.
    Registry → anyone (all non-registry staff).
    HOD / MD / Executive → anyone.
    Supervisor sending someone else's file → other supervisors + direct heads.
    Regular staff → unit manager if exists, else HOD.
    """
    from organization.models import Staff
    from document_management.views.base import EXCLUDE_REGISTRY_Q

    base_qs = Staff.objects.exclude(EXCLUDE_REGISTRY_Q).exclude(user=user).select_related(
        "user", "designation", "department", "unit"
    )
    staff = get_staff(user)
    if not staff:
        return base_qs.none()

    if is_registry(user) or is_executive(user) or is_hod(user):
        return base_qs

    if is_supervisor(user) and file.owner != staff:
        supervisor_pks = [s.pk for s in base_qs if s.is_effective_supervisor]
        head_pks = []
        if staff.unit and staff.unit.head:
            head_pks.append(staff.unit.head.pk)
        if staff.section and staff.section.head:
            head_pks.append(staff.section.head.pk)
        if staff.division and staff.division.head:
            head_pks.append(staff.division.head.pk)
        if staff.department and staff.department.head:
            head_pks.append(staff.department.head.pk)
        return base_qs.filter(pk__in=set(supervisor_pks + head_pks))

    # Regular staff: Unit Head → Section Head → Division Head → HOD
    if staff.unit and staff.unit.head:
        return base_qs.filter(pk=staff.unit.head.pk)
    if staff.section and staff.section.head:
        return base_qs.filter(pk=staff.section.head.pk)
    if staff.division and staff.division.head:
        return base_qs.filter(pk=staff.division.head.pk)
    if staff.department and staff.department.head:
        return base_qs.filter(pk=staff.department.head.pk)
    return base_qs.none()
