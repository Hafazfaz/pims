import io
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from core.constants import DEFAULT_WATERMARK_TEXT

def create_watermark_pdf(watermark_text=DEFAULT_WATERMARK_TEXT):
    """
    Creates a single-page PDF containing the watermark text.
    """
    watermark_output = io.BytesIO()
    c = canvas.Canvas(watermark_output, pagesize=letter)
    c.setFont('Helvetica', 30)
    c.setFillColorRGB(0, 0, 0, alpha=0.2) # Light gray, semi-transparent
    
    # Position watermark (e.g., diagonally across the page)
    page_width, page_height = letter
    text_width = c.stringWidth(watermark_text, 'Helvetica', 30)
    
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
    watermark_page = watermark_reader.pages[0] # Get the single watermark page

    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        
        # Merge watermark onto the page
        page.merge_page(watermark_page)
        writer.add_page(page)

    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    return output_pdf
