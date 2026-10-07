"""Sidebar navigation state: which single menu item reads as "active".

Exactly one key is resolved per request, so the menu can never show two
highlights at once. Deep pages (file/document detail, inbox movements,
access-request screens, ...) resolve back to the sidebar section they live
in, so the highlight follows you however far you navigate.

Keys are then normalised for the viewer: sections they cannot see (Registry
has no "My Records", a superuser has no "Inbox") fall back to their dashboard
instead of lighting up an item that is not on screen.
"""

# url names -> sidebar key, most specific sections first (only the first
# matching rule wins).
_URL_NAME_RULES = [
    ("notifications", {"notification_list", "mark_as_read", "mark_all_as_read"}),
    (
        "activity_report",
        {
            "my_activity_report",
            "activity_user_search",
            "export_access_denied",
            "export_full_activity",
        },
    ),
    ("audit_logs", {"audit_log_list"}),
    (
        "users",
        {
            "user_list",
            "user_create",
            "user_detail",
            "user_edit",
            "user_unlock",
            "user_suspend",
            "user_delete",
            "user_batch_upload",
            "user_sample_csv",
        },
    ),
    (
        "departments",
        {
            "department_list",
            "department_create",
            "department_detail",
            "department_edit",
            "department_delete",
            "department_search",
            "department_dependents",
        },
    ),
    ("divisions", {"division_list", "division_create", "division_edit", "division_delete"}),
    ("sections", {"section_list", "section_create", "section_edit", "section_delete"}),
    ("units", {"unit_list", "unit_create", "unit_edit", "unit_delete", "units_by_department"}),
    ("designations", {"designation_list", "designation_create", "designation_edit", "designation_delete"}),
    ("access_requests", {"access_request_list", "access_request_approve", "access_request_reject"}),
    (
        "document_types",
        {"document_type_list", "document_type_create", "document_type_delete", "documents_by_type"},
    ),
    ("outgoing", {"outgoing_dispatches", "dispatch_detail"}),
    ("create_file", {"file_create", "file_batch_upload", "file_batch_sample_csv"}),
    ("folders", {"staff_folder_list", "staff_folder_hub", "registry_file_view"}),
    ("explorer", {"record_explorer"}),
    ("new_urgent", {"urgent_document_create", "urgent_document_detail", "urgent_document_action"}),
    ("sent", {"outbox", "messages"}),
    # Dashboard is last: its url names are the generic landing pages.
    (
        "dashboard",
        {
            "home",
            "registry",
            "admin_dashboard",
            "admin_dashboard_health",
            "report_daily_movement",
            "report_dept_performance",
        },
    ),
]

# Sidebar sections whose highlight depends on who is looking.
_SECTION_URL_NAMES = {
    "inbox": {
        "inbox",
        "inbox_document_detail",
        "inbox_file_view",
        "inbox_ref_doc",
        "inbox_recipient_search",
        "document_action",
    },
    "my_files": {
        "file_detail",
        "file_edit",
        "file_delete",
        "file_close",
        "file_archive",
        "file_recall",
        "file_approve_creation",
        "file_documents_paginate",
        "staff_without_files",
        "document_add",
        "document_detail",
        "document_edit",
        "document_delete",
        "document_share",
        "document_share_email",
        "document_download",
        "document_approve_dispatch",
        "attachment_download",
        "attachment_view",
        "document_create",
    },
}

# Path fragments catch deep/odd URLs the url-name tables above miss.
_PATH_RULES = [
    ("notifications", ("notifications/",)),
    ("activity_report", ("my-activity",)),
    ("audit_logs", ("/audit/",)),
    ("access_requests", ("access-requests",)),
    ("document_types", ("document-types",)),
    ("outgoing", ("outgoing-dispatches", "/dispatch/")),
    ("explorer", ("/explorer",)),
    ("new_urgent", ("/urgent/",)),
    ("users", ("/accounts/users",)),
    ("departments", ("/org/departments",)),
    ("divisions", ("/org/divisions",)),
    ("sections", ("/org/sections",)),
    ("units", ("/org/units",)),
    ("designations", ("/org/designations",)),
    ("sent", ("/documents/outbox", "/documents/messages")),
    ("inbox", ("/documents/inbox",)),
    ("create_file", ("/documents/create", "/documents/batch-upload")),
    ("folders", ("/documents/staff/", "/documents/registry/")),
    (
        "my_files",
        ("/documents/my-files", "/documents/file/", "/documents/document/", "/documents/attachment/"),
    ),
]

# Sections only rendered for Registry staff (Files + Tools groups).
_REGISTRY_ONLY = {"folders", "create_file", "outgoing", "access_requests", "document_types"}

# Main-group items hidden from superusers (they only see Dashboard there).
_SUPERUSER_HIDDEN = {"my_files", "inbox", "sent", "new_urgent"} | _REGISTRY_ONLY

# Record-explorer section — only rendered for the roles the explorer opens
# up to: the executive/MD tier, HODs (their department) and unit heads (their unit).
_BROWSE_FILES = {"explorer"}

# Org tree items — only rendered for superusers.
_ORG_ONLY = {"departments", "divisions", "sections", "units", "designations"}


def _staff_of(user):
    """The user's Staff row, or None (a user without a profile never raises)."""
    try:
        return user.staff
    except Exception:
        return None


def _has(user, perm):
    """``user.has_perm`` that survives None/anonymous users."""
    try:
        return bool(user and user.has_perm(perm))
    except Exception:
        return False


def _section_key(key, user, is_superuser, is_registry, is_md, is_executive, is_head):
    """Remap a key onto an item that is actually rendered for this viewer.

    A page can belong to a section this user does not see (Registry has no
    "My Records", a superuser has no "Inbox", a regular officer has no record
    explorer), so in those cases the dashboard is highlighted instead —
    never a hidden item, and never two at once.
    """
    if is_superuser and key in _SUPERUSER_HIDDEN:
        return "dashboard"
    if key in _REGISTRY_ONLY:
        return key if is_registry else "dashboard"
    if key == "my_files":
        return "folders" if is_registry else "my_files"
    if key in {"sent", "new_urgent"} and is_registry:
        return "dashboard"
    if key in _BROWSE_FILES and not (is_md or is_head):
        return "dashboard"
    if key == "new_urgent" and not _has(user, "user_management.can_set_urgent_priority"):
        return "dashboard"
    if key == "users" and not (is_superuser or _has(user, "auth.view_user")):
        return "dashboard"
    if key in _ORG_ONLY and not is_superuser:
        return "dashboard"
    if key == "audit_logs" and not (is_superuser or getattr(user, "is_staff", False) or is_executive):
        return "dashboard"
    return key


def nav_active(request):
    """Expose ``nav_active`` — the single sidebar key for this request."""
    return {"nav_active": nav_key(request)}


def nav_key(request):
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""

    user = getattr(request, "user", None)
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    staff = _staff_of(user) if is_authenticated else None
    is_superuser = bool(getattr(user, "is_superuser", False))
    is_registry = bool(staff and staff.is_registry)
    is_md = bool(staff and staff.is_md)
    is_executive = bool(staff and staff.is_executive)
    is_head = bool(staff and (staff.is_hod or staff.is_unit_manager))

    url_name = match.url_name or ""
    path = request.path or ""

    # The MD's Dashboard link and the MD Office section share this URL (there
    # is no separate overview page), so it always resolves to Dashboard — the
    # single highlight on screen.
    if url_name == "executive_dashboard":
        return "dashboard"

    key = ""
    for section, names in _SECTION_URL_NAMES.items():
        if url_name in names:
            key = section
            break
    if not key:
        for section, names in _URL_NAME_RULES:
            if url_name in names:
                key = section
                break
    if not key:
        for section, fragments in _PATH_RULES:
            if any(fragment in path for fragment in fragments):
                key = section
                break
    if not key:
        return ""

    return _section_key(key, user, is_superuser, is_registry, is_md, is_executive, is_head)
