#!/usr/bin/env python
"""Capture manual screenshots with Playwright into docs/screenshots/<slug>.png.

Usage:
    # terminal A: python manage.py runserver 127.0.0.1:8123 --noreload
    # terminal B: SCREENSHOT_PASSWORD='...' python docs/capture_screenshots.py

Quality notes:
  * device_scale_factor=2 → retina-sharp text when scaled into the PDF.
  * Narrow viewport (1180px) → larger effective zoom, less dead whitespace.
  * Captures crop to the main content region (``clip``) instead of full_page,
    so tall dashboards don't shrink to unreadable thumbnails in the PDF.
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
VIEWPORT = {"width": 1180, "height": 860}
SCALE = 2
# Max captured height (CSS px) before we crop — keeps PDF images readable.
MAX_H = 1000


def new_context(browser):
    return browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)


def login(context, username):
    page = context.new_page()
    page.goto(f"{BASE}/accounts/login/")
    page.fill("input[name=username]", username)
    page.fill("input[name=password]", PW)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    return page


def shot(page, path, slug, max_h=MAX_H, selector=None, scroll=0):
    """Viewport screenshot (not full_page) so PDF images stay readable.

    Tall pages are intentionally cropped to the visible viewport — that is the
    part a user sees first. Pass ``scroll`` to capture further down the page.
    """
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")
    if scroll:
        page.mouse.wheel(0, scroll)
        page.wait_for_timeout(400)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / f"{slug}.png"))
    print(f"saved {slug}.png")


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8123")
    ap.add_argument("--only", default="", help="comma-separated slugs to refresh")
    args = ap.parse_args()
    BASE = args.base
    OUT.mkdir(exist_ok=True)
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    def want(slug):
        return not only or slug in only

    from playwright.sync_api import sync_playwright

    um = Staff.objects.get(user__username="test_um")
    um_movement = FileMovement.objects.filter(sent_to=um, action="sent", status="pending").first()
    sub_file = File.objects.filter(file_number="FMCAB/2026/PS/0004").first()
    pdf_doc = Document.objects.filter(attachment__iendswith=".pdf").first()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        if want("login"):
            ctx = new_context(browser)
            pg = ctx.new_page()
            pg.goto(f"{BASE}/accounts/login/")
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / "login.png"))
            print("saved login.png")
            ctx.close()

        if want("staff-hub") or want("notifications"):
            ctx = new_context(browser)
            pg = login(ctx, "test_staff1")
            if want("staff-hub"):
                shot(pg, "/documents/my-files/", "staff-hub", max_h=1050)
            if want("notifications"):
                shot(pg, "/notifications/", "notifications", max_h=900)
            ctx.close()

        if want("inbox-tabs") or want("hou-inbox"):
            ctx = new_context(browser)
            pg = login(ctx, "test_um")
            if want("inbox-tabs"):
                shot(pg, "/documents/inbox/", "inbox-tabs", max_h=760)
            if want("hou-inbox") and um_movement:
                shot(pg, f"/documents/inbox/movement/{um_movement.pk}/", "hou-inbox", max_h=1000)
            ctx.close()

        if want("hod-files") or want("exec-dashboard") or want("doc-viewer") or want("doc-detail"):
            ctx = new_context(browser)
            pg = login(ctx, "saadahmed")
            if want("hod-files") and sub_file:
                shot(pg, f"/documents/file/{sub_file.pk}/", "hod-files", max_h=820)
            if want("exec-dashboard"):
                shot(pg, "/documents/executive/dashboard/", "exec-dashboard", max_h=1000)
            if want("doc-viewer") and pdf_doc:
                shot(pg, f"/documents/document/{pdf_doc.pk}/attachment/main/view/", "doc-viewer", max_h=900)
            if want("doc-detail"):
                shot(pg, "/documents/document/40/detail/", "doc-detail")
            ctx.close()

        if want("supervisor-view"):
            ctx = new_context(browser)
            pg = login(ctx, "Andre")
            shot(pg, "/documents/file/1/", "supervisor-view", max_h=820)
            ctx.close()

        if (
            want("registry-hub")
            or want("file-create")
            or want("access-requests")
            or want("add-document")
            or want("staff-without-files")
            or want("outgoing-dispatches")
            or want("send-file")
        ):
            ctx = new_context(browser)
            pg = login(ctx, "registry")
            if want("registry-hub"):
                shot(pg, "/documents/registry/hub/", "registry-hub", max_h=1000)
            if want("file-create"):
                shot(pg, "/documents/create/", "file-create")
            if want("access-requests"):
                shot(pg, "/documents/access-requests/", "access-requests")
            if want("add-document"):
                shot(pg, "/documents/file/1/add-document/", "add-document")
            if want("staff-without-files"):
                shot(pg, "/documents/staff-without-files/", "staff-without-files")
            if want("outgoing-dispatches"):
                shot(pg, "/documents/outgoing-dispatches/", "outgoing-dispatches")
            if want("send-file"):
                # File page sidebar carries the dispatch ("Send File") controls.
                shot(pg, "/documents/file/1/", "send-file", scroll=500)
            ctx.close()

        if want("admin-users") or want("user-create") or want("admin-health"):
            ctx = new_context(browser)
            pg = login(ctx, "admin")
            if want("admin-users"):
                shot(pg, "/accounts/users/", "admin-users", max_h=1000)
            if want("user-create"):
                shot(pg, "/accounts/users/create/", "user-create")
            if want("admin-health"):
                shot(pg, "/accounts/admin/dashboard/health/", "admin-health")
            ctx.close()

        if want("profile") or want("treated-tab") or want("outbox"):
            ctx = new_context(browser)
            pg = login(ctx, "test_um")
            if want("profile"):
                shot(pg, "/accounts/profile/", "profile")
            if want("treated-tab"):
                shot(pg, "/documents/inbox/?tab=treated", "treated-tab", max_h=760)
            if want("outbox"):
                shot(pg, "/documents/outbox/", "outbox")
            ctx.close()

        browser.close()


if __name__ == "__main__":
    main()
