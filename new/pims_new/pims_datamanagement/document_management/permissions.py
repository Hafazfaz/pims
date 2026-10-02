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


def is_global_viewer(user):
    """Explicitly-granted global visibility: every file and staff record,
    regardless of department, ownership, or custody.

    Granted via ``user_management.can_view_all_staff_files`` — held by the
    MD, Executives, and Administrator groups, and assignable from the admin
    to any individual user (including people in no department at all).

    Gates that enforce separation of duties (Registry vs personnel records)
    check ``is_registry`` FIRST, so Registry stays denied even if someone
    grants this permission to the Registry group.
    """
    return bool(user and user.is_authenticated and user.has_perm("user_management.can_view_all_staff_files"))


def can_view_staff_documents(user):
    """
    Gate for seeing staff personnel documents — even just titles/metadata.

    Granted via the ``document_management.view_staff_documents`` permission,
    which every group EXCEPT Registry holds (see migration 0045), or via the
    global ``user_management.can_view_all_staff_files`` grant. Registry is
    hard-denied here regardless (separation of duties): registry staff manage
    file custody but must never see what documents a staff member has.
    """
    if user.is_superuser:
        return True
    staff = get_staff(user)
    if staff is not None and staff.is_registry:
        return False
    # Global viewers see personnel records too (registry still denied above).
    if is_global_viewer(user):
        return True
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
    if is_global_viewer(user):
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
        # Head of unit sees personal files of staff in their OWN unit
        # (HOD-like oversight, unit-scoped). Never their own file via this
        # branch — owners are handled above.
        if owner and owner.pk != staff.pk and staff.is_head_of_unit:
            try:
                headed_unit = staff.headed_unit
            except Exception:
                headed_unit = None
            if headed_unit is not None and owner.unit_id and owner.unit_id == headed_unit.pk:
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
    """Registry can activate any inactive file."""
    return is_registry(user) and file.status == "inactive"


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


def can_add_document(user, file, *, require_active=True):
    """Single source of truth: may ``user`` add a document to ``file``?

    Called by BOTH the add-document endpoint (``DocumentCreateView.dispatch``)
    and the button-visibility context (``can_add_minute``) so the button can
    never be shown for an action the endpoint will refuse.

    Rules (in order):
    - the file must be active (unless ``require_active=False``, used by the
      endpoint so it can show an accurate "file is not active" message);
    - Registry / superuser — always;
    - Mayor, MD, Executive — read & write on any file;
    - an approved, unexpired ``read_write`` FileAccessRequest;
    - movement-based RW — dispatched recipient still holding active access;
    - the file owner (any file type);
    - HOD of the file's department, on non-personal files.
    """
    if require_active and file.status != "active":
        return False
    if is_registry(user):
        return True
    staff = get_staff(user)
    if not staff:
        return False
    if is_mayor(user) or is_executive(user):
        return True
    from document_management.models import FileAccessRequest

    if (
        FileAccessRequest.objects.filter(
            file=file, requested_by=user, status="approved", access_type="read_write"
        )
        .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
        .exists()
    ):
        return True
    latest = file.movements.filter(sent_to=staff, action="sent").order_by("-moved_at").first()
    if latest and latest.is_active_access:
        return True
    if file.owner == staff:
        return True
    if file.file_type != "personal" and is_hod(user) and file.department == staff.department:
        return True
    return False


def can_manual_dispatch(user):
    """Who may manually dispatch/forward a file at all.

    Registry, oversight heads (HOD / section / division), flagged
    supervisors, executives, MD, Mayor (and superusers). Regular staff
    and pure heads-of-unit cannot dispatch — their documents auto-route
    up the reporting chain instead.
    """
    if user.is_superuser:
        return True
    return bool(is_registry(user) or is_privileged_viewer(user))


def can_dispatch_document(user, file):
    """
    Who can dispatch (send) a document from a file.
    Registry can dispatch to anyone.
    Other custodians follow the reporting-hierarchy rules.
    Regular staff cannot dispatch at all.
    File must be active.
    """
    if file.status != "active":
        return False
    if not can_manual_dispatch(user):
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


def has_content_scope(user, file, document=None):
    """Role/jurisdiction scope for viewing AND downloading document contents.

    Grants (registry NEVER passes — checked by callers first):
    - file owner — always, including their own personal file;
    - head of the owner's unit — personal files of members of that unit;
    - HOD or effective supervisor of the relevant department — personal
      files of staff in that department, or policy files of that department;
    - uploader of the specific document (when ``document`` is given).

    This is the jurisdiction scope used by the download gate
    (``can_download_document_file``) alongside the content gate, so View
    and Download stay in sync. On its own it grants nothing — the content
    gate additionally requires custody or an explicit grant for
    non-leadership roles. Approved documents are out of scope entirely:
    once a document is approved, standing scope ends and only top
    leadership or a fresh approved request opens it.
    """
    staff = get_staff(user)
    if staff is not None and staff.is_registry:
        return False
    # Global viewers (MD / Executives / granted users) always carry scope,
    # so their View and Download stay in sync.
    if is_global_viewer(user):
        return True
    if not staff:
        return False

    # Approved documents: standing scope is over (owner, unit head,
    # department, uploader). Only leadership (handled by callers) or an
    # explicit approved request re-opens them.
    if document is not None and document.status == "approved":
        return False

    owner = file.owner if file else None

    # Owner always carries scope for their own file.
    if owner is not None and owner.pk == staff.pk:
        return True

    # Head of the owner's unit — members' personal files.
    if owner is not None and file is not None and file.file_type == "personal":
        try:
            headed_unit = staff.headed_unit
        except Exception:
            headed_unit = None
        if headed_unit is not None and owner.unit_id and owner.unit_id == headed_unit.pk:
            return True

    # HOD / effective supervisor of the relevant department.
    dept_id = None
    if file is not None:
        if file.file_type == "personal" and owner is not None:
            dept_id = owner.department_id
        elif file.file_type == "policy":
            dept_id = file.department_id
    if dept_id and staff.department_id and dept_id == staff.department_id:
        if staff.is_hod or staff.is_effective_supervisor:
            return True

    # Uploader of this specific document.
    if document is not None and document.uploaded_by_id == user.pk:
        return True

    return False


def can_view_document_content(user, file=None, document=None):
    """
    Who can view the actual contents of documents (minute_content, attachments).

    Custody rule: HODs, unit/section/division heads, and supervisors see
    contents ONLY while they hold custody (current_location) or hold an
    explicit grant — an approved (unexpired) FileAccessRequest, an active
    FileMovement, or a direct document share. Browsing a file from the
    inbox/sent lists without custody shows metadata only.
    Standing access (no custody needed): holders of the explicit
    ``user_management.can_view_all_staff_files`` grant (MD / Executives /
    admin-designated viewers), superusers, Executives, MD, Mayor,
    the file owner, and the uploader of the specific document — except on
    approved documents, where owner/uploader standing access ends and only
    top leadership or a fresh approved request opens them.
    Registry can NEVER view contents (separation-of-duties), even as custodian.
    Sensitive files follow the same rule — no role bypasses it.
    """
    if user.is_superuser:
        return True
    staff = get_staff(user)
    # Separation of duties first: Registry stays denied even with the grant.
    if staff is not None and staff.is_registry:
        return False
    # Explicit global grant (MD / Executives / admin-designated viewers) —
    # works with or without a staff profile / department.
    if is_global_viewer(user):
        return True
    if not staff:
        return False
    # Top leadership retains oversight access without custody.
    if staff.is_executive or staff.is_md or getattr(staff, "is_mayor", False):
        return True
    if file is None:
        return False
    # Owner scope (own file, no custody needed) and uploader scope —
    # both end once the document is approved.
    _is_approved_doc = document is not None and document.status == "approved"
    owner = file.owner
    if owner is not None and owner.pk == staff.pk and not _is_approved_doc:
        return True
    if document is not None and document.uploaded_by_id == user.pk and not _is_approved_doc:
        return True
    # Head of the owner's unit — standing oversight of members' personal
    # files in that unit (mirrors has_content_scope so View and Download
    # stay in sync). Excludes approved documents and the viewer's own file.
    if (
        file.file_type == "personal"
        and owner is not None
        and owner.pk != staff.pk
        and not _is_approved_doc
        and staff.is_head_of_unit
    ):
        try:
            headed_unit = staff.headed_unit
        except Exception:
            headed_unit = None
        if headed_unit is not None and owner.unit_id and owner.unit_id == headed_unit.pk:
            return True
    # Everyone else — HODs, all heads, supervisors, regular staff — needs
    # custody or an explicit grant. No silent role-based viewing.
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
    Requires file-page access plus content access (custody or explicit
    grant; standing access for owner, uploader, Executive/MD/Mayor).
    Registry can never view contents.
    """
    if not can_view_file(user, document.file):
        return False
    return can_view_document_content(user, file=document.file, document=document)


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
    Regular staff (and pure heads-of-unit) → none; they cannot dispatch.
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

    # Regular staff and pure heads-of-unit cannot dispatch at all.
    if not can_manual_dispatch(user):
        return base_qs.none()

    if is_registry(user) or is_executive(user) or is_md(user) or is_mayor(user):
        return base_qs

    if is_hod(user) or (is_unit_manager(user) and is_privileged_viewer(user)):
        # HODs (and unit managers who ALSO hold an oversight role) can send to:
        # - Other HODs
        # - Heads of units, sections, divisions
        # - Supervisors
        # Pure heads-of-unit fall through to the regular hierarchy below.
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

    # Regular staff (and pure heads-of-unit): up the reporting hierarchy,
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
