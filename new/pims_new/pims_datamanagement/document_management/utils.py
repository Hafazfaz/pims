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

