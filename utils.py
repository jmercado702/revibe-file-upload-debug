import os
import json
from datetime import datetime
from flask import current_app, request
from flask_mail import Message
from flask_login import current_user
from app import db, mail
from models import AuditLog

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov', 'wmv', 'mkv', 'webm', 'pdf'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def log_action(action, table_name, record_id, ip_address, old_values=None, new_values=None):
    """Log user actions for audit trail"""
    try:
        audit_log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            table_name=table_name,
            record_id=record_id,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            ip_address=ip_address
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to log action: {str(e)}")
        db.session.rollback()

def send_email_notification(sale):
    """Send email notification for receipt sharing"""
    if not current_app.config.get('MAIL_USERNAME'):
        raise Exception("Email not configured")
    
    office_email = os.environ.get('OFFICE_EMAIL', current_app.config.get('MAIL_DEFAULT_SENDER'))
    
    msg = Message(
        subject=f'Receipt Shared - Invoice #{sale.invoice_number}',
        recipients=[office_email],
        body=f"""
        A receipt has been shared for:
        
        Invoice Number: {sale.invoice_number}
        Customer: {sale.customer.name}
        Item: {sale.inventory_item.item_type}
        Amount: ${sale.final_price}
        Payment Method: {sale.payment_method}
        Sold By: {sale.sold_by_user.username}
        Date: {sale.sale_date.strftime('%Y-%m-%d %H:%M')}
        
        Please confirm payment receipt in the reconciliation system.
        """
    )
    
    mail.send(msg)

def format_currency(amount):
    """Format decimal amount as currency"""
    return f"${amount:.2f}"

def calculate_profit(sale_price, purchase_cost, discount_percentage=0):
    """Calculate profit from a sale"""
    final_price = float(sale_price) * (1 - float(discount_percentage) / 100)
    return final_price - float(purchase_cost)

def calculate_business_profit(selling_price, purchase_cost, overhead_percentage=30):
    """Calculate profit after deducting overhead (labor, storage, etc.)"""
    gross_profit = float(selling_price) - float(purchase_cost)
    overhead_cost = float(selling_price) * (overhead_percentage / 100)
    net_profit = gross_profit - overhead_cost
    return net_profit

def calculate_actual_discount_percentage(retail_price, selling_price):
    """Calculate the actual discount percentage between retail and selling price"""
    if not retail_price or float(retail_price) <= 0:
        return 0
    discount_amount = float(retail_price) - float(selling_price)
    if discount_amount <= 0:
        return 0
    return (discount_amount / float(retail_price)) * 100

def get_file_icon(file_type):
    """Get appropriate icon class for file type"""
    icons = {
        'photo': 'fas fa-image',
        'video': 'fas fa-video',
        'document': 'fas fa-file-pdf'
    }
    return icons.get(file_type, 'fas fa-file')

def get_payment_status_badge_class(status):
    """Get Bootstrap badge class for payment status"""
    classes = {
        'pending': 'badge-warning',
        'received': 'badge-success',
        'reconciled': 'badge-primary'
    }
    return classes.get(status, 'badge-secondary')

def get_role_display_name(role):
    """Get user-friendly role name"""
    roles = {
        'intake_staff': 'Intake Staff',
        'sales_staff': 'Sales Staff',
        'office_admin': 'Office Admin'
    }
    return roles.get(role, role.replace('_', ' ').title())
