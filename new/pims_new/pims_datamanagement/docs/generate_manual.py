#!/usr/bin/env python
"""Generate the PIMS User Manual PDF (docs/PIMS_User_Manual.pdf).

Usage:
    python docs/generate_manual.py [--out docs/PIMS_User_Manual.pdf]

Phase 4 (screenshots): replace screenshot_slot() output with real images by
dropping PNGs into docs/screenshots/<slug>.png and flipping USE_SCREENSHOTS.
Requires only reportlab.
"""

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

BASE_DIR = Path(__file__).resolve().parent
OUT_DEFAULT = BASE_DIR / "PIMS_User_Manual.pdf"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
USE_SCREENSHOTS = True  # Phase 4: real captures in docs/screenshots/*.png

GREEN = colors.HexColor("#008751")
DARK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
LIGHT_BG = colors.HexColor("#f1f5f9")
AMBER_BG = colors.HexColor("#fffbeb")
AMBER_BORDER = colors.HexColor("#f59e0b")
GREEN_BG = colors.HexColor("#f0fdf4")
GREEN_BORDER = colors.HexColor("#16a34a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("CoverTitle", parent=styles["Title"], fontSize=30, leading=34, textColor=GREEN, spaceAfter=6))
styles.add(ParagraphStyle("CoverSub", parent=styles["Normal"], fontSize=13, leading=17, textColor=MUTED))
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, leading=22, textColor=DARK, spaceBefore=14, spaceAfter=8))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, leading=16, textColor=GREEN, spaceBefore=10, spaceAfter=6))
styles.add(ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, leading=14, textColor=DARK, spaceBefore=8, spaceAfter=4))
styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, leading=13.5, textColor=DARK, spaceAfter=4))
styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8.5, leading=11.5, textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=DARK))
styles.add(ParagraphStyle("CellHead", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=colors.white))
styles.add(ParagraphStyle("Caption", parent=styles["Normal"], fontSize=8, leading=10, textColor=MUTED, alignment=1))


def h1(text):
    return Paragraph(text, styles["H1"])


def h2(text):
    return Paragraph(text, styles["H2"])


def h3(text):
    return Paragraph(text, styles["H3"])


def p(text):
    return Paragraph(text, styles["Body"])


def small(text):
    return Paragraph(text, styles["Small"])


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(i, styles["Body"]), leftIndent=14, bulletColor=GREEN) for i in items],
        bulletType="bullet",
        leftIndent=14,
        bulletFontSize=8,
    )


def steps(items):
    return ListFlowable(
        [ListItem(Paragraph(i, styles["Body"]), leftIndent=18) for i in items],
        bulletType="1",
        leftIndent=18,
    )


def box(title, body, bg=GREEN_BG, border=GREEN_BORDER):
    inner = [
        [Paragraph(f"<b>{title}</b>", styles["Body"])],
        [Paragraph(body, styles["Body"])],
    ]
    t = Table(inner, colWidths=[16 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 1, border),
                ("INNERPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def note(body):
    return box("Note", body)


def warning(body):
    return box("Important", body, bg=AMBER_BG, border=AMBER_BORDER)


CONTENT_W = 17 * cm  # usable width with 2cm margins on A4 (21cm)


def screenshot_slot(slug, caption, width=CONTENT_W, max_h=13 * cm):
    """Embed a real screenshot scaled to fit, preserving aspect ratio."""
    path = SCREENSHOT_DIR / f"{slug}.png"
    if USE_SCREENSHOTS and path.exists():
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image, KeepTogether

        iw, ih = ImageReader(str(path)).getSize()
        w = width
        h = w * ih / iw
        if h > max_h:  # very tall capture: bound by height instead
            h = max_h
            w = h * iw / ih
        img = Image(str(path), width=w, height=h)
        img.hAlign = "CENTER"
        cap = Paragraph(caption, styles["Caption"])
        return [Spacer(1, 3 * mm), KeepTogether([img, Spacer(1, 1.5 * mm), cap]), Spacer(1, 4 * mm)]
    inner = [[Paragraph(f"[Screenshot: {caption}]", styles["Caption"])]]
    t = Table(inner, colWidths=[width], rowHeights=[3.2 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 1, MUTED),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return [t, Spacer(1, 2 * mm)]


def table(headers, rows, widths=None):
    data = [[Paragraph(f"<b>{h}</b>", styles["CellHead"]) for h in headers]]
    data += [[Paragraph(str(c), styles["Cell"]) for c in row] for row in rows]
    if widths:
        total = sum(widths)
        col_widths = [CONTENT_W * w / total for w in widths]
    else:
        col_widths = [CONTENT_W / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("INNERPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


# ---------------------------------------------------------------- chapters ---

def ch_welcome():
    return [
        h1("1. Welcome to PIMS"),
        p(
            "The <b>Personnel Information Management System (PIMS)</b> of the Federal Medical Centre Abuja "
            "is the digital home of every personnel folder. Physical folders live with Registry; "
            "PIMS tracks the folder, everything filed inside it, and every hand-off between officers — "
            "who holds what, what is pending, and what has been decided."
        ),
        h2("1.1 Logging in"),
        *screenshot_slot("login", "Login page — enter your username and password"),
        steps([
            "Open the application. You land on the <b>Staff Portal Login</b> page.",
            "Enter your <b>Username</b> and <b>Password</b> exactly as given by your administrator.",
            "Click <b>Sign In</b>.",
            "If this is your first login you will be redirected to <b>Change Password</b> — enter your current temporary password then choose a new one. Your new password is saved and you proceed to the dashboard.",
            "If your organisation uses email verification, a 6-digit code is sent to your registered address. Enter it on the verification screen (valid 5 minutes).",
        ]),
        h2("1.2 Account lockout"),
        p("Three consecutive wrong passwords lock your account for <b>15 minutes</b>. "
          "You will see a dedicated lockout page. An administrator can unlock you immediately from "
          "<b>Management → Users → Unlock</b> without waiting for the timer."),
        h2("1.3 Your profile and digital signature"),
        *screenshot_slot("profile", "Profile page — signature section"),
        steps([
            "Click your name in the bottom-left of the sidebar, or open <b>Activity → Profile</b>.",
            "Scroll to <b>Digital Signature</b>.",
            "Either draw your signature on the canvas pad or upload a clear PNG/JPG image.",
            "Submit. Your signature is saved and automatically verified.",
            "Once uploaded, you can immediately sign minutes and approve documents.",
        ]),
        warning(
            "Approvals, signing, and inbox actions all require an <b>active signature</b>. "
            "Signatures uploaded in your profile are verified automatically."
        ),
    ]


def ch_concepts():
    return [
        h1("2. Core concepts"),
        h2("2.1 Files, documents, and movements"),
        bullets([
            "<b>File (folder):</b> the primary container, identified by a unique file number "
            "(e.g. FMCAB/2026/PS/0004). A <b>Personal</b> file belongs to one named staff member; "
            "a <b>Policy</b> file belongs to a department or external party.",
            "<b>Document:</b> one entry inside a file — either a typed minute or one or more "
            "uploaded attachments. One document can carry <b>multiple attachment files</b>.",
            "<b>Movement / dispatch:</b> a digital record of a file or document being sent from "
            "one officer to another. At any moment a file has exactly one <b>current custodian</b>.",
        ]),
        h2("2.2 File statuses"),
        table(
            ["Status", "What it means"],
            [
                ["Active", "At rest with its custodian — the normal working state."],
                ["In Transit", "Sent to another officer; awaiting acknowledgement or approval."],
                ["Inactive", "Dormant; Registry can switch it back to Active from File Settings."],
                ["Closed", "Formally closed by Registry; no further entries."],
                ["Archived", "Long-term storage; read-only."],
            ],
            widths=[3, 7],
        ),
        h2("2.3 Document statuses"),
        table(
            ["Status", "What it means"],
            [
                ["Pending", "Filed; awaiting review or approval."],
                ["In Transit", "Dispatched to a recipient's inbox."],
                ["Approved", "Accepted by the approver; signature recorded."],
                ["Rejected", "Declined; reason stored on the entry."],
                ["Cancelled", "Withdrawn before a decision."],
            ],
            widths=[3, 7],
        ),
        h2("2.4 Visibility matrix"),
        table(
            ["Role", "Own file contents", "Subordinate files", "Org-wide"],
            [
                ["Regular staff", "Tracking only (titles + statuses while in transit, no content links)", "—", "—"],
                ["Unit manager (head of unit)", "Tracking only while in transit (titles + statuses, never contents); can add", "Own unit: full view + download", "—"],
                ["Section / division head, supervisor", "Visible", "Own section/division/dept", "—"],
                ["HOD", "Visible", "Entire department", "—"],
                ["Executive / MD / Mayor", "Visible", "Visible", "Yes"],
                ["Registry", "Hidden — custody management only", "File metadata only, never document content or titles", "Custody view"],
                ["Administrator", "Visible", "Visible", "Yes"],
            ],
            widths=[4, 5, 5, 2],
        ),
        note(
            "Registry handles physical custody but must never see document contents — not even titles. "
            "This separation of duties is enforced at every layer: views, search, downloads, and the viewer."
        ),
    ]


def ch_staff():
    return [
        h1("3. Regular staff"),
        p("As regular staff your main touchpoints are <b>My Files</b>, <b>Inbox</b>, and "
          "<b>Notifications</b>. Your personnel file exists and is managed by Registry; "
          "the contents are hidden from you by policy, but you can track your documents while they "
          "travel and file new records at any time."),
        h2("3.1 My Records hub (My Files)"),
        *screenshot_slot("staff-hub", "My Records hub — personnel identity card and pending files"),
        bullets([
            "<b>Personnel Identity card</b> — your file number, title, current status, and current custodian at a glance.",
            "<b>View My History</b> — opens the limited file history page (Movement History tab).",
            "<b>Inbox</b> shortcut — jumps straight to items waiting for your action.",
            "<b>Pending Files</b> — the section below the identity card. Only files that are currently <b>in transit</b> and involve you are listed here.",
            "When your own file is in transit you see a <b>tracking table</b>: document titles, types, and statuses — no clickable content links.",
            "When nothing is pending you see <b>You're All Caught Up</b>.",
        ]),
        h2("3.2 Filing a new document (e.g. a certificate or leave form)"),
        *screenshot_slot("add-document", "New Document form — Subject, Document Type, Minute Content, attachments"),
        steps([
            "From the My Records hub click <b>View My History</b> on your file.",
            "Click the green <b>+ Add Document</b> button.",
            "Fill <b>Subject</b> — a clear label (e.g. B.Sc ECONOMICS CERTIFICATE).",
            "Choose a <b>Document Type</b> from the dropdown.",
            "Either write text in <b>Minute Content</b> (rich editor) or leave it blank.",
            "Click the attachment area to select <b>one or more files</b> — PDF, Word, images. Multi-select is supported.",
            "If you are authorised and have an active signature, tick <b>Attach Digital Signature</b>.",
            "Click <b>Submit</b>. The document is saved as <b>Pending</b> and auto-routed to your direct head.",
        ]),
        note("Once submitted you can track the document's status (Pending → In Transit → Approved/Rejected) from the tracking table on your hub. You cannot open or download it — that is restricted by policy."),
        h2("3.3 Inbox — Untreated and Treated tabs"),
        *screenshot_slot("inbox-tabs", "Inbox — Untreated (2 pending) and Treated (5 done) tabs"),
        bullets([
            "<b>Untreated</b> (default) — items still needing action: forwarding, approving, or rejecting. The sidebar badge shows this count.",
            "<b>Treated</b> — items you have already acted on, each with its outcome badge (Approved / Rejected / Forwarded). Nothing here needs action.",
            "<b>Urgent</b> tab — urgent and high-priority documents across your accessible files.",
            "<b>Sent →</b> (top right) — your outbox, filterable by status.",
        ]),
        h2("3.4 Requesting access to your file"),
        steps([
            "Open your file from My Files → View My History.",
            "In the <b>Administrative Controls</b> panel on the right, look for <b>Request Access from Registry</b>. This button appears only when the file is <b>at rest with Registry</b>.",
            "Choose <b>Read-only</b> or <b>Read &amp; write</b>, enter a reason, and submit.",
            "The panel changes to <b>Access Pending</b>. Registry reviews it under <b>Tools → Access Requests</b>.",
            "Once approved the panel turns green and shows your grant type. A read &amp; write grant lets you add documents; a read-only grant is for viewing (your own file contents still remain hidden — the grant is for administrative actions).",
        ]),
        *screenshot_slot("supervisor-view", "Administrative Controls panel — Identity Locked with the "
                                           "Request Access from Registry button, shown when a file is at rest with Registry"),
        warning("You can only submit an access request while the file is <b>at rest with Registry</b>. "
                "If it is with another custodian the panel reads <b>File In Transit — Requests Disabled</b>; "
                "wait for it to return to Registry."),
    ]


def ch_unit_managers():
    return [
        h1("4. Unit managers (heads of unit)"),
        p("As a unit manager you get HOD-style oversight, but limited to <b>your own unit</b>: "
          "you can open, read, and download the personal files of every staff member in your unit. "
          "Chapter 3 still applies to your own file and everything outside your unit."),
        h2("4.1 Unit Files in the sidebar"),
        *screenshot_slot("unit-files", "Unit Files — record explorer scoped to the manager's own unit"),
        p("Your sidebar has a <b>Unit</b> section with a <b>Unit Files</b> link. It opens the record "
          "explorer pre-scoped to your unit: every active personal file of your unit members, "
          "searchable by file number, title, or keyword. Your own file is excluded from this list — "
          "use View My History for that."),
        bullets([
            "Open any unit file to read its Chronicle, view attachments in the protected viewer, and download files.",
            "Your <b>My Files</b> also lists your unit's files alongside your own pending work, with the same View/Download links.",
            "Approved documents need a fresh grant or leadership — same rule as everyone else.",
        ]),
        h2("4.2 Forwarding and routing"),
        bullets([
            "The <b>Approve</b> button in your inbox <b>auto-forwards to your HOD</b> — you confirm and "
            "a movement is created to the department head. You do not pick the recipient manually.",
            "Adding a document to a file auto-routes it up your reporting chain, skipping yourself as recipient.",
            "If you also carry a flagged supervisor role, the wider oversight permissions apply to you instead.",
        ]),
        *screenshot_slot("hou-inbox", "Unit manager inbox — Untreated items with Approve and Reject actions"),
        h2("4.3 Treated tab"),
        *screenshot_slot("treated-tab", "Treated tab — forwarded items with outcome badges"),
        p("After you forward or reject an item it immediately moves from Untreated to Treated. "
          "The Treated tab gives you a full audit trail of every item you have acted on, "
          "with the outcome badge and the date."),
    ]


def ch_hod():
    return [
        h1("5. Heads of department (HOD)"),
        p("HODs can view and manage personal files of every staff member in their department, "
          "their own policy files, and dispatch or approve documents."),
        h2("5.1 Subordinate file access"),
        *screenshot_slot("hod-files", "HOD viewing a subordinate personal file — Full Admin Access Granted"),
        bullets([
            "<b>My Files</b> shows your own files plus every personal file in your department.",
            "Open any subordinate file: the <b>Administrative Controls</b> panel shows <b>Full Admin Access Granted — You can view and add documents</b>.",
            "Navigate to the <b>Chronicle</b> tab to read all documents and download attachments.",
            "<b>Department Files</b> in the sidebar opens the record explorer scoped to your department.",
        ]),
        h2("5.2 Approving a document from the inbox"),
        steps([
            "Open <b>Inbox → Untreated</b>.",
            "Click <b>View Doc</b> on the item to read the full document, reference documents, and movement history.",
            "Return to the inbox row. Click <b>Approve</b> to accept (signs with your active signature) or <b>Reject</b> (enter a mandatory reason).",
            "Approval marks the document <b>Approved</b>, returns the file to <b>Active</b> with Registry, and notifies the sender.",
            "The item moves to the <b>Treated</b> tab.",
        ]),
        h2("5.3 Dispatching a file"),
        steps([
            "Open a file you hold. Click <b>+ Add Document</b> or use an existing document.",
            "Scroll to the <b>Administrative Controls</b> sidebar — if the file is active and yours to send, a <b>Send File</b> (dispatch) section appears.",
            "Search for the recipient by name, designation, or department.",
            "Optionally attach reference documents from the same file.",
            "Add a covering note and click <b>Dispatch</b>. The file moves to <b>In Transit</b>.",
        ]),
        h2("5.4 Email sharing (if permitted)"),
        p("HODs granted the <b>Can share documents with other users</b> permission can open a document "
          "and share it by email from the file's Chronicle tab, optionally including a signature image."),
    ]


def ch_mid_heads():
    return [
        h1("6. Section / division heads and supervisors"),
        *screenshot_slot("supervisor-view", "A head opening a departmental personal file that is at rest with Registry — "
                                           "administrative controls show Identity Locked with Request Access from Registry"),
        bullets([
            "You can open and read personal files of every staff member in your section, division, or department.",
            "<b>My Files</b> includes those subordinate files alongside your own.",
            "Downloads and the attachment viewer work for you exactly as described in Chapter 11.",
            "Your own personal file follows the hidden-from-self rule: you can add documents but not read existing contents.",
            "Dispatch and approval work exactly as described for HODs in Chapter 5.",
        ]),
        note("Reading a file and holding <b>administrative</b> rights over it are separate things. "
             "In the screenshot above the head can open the file and read its Chronicle, but the "
             "<b>Administrative Controls</b> panel reads <b>Identity Locked</b> because no access grant is "
             "held — the file is at rest with Registry. Clicking <b>Request Access from Registry</b> asks "
             "for custody so that documents can be added."),
    ]


def ch_exec():
    return [
        h1("7. Executive, MD, and Mayor"),
        *screenshot_slot("exec-dashboard", "Executive Dashboard — organisation-wide totals and recent files"),
        bullets([
            "<b>Executive Dashboard</b> (sidebar → Dashboard / Overview): total record containers, "
            "active/pending/overdue counts, activity velocity (documents today, files this week), "
            "file distribution by type, staff file coverage, and a list of the most recent files.",
            "All Files explorer — every file in the system, searchable and filterable.",
            "Open and read any file, view/download any document.",
            "Approve, reject, and dispatch from inbox exactly as HODs.",
            "MD and Mayor see the same breadth; Mayor additionally carries a special override on certain access checks.",
        ]),
    ]


def ch_registry():
    return [
        h1("8. Registry"),
        p("Registry manages physical custody of every folder. "
          "Document contents are hidden from Registry by policy — you see file metadata and "
          "custody tracking, but never titles, document bodies, or attachments."),
        h2("8.1 Registry hub (All Files)"),
        *screenshot_slot("registry-hub", "Registry hub — status tiles, quick links, file list with custodians"),
        bullets([
            "Status tiles: <b>Active Files</b>, <b>Archived</b>, <b>Files Out</b>, <b>Overdue</b>.",
            "Quick-link cards: <b>Doc Types</b> (manage document type categories), <b>Divisions</b>, "
            "<b>Sections</b>, <b>Staff Without Files</b> (staff who have no folder yet).",
            "<b>All Files</b> table — every active file, current custodian, and status. "
            "Search by file number, title, or keyword; filter by type, department, or status.",
            "<b>Outgoing Files Tracking</b> below the main list — all files currently out with staff.",
        ]),
        h2("8.2 Creating a file"),
        *screenshot_slot("file-create", "Initialize New Record form — Folder Title, Category, Associated Staff"),
        steps([
            "Go to <b>Files → Create File</b> (sidebar) or open a staff member's profile and click <b>Create File</b> — the title and owner auto-fill.",
            "<b>Folder Title</b> — always uppercase, e.g. PERSONNEL RECORD OF ADAMU MUSA.",
            "<b>Folder Category</b> — <b>Personal</b> (one staff member, owner required, Registry officers cannot be owners) or <b>Policy</b> (department-level or external party).",
            "<b>Associated Staff</b> — search and select the file owner (Personal only). Use the <b>Assign to Staff</b> button.",
            "<b>Mark as Sensitive</b> — tick this to restrict document contents to HOD/Supervisor/Executive/MD only.",
            "The form previews <b>Will Be Dispatched To</b> — the first recipient in the owner's reporting chain. Fill a <b>Covering Note</b>.",
            "Click <b>Initialize Record</b>. The file is created and dispatched in one step. Registry uploads attached to it are auto-approved.",
        ]),
        *screenshot_slot("staff-without-files", "Staff Without Files — list of staff with no folder yet, Create File button per row"),
        h2("8.3 File status"),
        bullets([
            "Files are created <b>Active</b> — there is no activation queue.",
            "Registry can switch a file between <b>Active</b> and <b>Inactive</b> from the file's <b>Settings</b> tab.",
            "<b>Close File</b> — moves an active file to Closed (available from the file's Administrative Controls sidebar).",
            "<b>Return to Owner</b> — sends the file back to the owner from Registry.",
            "Only Registry can change status, close, and archive.",
        ]),
        h2("8.4 Filing documents"),
        *screenshot_slot("add-document", "New Document form — same form Registry uses, uploads auto-approved"),
        steps([
            "Open a file. Click <b>+ Add Document</b>.",
            "Fill Subject, Document Type, content or attachment(s).",
            "Click Submit. Because you are Registry, the document saves immediately as <b>Approved</b> and no dispatch is created.",
            "The file owner and relevant HOD receive an in-app notification.",
        ]),
        h2("8.5 Outgoing dispatches"),
        *screenshot_slot("outgoing-dispatches", "Outgoing Dispatches — every dispatch out with recipient and movement detail"),
        p("Sidebar → <b>Outgoing Dispatches</b> lists every movement initiated from Registry, "
          "with the recipient, date sent, and whether it has been acknowledged. "
          "Click any row to open the dispatch detail and manually close a movement if needed."),
        h2("8.6 Access requests"),
        *screenshot_slot("access-requests", "Access Requests — staff requests listed with Approve and Reject actions"),
        steps([
            "Open <b>Tools → Access Requests</b>.",
            "Each row shows the requester, file, access type (read-only or read &amp; write), date, and reason.",
            "Click <b>Approve</b> — optionally set an expiry date. The requester is notified.",
            "Click <b>Reject</b> — the requester is notified with your reason.",
            "Approved grants expire when the file is recalled or when the expiry date passes.",
        ]),
    ]


def ch_admin():
    return [
        h1("9. Administrator"),
        p("Administrators (superusers) manage the full user directory, org structure, and system health."),
        h2("9.1 User management"),
        *screenshot_slot("admin-users", "User directory — search, filters, and per-user action buttons"),
        h3("Creating a user"),
        *screenshot_slot("user-create", "Add Single User — Account Details and Organisation Placement panels"),
        steps([
            "Open <b>Management → Users → Add Single User</b>.",
            "<b>Account Details</b> (left panel): Username, Email Address, First Name, Last Name, Password.",
            "<b>Organisation Placement</b> (right panel): Department (required), Unit (optional, filtered by department), Designation, Staff Type (Permanent / Contract / Temp).",
            "<b>Permissions</b> checkboxes: <b>Supervisor</b> (grants flagged-supervisor oversight), "
            "<b>Can Mark Documents as Urgent/High Priority</b>, <b>Can Share Documents with Other Users</b>.",
            "Click <b>Create User Account</b>. The user receives a welcome email with their password and must change it on first login. "
            "User creation is immediate; the new account can log in right away. Signature verification is only required later for signing or approving documents.",
        ]),
        h3("Batch user upload"),
        steps([
            "Open <b>Management → Users → Batch Upload</b>.",
            "Click <b>Download Sample CSV</b> to get the template (columns: username, email, first_name, last_name, department_code, unit_name, designation_name, staff_type).",
            "Fill one row per user and upload the CSV. Each row is processed independently; per-row errors are shown without stopping the rest.",
        ]),
        h3("Other actions"),
        bullets([
            "<b>Edit</b> — update any field; add or remove the two per-user permissions.",
            "<b>Unlock</b> — clear a lockout immediately (three failed logins).",
            "<b>Suspend</b> — deactivate the account. Reactivate via Edit → is_active.",
            "<b>Delete</b> — removes the user, their Staff record, notifications, and OTP devices. Cannot delete superusers.",
        ]),
        h2("9.2 Organisation structure"),
        p("Under <b>Management</b>: Departments, Divisions, Sections, Units, Designations — each with create, edit, and delete. "
          "Registry officers can manage Divisions and Sections; all other structure changes require a superuser."),
        p("<b>Assigning heads:</b> open a Department/Division/Section/Unit, select the <b>Head</b> dropdown, "
          "and save. Headship is the single factor that determines who can view and approve what in their jurisdiction. "
          "Remove a head before deleting a unit to avoid orphaned permission data."),
        h2("9.3 Health dashboard and audit"),
        *screenshot_slot("admin-health", "Admin Health Dashboard — user stats and recent security events"),
        bullets([
            "<b>Admin → Dashboard</b>: active/inactive/locked users, files by status, documents total, last 5 security events (login failures, lockouts, unlocks).",
            "<b>Management → Audit Logs</b>: every LOGIN, CREATE, DISPATCH, APPROVAL, DOWNLOAD with actor, timestamp, and IP.",
            "<b>Activity → Activity Report</b>: your own action trail.",
        ]),
    ]


def ch_permissions():
    return [
        h1("10. Permissions reference"),
        p("Access in PIMS is decided by <b>three independent layers</b>. A user is allowed to do "
          "something if any applicable layer grants it — and blocked wherever a policy rule denies it "
          "outright (for example Registry viewing document contents)."),
        table(
            ["Layer", "Where it comes from", "Who changes it"],
            [
                ["1. Role (position)", "Derived automatically from the organisation chart — being the head of a department, division, section, or unit, or carrying the Supervisor flag.",
                 "Administrator, by assigning heads under Management → Departments/Divisions/Sections/Units, or ticking Supervisor on the user."],
                ["2. Group membership", "Named groups (Registry, Staff, HOD/HOU, Executive, Mayor, Administrator) each carry a bundle of permissions.",
                 "Administrator, via the user's groups."],
                ["3. Per-user permission", "Two special switches granted to an individual regardless of group.",
                 "Administrator, via the checkboxes on the Add/Edit user form."],
            ],
            widths=[3, 7, 5],
        ),
        note("A <b>superuser</b> (Administrator account) bypasses all permission checks and sees everything. "
             "Grant superuser sparingly."),

        h2("10.1 Role-based permissions (from the organisation chart)"),
        p("These are not checkboxes — they are consequences of <i>where a person sits</i>. "
          "Assign the head of a unit and that person immediately gains the unit-head behaviour."),
        table(
            ["Role", "How a user gets it", "What it unlocks"],
            [
                ["Registry officer", "Designation contains 'registry', or membership of the <b>Registry</b> group.",
                 "Create/activate/close/archive files; full custody tracking; approve access requests; file auto-approved documents. <b>Never</b> sees document contents or titles."],
                ["Head of Unit (unit manager)", "Set as <b>Head</b> of a Unit.",
                 "Open, read, and download the personal files of staff in their <b>own unit only</b> (via My Files and the Unit Files sidebar entry); inbox items auto-forward to their HOD."],
                ["Head of Section / Division", "Set as <b>Head</b> of a Section or Division.",
                 "View and download personnel documents of staff in that section/division; dispatch to peers and heads."],
                ["HOD", "Set as <b>Head</b> of a Department, or designation contains 'head of department', 'hod', or 'director'.",
                 "View/download every personal file in the department plus department policy files; approve or reject dispatched documents."],
                ["Supervisor (flagged)", "Tick <b>Supervisor</b> on the user form.",
                 "Oversight of personnel documents in their department, in addition to whatever their position gives."],
                ["Executive / MD", "Membership of the <b>Executive</b> or <b>MD</b> group.",
                 "Organisation-wide file visibility, the Executive Dashboard, and dispatch to anyone."],
                ["Mayor", "Membership of the <b>Mayor</b> group, or designation contains 'mayor'.",
                 "Organisation-wide read plus read &amp; write on every file."],
            ],
            widths=[3, 5, 8],
        ),
        warning("Two hard rules to remember. <b>1)</b> You can read your <b>own</b> personnel file while "
                "its documents are still pending, in transit, or rejected — but once a document is "
                "<b>approved</b> it closes to everyone except top leadership or a fresh approved request. "
                "<b>2)</b> <b>Registry can never read document contents or titles</b> — not as custodian, "
                "not with any grant. Oversight of other people's files belongs to unit heads (own unit), "
                "section/division heads, HODs, supervisors, executives, MD, and Mayor."),

        h2("10.2 What each permission lets you do (plain English)"),
        p("If a button or page is missing for someone, find the row below — that is the permission they lack."),
        table(
            ["Permission", "In plain English", "Who normally has it"],
            [
                ["Create files",
                 "See the <b>Create File</b> button and open new personal or policy folders.",
                 "Registry, administrators"],
                ["Change file status",
                 "Switch a file between <b>Active</b> and <b>Inactive</b> from File Settings.",
                 "Registry, administrators"],
                ["Close files",
                 "Close an active file so nothing more can be filed in it.",
                 "Registry, administrators"],
                ["Archive files",
                 "See the <b>Archive</b> action on a closed file and move it to archives.",
                 "Registry, administrators"],
                ["View files &amp; documents",
                 "Open file pages, document pages, and dashboards. Without this, pages refuse to load.",
                 "Registry, Staff, HOD/HOU groups"],
                ["See staff document lists",
                 "See <b>that</b> documents exist — titles, counts, lists. Without it, lists show a policy notice instead.",
                 "Everyone <b>except Registry</b>"],
                ["Mark urgent",
                 "Create urgent/high-priority documents and see the <b>New Urgent</b> menu. Tick-box per person.",
                 "Granted per user by an administrator"],
                 ["Share documents",
                 "Email a document to someone outside the workflow, with your signature attached. Needs an active signature; works for HODs.",
                 "Granted per user by an administrator"],
                ["Manage users",
                 "Open Management → Users: create, edit, unlock, suspend, and delete accounts.",
                 "Administrators (superusers)"],
                ["Read audit trail",
                 "Open Audit Logs and see who did what, when.",
                 "Registry, executives, administrators"],
                ["Supervisor flag",
                 "Not a checkbox permission but a role: oversight of personnel documents in your department.",
                 "Ticked per user by an administrator"],
            ],
            widths=[4, 9, 4],
        ),
        note("Three old switches you may see in settings — <b>send_file</b>, <b>add_minute</b>, "
             "<b>add_attachment</b> — no longer decide anything. Dispatch follows custody and the "
             "reporting chain; filing follows custody, ownership, and access grants."),
        h2("10.3 The checkboxes on the user form"),
        p("When an administrator creates or edits a user, the Permissions section of the form has "
          "exactly three checkboxes. Each one grants something different:"),
        *screenshot_slot("user-create", "Add Single User — the three Permissions checkboxes on the right"),
        table(
            ["Checkbox", "What it grants", "Good to know"],
            [
                ["Supervisor",
                 "Makes the person a <b>flagged supervisor</b>: oversight of personnel documents in their own department, even without holding any headship.",
                 "Works together with whatever position the person already holds."],
                ["Can Mark Documents as Urgent/High Priority",
                 "Unlocks the <b>New Urgent</b> sidebar entry and lets the person file standalone <b>urgent/high-priority</b> documents that notify heads directly.",
                 "Useful for front-desk or records staff who raise time-sensitive matters."],
                 ["Can Share Documents with Other Users",
                  "Unlocks the <b>Share</b> action on a document, emailing it outside the workflow with the sender's signature image attached.",
                  "Only takes effect for HODs, and only with an active signature on their profile."],
            ],
            widths=[4, 8, 5],
        ),

        h2("10.4 Granting and revoking"),
        steps([
            "Open <b>Management → Users</b> and choose the person, then <b>Edit</b>.",
            "To change <b>role-based</b> power: change their Department/Unit/Designation, tick or untick <b>Supervisor</b>, "
            "or (for headship) assign them as Head under Management → Departments/Divisions/Sections/Units.",
            "To change the <b>three checkboxes</b>: tick or untick <b>Supervisor</b>, <b>Can Mark Documents as Urgent/High Priority</b> and "
            "<b>Can Share Documents with Other Users</b>.",
            "Save. Changes take effect on the user's next page load — no restart needed.",
            "To remove all access immediately, use <b>Suspend</b> (deactivates the account) rather than deleting it, "
            "so the audit trail stays intact.",
        ]),
        warning("Never add <b>view_staff_documents</b> to the Registry group. Registry's inability to see "
                "document titles and contents is a deliberate separation-of-duties control, and the system "
                "also blocks Registry in code as a second line of defence."),
        note("Currently the user-management pages are effectively <b>superuser-only</b>: they require a "
             "permission code (<i>auth.view_user</i>) that does not exist on this project's custom user model, "
             "so no ordinary group can satisfy it. If you want a non-superuser role to administer accounts, "
             "this needs a small code change to <i>user_management.view_customuser</i>."),
    ]


def ch_documents():
    return [
        h1("11. Documents, attachments, and the viewer"),
        h2("11.1 The New Document form"),
        *screenshot_slot("add-document", "New Document form — Subject, Document Type, Minute Content, attachment upload"),
        p("The form is the same for everyone with access to a file. "
          "All fields except Document Type and at least one of (Minute Content / Attachment) are optional."),
        table(
            ["Field", "What to fill"],
            [
                ["Subject", "The document title — always shown in lists, e.g. APPLICATION FOR STUDY LEAVE 2026."],
                ["Document Type", "Select from the configured type list (managed by Registry under Tools → Document Types)."],
                ["Minute Content", "Rich-text body. Use for formal minutes, memos, or cover letters."],
                ["Upload Attachment(s)", "Select one or more files (PDF, Word, image). All files land on the same document record."],
                ["Attach Digital Signature", "Available only if your role permits signing. Requires an active signature on your profile."],
            ],
            widths=[4, 8],
        ),
        h2("11.2 Viewing attachments — the protected viewer"),
        *screenshot_slot("doc-detail", "Document detail — every attachment listed with View and Download"),
        *screenshot_slot("doc-viewer", "Attachment Viewer — filename header, file reference, Download button, inline viewer"),
        bullets([
            "Open a document from the Chronicle tab or the document detail page.",
            "Every attachment is listed with a <b>View</b> link and a <b>Download</b> link. A count badge shows the total (e.g. Download (3)).",
            "<b>View</b> opens the Attachment Viewer: PDFs render in-page, images inline, other formats show a Download-to-View fallback.",
            "Every open and download re-checks your permission at that moment. The page cannot be embedded in other sites.",
            "Every access is written to the audit log.",
        ]),
        h2("11.3 Who can view attachments"),
        bullets([
            "HODs, section/division heads, supervisors, executives, MD, Mayor — over files in their jurisdiction.",
            "The file's current custodian.",
            "A holder of an approved, unexpired <b>FileAccessRequest</b>.",
            "A recipient of an active FileMovement (dispatch).",
            "A user the document was directly shared with.",
            "<b>Registry and owners of their own personal file</b> are always blocked, regardless of other grants.",
        ]),
        h2("11.4 Dispatch → review → return cycle"),
        *screenshot_slot("send-file", "File detail page — Administrative Controls sidebar with registry custody notice and action buttons"),
        steps([
            "The custodian opens the file, clicks <b>+ Add Document</b> or selects an existing document.",
            "Uses the dispatch (Send File) controls in the sidebar: search for the recipient, attach reference docs, write a note.",
            "File moves to <b>In Transit</b>; recipient sees it in Inbox → Untreated.",
            "Recipient opens the inbox item → View Doc → reads document and reference docs.",
            "Recipient clicks <b>Approve</b> (signs) or <b>Reject</b> (reason required). HODs approve; unit managers forward to their HOD.",
            "On final approval: document marked <b>Approved</b>, file returns to <b>Active</b> with Registry, sender notified.",
        ]),
        h2("11.5 New versions"),
        p("Open a document → click <b>Edit / New Version</b>. Enter updated content and/or attachments. "
          "The new version links back to the original via <b>Parent</b>; the original is preserved. "
          "Registry versions are auto-approved; others follow the normal approval path."),
    ]


def ch_inbox():
    return [
        h1("12. Inbox, outbox, and notifications"),
        h2("12.1 Inbox tabs"),
        *screenshot_slot("inbox-tabs", "Inbox — mode tabs (Inbox / Urgent) and Untreated / Treated sub-tabs with counts"),
        bullets([
            "<b>Inbox / Urgent mode tabs</b> (top): Inbox shows document movements; Urgent lists high-priority documents across accessible files.",
            "<b>Untreated / Treated sub-tabs</b>: Untreated = pending, needs action. Treated = done, audit trail.",
            "Acting on an item (Approve / Reject / Forward) moves it instantly from Untreated to Treated.",
            "Sidebar badge always shows the <b>Untreated</b> count only.",
        ]),
        h2("12.2 Treated tab detail"),
        *screenshot_slot("treated-tab", "Treated tab — outcome badges (Forwarded, Approved, Rejected)"),
        bullets([
            "Each treated row carries an outcome badge: green Approved, red Rejected, blue Forwarded.",
            "View Doc still works — you can re-read what you decided on at any time.",
        ]),
        h2("12.3 Outbox"),
        *screenshot_slot("outbox", "Sent / Outbox — dispatches you have initiated, filterable by status"),
        p("Open <b>Sent →</b> from the inbox header, or <b>Sent</b> from the sidebar. "
          "Every dispatch you have created is listed with the recipient, date, document, and current movement status. "
          "Search by file number, title, document label, or recipient name."),
        h2("12.4 Notifications"),
        *screenshot_slot("notifications", "Notifications list — unread count, mark-all-read"),
        bullets([
            "Bell icon shows unread count. Click to open the full list.",
            "Each notification links to the relevant file or document.",
            "Click a notification to mark it read and jump to the target.",
            "<b>Mark All as Read</b> button clears the badge.",
            "Some events also send an email (e.g. access request decisions, approvals).",
        ]),
    ]


def ch_faq():
    faqs = [
        ("I see 'Limited Access View'. What does it mean?",
         "You can open the file page but not its contents. Either your role restricts you from viewing that file's documents (e.g. your own personal file), or you have not yet been granted access. If the file is at rest with Registry, use Request Access from Registry. If it is in transit, wait."),
        ("'Identity Locked — Request Unavailable'. I already submitted a request.",
         "That panel means you currently hold no active grant. A still-pending request shows 'Access Pending' instead. Possible causes: your previous grant expired; you submitted on a different file; or the file moved to another custodian and the grant was revoked. Confirm the file is at rest with Registry and re-submit if needed."),
        ("The 'Request Access' button is missing.",
         "The button only appears when the file is active and held by Registry. If the file is in transit the panel says 'File In Transit — Requests Disabled'. Wait for it to return."),
        ("I approved something but the file still shows 'In Transit'.",
         "Final approval returns the file to active automatically. If it lingers, check Movement History on the file — there may be another open step or an unacknowledged movement."),
        ("My file disappeared from My Files / Pending Files.",
         "Regular staff only see files that are currently in transit. Once the file is settled (active) it leaves the list. Use View My History or your Inbox for historical items."),
        ("I cannot sign or approve — 'no verified signature'.",
         "Upload a signature on your Profile. It is verified automatically on upload and you can then sign and approve documents."),
        ("I was locked out.",
         "Three failed logins trigger a 15-minute lockout. An administrator can unlock you immediately from Management → Users → Unlock."),
        ("I can see a document listed but cannot open or download it.",
         "Listing and opening are gated separately. You need at least one of: custody of the file, an approved access grant, an active dispatch movement, a direct share, or an oversight role over that file."),
        ("A document I uploaded is still 'Pending'.",
         "Only Registry uploads auto-approve. Your document routes to your head for approval; it becomes 'Approved' once the last approver signs off. Track progress on your hub."),
        ("How do I find a file for a staff member who left?",
         "Registry: open All Files, filter by department or search by name. Files are never deleted; they can be closed or archived but remain searchable."),
    ]
    story = [h1("13. Troubleshooting")]
    for q, a in faqs:
        story += [h3(q), p(a)]
    return story


def ch_appendix():
    return [
        h1("Appendix A. Statuses at a glance"),
        table(
            ["Object", "Status", "Meaning"],
            [
                ["File", "Active", "At rest with custodian; normal state."],
                ["File", "In Transit", "Sent to another officer; awaiting action."],
                ["File", "Inactive / Closed / Archived", "Registry end-states; read-only."],
                ["Document", "Pending", "Filed; awaiting review."],
                ["Document", "In Transit", "Dispatched for review/approval."],
                ["Document", "Approved / Rejected", "Decided by approver; signature on record."],
                ["Movement", "Pending", "Untreated inbox item."],
                ["Movement", "Approved / Rejected / Forwarded", "Treated; recorded under the Treated tab."],
            ],
            widths=[3, 4, 7],
        ),
        Spacer(1, 6 * mm),
        h1("Appendix B. Glossary"),
        table(
            ["Term", "Definition"],
            [
                ["Custodian", "The officer currently holding a file."],
                ["At rest with Registry", "Active file held by Registry — the only state in which access can be requested."],
                ["Oversight head", "HOD, section/division head, flagged supervisor, executive, MD, or Mayor — roles that can view personnel documents in their jurisdiction. Pure unit managers are excluded."],
                ["Chronicle", "The file's unified history: documents filed and audit entries in chronological order."],
                ["Read & write grant", "An approved access request allowing both viewing and adding documents."],
                ["Treated", "An inbox item on which you have taken an action (approve, reject, or forward)."],
                ["Untreated", "An inbox item still pending your action."],
                ["Auto-approved", "Registry uploads are saved as Approved immediately, bypassing the approval workflow."],
            ],
            widths=[5, 9],
        ),
        Spacer(1, 6 * mm),
        small("Generated from the live PIMS codebase with real Playwright screenshots. "
              "To regenerate: python docs/generate_manual.py"),
    ]


CHAPTERS = [
    ch_welcome,
    ch_concepts,
    ch_staff,
    ch_unit_managers,
    ch_hod,
    ch_mid_heads,
    ch_exec,
    ch_registry,
    ch_admin,
    ch_permissions,
    ch_documents,
    ch_inbox,
    ch_faq,
    ch_appendix,
]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, 1.2 * cm, "PIMS User Manual — Federal Medical Centre Abuja")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


def cover_footer(canvas, doc):
    pass


def build(out_path):
    from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageTemplate

    story = []
    story.append(Spacer(1, 5 * cm))
    story.append(Paragraph("Personnel Information Management System", styles["CoverSub"]))
    story.append(Paragraph("User Manual", styles["CoverTitle"]))
    story.append(Paragraph("Federal Medical Centre Abuja — for Registry, Administrators, Heads, and Staff", styles["CoverSub"]))
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="30%", thickness=2, color=GREEN, spaceAfter=12))
    story.append(Paragraph("Covers: login &amp; signatures · files, documents &amp; movements · role guides · inbox &amp; approvals · troubleshooting", styles["Small"]))
    story.append(PageBreak())

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC1", parent=styles["Normal"], fontSize=11, leading=15, textColor=DARK, spaceBefore=4),
        ParagraphStyle("TOC2", parent=styles["Normal"], fontSize=9.5, leading=13, textColor=MUTED, leftIndent=14),
    ]
    story.append(Paragraph("Contents", styles["H1"]))
    story.append(toc)
    story.append(PageBreak())

    for ch in CHAPTERS:
        story.extend(ch())
        story.append(PageBreak())

    doc = BaseDocTemplate(str(out_path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=footer)])

    def after_flowable(flowable):
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            if style == "H1":
                toc.addEntry(0, flowable.getPlainText(), doc.page)
            elif style == "H2":
                toc.addEntry(1, flowable.getPlainText(), doc.page)

    doc.afterFlowable = after_flowable
    doc.multiBuild(story)
    print(f"Wrote {out_path} ({out_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    build(Path(args.out))
