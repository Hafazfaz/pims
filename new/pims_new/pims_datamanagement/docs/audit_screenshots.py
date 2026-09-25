#!/usr/bin/env python
"""Audit manual screenshots: detect captures that landed on login / redirected away.

Usage:
    python manage.py runserver 127.0.0.1:8123 --noreload &
    python docs/audit_screenshots.py
"""

import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pims_datamanagement.settings")
django.setup()

from document_management.models import Document, File, FileMovement  # noqa: E402
from organization.models import Staff  # noqa: E402

BASE = "http://127.0.0.1:8123"
PW = os.environ.get("SCREENSHOT_PASSWORD", "ManualShot123!")


def main():
    from playwright.sync_api import sync_playwright

    um = Staff.objects.get(user__username="test_um")
    mv = FileMovement.objects.filter(sent_to=um, action="sent", status="pending").first()
    pdf_doc = Document.objects.filter(attachment__iendswith=".pdf").first()

    checks = [
        ("login", None, "/accounts/login/"),
        ("staff-hub", "test_staff1", "/documents/my-files/"),
        ("notifications", "test_staff1", "/notifications/"),
        ("inbox-tabs", "test_um", "/documents/inbox/"),
        ("hou-inbox", "test_um", f"/documents/inbox/movement/{mv.pk}/" if mv else None),
        ("treated-tab", "test_um", "/documents/inbox/?tab=treated"),
        ("outbox", "test_um", "/documents/outbox/"),
        ("profile", "test_um", "/accounts/profile/"),
        ("hod-files", "saadahmed", "/documents/file/4/"),
        ("exec-dashboard", "saadahmed", "/documents/executive/dashboard/"),
        ("doc-viewer", "saadahmed", f"/documents/document/{pdf_doc.pk}/attachment/main/view/" if pdf_doc else None),
        ("doc-detail", "saadahmed", "/documents/document/40/detail/"),
        ("supervisor-view", "Andre", "/documents/file/1/"),
        ("registry-hub", "registry", "/documents/registry/hub/"),
        ("file-create", "registry", "/documents/create/"),
        ("access-requests", "registry", "/documents/access-requests/"),
        ("add-document", "registry", "/documents/file/1/add-document/"),
        ("staff-without-files", "registry", "/documents/staff-without-files/"),
        ("outgoing-dispatches", "registry", "/documents/outgoing-dispatches/"),
        ("send-file", "registry", "/documents/file/1/"),
        ("admin-users", "admin", "/accounts/users/"),
        ("user-create", "admin", "/accounts/users/create/"),
        ("admin-health", "admin", "/accounts/admin/dashboard/health/"),
    ]

    bad = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for slug, user, path in checks:
            if not path:
                print(f"SKIP  {slug}: no target")
                continue
            ctx = browser.new_context(viewport={"width": 1180, "height": 860})
            pg = ctx.new_page()
            if user:
                pg.goto(f"{BASE}/accounts/login/")
                pg.fill("input[name=username]", user)
                pg.fill("input[name=password]", PW)
                pg.click("button[type=submit]")
                pg.wait_for_load_state("networkidle")
            pg.goto(f"{BASE}{path}")
            pg.wait_for_load_state("networkidle")
            final = pg.url.replace(BASE, "")
            title = pg.title()
            body = pg.content()
            is_login = "/accounts/login" in final or "Staff Portal Login" in body
            denied = "do not have permission" in body or "Only registry staff" in body
            forced = "/password/change/force" in final
            expected_login = slug == "login"  # the login shot is meant to be the login page
            if expected_login:
                status = "ok" if is_login else "UNEXPECTED"
            elif is_login:
                status = "LOGIN-REDIRECT"
            elif forced:
                status = "FORCED-PW-CHANGE"
            elif denied:
                status = "DENIED-MSG"
            else:
                status = "ok"
            if status != "ok":
                bad.append((slug, user, path, final, status))
            print(f"{status:15s} {slug:22s} user={user or '-':12s} -> {final}  | {title[:48]}")
            ctx.close()
        browser.close()

    print("\n=== PROBLEMS ===" if bad else "\n=== ALL GOOD ===")
    for slug, user, path, final, status in bad:
        print(f"  {slug}: {user} {path} -> {final} ({status})")


if __name__ == "__main__":
    main()
