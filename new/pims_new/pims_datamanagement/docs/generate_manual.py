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


def screenshot_slot(slug, caption):
    """Phase 4 hook: real screenshot if available, else a labelled placeholder."""
    path = SCREENSHOT_DIR / f"{slug}.png"
    if USE_SCREENSHOTS and path.exists():
        from reportlab.platypus import Image

        return [Image(str(path), width=16 * cm, height=9 * cm, kind="proportional"), Paragraph(caption, styles["Caption"])]
    inner = [[Paragraph(f"[Screenshot: {caption}]", styles["Caption"])]]
    t = Table(inner, colWidths=[16 * cm], rowHeights=[3.2 * cm])
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


def table(headers, rows):
    data = [[Paragraph(f"<b>{h}</b>", styles["CellHead"]) for h in headers]]
    data += [[Paragraph(str(c), styles["Cell"]) for c in row] for row in rows]
    t = Table(data, colWidths=[16 * cm / len(headers)] * len(headers), repeatRows=1)
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
            "is the digital home of personnel records. Physical folders live with Registry; PIMS tracks every "
            "folder, every document inside it, and every movement between officers — who holds what, what is "
            "pending, and what has been approved."
        ),
        h2("1.1 Logging in"),
        steps(
            [
                "Open the application and go to the login page (<b>Accounts &gt; Login</b>).",
                "Enter your <b>username and password</b>, then submit.",
                "If this is your first login, you will be asked to <b>change your temporary password</b> before continuing.",
                "If email verification is enabled, enter the 6-digit code sent to your email.",
                "You land on your <b>Dashboard</b> (or Home page for regular staff).",
            ]
        ),
        *screenshot_slot("login", "Login page"),
        h2("1.2 If you get locked out"),
        p(
            "Three wrong passwords in a row locks your account for <b>15 minutes</b>. Contact your administrator, "
            "who can unlock it from <b>Management &gt; Users</b>. Your failed attempts are logged for security."
        ),
        h2("1.3 Your profile and digital signature"),
        steps(
            [
                "Click your name (bottom-left) or open <b>Accounts &gt; Profile</b>.",
                "In the <b>Digital Signature</b> section, upload a clear PNG/JPG of your signature (or draw it).",
                "Your signature stays <b>Pending</b> until verified; approvals and signing require a verified signature.",
            ]
        ),
        warning(
            "You cannot approve documents, sign minutes, or action inbox items until you have an "
            "<b>active, verified</b> signature on your profile."
        ),
    ]


def ch_concepts():
    return [
        h1("2. Core concepts"),
        h2("2.1 Files, documents, movements"),
        bullets(
            [
                "<b>File (folder):</b> a container with a file number (e.g. FMCAB/2026/PS/0004). <b>Personal</b> files belong to one staff member; <b>policy</b> files belong to a department.",
                "<b>Document:</b> a minute (typed content) or attachment(s) filed inside a file. One document can carry <b>multiple files</b>.",
                "<b>Movement (dispatch):</b> a record of a file or document sent from one officer to another. The file has exactly one <b>current custodian</b> at a time.",
            ]
        ),
        h2("2.2 File statuses"),
        bullets(
            [
                "<b>Active</b> — at rest with its custodian; the normal state.",
                "<b>In Transit</b> — sent and awaiting acknowledgement; still pending work.",
                "<b>Pending Activation / Inactive / Closed / Archived</b> — Registry-managed lifecycle states.",
            ]
        ),
        h2("2.3 Document statuses"),
        bullets(
            [
                "<b>Pending</b> — newly added, awaiting review.",
                "<b>In Transit</b> — dispatched for review/approval.",
                "<b>Approved / Rejected / Cancelled</b> — decided by the approver.",
            ]
        ),
        h2("2.4 Who can see what (summary)"),
        table(
            ["Role", "Own file contents", "Subordinate files", "All files"],
            [
                ["Regular staff", "Tracking only while in transit (titles + statuses, never contents); can add", "—", "—"],
                ["Unit manager", "Tracking only while in transit (titles + statuses, never contents); can add", "Own unit: no browsing", "—"],
                ["HOD / Section / Division head", "Visible", "Same jurisdiction", "—"],
                ["Executive / MD / Mayor", "Visible", "Visible", "Yes"],
                ["Registry", "Hidden (custody only)", "File info only, no documents", "Custody view"],
                ["Administrator", "Visible", "Visible", "Yes"],
            ],
        ),
        note(
            "Registry manages custody of every file but can never see document contents — not even titles. "
            "This separation of duties is enforced everywhere, including search, lists, and downloads."
        ),
    ]


def ch_staff():
    return [
        h1("3. Regular staff"),
        p("Staff see a personal hub — not a file browser. You can file new records and track pending work, but the contents of your own personnel file are hidden from you by policy."),
        h2("3.1 My Records hub"),
        p("Open <b>My Files</b> in the sidebar to find:"),
        bullets(
            [
                "Your <b>Personnel Identity</b> card: file number, title, status, and current custodian.",
                "<b>View My History</b> — opens your file's limited history page.",
                "<b>Inbox</b> shortcut for items needing you.",
                "<b>Pending Files</b> — only files still <b>in transit</b> involving you appear here. Your own in-transit file shows a tracking list (titles and statuses, no links); settled files show a restricted notice instead. Once a file is settled (active), it leaves this list.",
                "If nothing is pending you will see <b>You're All Caught Up</b> instead of a file list.",
            ]
        ),
        *screenshot_slot("staff-hub", "My Records hub with Pending Files"),
        h2("3.2 Adding a document (e.g. a certificate)"),
        steps(
            [
                "Open your file (View My History) and click <b>Add Minute / Document</b>.",
                "Enter a title, choose the document type, type minute content and/or <b>select one or more files</b>.",
                "Submit. Your upload starts as <b>Pending</b> and is auto-routed to your head for review — you can track its titles and statuses while it travels, but never open its contents.",
            ]
        ),
        h2("3.3 Inbox: Untreated and Treated"),
        bullets(
            [
                "<b>Untreated</b> (default) — items still needing you: review, forward, approve, or reject.",
                "<b>Treated</b> — everything you already approved, rejected, or forwarded, with counts on each tab.",
                "Use <b>Sent</b> to see what you dispatched to others.",
            ]
        ),
        *screenshot_slot("inbox-tabs", "Inbox with Untreated and Treated tabs"),
        h2("3.4 Requesting access to a file"),
        steps(
            [
                "Open the file. If it is <b>at rest with Registry</b> you will see <b>Request Access from Registry</b>.",
                "Choose read-only or read &amp; write, give a reason, and submit.",
                "While waiting you will see <b>Access Pending</b>. Registry reviews it under <b>Access Requests</b>.",
            ]
        ),
        warning(
            "You can only request access while a file is at rest with Registry. "
            "If it is with another custodian, wait until it returns — the page will say so."
        ),
    ]


def ch_unit_managers():
    return [
        h1("4. Unit managers (heads of unit)"),
        p(
            "For viewing personnel documents, unit managers are treated exactly like regular staff "
            "(Chapter 3 applies in full). Your managerial sending powers are unchanged:"
        ),
        bullets(
            [
                "Your <b>Approve</b> button in the inbox <b>auto-forwards to your HOD</b> — you cannot pick other recipients.",
                "Adding a document auto-routes it up your chain of command (never to yourself).",
                "If you also hold another oversight role (e.g. flagged supervisor), the wider head permissions apply to you.",
            ]
        ),
        *screenshot_slot("hou-inbox", "Unit manager inbox with auto-forward to HOD"),
    ]


def ch_hod():
    return [
        h1("5. Heads of department (HOD)"),
        p("HODs have oversight of every personal file in their department, plus their department's policy files."),
        h2("5.1 What you can see and do"),
        bullets(
            [
                "<b>My Files</b> lists your own files <b>plus</b> personal files of staff in your department — open any of them to review contents and download attachments.",
                "<b>Department Files</b> in the sidebar opens the record explorer scoped to your department.",
                "Approve or reject dispatched documents sent to you, with your verified digital signature.",
                "Dispatch files onward to other HODs, unit/section/division heads, and supervisors.",
            ]
        ),
        h2("5.2 Approving a document"),
        steps(
            [
                "Open the item from your <b>Inbox</b> (Untreated tab).",
                "Review the document and any reference documents.",
                "Click <b>Approve</b> (or <b>Reject</b> with a reason). Approval marks the document <b>approved</b> and returns the file to <b>active</b> with Registry; the sender is notified.",
            ]
        ),
        h2("5.3 Sharing a document by email"),
        p(
            "HODs granted the <b>Share documents</b> permission (with a verified signature) can share a file's "
            "documents by email from the file page, optionally attaching their signature image."
        ),
        *screenshot_slot("hod-files", "HOD view of a subordinate file"),
    ]


def ch_mid_heads():
    return [
        h1("6. Section / division heads and supervisors"),
        bullets(
            [
                "You can open and review personal files of staff in your <b>section / division / department</b>, including downloads.",
                "Your <b>My Files</b> includes those subordinate files alongside your own.",
                "You can dispatch to fellow heads and supervisors per the routing rules.",
                "Your own personal file contents follow the same hidden-from-self rule as regular staff.",
            ]
        ),
        *screenshot_slot("supervisor-view", "Supervisor reviewing a subordinate file"),
    ]


def ch_exec():
    return [
        h1("7. Executive, MD, and Mayor"),
        bullets(
            [
                "The <b>Executive Dashboard</b> (sidebar &gt; Overview) shows organisation-wide totals: files by status and type, overdue files, documents added today, and pending access requests.",
                "You can open <b>any file</b> and view/download any document, organisation-wide (<b>All Files</b> explorer for MD).",
                "Dispatch to anyone; approvals and signatures work as for HODs.",
            ]
        ),
        *screenshot_slot("exec-dashboard", "Executive dashboard"),
    ]


def ch_registry():
    return [
        h1("8. Registry"),
        p("Registry is the custodian of every physical folder. You manage files, never their contents: even document titles are hidden from you by policy."),
        h2("8.1 Creating a file"),
        steps(
            [
                "Go to <b>Files &gt; Create File</b> (or find the staff member under <b>Staff Without Files</b> and create from there — details auto-fill).",
                "Choose <b>Personal</b> (one per staff member, owner required, never a Registry officer) or <b>Policy</b> (department or external party required).",
                "Attach initial documents if available — Registry uploads are official records and are saved <b>approved</b> automatically.",
                "Save as draft, or dispatch immediately (recipient preview shows where it will go).",
            ]
        ),
        h2("8.2 Activation lifecycle"),
        bullets(
            [
                "New files needing owner sign-off sit at <b>Pending Activation</b> (<b>Pending Activation</b> sidebar, with counts).",
                "Activate them once approved; close <b>active</b> files when done; archive <b>closed</b> files.",
                "Only Registry can activate, close, and archive.",
            ]
        ),
        h2("8.3 Tracking custody"),
        bullets(
            [
                "<b>All Files / Registry Hub</b> — every file with its current custodian and custody duration; overdue files are flagged.",
                "<b>Outgoing Dispatches</b> — every dispatch out, with detail pages and manual movement closure.",
                "<b>All Folders</b> — browse personal, policy, and other files with search and filters.",
            ]
        ),
        h2("8.4 Access requests"),
        p(
            "Staff requests land under <b>Tools &gt; Access Requests</b>. Approve (read-only or read &amp; write, "
            "optionally expiring) or reject. Recalling a file automatically expires its grants."
        ),
        h2("8.5 Filing documents"),
        p(
            "Adding a document to a file as Registry skips routing entirely: the document is filed <b>approved</b>, "
            "the file stays put, and the owner (or HOD for policy files) is notified. No dispatch is created."
        ),
        h2("8.6 Reference data"),
        p("Manage <b>Document Types</b> under Tools. Departments, divisions, sections, units, and designations are managed by Administrators (Registry may manage divisions and sections)."),
        *screenshot_slot("registry-hub", "Registry hub with custody tracking"),
    ]


def ch_admin():
    return [
        h1("9. Administrator"),
        p("Administrators (superusers) manage people, structure, and system health. You can see everything."),
        h2("9.1 Managing users"),
        bullets(
            [
                "<b>Management &gt; Users</b>: search, filter, create, edit, unlock, suspend, and delete users.",
                "Creating a user sets department/unit/designation, supervisor flag, the two special permissions (<b>Share documents</b>, <b>Urgent priority</b>), and a temporary password the user must change at first login.",
                "<b>Batch upload</b>: download the sample CSV, fill one row per user, upload — each row reports success or the exact error.",
                "Locked accounts (3 failed logins) can be unlocked; deactivated accounts reactivated from Edit.",
            ]
        ),
        h2("9.2 Organisation structure"),
        p(
            "Under <b>Management</b>: Departments, Divisions, Sections, Units, Designations. "
            "Assign each unit/section/division/department <b>head</b> here — headship drives who can view and approve what."
        ),
        h2("9.3 Health dashboard and audit"),
        bullets(
            [
                "<b>Admin &gt; Dashboard</b>: user totals, locked accounts, files by status, recent security events.",
                "<b>Audit Logs</b>: every login, creation, dispatch, approval, and download, with actor and timestamp.",
                "<b>Activity Report</b> (all users): your own trail.",
            ]
        ),
        *screenshot_slot("admin-users", "User management list"),
    ]


def ch_documents():
    return [
        h1("10. Documents in depth"),
        h2("10.1 Adding documents and minutes"),
        bullets(
            [
                "On any <b>active</b> file you hold or own, click <b>Add Minute / Document</b>.",
                "Give a title and type; write minute content and/or <b>select multiple files</b> — one document can carry many attachments.",
                "Attach your digital signature where permitted; new versions preserve the original (Edit saves as Version N+1).",
            ]
        ),
        h2("10.2 Viewing attachments (protected viewer)"),
        bullets(
            [
                "Open a document to see every file listed with <b>View</b> and <b>Download</b>.",
                "The viewer previews PDFs in-page and images inline; other formats offer download instead.",
                "Every view and download re-checks your permission at open time: HOD/supervisor/executive/MD/Mayor, custodian, approved-request holder, movement recipient, or directly-shared user. Registry and owners viewing their own file are always blocked.",
                "Inline views cannot be embedded on other sites, and every serve is audit-logged.",
            ]
        ),
        h2("10.3 Dispatch, approval, and return"),
        steps(
            [
                "The custodian dispatches a document (optionally with reference documents) — file goes <b>in transit</b>.",
                "Each recipient treats it from their inbox: <b>forward</b> onward, or (HOD/owner) <b>approve/reject</b> with a signature.",
                "Approval marks the document <b>approved</b> and returns the file to <b>active</b> with Registry; rejection sends it back with reasons. Everyone involved is notified.",
            ]
        ),
        *screenshot_slot("doc-viewer", "Protected attachment viewer"),
    ]


def ch_inbox():
    return [
        h1("11. Inbox, outbox, and notifications"),
        h2("11.1 Inbox tabs"),
        bullets(
            [
                "<b>Untreated</b>: pending items needing action (also the sidebar badge count).",
                "<b>Treated</b>: items you approved, rejected, or forwarded — with counts and per-status badges.",
                "Acting on an item moves it from Untreated to Treated automatically.",
            ]
        ),
        h2("11.2 Urgent mode and outbox"),
        bullets(
            [
                "<b>Urgent</b> mode lists urgent/high-priority documents across your accessible files.",
                "<b>Sent</b> (outbox) shows everything you dispatched, filterable by status, with search.",
            ]
        ),
        h2("11.3 Notifications"),
        p(
            "The bell lists everything addressed to you (dispatches, approvals, access decisions, lockouts). "
            "Opening a notification marks it read and jumps to the related file. Some events also send email."
        ),
        *screenshot_slot("notifications", "Notifications list"),
    ]


def ch_faq():
    faqs = [
        ("I see “Limited Access View”. What does it mean?",
         "You can open the file's page but not its contents. Either request access (if the file is at rest with Registry), or the contents are hidden from you by policy (e.g. your own personnel file, or Registry viewing any file)."),
        ("“Identity Locked — Request Unavailable”. I already requested access. Why?",
         "That panel means you currently hold no grant on this file. If your request is still pending you would see “Access Pending” instead — so an approved-then-expired or rejected request, or a request on a different file, are the usual causes. If the file is with another custodian, wait until it returns to Registry and request again. Owners adding to their own file: ask Registry for a read &amp; write grant — your approved grant lets you file new records (existing contents stay hidden)."),
        ("“Access Pending” never changes. What now?",
         "Only Registry can approve access requests (Tools &gt; Access Requests). Nudge your Registry officer; ensure the file is at rest with Registry, otherwise approval cannot land."),
        ("“File In Transit — Requests Disabled”.",
         "The file is with another custodian. You cannot request access mid-transit; wait until it returns to Registry."),
        ("My file disappeared from My Files / My Records.",
         "Lower staff only ever see files still <b>in transit</b>. Once settled (active), files leave that list — use <b>View My History</b> or your <b>Inbox</b>. Heads see wider lists."),
        ("I approved something but the file still says In Transit.",
         "Final approval returns the file to active automatically. If it lingers, the file is genuinely awaiting someone's acknowledgement — check Movement History on the file."),
        ("I can't approve / sign — “need a verified signature”.",
         "Upload a signature on your Profile and have it verified. Approvals, signing, and inbox actions all require it."),
        ("Locked out after wrong passwords.",
         "Three failures lock you for 15 minutes. An administrator can unlock you immediately from Management &gt; Users."),
        ("I can't download an attachment I can see listed.",
         "Listing titles and opening bytes are gated separately. You need one of: custody, an approved grant, an active movement, a direct share, or an oversight role over that file."),
        ("A document I uploaded is still Pending.",
         "Only Registry uploads are auto-approved. Yours routes to your head; it flips to approved once the last approver signs off."),
    ]
    story = [h1("12. Troubleshooting")]
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
                ["File", "In Transit", "Sent; awaiting acknowledgement. Still pending."],
                ["File", "Pending Activation", "Approved creation; Registry must activate."],
                ["File", "Inactive / Closed / Archived", "Registry lifecycle end-states."],
                ["Document", "Pending", "Filed; awaiting review."],
                ["Document", "In Transit", "Dispatched for review/approval."],
                ["Document", "Approved / Rejected", "Decided by approver (signature recorded)."],
                ["Movement", "Pending", "Untreated inbox item."],
                ["Movement", "Approved / Rejected / Forwarded", "Treated; lives under the Treated tab."],
            ],
        ),
        h1("Appendix B. Glossary"),
        bullets(
            [
                "<b>Custodian</b> — whoever currently holds a file.",
                "<b>At rest with Registry</b> — active file held by Registry; the only time access can be requested.",
                "<b>Oversight head</b> — HOD, section/division head, flagged supervisor, executive, MD, Mayor (excludes pure unit managers).",
                "<b>Chronicle</b> — the file's unified history: documents and audit entries.",
                "<b>Read &amp; write grant</b> — approved access request allowing adds as well as views.",
            ]
        ),
        small("Generated from the live PIMS codebase. Screenshot placeholders will be filled in Phase 4 (Playwright)."),
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
