"""
Simple receipt generator for sales with customer sharing options
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


def create_sale_receipt(sale, customer, inventory_item, quantity_sold, format_type='standard'):
    """
    Create a sale receipt PDF with as-is disclaimer
    format_type: 'standard' for regular letter size, 'thermal' for 80mm thermal paper
    """
    format_suffix = "_thermal" if format_type == 'thermal' else ""
    filename = f"receipt_{sale.invoice_number}{format_suffix}.pdf"
    filepath = os.path.join('uploads', filename)
    
    # Ensure uploads directory exists
    os.makedirs('uploads', exist_ok=True)
    
    print(f"Creating receipt: {filepath} (format: {format_type})")
    print(f"Sale items count: {len(sale.sale_items) if sale.sale_items else 0}")
    print(f"Inventory item: {inventory_item.item_type if inventory_item else 'None (multi-item)'}")
    print(f"Sale date: {sale.sale_date} (type: {type(sale.sale_date)})")
    
    # Configure page size based on format
    if format_type == 'thermal':
        # 80mm thermal paper dimensions (80mm width, variable height)
        page_width = 80 * mm
        page_height = 200 * mm  # Start with reasonable height, will auto-adjust
        pagesize = (page_width, page_height)
        margins = (5 * mm, 5 * mm, 5 * mm, 5 * mm)  # Small margins for thermal
    else:
        pagesize = letter
        margins = (72, 72, 72, 72)  # Standard 1-inch margins
    
    # Create the PDF document
    doc = SimpleDocTemplate(filepath, pagesize=pagesize, 
                          leftMargin=margins[0], rightMargin=margins[1],
                          topMargin=margins[2], bottomMargin=margins[3])
    styles = getSampleStyleSheet()
    
    # Custom styles - adjust for thermal vs standard
    if format_type == 'thermal':
        title_font_size = 12
        header_font_size = 8
        normal_font_size = 7
        disclaimer_font_size = 6
        spacer_size = 3
    else:
        title_font_size = 16
        header_font_size = 10
        normal_font_size = 9
        disclaimer_font_size = 8
        spacer_size = 8
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=title_font_size,
        spaceAfter=spacer_size,
        alignment=TA_CENTER
    )
    
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=header_font_size,
        alignment=TA_CENTER,
        spaceAfter=spacer_size
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=normal_font_size,
        alignment=TA_LEFT
    )
    
    disclaimer_style = ParagraphStyle(
        'Disclaimer',
        parent=styles['Normal'],
        fontSize=disclaimer_font_size,
        alignment=TA_LEFT,
        spaceBefore=spacer_size,
        spaceAfter=spacer_size//2,
        backColor=colors.lightgrey,
        borderPadding=2 if format_type == 'thermal' else 5
    )
    
    # Build the content
    content = []
    
    # Add ReVibe logo at the top (size based on format)
    try:
        logo_path = os.path.join('static', 'images', 'ReVibe Logo.png')
        if os.path.exists(logo_path):
            if format_type == 'thermal':
                logo = Image(logo_path, width=20*mm, height=20*mm)
            else:
                logo = Image(logo_path, width=2*inch, height=2*inch)
            logo.hAlign = 'CENTER'
            content.append(logo)
            content.append(Spacer(1, spacer_size//2))
    except:
        pass  # Continue without logo if there's an issue
    
    # Business header
    content.append(Paragraph("ReVibe - New Life, Endless Possibilities", title_style))
    content.append(Paragraph("Phone: 702-326-1193", header_style))
    content.append(Spacer(1, spacer_size))
    
    # Receipt details - handle date formatting safely
    from datetime import datetime
    if isinstance(sale.sale_date, str):
        try:
            sale_date = datetime.fromisoformat(sale.sale_date.replace('Z', '+00:00'))
        except:
            sale_date = datetime.now()
    else:
        sale_date = sale.sale_date

    receipt_data = [
        ['Invoice #:', sale.invoice_number],
        ['Date:', sale_date.strftime('%m/%d/%Y %I:%M %p')],
        ['Customer:', customer.name],
        ['Email:', customer.email or 'N/A'],
        ['Phone:', customer.phone or 'N/A'],
        ['Payment Method:', sale.payment_method.title()],
        ['Received By:', sale.payment_receiver],
    ]
    
    # Adjust table column widths for format
    if format_type == 'thermal':
        col_widths = [25*mm, 45*mm]
    else:
        col_widths = [1.5*inch, 4*inch]
    
    receipt_table = Table(receipt_data, colWidths=col_widths)
    receipt_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), normal_font_size),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3 if format_type == 'thermal' else 4),
    ]))
    content.append(receipt_table)
    content.append(Spacer(1, spacer_size))
    
    # Item details
    item_header_style = ParagraphStyle(
        'ItemHeader',
        parent=styles['Heading3'],
        fontSize=normal_font_size + 1,
        alignment=TA_CENTER if format_type == 'thermal' else TA_LEFT
    )
    content.append(Paragraph("ITEM(S) PURCHASED:", item_header_style))
    
    # Handle multi-item vs single-item sales
    if inventory_item:
        # Legacy single-item sale
        item_description = inventory_item.item_type
        # Process text wrapping for thermal format
        if format_type == 'thermal' and len(item_description) > 20:
            # Split long descriptions into multiple lines for thermal receipts
            words = item_description.split()
            lines = []
            current_line = ""
            for word in words:
                if len(current_line + " " + word) <= 20:
                    current_line += " " + word if current_line else word
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            item_description = "<br/>".join(lines)

    
    # Build item data based on sale type
    if inventory_item:
        # Single-item sale
        item_data = [
            ['Description', 'Qty', 'Unit Price', 'Total'],
            [Paragraph(item_description, normal_style), str(quantity_sold), f"${float(inventory_item.selling_price):.2f}", f"${float(sale.sale_price):.2f}"]
        ]
    else:
        # Multi-item sale
        item_data = [['Description', 'Qty', 'Unit Price', 'Total']]
        for sale_item in sale.sale_items:
            item_desc = sale_item.inventory_item.item_type
            if format_type == 'thermal' and len(item_desc) > 20:
                # Wrap long descriptions for thermal
                words = item_desc.split()
                lines = []
                current_line = ""
                for word in words:
                    if len(current_line + " " + word) <= 20:
                        current_line += " " + word if current_line else word
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                item_desc = "<br/>".join(lines)
            
            item_data.append([
                Paragraph(item_desc, normal_style),
                str(sale_item.quantity_sold),
                f"${float(sale_item.unit_price):.2f}",
                f"${float(sale_item.final_line_total):.2f}"
            ])
    
    # Add discount row if applicable
    if inventory_item and sale.discount_percentage and sale.discount_percentage > 0:
        discount_amount = float(sale.sale_price) - float(sale.final_price)
        item_data.append(['Discount Applied', '', f"-{sale.discount_percentage}%", f"-${discount_amount:.2f}"])
    elif not inventory_item and sale.total_discount_amount > 0:
        item_data.append(['Total Discount', '', '', f"-${float(sale.total_discount_amount):.2f}"])
    
    # Add total row
    final_total = float(sale.final_total_price) if sale.final_total_price else float(sale.final_price or 0)
    if format_type == 'thermal':
        total_text = Paragraph('<font size="6">TOTAL PAID:</font>', normal_style)
        item_data.append(['', '', total_text, f"${final_total:.2f}"])
    else:
        item_data.append(['', '', 'TOTAL PAID:', f"${final_total:.2f}"])
    
    # Adjust table column widths for format - give more space to amount for thermal
    if format_type == 'thermal':
        item_col_widths = [42*mm, 8*mm, 10*mm, 15*mm]
    else:
        item_col_widths = [3*inch, 0.8*inch, 1*inch, 1*inch]
    
    item_table = Table(item_data, colWidths=item_col_widths)
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), normal_font_size),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3 if format_type == 'thermal' else 4),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
    ]))
    content.append(item_table)
    content.append(Spacer(1, spacer_size))
    
    # As-is disclaimer - condensed for thermal
    if format_type == 'thermal':
        disclaimer_text = """
        <b>DISCLAIMER:</b> ALL ITEMS SOLD "AS-IS" WITH NO WARRANTIES.<br/>
        NO RETURNS. ALL SALES FINAL.<br/>
        Customer accepts all responsibility for item condition.
        """
    else:
        disclaimer_text = """
        <b>IMPORTANT DISCLAIMER - PLEASE READ CAREFULLY</b><br/><br/>
        
        ALL ITEMS ARE SOLD "AS-IS, WHERE-IS" WITH NO WARRANTIES OR GUARANTEES.<br/><br/>
        
        • All products are sold as USED items in their current condition<br/>
        • No warranties, express or implied, are provided<br/>
        • All sales are FINAL - no returns or exchanges<br/>
        • Buyer accepts all responsibility for item condition and functionality<br/>
        • Seller is not responsible for any defects, damages, or issues<br/>
        • Items should be inspected before purchase<br/><br/>
        
        By accepting this receipt, customer acknowledges reading and agreeing to these terms.
        """
    
    content.append(Paragraph(disclaimer_text, disclaimer_style))
    content.append(Spacer(1, spacer_size))
    
    # Footer
    footer_text = "Thank you for your business! - Phone: 702-326-1193"
    content.append(Paragraph(footer_text, header_style))
    
    # Build the PDF
    try:
        doc.build(content)
        print(f"PDF successfully created at: {filepath}")
        return filepath
    except Exception as e:
        print(f"Error building PDF: {e}")
        raise


def get_receipt_sharing_options(sale_id):
    """
    Get sharing options for a receipt (email, SMS, download)
    """
    return {
        'email_url': f'/share_receipt/{sale_id}/email',
        'sms_url': f'/share_receipt/{sale_id}/sms', 
        'download_url': f'/download_receipt/{sale_id}',
        'view_url': f'/view_receipt/{sale_id}'
    }