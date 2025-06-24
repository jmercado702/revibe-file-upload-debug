import os
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image as PILImage
import tempfile

def create_product_flyer(item, base_url):
    """
    Create a professional product flyer PDF for an inventory item
    """
    # Create a temporary file for the PDF
    pdf_buffer = io.BytesIO()
    
    # Create the PDF document
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#2c3e50')
    )
    
    price_style = ParagraphStyle(
        'PriceStyle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.HexColor('#e74c3c'),
        alignment=1,
        spaceAfter=20
    )
    
    detail_style = ParagraphStyle(
        'DetailStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10,
        textColor=colors.HexColor('#34495e')
    )
    
    # Story elements
    story = []
    
    # Add ReVibe logo at the top
    try:
        logo_path = os.path.join('static', 'images', 'ReVibe Logo.png')
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=1.5*inch, height=1.5*inch)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 0.1*inch))
    except:
        pass  # Continue without logo if there's an issue
    
    # Business name
    story.append(Paragraph("<b>ReVibe - New Life, Endless Possibilities</b>", 
                          ParagraphStyle('BusinessName', parent=styles['Normal'], 
                                       fontSize=14, alignment=1, spaceAfter=10)))
    
    # Title
    story.append(Paragraph("FOR SALE", title_style))
    story.append(Spacer(1, 12))
    
    # Add product image if available
    photo_file = None
    for file in item.files:
        if file.file_type == 'photo':
            photo_file = file
            break
    
    if photo_file:
        try:
            # Get the image path
            image_path = photo_file.file_path
            if os.path.exists(image_path):
                # Open and resize image
                pil_img = PILImage.open(image_path)
                
                # Convert RGBA to RGB if necessary (for PNG with transparency)
                if pil_img.mode in ('RGBA', 'LA'):
                    # Create a white background
                    background = PILImage.new('RGB', pil_img.size, (255, 255, 255))
                    if pil_img.mode == 'RGBA':
                        background.paste(pil_img, mask=pil_img.split()[-1])  # Use alpha channel as mask
                    else:
                        background.paste(pil_img, mask=pil_img.split()[-1])
                    pil_img = background
                elif pil_img.mode not in ('RGB', 'L'):
                    pil_img = pil_img.convert('RGB')
                
                # Calculate dimensions to fit in 4x4 inch square
                max_size = 4 * inch
                img_width, img_height = pil_img.size
                
                if img_width > img_height:
                    new_width = max_size
                    new_height = (img_height / img_width) * max_size
                else:
                    new_height = max_size
                    new_width = (img_width / img_height) * max_size
                
                # Resize image
                pil_img_resized = pil_img.resize((int(new_width * 72 / inch), int(new_height * 72 / inch)), PILImage.Resampling.LANCZOS)
                
                # Create a temporary file that persists through PDF generation
                import tempfile
                temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg')
                try:
                    # Save resized image to temp file
                    pil_img_resized.save(temp_path, 'JPEG', quality=85)
                    os.close(temp_fd)  # Close file descriptor
                    
                    # Add image to PDF using the temp file path
                    img = Image(temp_path, width=new_width, height=new_height)
                    img.hAlign = 'CENTER'
                    story.append(img)
                    story.append(Spacer(1, 20))
                    
                    # Store temp path for cleanup after PDF is built
                    temp_files_to_cleanup = [temp_path]
                    
                except Exception as img_error:
                    print(f"Error adding image to PDF: {img_error}")
                    os.close(temp_fd) if temp_fd else None
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                
        except Exception as e:
            print(f"Error processing image: {e}")
            # Continue without image
            pass
    
    # Item name/type
    story.append(Paragraph(f"<b>{item.item_type}</b>", title_style))
    story.append(Spacer(1, 12))
    
    # Price
    story.append(Paragraph(f"<b>${item.selling_price:.2f}</b>", price_style))
    story.append(Spacer(1, 20))
    
    # Details table
    details_data = [
        ['Item ID:', f'#{item.id}'],
        ['Source:', item.source_location],
        ['Date Added:', item.date_added.strftime('%B %d, %Y')],
        ['Status:', item.status.title()],
        ['Added By:', item.created_by_user.username]
    ]
    
    details_table = Table(details_data, colWidths=[2*inch, 3*inch])
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(details_table)
    story.append(Spacer(1, 30))
    
    # Contact information
    contact_info = f"""
    <b>Interested in purchasing?</b><br/>
    Contact us to buy this item:<br/>
    <br/>
    <b>Phone:</b> (702) 326-1193<br/>
    <b>Email:</b> sales@recyclingbusiness.com<br/>
    <b>Web:</b> {base_url}/view/{item.id}<br/>
    <br/>
    <b>Business:</b> Recycling Business Manager<br/>
    <i>Quality recycled items at great prices!</i>
    """
    
    story.append(Paragraph(contact_info, detail_style))
    
    # Build PDF
    doc.build(story)
    
    # Clean up temporary files if any were created
    try:
        if 'temp_files_to_cleanup' in locals():
            for temp_file in temp_files_to_cleanup:
                try:
                    os.unlink(temp_file)
                except:
                    pass
    except:
        pass
    
    # Get PDF data
    pdf_data = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    return pdf_data

def create_simple_product_image(item, base_url):
    """
    Create a simple product image with price overlay for quick sharing
    """
    from PIL import Image as PILImage, ImageDraw, ImageFont
    
    # Find the first photo
    photo_file = None
    for file in item.files:
        if file.file_type == 'photo':
            photo_file = file
            break
    
    if not photo_file or not os.path.exists(photo_file.file_path):
        return None
    
    try:
        # Open the original image
        original_img = PILImage.open(photo_file.file_path)
        
        # Convert RGBA to RGB if necessary (for PNG with transparency)
        if original_img.mode in ('RGBA', 'LA'):
            # Create a white background
            background = PILImage.new('RGB', original_img.size, (255, 255, 255))
            if original_img.mode == 'RGBA':
                background.paste(original_img, mask=original_img.split()[-1])  # Use alpha channel as mask
            else:
                background.paste(original_img, mask=original_img.split()[-1])
            original_img = background
        elif original_img.mode not in ('RGB', 'L'):
            original_img = original_img.convert('RGB')
        
        # Resize to a standard size (800x600)
        img = original_img.resize((800, 600), PILImage.Resampling.LANCZOS)
        
        # Create a copy to draw on
        img_with_overlay = img.copy()
        draw = ImageDraw.Draw(img_with_overlay)
        
        # Try to load a font, fallback to default if not available
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
        
        # Add price overlay at the bottom
        overlay_height = 100
        overlay_rect = [(0, 500), (800, 600)]
        
        # Semi-transparent black background
        overlay = PILImage.new('RGBA', (800, 100), (0, 0, 0, 180))
        img_with_overlay.paste(overlay, (0, 500), overlay)
        
        # Add text
        price_text = f"${item.selling_price:.2f}"
        item_text = f"{item.item_type} - Item #{item.id}"
        
        # Draw price
        draw.text((50, 520), price_text, fill=(255, 255, 255), font=font_large)
        
        # Draw item info
        draw.text((50, 570), item_text, fill=(255, 255, 255), font=font_medium)
        
        # Add "For Sale" text in top right
        draw.text((650, 30), "FOR SALE", fill=(255, 255, 255), font=font_medium)
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        img_with_overlay.save(temp_file.name, 'JPEG', quality=90)
        
        with open(temp_file.name, 'rb') as f:
            image_data = f.read()
        
        os.unlink(temp_file.name)
        return image_data
        
    except Exception as e:
        print(f"Error creating product image: {e}")
        return None