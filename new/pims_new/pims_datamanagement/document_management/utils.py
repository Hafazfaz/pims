"""
Mailto URL generation utilities for opening user's default mail client.
"""
from urllib.parse import quote_plus


def build_mailto_url(
    to: str,
    subject: str = "",
    body: str = "",
    cc: str = "",
    bcc: str = "",
) -> str:
    """
    Build a mailto: URL with the given parameters.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
        cc: CC email address
        bcc: BCC email address
    
    Returns:
        A mailto: URL string
    """
    params = {}
    if subject:
        params["subject"] = subject
    if body:
        params["body"] = body
    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc
    
    query_string = "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
    return f"mailto:{to}?{query_string}"


def build_share_document_mailto(
    recipient_email: str,
    document_title: str,
    file_number: str,
    sender_name: str,
    department: str,
    message: str = "",
    include_signature: bool = False,
    sender_email: str = "",
) -> str:
    """
    Build a mailto URL for sharing a document.
    
    Args:
        recipient_email: Email address of the recipient
        document_title: Title of the document being shared
        file_number: File number/reference
        sender_name: Name of the person sharing
        department: Sender's department
        message: Optional personal message
        include_signature: Whether to include signature note
        sender_email: Sender's email (for reply-to)
    
    Returns:
        A mailto: URL string
    """
    from django.utils import timezone
    
    subject = f"Shared Document: {document_title or 'Untitled'}"
    
    body_parts = []
    if message:
        body_parts.append(message.strip())
        body_parts.append("")  # blank line
    
    body_parts.extend([
        "---",
        f"Document: {document_title or 'Untitled'}",
        f"File: {file_number}",
        f"Shared by: {sender_name}",
        f"Department: {department or 'N/A'}",
        f"Date: {timezone.now().strftime('%B %d, %Y @ %H:%M')}",
        "",
        "This document was shared via the Personnel Information Management System (PIMS).",
    ])
    
    if include_signature:
        body_parts.append("")
        body_parts.append("[Digital signature attached - please verify in PIMS]")
    
    if sender_email:
        body_parts.append(f"Reply to: {sender_email}")
    
    body = "\n".join(body_parts)
    
    return build_mailto_url(to=recipient_email, subject=subject, body=body)


# ---------------------------------------------------------------------------
# Office document -> PDF preview conversion
# ---------------------------------------------------------------------------

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Upload whitelist: PDF + JPEG/PNG images only
# ---------------------------------------------------------------------------
#
# Plain downloads are disabled system-wide (inline preview only), so an
# upload is only useful when the browser can display it directly. Anything
# else (DOCX/XLSX/TXT/ZIP/videos/...) is rejected on the client, in forms,
# and in the views that read request.FILES.

from django.core.exceptions import ValidationError

# The only extensions we accept.
ALLOWED_UPLOAD_EXTS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
}

# MIME types browsers report for those extensions (plus common aliases).
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/pjpeg",
    "image/png",
    "image/x-png",
}

# Value for the file inputs' accept attribute / picker hint text.
UPLOAD_ACCEPT = ".pdf,.jpg,.jpeg,.png"
UPLOAD_HINT = "PDF or image files only (JPG, JPEG, PNG) up to 10MB each"


def upload_rejection_reason(filename, content_type=None):
    """Return why a file is not allowed, or None when it is accepted."""
    name = os.path.basename(filename or "") or "untitled file"
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        return f"'{name}' is not a supported type. Only PDF, JPG, JPEG and PNG files can be uploaded."
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and mime != "application/octet-stream" and mime not in ALLOWED_UPLOAD_MIME_TYPES:
        return f"'{name}' does not look like a PDF, JPG or PNG file."
    return None


def rejected_upload_reasons(files):
    """List of rejection reasons for a batch of uploads ([] when all fine)."""
    reasons = []
    for f in files or []:
        if not f:
            continue
        reason = upload_rejection_reason(getattr(f, "name", ""), getattr(f, "content_type", None))
        if reason:
            reasons.append(reason)
    return reasons


def validate_allowed_uploads(files):
    """Raise ``ValidationError`` unless every file is a browser-renderable PDF/image."""
    reasons = rejected_upload_reasons(files)
    if reasons:
        raise ValidationError(reasons)


# MIME types / extensions we can convert to PDF for in-browser preview.
CONVERTIBLE_TO_PREVIEW = {
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def convert_office_to_pdf(source_path, output_dir=None):
    """Convert an Office document to PDF using LibreOffice (soffice).

    Returns the path to the generated PDF, or None if conversion fails.
    """
    source_path = Path(source_path)
    if not source_path.exists():
        return None

    if output_dir is None:
        output_dir = source_path.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "soffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(source_path),
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("Office-to-PDF conversion failed for %s: %s", source_path, exc)
        return None

    pdf_path = output_dir / f"{source_path.stem}.pdf"
    return pdf_path if pdf_path.exists() else None


# Add timezone import at module level
from django.utils import timezone

