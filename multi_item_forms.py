"""
Forms for multi-item sales functionality
"""
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DecimalField, SelectField, TextAreaField, BooleanField, SubmitField, FieldList, FormField, HiddenField
from wtforms.validators import DataRequired, Optional, NumberRange, Length, ValidationError
from models import Customer, InventoryItem

class SaleItemForm(FlaskForm):
    """Form for individual items within a sale"""
    inventory_id = SelectField('Item', coerce=int, validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)], default=1)
    unit_price = DecimalField('Unit Price ($)', validators=[DataRequired(), NumberRange(min=0)], places=2)
    discount_percentage = DecimalField('Discount (%)', validators=[Optional(), NumberRange(min=0, max=100)], default=0, places=2)

class MultiItemSaleForm(FlaskForm):
    """Form for creating multi-item sales"""
    customer_id = SelectField('Existing Customer', coerce=int, validators=[Optional()])
    
    # New customer fields (shown when creating new customer)
    new_customer_name = StringField('Customer Name', validators=[Optional(), Length(max=100)])
    new_customer_email = StringField('Email', validators=[Optional(), Length(max=120)])
    new_customer_phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    
    # Sale items - will be populated dynamically
    sale_items = FieldList(FormField(SaleItemForm), min_entries=1)
    
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'),
        ('check', 'Check'),
        ('card', 'Credit/Debit Card'),
        ('transfer', 'Bank Transfer'),
        ('zelle', 'Zelle')
    ], validators=[DataRequired()])
    
    payment_receiver = StringField('Payment Received By', validators=[DataRequired(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=500)])
    zelle_payment = BooleanField('Customer will pay via Zelle (702-326-1193)')
    
    submit = SubmitField('Create Sale')

    def __init__(self, *args, **kwargs):
        super(MultiItemSaleForm, self).__init__(*args, **kwargs)
        
        # Populate customer choices
        customers = Customer.query.order_by(Customer.name).all()
        self.customer_id.choices = [(0, 'Create New Customer')] + [(c.id, c.name) for c in customers]
        
        # Populate inventory choices for each sale item
        available_items = InventoryItem.query.filter_by(status='available').order_by(InventoryItem.item_type).all()
        inventory_choices = [(0, 'Select an item...')] + [(item.id, f"{item.item_type} - ${item.selling_price}") for item in available_items]
        
        for sale_item in self.sale_items:
            sale_item.inventory_id.choices = inventory_choices

class EditSaleForm(FlaskForm):
    """Form for editing existing sales"""
    customer_id = SelectField('Customer', coerce=int, validators=[DataRequired()])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'),
        ('check', 'Check'),
        ('card', 'Credit/Debit Card'),
        ('transfer', 'Bank Transfer'),
        ('zelle', 'Zelle')
    ], validators=[DataRequired()])
    payment_receiver = StringField('Payment Received By', validators=[DataRequired(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=500)])
    zelle_payment = BooleanField('Customer will pay via Zelle (702-326-1193)')
    submit = SubmitField('Update Sale')

    def __init__(self, *args, **kwargs):
        super(EditSaleForm, self).__init__(*args, **kwargs)
        customers = Customer.query.order_by(Customer.name).all()
        self.customer_id.choices = [(c.id, c.name) for c in customers]

class VoidSaleForm(FlaskForm):
    """Form for voiding sales"""
    void_reason = StringField('Reason for Voiding', validators=[DataRequired(), Length(max=255)])
    submit = SubmitField('Void Sale')