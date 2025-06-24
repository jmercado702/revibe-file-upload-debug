from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, MultipleFileField
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, DecimalField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, ValidationError
from models import User, Customer, InventoryItem

class CustomerLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class CustomerRegisterForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Confirm Password', 
                             validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create Account')
    
    def validate_email(self, email):
        customer = Customer.query.filter_by(email=email.data).first()
        if customer and hasattr(customer, 'password_hash'):
            raise ValidationError('Email already registered. Please sign in instead.')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Confirm Password', 
                             validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Role', choices=[
        ('intake_staff', 'Intake Staff'),
        ('sales_staff', 'Sales Staff'),
        ('office_admin', 'Office Admin')
    ], validators=[DataRequired()])
    submit = SubmitField('Create User')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already exists. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please choose a different one.')

class InventoryForm(FlaskForm):
    item_type = StringField('Item Type/Material', validators=[DataRequired(), Length(max=100)])
    source_location = StringField('Source/Collection Location', validators=[DataRequired(), Length(max=200)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)], default=1)
    purchase_cost = DecimalField('Purchase Cost ($)', validators=[DataRequired(), NumberRange(min=0)])
    retail_price = DecimalField('Retail Price ($)', validators=[Optional(), NumberRange(min=0)])
    selling_price = DecimalField('Selling Price ($)', validators=[DataRequired(), NumberRange(min=0)])
    discount_percentage = SelectField('Discount vs Retail', choices=[
        (0, 'No discount badge - just show price'),
        (10, '10% OFF retail price!'),
        (25, '25% OFF retail price!'),
        (50, '50% OFF retail price!'),
        (75, '75% OFF retail price!'),
        (90, '90% OFF retail price!'),
        (100, 'HUGE SAVINGS vs retail!')
    ], coerce=int, validators=[], default=0)
    rematter_reference = StringField('Rematter/Work Order Reference', validators=[Optional(), Length(max=100)])
    files = MultipleFileField('Upload Files (Photos, Videos, Documents)', 
                             validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov', 'pdf'], 
                                                   'Invalid file format')])
    submit = SubmitField('Add Inventory Item')

class CustomerForm(FlaskForm):
    name = StringField('Customer Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[Optional(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Add Customer')

class EditCustomerForm(FlaskForm):
    name = StringField('Customer Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[Optional(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Update Customer')

class PaymentConfirmationForm(FlaskForm):
    payment_proof = FileField('Upload Payment Proof', 
                             validators=[FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 
                                                   'Only JPG, PNG, and PDF files allowed')])
    confirmation_notes = TextAreaField('Confirmation Notes', 
                                     validators=[Optional(), Length(max=500)], 
                                     render_kw={"rows": 3, "placeholder": "Optional notes about payment confirmation..."})
    submit = SubmitField('Confirm Payment Received')

class SaleForm(FlaskForm):
    customer_id = SelectField('Existing Customer', coerce=int, validators=[Optional()])
    inventory_id = SelectField('Item to Sell', coerce=int, validators=[DataRequired()])
    quantity_to_sell = IntegerField('Quantity to Sell', validators=[DataRequired(), NumberRange(min=1)], default=1)
    discount_percentage = DecimalField('Discount (%)', validators=[Optional(), NumberRange(min=0, max=100)])
    payment_method = SelectField('Payment Method', choices=[
        ('cash', 'Cash'),
        ('check', 'Check'),
        ('card', 'Credit/Debit Card'),
        ('transfer', 'Bank Transfer'),
        ('zelle', 'Zelle')
    ], validators=[DataRequired()])
    payment_receiver = StringField('Payment Received By', validators=[DataRequired(), Length(max=100)])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=500)], render_kw={"rows": 3})
    zelle_payment = BooleanField('Customer will pay via Zelle (702-326-1193)')
    submit = SubmitField('Create Sale')

    def __init__(self, *args, **kwargs):
        super(SaleForm, self).__init__(*args, **kwargs)
        # Populate customer choices
        self.customer_id.choices = [(0, 'Create New Customer')] + [
            (c.id, c.name) for c in Customer.query.all()
        ]
        
        # Populate inventory choices with available items only
        available_items = InventoryItem.query.filter_by(status='available').all()
        self.inventory_id.choices = [
            (item.id, f"{item.item_type} - ${item.selling_price:.2f} ({item.discount_percentage}% discount)" if item.discount_percentage > 0 else f"{item.item_type} - ${item.selling_price:.2f}")
            for item in available_items
        ]
