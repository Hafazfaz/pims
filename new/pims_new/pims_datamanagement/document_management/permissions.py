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
    """Registry custody management access.

    Separation of duties is preserved elsewhere: this only grants custody
    management rights (create file, activate/close/archive, approve access),
    not content viewing.
    """
    if user.is_superuser:
        return True
    return user.has_perm("user_management.can_manage_registry")


def is_hod(user):
    """Department-head scope.

    Delegates to :attr:`Staff.is_hod`, which reads the
    ``user_management.can_head_department`` permission granted by the
    organization signals on appointment.
    """
    staff = get_staff(user)
    return staff is not None and staff.is_hod


def is_unit_manager(user):
    """Head-of-unit scope (``user_management.can_head_unit``)."""
    staff = get_staff(user)
    return staff is not None and staff.is_unit_manager


def is_supervisor(user):
    """Effective supervisor: flagged, head of unit/section/division, HOD, or
    holder of ``can_supervise`` / ``can_executive``."""
    staff = get_staff(user)
    return staff is not None and staff.is_effective_supervisor


def is_executive(user):
    """Executive / MD / Mayor level broad access."""
    if user.is_superuser:
        return True
    return user.has_perm("user_management.can_executive")


def is_md(user):
    """MD is covered by the executive permission bundle."""
    return is_executive(user)


def is_mayor(user):
    """Mayor is covered by the executive permission bundle."""
    return is_executive(user)


def is_head_or_supervisor(user):
    """Oversight heads (HOD / section / division) or supervisor / executive /
    MD / Mayor (and superusers)."""
    return is_privileged_viewer(user)


def is_privileged_viewer(user):
    """Who counts as oversight for VIEWING personnel documents.

    Backed by :attr:`Staff.is_privileged_head`: HOD, section/division heads,
    flagged/group-granted supervisors, executives, MD, Mayor (and
    superusers). Pure heads-of-unit are NOT included — they get the same
    lower-staff treatment: their own pending documents open on their own
    file while approved ones stay closed, and no subordinate browsing.
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
    if is_registry(user):
        return False
    # Global viewers see personnel records too (registry still denied above).
    if is_global_viewer(user):
        return True
    return user.has_perm("document_management.view_staff_documents")


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------


def can_create_file(user):
    """Only registry staff (permission-based) can create files."""
    return is_registry(user)


def can_view_file(user, file):
    """Who can open the file detail page (capability + relational scope)."""
    if user.is_superuser or is_registry(user) or is_executive(user):
        return True
    if is_global_viewer(user):
        return True
    staff = get_staff(user)
    if not staff:
        return False
    if file.owner == staff or file.current_location == staff:
        return True
    if file.file_type == "policy" and user.has_perm("user_management.can_supervise") and file.department == staff.department:
        return True
    if file.file_type == "personal":
        owner = file.owner
        owner_dept = owner.department if owner else None
        file_dept = file.department
        # Supervisors see personal files in their department / unit / section / division.
        if user.has_perm("user_management.can_supervise"):
            if owner and owner_dept and staff.department and owner_dept.pk == staff.department.pk:
                return True
            if file_dept and staff.department and file_dept.pk == staff.department.pk:
                return True
            # Unit scope
            if owner and owner.unit_id and staff.unit_id and owner.unit_id == staff.unit_id:
                return True
        # Head of the owner's unit (kept as a narrower scope for unit heads)
        if owner and owner.pk != staff.pk and user.has_perm("user_management.can_supervise"):
            try:
                headed_unit = staff.headed_unit
            except Exception:
                headed_unit = None
            if headed_unit is not None and owner.unit_id and owner.unit_id == headed_unit.pk:
                return True
    # Approved access request — only while its holder still has custody.
    return active_access_request(file, user) is not None


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
# Access-request grants (tied to custody)
# ---------------------------------------------------------------------------


def active_access_request(file, user, *, access_type=None):
    """The user's approved, unexpired FileAccessRequest — but ONLY while they
    still hold custody of the file.

    Approving a request transfers custody to the requester
    (``FileAccessRequestApproveView``), so a grant is valid exactly as long
    as its holder's custody. Every custody change expires grants through
    :func:`revoke_approved_access`; this check is the belt-and-braces half of
    the same rule, so a stale row can never reopen a file whose custody has
    moved on. Returns the ``FileAccessRequest`` or ``None``.
    """
    from document_management.models import FileAccessRequest

    staff = get_staff(user)
    if staff is None or file is None or file.current_location_id != staff.pk:
        return None
    qs = FileAccessRequest.objects.filter(file=file, requested_by=user, status="approved")
    if access_type:
        qs = qs.filter(access_type=access_type)
    return qs.filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).first()


def revoke_approved_access(file, *, keep=None):
    """Expire every approved grant on ``file`` — all but ``keep`` if given.

    Called at EVERY custody change (recall, send/dispatch, document
    auto-route, inbox approve/forward/reject, final approval, signature
    approvals, custody reclaim, and approval of a newer access request) so a
    grant lives exactly as long as its holder's custody: once the file moves
    out of someone's hands their grant is expired and they must request
    access again. Returns the number of grants revoked.
    """
    from document_management.models import FileAccessRequest

    qs = FileAccessRequest.objects.filter(file=file, status="approved")
    if keep is not None:
        qs = qs.exclude(pk=keep.pk)
    return qs.update(status="expired")


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
    - personal files — the owner (only while they hold custody) and Registry only;
    - Registry / superuser / Executives — always (other file types);
    - non-registry staff MUST be the current custodian to write;
    - an approved, unexpired ``read_write`` FileAccessRequest (read_only never
      permits writing) — valid ONLY while its holder still has custody; every
      custody change expires grants (``revoke_approved_access``), so once the
      file moves out of their hands they must request access again;
    - movement-based RW — dispatched recipient whose pending movement is still active;
    - the file owner while they hold custody;
    - Supervisor of the file's department, on non-personal files, while holding custody.
    """
    if require_active and file.status != "active":
        return False
    if file.file_type == "personal":
        if is_registry(user) or user.is_superuser:
            return True
        staff = get_staff(user)
        return bool(
            staff
            and file.owner_id == staff.pk
            and file.current_location_id == staff.pk
        )
    if is_registry(user) or user.is_superuser or is_executive(user):
        return True
    staff = get_staff(user)
    if not staff:
        return False
    if file.current_location_id != staff.pk:
        return False
    if active_access_request(file, user, access_type="read_write") is not None:
        return True
    latest = (
        file.movements.filter(sent_to=staff, action="sent", status="pending")
        .order_by("-moved_at")
        .first()
    )
    if latest and latest.is_active_access:
        return True
    if file.owner == staff:
        return True
    if (
        file.file_type != "personal"
        and user.has_perm("user_management.can_supervise")
        and file.department == staff.department
    ):
        return True
    return False


def can_manual_dispatch(user):
    """Any authenticated staff member may route a document."""
    if user.is_superuser:
        return True
    staff = get_staff(user)
    return staff is not None


def can_dispatch_document(user, file):
    """Any current custodian (or registry) can dispatch from an active file."""
    if file.status != "active":
        return False
    if is_registry(user) or user.is_superuser:
        return True
    staff = get_staff(user)
    return staff is not None and file.current_location == staff


def can_delete_document(user, document):
    """Only the uploader or registry can delete a document."""
    return is_registry(user) or document.uploaded_by == user


def can_edit_document(user, document=None):
    """Who may edit a document's title, minute content or attachments.

    Editing is NEVER implied by viewing (or by executive/HOD/MD standing) —
    that let oversight roles rewrite other people's documents. Editing
    someone else's document requires the explicit, manually assigned
    ``user_management.can_edit_staff_documents`` grant. The document's own
    uploader, Registry and superusers always keep access.
    """
    if user.is_superuser:
        return True
    if is_registry(user):
        return True
    if document is not None and document.uploaded_by_id == user.pk:
        return True
    return user.has_perm("user_management.can_edit_staff_documents")


def has_content_scope(user, file, document=None):
    """Permission/jurisdiction scope for viewing AND downloading document contents.

    Grants (registry NEVER passes — checked by callers first):
    - file owner — always, including their own personal file;
    - head of the owner's unit — personal files of members of that unit;
    - Supervisor of the relevant department — personal files of staff in that
      department, or policy files of that department;
    - uploader of the specific document (when ``document`` is given).

    This is the jurisdiction scope used by the download gate
    (``can_download_document_file``) alongside the content gate, so View
    and Download stay in sync. On its own it grants nothing — the content
    gate additionally requires custody or an explicit grant for
    non-leadership roles. Approved documents are out of scope entirely:
    once a document is approved, standing scope ends and only top
    leadership or a fresh approved request opens it.
    """
    if is_registry(user):
        return False
    if is_global_viewer(user):
        return True
    staff = get_staff(user)
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

    # Department head / supervisor of the file's department.
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

    Custody rule: supervisors see contents ONLY while they hold custody
    (current_location) or hold an explicit grant — an approved (unexpired)
    FileAccessRequest, an active FileMovement, or a direct document share.
    Approved grants are custody-tied: they are valid only while the holder
    still has custody, and every custody change expires them
    (``revoke_approved_access``), so a former holder must request again.
    Browsing a file from the inbox/sent lists without custody shows metadata only.
    Standing access (no custody needed): holders of the explicit
    ``user_management.can_view_all_staff_files`` grant (MD / Executives /
    admin-designated viewers), superusers, Executives, the file owner, and the
    uploader of the specific document — except on approved documents, where
    owner/uploader standing access ends and only top leadership or a fresh
    approved request opens them.
    Registry can NEVER view contents (separation-of-duties), even as custodian.
    Sensitive files follow the same rule — no role bypasses it.

    Personal files are grant-based and nothing else: the contents open only
    while the viewer holds an approved, unexpired access request on that file
    (Read or Read & Write) or a direct share on that document. Ownership,
    custody, uploads, approved requests on other files, movements and
    supervisory standing never open someone's personnel file — those callers
    keep the file page with titles and metadata only. That includes the file
    owner: they must request access like anyone else. Executives need the
    global grant for personal files too.
    """
    if user.is_superuser:
        return True
    staff = get_staff(user)
    # Separation of duties first: Registry stays denied even with the grant.
    if is_registry(user):
        return False
    # Explicit global grant (MD / Executives / admin-designated viewers) —
    # works with or without a staff profile / department.
    if is_global_viewer(user):
        return True
    if not staff:
        return False
    if file is not None and file.file_type == "personal":
        # Grant-based: the approved request must also still hold custody.
        if active_access_request(file, user) is not None:
            return True
        if document is not None and document.shared_with.filter(pk=user.pk).exists():
            return True
        latest_movement = file.movements.filter(sent_to=staff, action="sent").order_by("-moved_at").first()
        if latest_movement and latest_movement.is_active_access:
            return True
        return False
    # Top leadership retains oversight access without custody.
    if is_executive(user):
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
    # Everyone else — supervisors, regular staff — needs custody or an
    # explicit grant. No silent role-based viewing.
    if file.current_location == staff:
        return True
    if active_access_request(file, user) is not None:
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
    """Returns all non-registry staff (excluding the sender) as valid recipients."""
    from organization.models import Staff

    from document_management.views.base import EXCLUDE_REGISTRY_Q

    return (
        Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
        .exclude(user=user)
        .select_related("user", "designation", "department", "unit", "section", "division")
    )


def revoke_custody_access(file, previous_custodian_user=None):
    """Expire approved FileAccessRequests on ``file`` when custody changes.

    Deprecated alias of :func:`revoke_approved_access`: every holder's
    approved grants are revoked (``previous_custodian_user`` is ignored) —
    an approved grant is valid exactly as long as its holder has custody.
    """
    return revoke_approved_access(file)


def can_share_document(user):
    """Check if user has permission to share documents via email."""
    if user.is_superuser:
        return True
    return user.has_perm("user_management.can_share_documents")


# ---------------------------------------------------------------------------
# Final approval (the single document-approval right)
# ---------------------------------------------------------------------------


def can_final_approve_document(user):
    """Holder of ``can_approve_document`` — the Medical Director role.

    Nobody else settles a document: HODs, unit heads and supervisors route
    their approval to an approver instead.
    """
    if user.is_superuser:
        return True
    return user.has_perm("user_management.can_approve_document")


def get_final_approvers(exclude_staff=None):
    """Staff who can give the final document approval."""
    from django.contrib.auth.models import Permission

    from organization.models import Staff

    perm = Permission.objects.get(codename="can_approve_document", content_type__app_label="user_management")
    qs = (
        Staff.objects.filter(
            Q(user__user_permissions=perm) | Q(user__groups__permissions=perm) | Q(user__is_superuser=True)
        )
        .select_related("user", "designation", "department", "unit")
        .distinct()
    )
    if exclude_staff is not None:
        qs = qs.exclude(pk=exclude_staff.pk)
    return qs
