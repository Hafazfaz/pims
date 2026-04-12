def environment_callback(request):
    return ["Production", "danger"]


def dashboard_callback(request, context):
    from document_management.models import File, Document
    from organization.models import Staff, Department
    from user_management.models import CustomUser
    from django.utils import timezone

    today = timezone.now().date()
    context.update({
        "kpis": [
            {"title": "Total Files", "value": File.objects.count(), "icon": "folder"},
            {"title": "Active Files", "value": File.objects.filter(status="active").count(), "icon": "folder_open"},
            {"title": "Pending Activation", "value": File.objects.filter(status="pending_activation").count(), "icon": "pending"},
            {"title": "Total Staff", "value": Staff.objects.count(), "icon": "badge"},
            {"title": "Departments", "value": Department.objects.count(), "icon": "account_tree"},
            {"title": "Documents Today", "value": Document.objects.filter(uploaded_at__date=today).count(), "icon": "description"},
        ],
    })
    return context


UNFOLD = {
    "SITE_TITLE": "PIMS Administration",
    "SITE_HEADER": "PIMS Records Matrix",
    "SITE_URL": "/",
    "SITE_ICON": None,
    "SITE_SYMBOL": "folder_open",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "THEME": "light",
    "ENVIRONMENT": "pims_datamanagement.unfold_config.environment_callback",
    "DASHBOARD_CALLBACK": "pims_datamanagement.unfold_config.dashboard_callback",
    "STYLES": [
        lambda request: """
            input:not([type=checkbox]):not([type=radio]),
            select, textarea {
                border: 1px solid #cbd5e1 !important;
                border-radius: 6px !important;
                padding: 6px 10px !important;
                background: #fff !important;
                color: #0f172a !important;
            }
            input:not([type=checkbox]):not([type=radio]):focus,
            select:focus, textarea:focus {
                border-color: #008751 !important;
                outline: none !important;
                box-shadow: 0 0 0 2px rgba(0,135,81,0.15) !important;
            }
        """
    ],
    "COLORS": {
        "font": {
            "subtle-light": "100 116 139",    # slate-500
            "subtle-dark": "148 163 184",     # slate-400
            "default-light": "15 23 42",      # slate-900
            "default-dark": "226 232 240",    # slate-200
            "important-light": "0 0 0",
            "important-dark": "255 255 255",
        },
        "primary": {
            "50": "230 243 238",
            "100": "204 231 221",
            "200": "153 207 187",
            "300": "102 183 153",
            "400": "51 159 119",
            "500": "0 135 81",
            "600": "0 121 73",
            "700": "0 94 57",
            "800": "0 67 41",
            "900": "0 41 24",
            "950": "0 20 12",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Records Management",
                "separator": True,
                "items": [
                    {
                        "title": "Files",
                        "icon": "folder",
                        "link": "/admin/document_management/file/",
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "Documents",
                        "icon": "description",
                        "link": "/admin/document_management/document/",
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "File Movements",
                        "icon": "swap_horiz",
                        "link": "/admin/document_management/filemovement/",
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "Access Requests",
                        "icon": "lock_open",
                        "link": "/admin/document_management/fileaccessrequest/",
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
            {
                "title": "Organisation",
                "separator": True,
                "items": [
                    {
                        "title": "Departments",
                        "icon": "account_tree",
                        "link": "/admin/organization/department/",
                    },
                    {
                        "title": "Units",
                        "icon": "workspaces",
                        "link": "/admin/organization/unit/",
                    },
                    {
                        "title": "Staff",
                        "icon": "badge",
                        "link": "/admin/organization/staff/",
                    },
                    {
                        "title": "Designations",
                        "icon": "military_tech",
                        "link": "/admin/organization/designation/",
                    },
                ],
            },
            {
                "title": "User Management",
                "separator": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": "/admin/user_management/customuser/",
                    },
                    {
                        "title": "Groups & Roles",
                        "icon": "group",
                        "link": "/admin/auth/group/",
                    },
                    {
                        "title": "Password History",
                        "icon": "key",
                        "link": "/admin/user_management/passwordhistory/",
                    },
                ],
            },
            {
                "title": "Audit & Security",
                "separator": True,
                "items": [
                    {
                        "title": "Audit Log",
                        "icon": "history",
                        "link": "/admin/audit_log/auditlogentry/",
                    },
                    {
                        "title": "Notifications",
                        "icon": "notifications",
                        "link": "/admin/notifications/notification/",
                    },
                ],
            },
        ],
    },
    "TABS": [
        {
            "models": ["document_management.file"],
            "items": [
                {"title": "Overview", "link": "/admin/document_management/file/"},
                {"title": "Documents", "link": "/admin/document_management/document/"},
                {"title": "Movements", "link": "/admin/document_management/filemovement/"},
            ],
        },
    ],
}
