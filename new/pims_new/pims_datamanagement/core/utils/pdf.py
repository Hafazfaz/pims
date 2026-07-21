import io
import os
import re

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from core.constants import DEFAULT_WATERMARK_TEXT

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "static", "img", "logo.png")


def create_watermark_pdf(watermark_text=DEFAULT_WATERMARK_TEXT):
    """
    Creates a single-page PDF containing the watermark text.
    """
    watermark_output = io.BytesIO()
    c = canvas.Canvas(watermark_output, pagesize=letter)
    c.setFont("Helvetica", 30)
    c.setFillColorRGB(0, 0, 0, alpha=0.2)  # Light gray, semi-transparent

    # Position watermark (e.g., diagonally across the page)
    page_width, page_height = letter
    text_width = c.stringWidth(watermark_text, "Helvetica", 30)

    # Simple centered placement
    x = (page_width - text_width) / 2
    y = page_height / 2

    c.drawString(x, y, watermark_text)
    c.save()
    watermark_output.seek(0)
    return PdfReader(watermark_output)


def watermark_pdf_file(original_pdf_file, watermark_text=DEFAULT_WATERMARK_TEXT):
    """
    Applies a text watermark to a PDF file.

    Args:
        original_pdf_file: A file-like object containing the original PDF.
        watermark_text: The text to use as a watermark.

    Returns:
        A file-like object containing the watermarked PDF.
    """
    reader = PdfReader(original_pdf_file)
    writer = PdfWriter()

    # Create the watermark once
    watermark_reader = create_watermark_pdf(watermark_text)
    watermark_page = watermark_reader.pages[0]  # Get the single watermark page

    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]

        # Merge watermark onto the page
        page.merge_page(watermark_page)
        writer.add_page(page)

    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    return output_pdf


def _strip_html(html_text):
    text = re.sub(r"<br\s*/?>", "\n", html_text)
    text = re.sub(r"<p[^>]*>", "\n", text)
    text = re.sub(r"</p>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return text.strip()


def generate_document_pdf(document_title, document_content, sender_name, sender_dept, signature_image=None):
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    page_width, page_height = letter
    margin = 60
    usable_width = page_width - 2 * margin
    y = page_height - margin

    green = (0.0, 0.529, 0.318)

    c.setFillColorRGB(*green)
    c.rect(0, page_height - 80, page_width, 80, fill=True, stroke=False)
    try:
        logo = ImageReader(LOGO_PATH)
        logo_x = margin
        logo_y = page_height - 70
        logo_w = 50
        logo_h = 60
        c.setFillColorRGB(1, 1, 1)
        c.roundRect(logo_x - 4, logo_y - 4, logo_w + 8, logo_h + 8, 6, fill=True, stroke=False)
        c.drawImage(logo, logo_x, logo_y, width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
        text_x = margin + 60
    except Exception:
        text_x = margin
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString((text_x + page_width) / 2, page_height - 35, "PERSONNEL INFORMATION MANAGEMENT SYSTEM")
    c.setFont("Helvetica", 10)
    c.drawCentredString((text_x + page_width) / 2, page_height - 55, "Document Share")

    y = page_height - 110
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, document_title.upper())
    y -= 5
    c.setStrokeColorRGB(*green)
    c.setLineWidth(2)
    c.line(margin, y, margin + usable_width, y)
    y -= 25

    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, f"Shared by: {sender_name}")
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, f"Department: {sender_dept}")
    y -= 25

    plain = _strip_html(document_content) if document_content else "No content."
    lines = plain.split("\n")
    c.setFont("Helvetica", 10)
    for line in lines:
        line = line.strip()
        if not line:
            y -= 8
            continue
        wrapped = []
        while len(line) > 90:
            split_at = line.rfind(" ", 0, 90)
            if split_at == -1:
                split_at = 90
            wrapped.append(line[:split_at])
            line = line[split_at:].strip()
        wrapped.append(line)
        for wl in wrapped:
            if y < margin + 100:
                c.showPage()
                y = page_height - margin
                c.setFont("Helvetica", 10)
            c.drawString(margin, y, wl)
            y -= 14
        y -= 4

    y -= 20
    if signature_image:
        try:
            sig = ImageReader(signature_image)
            sig_w = 120
            sig_h = 40
            sig_x = page_width - margin - sig_w
            if y - sig_h < margin:
                c.showPage()
                y = page_height - margin
            c.drawImage(sig, sig_x, y - sig_h, width=sig_w, height=sig_h, preserveAspectRatio=True, mask='auto')
            y -= sig_h + 5
        except Exception:
            pass

    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(0.5)
    c.line(margin, y, margin + usable_width, y)
    y -= 15
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.setFont("Helvetica", 8)
    c.drawString(margin, y, f"Digitally signed by: {sender_name}")
    y -= 12
    c.drawString(margin, y, "Generated by PIMS — Personnel Information Management System")

    c.save()
    output.seek(0)
    return output
