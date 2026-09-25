#!/usr/bin/env python
"""Capture manual screenshots with Playwright into docs/screenshots/<slug>.png.

Usage:
    # 1. terminal A: python manage.py runserver 127.0.0.1:8123 --noreload
    # 2. terminal B: SCREENSHOT_PASSWORD='...' python docs/capture_screenshots.py [--base URL]

Requires screenshot accounts to exist with known passwords (see manual Phase 4).
"""

import argparse
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

PW = os.environ.get("SCREENSHOT_PASSWORD", "ManualShot123!")
OUT = Path(__file__).resolve().parent / "screenshots"


def login(context, username):
    page = context.new_page()
    page.goto(f"{BASE}/accounts/login/")
    page.fill("input[name=username]", username)
    page.fill("input[name=password]", PW)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    return page


def shot(page, path, slug):
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / f"{slug}.png"), full_page=True)
    print(f"saved {slug}.png")


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8123")
    args = ap.parse_args()
    BASE = args.base
    OUT.mkdir(exist_ok=True)

    from playwright.sync_api import sync_playwright

    um = Staff.objects.get(user__username="test_um")
    um_movement = FileMovement.objects.filter(sent_to=um, action="sent", status="pending").first()
    sub_file = File.objects.filter(file_number="FMCAB/2026/PS/0004").first()
    waec_doc = Document.objects.filter(pk=44).first()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 1. login (anonymous)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.goto(f"{BASE}/accounts/login/")
        pg.wait_for_load_state("networkidle")
        pg.screenshot(path=str(OUT / "login.png"))
        print("saved login.png")
        ctx.close()

        # 2-3. staff hub + notifications (test_staff1)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = login(ctx, "test_staff1")
        shot(pg, "/documents/my-files/", "staff-hub")
        shot(pg, "/notifications/", "notifications")
        ctx.close()

        # 4-5. inbox tabs + forward detail (test_um)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = login(ctx, "test_um")
        shot(pg, "/documents/inbox/", "inbox-tabs")
        if um_movement:
            shot(pg, f"/documents/inbox/movement/{um_movement.pk}/", "hou-inbox")
        ctx.close()

        # 6-7. HOD file + exec dashboard (saadahmed)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = login(ctx, "saadahmed")
        if sub_file:
            shot(pg, f"/documents/file/{sub_file.pk}/", "hod-files")
        shot(pg, "/documents/executive/dashboard/", "exec-dashboard")
        ctx.close()

        # 8. supervisor view (Andre on IT file)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = login(ctx, "Andre")
        shot(pg, "/documents/file/1/", "supervisor-view")
        ctx.close()

        # 9. registry hub
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = login(ctx, "registry")
        shot(pg, "/documents/registry/hub/", "registry-hub")
        ctx.close()

        # 10. admin users
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = login(ctx, "admin")
        shot(pg, "/accounts/users/", "admin-users")
        ctx.close()

        # 11. protected viewer (test_hod on Waec doc)
        if waec_doc:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            pg = login(ctx, "test_hod")
            shot(pg, f"/documents/document/{waec_doc.pk}/attachment/main/view/", "doc-viewer")
            ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
