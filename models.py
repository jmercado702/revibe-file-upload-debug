from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False, default='intake_staff')  # intake_staff, sales_staff, office_admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    inventory_items = db.relationship('InventoryItem', backref='created_by_user', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission):
        """Check if user has specific permission based on role"""
        permissions = {
            'office_admin': [
                'manage_users', 'view_all', 'reconcile_payments', 'manage_inventory', 
                'create_sales', 'view_inventory', 'view_sales', 'edit_inventory', 
                'delete_inventory', 'edit_sales', 'delete_sales', 'manage_customers',
                'view_customers', 'edit_customers', 'delete_customers', 'manage_files',
                'view_files', 'edit_files', 'delete_files', 'generate_reports',
                'export_data', 'import_data', 'system_settings', 'view_reports'
            ],
            'sales_staff': [
                'create_sales', 'view_inventory', 'view_sales', 'manage_customers',
                'view_customers', 'edit_customers', 'view_files', 'view_reports'
            ],
            'intake_staff': [
                'manage_inventory', 'view_inventory', 'edit_inventory', 
                'manage_files', 'view_files', 'edit_files'
            ]
        }
        return permission in permissions.get(self.role, [])

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    item_type = db.Column(db.String(100), nullable=False)
    source_location = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)  # Number of units
    purchase_cost = db.Column(db.Numeric(10, 2), nullable=False)
    retail_price = db.Column(db.Numeric(10, 2))  # Original/retail price before discount
    selling_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount_percentage = db.Column(db.Integer, default=0)  # 0, 10, 25, 50, 75, 100 etc
    rematter_reference = db.Column(db.String(100))
    status = db.Column(db.String(20), default='available')  # available, sold, reserved
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    files = db.relationship('InventoryFile', backref='inventory_item', lazy=True, cascade='all, delete-orphan')
    sales = db.relationship('Sale', backref='inventory_item', lazy=True)

class InventoryFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)  # photo, video, document
    file_path = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256))  # For customer accounts
    is_registered = db.Column(db.Boolean, default=False)  # Track if customer has account
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    sales = db.relationship('Sale', backref='customer', lazy=True)
    
    def set_password(self, password):
        """Set password hash for registered customers"""
        self.password_hash = generate_password_hash(password)
        self.is_registered = True

    def check_password(self, password):
        """Check password for registered customers"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    
    # Multi-item support - these fields are now totals for the entire sale
    total_sale_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_discount_amount = db.Column(db.Numeric(10, 2), default=0)
    final_total_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    
    payment_method = db.Column(db.String(50), nullable=False)  # cash, check, card, transfer, zelle
    payment_receiver = db.Column(db.String(100), nullable=False)
    payment_status = db.Column(db.String(20), default='pending')  # pending, received, reconciled, voided
    notes = db.Column(db.Text)  # Additional notes for the sale
    zelle_payment = db.Column(db.Boolean, default=False)  # Whether customer will pay via Zelle
    sold_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receipt_shared = db.Column(db.Boolean, default=False)
    receipt_shared_at = db.Column(db.DateTime)
    payment_confirmed_at = db.Column(db.DateTime)  # When payment was confirmed
    payment_confirmed_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Who confirmed payment
    payment_proof_file = db.Column(db.String(255))  # File path for payment proof
    voided_at = db.Column(db.DateTime)  # When sale was voided
    voided_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Who voided the sale
    void_reason = db.Column(db.String(255))  # Reason for voiding
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    sold_by_user = db.relationship('User', foreign_keys=[sold_by], backref='sales_made', lazy='select')
    payment_confirmed_by_user = db.relationship('User', foreign_keys=[payment_confirmed_by], backref='payments_confirmed', lazy='select')
    voided_by_user = db.relationship('User', foreign_keys=[voided_by], backref='sales_voided', lazy='select')
    sale_items = db.relationship('SaleItem', backref='sale', lazy=True, cascade='all, delete-orphan')
    
    # Legacy support - for backward compatibility
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=True)
    quantity_sold = db.Column(db.Integer, default=1)
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)
    discount_percentage = db.Column(db.Numeric(5, 2), default=0)
    final_price = db.Column(db.Numeric(10, 2), nullable=True)

    def generate_invoice_number(self):
        """Generate unique invoice number"""
        today = datetime.utcnow()
        prefix = f"INV{today.strftime('%Y%m%d')}"
        
        # Get the last invoice number for today
        last_invoice = Sale.query.filter(
            Sale.invoice_number.like(f"{prefix}%")
        ).order_by(Sale.invoice_number.desc()).first()
        
        if last_invoice:
            # Extract the sequence number and increment
            sequence = int(last_invoice.invoice_number.split('-')[-1]) + 1
        else:
            sequence = 1
            
        self.invoice_number = f"{prefix}-{sequence:04d}"
    
    def calculate_totals(self):
        """Calculate total prices from sale items"""
        if self.sale_items:
            self.total_sale_price = sum(item.line_total for item in self.sale_items)
            self.total_discount_amount = sum(item.discount_amount for item in self.sale_items)
            self.final_total_price = sum(item.final_line_total for item in self.sale_items)
        else:
            # Legacy single item support
            self.total_sale_price = self.sale_price or 0
            self.final_total_price = self.final_price or 0

class SaleItem(db.Model):
    """Individual items within a multi-item sale"""
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    quantity_sold = db.Column(db.Integer, default=1, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)  # Price per unit
    line_total = db.Column(db.Numeric(10, 2), nullable=False)  # quantity * unit_price
    discount_percentage = db.Column(db.Numeric(5, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    final_line_total = db.Column(db.Numeric(10, 2), nullable=False)  # line_total - discount_amount
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    inventory_item = db.relationship('InventoryItem', backref='sale_items', lazy='select')
    
    def calculate_line_totals(self):
        """Calculate line totals based on quantity and discounts"""
        self.line_total = self.quantity_sold * self.unit_price
        self.discount_amount = (self.line_total * self.discount_percentage) / 100
        self.final_line_total = self.line_total - self.discount_amount

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    table_name = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer, nullable=False)
    old_values = db.Column(db.Text)
    new_values = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
