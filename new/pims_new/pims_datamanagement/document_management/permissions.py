"""
Central permission/policy rules for document management.

All role-based checks should be defined here as plain functions.
Views import and call these instead of duplicating logic inline.
"""

from django.db.models import Q
from django.utils import timezone

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


def is_md(user):
    staff = get_staff(user)
    return staff is not None and staff.is_md


def is_mayor(user):
    staff = get_staff(user)
    return staff is not None and staff.is_mayor


def is_head_or_supervisor(user):
    """Oversight heads (HOD / section / division) or supervisor / executive /
    MD / Mayor. Pure heads-of-unit are treated like regular staff."""
    return is_privileged_viewer(user)


def is_privileged_viewer(user):
    """Who counts as oversight for VIEWING personnel documents.

    HOD, section/division heads, flagged supervisors, executives, MD, Mayor
    (and superusers). Pure heads-of-unit are NOT included — they get the same
    lower-staff treatment: no own-file contents, in-transit-only My Files,
    no subordinate browsing.
    """
    staff = get_staff(user)
    if not staff:
        return user.is_superuser
    return bool(user.is_superuser or staff.is_privileged_head)


def can_view_staff_documents(user):
    """
    Gate for seeing staff personnel documents — even just titles/metadata.

    Granted via the ``document_management.view_staff_documents`` permission,
    which every group EXCEPT Registry holds (see migration 0045). Registry is
    hard-denied here regardless (separation of duties): registry staff manage
    file custody but must never see what documents a staff member has.
    """
    if user.is_superuser:
        return True
    staff = get_staff(user)
    if staff is not None and staff.is_registry:
        return False
    return user.has_perm("document_management.view_staff_documents")


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------


def can_create_file(user):
    """Only registry staff can create files."""
    return is_registry(user)


def can_view_file(user, file):
    """Who can open the file detail page."""
    if user.is_superuser or is_registry(user) or is_executive(user) or is_mayor(user):
        return True
    staff = get_staff(user)
    if not staff:
        return False
    if file.owner == staff or file.current_location == staff:
        return True
    if file.file_type == "policy" and is_hod(user) and file.department == staff.department:
        return True
    if file.file_type == "personal":
        owner = file.owner
        owner_dept = owner.department if owner else None
        file_dept = file.department
        # HOD sees personal files in their department.
        if is_hod(user) and (
            (owner and owner_dept == staff.department) or file_dept == staff.department
        ):
            return True
        # Section / division heads + supervisors see staff files in their own
        # jurisdiction (section / division / department). Pure heads-of-unit
        # are treated like regular staff and get nothing here.
        if staff.is_privileged_head:
            if owner:
                if staff.is_head_of_section and owner.section_id:
                    try:
                        if owner.section_id == staff.headed_section.pk:
                            return True
                    except Exception:
                        pass
                if staff.is_head_of_division and owner.division_id:
                    try:
                        if owner.division_id == staff.headed_division.pk:
                            return True
                    except Exception:
                        pass
                # Fallback: same-department visibility for any oversight head.
                if owner_dept and staff.department and owner_dept.pk == staff.department.pk:
                    return True
            elif file_dept and staff.department and file_dept.pk == staff.department.pk:
                return True
    # Approved access request
    from document_management.models import FileAccessRequest

    return (
        FileAccessRequest.objects.filter(file=file, requested_by=user, status="approved")
        .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
        .exists()
    )


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
    """Registry, Mayor, or current custodian with RW access can add documents."""
    if file.status != "active":
        return False
    if file.is_in_active_chain:
        return False
    if is_registry(user):
        return True
    staff = get_staff(user)
    if not staff:
        return False
    # Mayor carries read & write on any file they can open.
    if is_mayor(user):
        return True
    if file.current_location != staff:
        return False
    from document_management.models import FileAccessRequest

    if (
        FileAccessRequest.objects.filter(file=file, requested_by=user, status="approved", access_type="read_write")
        .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
        .exists()
    ):
        return True
    # Movement-based RW: dispatched recipient holding (or sent) the file.
    latest = file.movements.filter(sent_to=staff, action="sent").order_by("-moved_at").first()
    return bool(latest and latest.is_active_access)


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


def can_share_document(user):
    """Check if user can share documents via email (HODs with permission)."""
    if user.is_superuser:
        return True
    staff = get_staff(user)
    if not staff:
        return False
    # HODs with the can_share_documents permission
    return staff.is_hod and user.has_perm("user_management.can_share_documents")


def can_view_document_content(user, file=None):
    """
    Who can view the actual contents of documents (minute_content, attachments).

    Role base: HODs, Supervisors, Executives, MD can always view.
    Registry can NEVER view contents (separation-of-duties), even as custodian.
    Contextual grants (non-registry only): file owner, current custodian,
    holder of an approved (unexpired) FileAccessRequest, or recipient of an
    active FileMovement can view — otherwise an owner with "Full Access"
    would still see a "Limited Access View" banner (the reported bug).
    Sensitive files still require HOD+ / supervisor / executive / MD unless
    one of the contextual grants above applies.
    """
    if user.is_superuser:
        return True
    staff = get_staff(user)
    if not staff:
        return False
    # Role base — always allowed (registry excluded below).
    # Mayor carries full read access like MD/Executive. Pure heads-of-unit
    # are NOT included — they are treated like regular staff.
    if is_privileged_viewer(user):
        return True
    if staff.is_registry:
        return False
    if file is None:
        return False
    # Lower staff can NEVER view contents of their OWN personal file —
    # not via custody, movement, share, or access request. Only heads/
    # supervisors / executives / MD / Mayor may view a staff member's file.
    if file.file_type == "personal" and file.owner_id and file.owner_id == staff.pk:
        return False
    # Contextual grants for regular staff.
    # Owner alone is NOT enough when file is at rest with Registry —
    # owner must hold custody or hold an approved request/movement/share.
    # This enforces "request from Registry" instead of silent auto-view.
    if file.owner == staff and file.current_location == staff:
        return True
    if file.current_location == staff:
        return True
    from document_management.models import FileAccessRequest

    has_approved = (
        FileAccessRequest.objects.filter(file=file, requested_by=user, status="approved")
        .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
        .exists()
    )
    if has_approved:
        return True
    latest_movement = file.movements.filter(sent_to=staff, action="sent").order_by("-moved_at").first()
    if latest_movement and latest_movement.is_active_access:
        return True
    # Shared directly on a document in this file.
    if file.documents.filter(shared_with=user).exists():
        return True
    return False


def can_view_document(user, document):
    """
    Who can view a document's detail page.
    Only HODs, Supervisors, and Executives can view document contents.
    Registry and general staff cannot view document contents.
    """
    if not can_view_file(user, document.file):
        return False
    return can_view_document_content(user, file=document.file)


# ---------------------------------------------------------------------------
# Dispatch recipient rules
# ---------------------------------------------------------------------------


def get_dispatch_recipients(user, file):
    """
    Returns a Staff queryset of valid recipients for dispatching a document.
    Registry → anyone (all non-registry staff).
    MD / Executive → anyone.
    HOD → other HODs, heads of units/sections/divisions, supervisors.
    Unit Manager → HOD, other HODs, heads of units/sections/divisions, supervisors.
    Supervisor sending someone else's file → other supervisors + direct heads.
    Regular staff → unit manager if exists, else section head, else division head, else HOD.
    """
    from organization.models import Department as Dept
    from organization.models import Staff, Unit

    from document_management.views.base import EXCLUDE_REGISTRY_Q

    base_qs = (
        Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
        .exclude(user=user)
        .select_related("user", "designation", "department", "unit", "section", "division")
    )
    staff = get_staff(user)
    if not staff:
        return base_qs.none()

    if is_registry(user) or is_executive(user) or is_md(user) or is_mayor(user):
        return base_qs

    if is_hod(user) or (is_unit_manager(user) and is_privileged_viewer(user)):
        # HODs (and unit managers who ALSO hold an oversight role) can send to:
        # - Other HODs
        # - Heads of units, sections, divisions
        # - Supervisors
        # Pure heads-of-unit fall through to the regular chain below.
        allowed_pks = set()
        
        # Other HODs
        for d in Dept.objects.filter(head__isnull=False):
            if d.head.pk != staff.pk:
                allowed_pks.add(d.head.pk)
        
        # Heads of units
        for u in Unit.objects.filter(head__isnull=False):
            if u.head.pk != staff.pk:
                allowed_pks.add(u.head.pk)
        
        # Heads of sections
        from organization.models import Section
        for s in Section.objects.filter(head__isnull=False):
            if s.head.pk != staff.pk:
                allowed_pks.add(s.head.pk)
        
        # Heads of divisions
        from organization.models import Division
        for d in Division.objects.filter(head__isnull=False):
            if d.head.pk != staff.pk:
                allowed_pks.add(d.head.pk)
        
        # Supervisors
        for s in base_qs.filter(is_supervisor=True):
            if s.pk != staff.pk:
                allowed_pks.add(s.pk)
        
        return base_qs.filter(pk__in=allowed_pks)

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

    # Regular staff (and pure heads-of-unit): up the chain of command,
    # skipping self so a unit manager routes to THEIR head, not themselves.
    for head in (
        staff.unit.head if staff.unit else None,
        staff.section.head if staff.section else None,
        staff.division.head if staff.division else None,
        staff.department.head if staff.department else None,
    ):
        if head and head.pk != staff.pk:
            return base_qs.filter(pk=head.pk)
    return base_qs.none()


def can_share_document(user):
    """Check if user has permission to share documents via email."""
    if user.is_superuser:
        return True
    return user.has_perm("user_management.can_share_documents")
