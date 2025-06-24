import os
import uuid
from datetime import datetime
from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash, send_file, send_from_directory, jsonify, make_response, session, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from flask_mail import Message
import json

from app import app, db, login_manager, mail
from models import User, InventoryItem, InventoryFile, Customer, Sale, SaleItem, AuditLog
from forms import LoginForm, RegisterForm, InventoryForm, SaleForm, CustomerForm, EditCustomerForm, PaymentConfirmationForm, CustomerLoginForm, CustomerRegisterForm
from multi_item_forms import MultiItemSaleForm, EditSaleForm, VoidSaleForm
from utils import allowed_file, log_action, send_email_notification, calculate_business_profit, calculate_actual_discount_percentage
from template_helpers import safe_calculate_totals
from receipt_generator import create_sale_receipt
from barcode_scanner import ProductLookupService
from ai_product_identifier import identify_product_from_image, analyze_product_for_recycling
from pdf_generator import create_product_flyer, create_simple_product_image
from utils import allowed_file

@app.route('/shop')
def public_storefront():
    """Public storefront for customers to browse and inquire about items"""
    search_query = request.args.get('search', '').strip()
    
    # Get available inventory items
    query = InventoryItem.query.filter_by(status='available')
    
    if search_query:
        search_filter = f"%{search_query}%"
        query = query.filter(
            db.or_(
                InventoryItem.item_type.ilike(search_filter),
                InventoryItem.source_location.ilike(search_filter)
            )
        )
    
    items = query.order_by(InventoryItem.date_added.desc()).all()
    
    return render_template('public_storefront.html', items=items, search=search_query)

@app.route('/api/customer-inquiry', methods=['POST'])
def customer_inquiry():
    """Handle customer inquiries from the public storefront"""
    try:
        item_id = request.form.get('item_id')
        customer_name = request.form.get('customer_name', '').strip()
        customer_email = request.form.get('customer_email', '').strip()
        customer_phone = request.form.get('customer_phone', '').strip()
        message = request.form.get('message', '').strip()
        
        if not customer_name or not item_id:
            return jsonify({'success': False, 'error': 'Name and item are required'})
        
        # Get the inventory item
        item = InventoryItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'Item not found'})
        
        # Create or find customer
        customer = Customer.query.filter_by(name=customer_name).first()
        if not customer:
            customer = Customer()
            customer.name = customer_name
            customer.email = customer_email if customer_email else None
            customer.phone = customer_phone if customer_phone else None
            db.session.add(customer)
            db.session.flush()
        
        # Log the inquiry as an audit entry for follow-up
        inquiry_details = {
            'customer_name': customer_name,
            'customer_email': customer_email,
            'customer_phone': customer_phone,
            'item_type': item.item_type,
            'item_price': str(item.selling_price),
            'message': message,
            'inquiry_type': 'website_storefront'
        }
        
        # Create audit log for the inquiry
        audit_log = AuditLog()
        audit_log.user_id = 1  # System user for public inquiries
        audit_log.action = 'customer_inquiry'
        audit_log.table_name = 'inventory_item'
        audit_log.record_id = item.id
        audit_log.new_values = json.dumps(inquiry_details)
        audit_log.ip_address = request.remote_addr
        db.session.add(audit_log)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Inquiry received successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to process inquiry'})

@app.route('/customer/login', methods=['GET', 'POST'])
def customer_login():
    """Customer login page"""
    form = CustomerLoginForm()
    if form.validate_on_submit():
        customer = Customer.query.filter_by(email=form.email.data).first()
        if customer and customer.check_password(form.password.data):
            # Store customer in session
            session['customer_id'] = customer.id
            session['customer_name'] = customer.name
            flash('Welcome back!', 'success')
            return redirect(url_for('public_storefront'))
        flash('Invalid email or password', 'danger')
    return render_template('customer_login.html', form=form)

@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    """Customer registration page"""
    form = CustomerRegisterForm()
    if form.validate_on_submit():
        # Check if customer already exists (even without password)
        existing_customer = Customer.query.filter_by(email=form.email.data).first()
        
        if existing_customer and existing_customer.is_registered:
            flash('Email already registered. Please sign in instead.', 'danger')
            return redirect(url_for('customer_login'))
        
        if existing_customer:
            # Upgrade existing customer to registered account
            existing_customer.name = form.name.data
            existing_customer.phone = form.phone.data
            existing_customer.set_password(form.password.data)
            customer = existing_customer
        else:
            # Create new customer
            customer = Customer()
            customer.name = form.name.data
            customer.email = form.email.data
            customer.phone = form.phone.data
            customer.set_password(form.password.data)
            db.session.add(customer)
        
        db.session.commit()
        
        # Log them in automatically
        session['customer_id'] = customer.id
        session['customer_name'] = customer.name
        flash('Account created successfully! Welcome to ReVibe!', 'success')
        return redirect(url_for('public_storefront'))
    
    return render_template('customer_register.html', form=form)

@app.route('/customer/logout')
def customer_logout():
    """Customer logout"""
    session.pop('customer_id', None)
    session.pop('customer_name', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('public_storefront'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user, remember=form.remember_me.data)
            log_action('login', 'user', user.id, request.remote_addr)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if not current_user.has_permission('manage_users'):
        flash('You do not have permission to create users', 'danger')
        return redirect(url_for('dashboard'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        user = User()
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        log_action('create', 'user', user.id, request.remote_addr)
        flash('User created successfully', 'success')
        return redirect(url_for('user_management'))
    
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    log_action('logout', 'user', current_user.id, request.remote_addr)
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get summary statistics
    total_inventory = InventoryItem.query.filter_by(status='available').count()
    total_sales = Sale.query.count()
    pending_payments = Sale.query.filter_by(payment_status='pending').count()
    
    recent_sales = Sale.query.order_by(Sale.sale_date.desc()).limit(5).all()
    recent_inventory = InventoryItem.query.order_by(InventoryItem.date_added.desc()).limit(5).all()
    
    return render_template('dashboard.html',
                         total_inventory=total_inventory,
                         total_sales=total_sales,
                         pending_payments=pending_payments,
                         recent_sales=recent_sales,
                         recent_inventory=recent_inventory)

@app.route('/inventory')
@login_required
def inventory():
    if not current_user.has_permission('view_inventory'):
        flash('You do not have permission to view inventory', 'danger')
        return redirect(url_for('dashboard'))
    
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    query = InventoryItem.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    items = query.order_by(InventoryItem.date_added.desc()).paginate(
        page=page, per_page=20, error_out=False)
    
    # Calculate totals safely in Python
    all_items = query.all()
    totals = {
        'total_quantity': sum((item.quantity or 1) for item in all_items),
        'total_investment': sum(float(item.purchase_cost or 0) * (item.quantity or 1) for item in all_items),
        'total_revenue': sum(float(item.selling_price or 0) * (item.quantity or 1) for item in all_items),
        'total_net_profit': 0
    }
    
    for item in all_items:
        if item.selling_price and item.purchase_cost:
            selling = float(item.selling_price)
            purchase = float(item.purchase_cost)
            gross = selling - purchase
            overhead = selling * 0.3
            net_per_item = gross - overhead
            totals['total_net_profit'] += net_per_item * (item.quantity or 1)
    
    return render_template('inventory.html', items=items, status_filter=status_filter, totals=totals)

@app.route('/api/inventory/<int:item_id>')
@login_required
def get_inventory_item(item_id):
    """API endpoint to get inventory item data for editing"""
    if not current_user.has_permission('view_inventory'):
        return jsonify({'error': 'Permission denied'}), 403
    
    item = InventoryItem.query.get_or_404(item_id)
    
    # Force refresh the database session to get latest files
    db.session.refresh(item)
    
    # Include file information
    files_data = []
    for file in item.files:
        files_data.append({
            'id': file.id,
            'filename': file.filename,
            'original_filename': file.original_filename,
            'file_type': file.file_type,
            'url': url_for('public_image', file_id=file.id)
        })
    
    app.logger.info(f"API: Item {item_id} returning {len(files_data)} files")
    
    return jsonify({
        'id': item.id,
        'item_type': item.item_type,
        'source_location': item.source_location,
        'quantity': item.quantity,
        'purchase_cost': float(item.purchase_cost),
        'retail_price': float(item.retail_price) if item.retail_price else None,
        'selling_price': float(item.selling_price),
        'discount_percentage': item.discount_percentage,
        'rematter_reference': item.rematter_reference,
        'status': item.status,
        'files': files_data
    })

@app.route('/edit_inventory/<int:item_id>', methods=['POST'])
@login_required  
def edit_inventory(item_id):
    """Edit an existing inventory item"""
    if not current_user.has_permission('manage_inventory'):
        flash('You do not have permission to edit inventory', 'danger')
        return redirect(url_for('inventory'))
    
    item = InventoryItem.query.get_or_404(item_id)
    
    # Store old values for audit log
    old_values = {
        'item_type': item.item_type,
        'source_location': item.source_location,
        'quantity': item.quantity,
        'purchase_cost': float(item.purchase_cost),
        'retail_price': float(item.retail_price) if item.retail_price else None,
        'selling_price': float(item.selling_price),
        'discount_percentage': item.discount_percentage,
        'rematter_reference': item.rematter_reference,
        'status': item.status
    }
    
    # Update item with new values
    item.item_type = request.form.get('item_type')
    item.source_location = request.form.get('source_location')
    item.quantity = int(request.form.get('quantity', 1))
    item.purchase_cost = request.form.get('purchase_cost')
    item.retail_price = request.form.get('retail_price') if request.form.get('retail_price') else None
    item.selling_price = request.form.get('selling_price')
    item.discount_percentage = int(request.form.get('discount_percentage', 0))
    item.rematter_reference = request.form.get('rematter_reference')
    item.status = request.form.get('status')
    
    new_values = {
        'item_type': item.item_type,
        'source_location': item.source_location,
        'quantity': item.quantity,
        'purchase_cost': float(item.purchase_cost) if item.purchase_cost else 0.0,
        'retail_price': float(item.retail_price) if item.retail_price else None,
        'selling_price': float(item.selling_price) if item.selling_price else 0.0,
        'discount_percentage': item.discount_percentage,
        'rematter_reference': item.rematter_reference,
        'status': item.status
    }
    
    # Handle new file uploads BEFORE committing item changes
    uploaded_files = request.files.getlist('files')  # Fixed: was 'new_files', now matches HTML name="files"
    app.logger.info(f"Edit inventory: Found {len(uploaded_files)} files to process for item {item_id}")
    app.logger.info(f"Request files keys: {list(request.files.keys())}")  # Debug what files are being sent
    app.logger.info(f"Form data keys: {list(request.form.keys())}")  # Debug form data
    
    for file in uploaded_files:
        if file and file.filename and allowed_file(file.filename):
            app.logger.info(f"Processing file: {file.filename}")
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # Ensure upload directory exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            try:
                file.save(filepath)
                app.logger.info(f"File saved to: {filepath}")
                
                # Verify file was actually saved
                if not os.path.exists(filepath):
                    raise Exception(f"File was not saved successfully to {filepath}")
                
                # Determine file type
                file_type = 'document'
                if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    file_type = 'photo'
                elif filename.lower().endswith(('.mp4', '.avi', '.mov', '.wmv')):
                    file_type = 'video'
                
                inventory_file = InventoryFile()
                inventory_file.inventory_id = item.id
                inventory_file.filename = unique_filename
                inventory_file.original_filename = filename
                inventory_file.file_type = file_type
                inventory_file.file_path = f"uploads/{unique_filename}"  # Store relative path consistently
                db.session.add(inventory_file)
                app.logger.info(f"Added file record to database: {file_type} - {filename} at {inventory_file.file_path}")
                
            except Exception as e:
                app.logger.error(f"Error saving file {filename}: {str(e)}")
                # Clean up partial file if it exists
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except:
                        pass
        else:
            app.logger.warning(f"Skipped invalid file: {file.filename if file else 'None'}")
    
    # Commit all changes together (item + files)
    try:
        db.session.commit()
        app.logger.info("Database changes committed successfully")
        log_action('update', 'inventory_item', item.id, request.remote_addr, 
                   json.dumps(old_values), json.dumps(new_values))
        
        files_uploaded = len([f for f in uploaded_files if f and f.filename])
        if files_uploaded > 0:
            flash(f'Inventory item "{item.item_type}" updated successfully! {files_uploaded} file(s) uploaded.', 'success')
        else:
            flash(f'Inventory item "{item.item_type}" updated successfully!', 'success')
    except Exception as e:
        app.logger.error(f"Error committing database changes: {str(e)}")
        db.session.rollback()
        flash(f'Error saving changes: {str(e)}', 'danger')
        return redirect(url_for('inventory'))  # Return proper redirect on error
    
    return redirect(url_for('inventory'))
    
    return redirect(url_for('inventory'))

@app.route('/api/file/<int:file_id>/delete', methods=['DELETE'])
@login_required
def delete_file(file_id):
    """Delete a file from an inventory item"""
    if not current_user.has_permission('manage_inventory'):
        return jsonify({'error': 'Permission denied'}), 403
    
    file = InventoryFile.query.get_or_404(file_id)
    
    try:
        # Delete physical file
        if os.path.exists(file.file_path):
            os.remove(file.file_path)
        
        # Delete database record
        db.session.delete(file)
        db.session.commit()
        
        log_action('delete', 'inventory_file', file_id, request.remote_addr)
        
        return jsonify({'success': True, 'message': 'File deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error deleting file'}), 500

@app.route('/inventory/add', methods=['GET', 'POST'])
@login_required
def add_inventory():
    if not current_user.has_permission('manage_inventory'):
        flash('You do not have permission to add inventory', 'danger')
        return redirect(url_for('inventory'))
    
    form = InventoryForm()
    print(f"Form data submitted: {request.form}")
    print(f"Form validation result: {form.validate_on_submit()}")
    if not form.validate_on_submit():
        print(f"Form errors: {form.errors}")
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    
    if form.validate_on_submit():
        try:
            item = InventoryItem()
            item.item_type = form.item_type.data
            item.source_location = form.source_location.data
            item.quantity = form.quantity.data
            item.purchase_cost = form.purchase_cost.data
            item.retail_price = form.retail_price.data
            item.selling_price = form.selling_price.data
            item.discount_percentage = form.discount_percentage.data
            item.rematter_reference = form.rematter_reference.data
            item.created_by = current_user.id
            db.session.add(item)
            db.session.flush()  # Get the ID before committing
            
            # Handle file uploads
            uploaded_files = request.files.getlist('files')
            for file in uploaded_files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(filepath)
                    
                    # Determine file type
                    file_type = 'document'
                    if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        file_type = 'photo'
                    elif filename.lower().endswith(('.mp4', '.avi', '.mov', '.wmv')):
                        file_type = 'video'
                    
                    inventory_file = InventoryFile()
                    inventory_file.inventory_id = item.id
                    inventory_file.filename = unique_filename
                    inventory_file.original_filename = filename
                    inventory_file.file_type = file_type
                    inventory_file.file_path = f"uploads/{unique_filename}"  # Store relative path consistently
                    db.session.add(inventory_file)
            
            db.session.commit()
            log_action('create', 'inventory_item', item.id, request.remote_addr)
            flash('Inventory item added successfully', 'success')
            return redirect(url_for('inventory'))
        except Exception as e:
            db.session.rollback()
            print(f"Database error: {e}")
            flash(f'Error saving inventory item: {str(e)}', 'danger')
    
    # Get inventory items for display
    page = 1
    status_filter = 'all'
    query = InventoryItem.query
    items = query.order_by(InventoryItem.date_added.desc()).paginate(
        page=page, per_page=20, error_out=False)
    
    # Calculate totals for the dashboard
    totals = safe_calculate_totals(query.all())
    
    return render_template('inventory.html', form=form, add_mode=True, items=items, status_filter=status_filter, totals=totals)

@app.route('/barcode_lookup', methods=['POST'])
@login_required
def barcode_lookup():
    """Lookup product information from barcode"""
    if not current_user.has_permission('manage_inventory'):
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    barcode = data.get('barcode')
    if not barcode:
        return jsonify({'error': 'No barcode provided'}), 400
    
    try:
        lookup_service = ProductLookupService()
        product_info = lookup_service.lookup_product(barcode)
        
        if product_info:
            # Download product images
            downloaded_images = []
            if product_info.get('images'):
                downloaded_images = lookup_service.download_product_images(
                    product_info['images'], 
                    app.config['UPLOAD_FOLDER']
                )
            
            return jsonify({
                'success': True,
                'product': {
                    'title': product_info.get('title', ''),
                    'description': product_info.get('description', ''),
                    'brand': product_info.get('brand', ''),
                    'category': product_info.get('category', ''),
                    'source': product_info.get('source', ''),
                    'images': downloaded_images
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Product not found in database'
            })
            
    except Exception as e:
        app.logger.error(f"Barcode lookup error: {str(e)}")
        return jsonify({'error': 'Lookup service unavailable'}), 500

@app.route('/ai_photo_analysis', methods=['POST'])
@login_required
def ai_photo_analysis():
    """Use AI to analyze product photos and extract information"""
    if not current_user.has_permission('manage_inventory'):
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'No photo provided'})
    
    photo = request.files['photo']
    if photo.filename == '':
        return jsonify({'success': False, 'message': 'No photo selected'})
    
    try:
        # Read the image data
        photo_data = photo.read()
        
        # Get AI analysis
        result = identify_product_from_image(photo_data)
        
        if result['success']:
            # Also get recycling-specific analysis
            recycling_analysis = analyze_product_for_recycling(photo_data)
            
            # Save the uploaded photo for reference
            upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            
            # Save the photo
            filename = secure_filename(photo.filename or 'photo.jpg')
            unique_filename = f"{uuid.uuid4()}_{filename}"
            filepath = os.path.join(upload_folder, unique_filename)
            
            # Write the photo data to file
            with open(filepath, 'wb') as f:
                f.write(photo_data)
            
            result['uploaded_photo'] = {
                'filename': unique_filename,
                'path': filepath
            }
            
            if recycling_analysis['success']:
                result['recycling_analysis'] = recycling_analysis['analysis']
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"AI photo analysis error: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'AI analysis failed: {str(e)}'
        })

@app.route('/api/available_inventory')
@login_required
def get_available_inventory():
    """Get available inventory items as JSON for multi-item sales"""
    try:
        items = InventoryItem.query.filter_by(status='available').order_by(InventoryItem.item_type).all()
        
        items_data = []
        for item in items:
            item_data = {
                'id': item.id,
                'item_type': item.item_type,
                'selling_price': float(item.selling_price),
                'purchase_cost': float(item.purchase_cost),
                'source_location': item.source_location,
                'date_added': item.date_added.strftime('%Y-%m-%d'),
                'quantity': item.quantity or 1,
                'image_url': None
            }
            
            # Add first image if available and file exists
            if item.files:
                first_image = next((f for f in item.files if f.file_type == 'photo'), None)
                if first_image and os.path.exists(first_image.file_path):
                    item_data['image_url'] = url_for('public_image', file_id=first_image.id)
            
            items_data.append(item_data)
        
        return jsonify(items_data)
        
    except Exception as e:
        app.logger.error(f"Error getting available inventory: {str(e)}")
        return jsonify([])

@app.route('/sales')
@login_required
def sales():
    if not current_user.has_permission('view_sales'):
        flash('You do not have permission to view sales', 'danger')
        return redirect(url_for('dashboard'))
    
    page = request.args.get('page', 1, type=int)
    sales_list = Sale.query.order_by(Sale.sale_date.desc()).paginate(
        page=page, per_page=20, error_out=False)
    
    # Create forms for the modal
    form = SaleForm()
    customer_form = CustomerForm()
    customers = Customer.query.all()
    
    # Create multi-item form for CSRF token
    from multi_item_forms import MultiItemSaleForm
    multi_item_form = MultiItemSaleForm()
    
    return render_template('sales.html', sales=sales_list, form=form, 
                         customer_form=customer_form, customers=customers,
                         multi_item_form=multi_item_form)

@app.route('/sales/add', methods=['GET', 'POST'])
@login_required
def add_sale():
    if not current_user.has_permission('create_sales'):
        flash('You do not have permission to create sales', 'danger')
        return redirect(url_for('sales'))
    
    form = SaleForm()
    customer_form = CustomerForm()
    
    # Populate available inventory
    available_items = InventoryItem.query.filter_by(status='available').all()
    form.inventory_id.choices = [(item.id, f"{item.item_type} - ${item.selling_price}") 
                                 for item in available_items]
    
    if form.validate_on_submit():
        # Handle customer creation or selection
        customer = None
        if form.customer_id.data:
            customer = Customer.query.get(form.customer_id.data)
        else:
            # Create new customer from form data
            customer_name = request.form.get('customer_name')
            customer_email = request.form.get('customer_email')
            customer_phone = request.form.get('customer_phone')
            
            if not customer_name:
                flash('Customer name is required', 'danger')
                return redirect(url_for('sales'))
            
            customer = Customer()
            customer.name = customer_name
            customer.email = customer_email
            customer.phone = customer_phone
            db.session.add(customer)
            db.session.flush()
        
        # Create sale with quantity
        inventory_item = InventoryItem.query.get(form.inventory_id.data)
        quantity_to_sell = form.quantity_to_sell.data
        
        # Check if inventory item exists and has sufficient quantity
        if not inventory_item:
            flash('Inventory item not found', 'danger')
            return redirect(url_for('sales'))
            
        available_qty = inventory_item.quantity or 0
        if quantity_to_sell > available_qty:
            flash(f'Only {available_qty} units available', 'danger')
            return redirect(url_for('sales'))
        
        # Calculate final price based on quantity
        unit_price = float(inventory_item.selling_price or 0)
        subtotal = unit_price * quantity_to_sell
        discount_pct = float(form.discount_percentage.data or 0)
        final_price = subtotal * (1 - discount_pct / 100)
        
        sale = Sale()
        sale.customer_id = customer.id
        sale.inventory_id = form.inventory_id.data
        sale.quantity_sold = quantity_to_sell
        sale.sale_price = Decimal(str(subtotal))
        sale.discount_percentage = form.discount_percentage.data
        sale.final_price = Decimal(str(final_price))
        sale.payment_method = form.payment_method.data
        sale.payment_receiver = form.payment_receiver.data
        sale.notes = form.notes.data
        sale.zelle_payment = form.zelle_payment.data
        sale.sold_by = current_user.id
        sale.generate_invoice_number()
        
        # Update inventory quantity safely
        current_qty = inventory_item.quantity or 0
        inventory_item.quantity = current_qty - quantity_to_sell
        if inventory_item.quantity <= 0:
            inventory_item.status = 'sold'
        
        db.session.add(sale)
        db.session.commit()
        
        log_action('create', 'sale', sale.id, request.remote_addr)
        flash('Sale created successfully', 'success')
        return redirect(url_for('sales'))
    
    customers = Customer.query.all()
    # Get sales data for the template
    page = request.args.get('page', 1, type=int)
    sales = Sale.query.order_by(Sale.sale_date.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    
    return render_template('sales.html', form=form, customer_form=customer_form, 
                         customers=customers, sales=sales, add_mode=True)

@app.route('/edit_customer/<int:customer_id>', methods=['GET', 'POST'])
@login_required
def edit_customer(customer_id):
    if not current_user.has_permission('manage_sales'):
        flash('You do not have permission to edit customers', 'danger')
        return redirect(url_for('dashboard'))
    
    customer = Customer.query.get_or_404(customer_id)
    form = EditCustomerForm(obj=customer)
    
    if form.validate_on_submit():
        customer.name = form.name.data
        customer.email = form.email.data
        customer.phone = form.phone.data
        db.session.commit()
        
        flash('Customer updated successfully!', 'success')
        return redirect(url_for('sales'))
    
    return render_template('edit_customer.html', form=form, customer=customer)

@app.route('/api/available_inventory')
@login_required
def api_available_inventory():
    """API endpoint to get available inventory items with thumbnails"""
    try:
        available_items = InventoryItem.query.filter(
            InventoryItem.status == 'available',
            InventoryItem.quantity > 0
        ).all()
        items_data = []
        
        for item in available_items:
            # Get first image as thumbnail
            thumbnail = None
            if item.files:
                for file in item.files:
                    if file.file_type == 'photo':
                        thumbnail = url_for('download_file', file_id=file.id)
                        break
            
            items_data.append({
                'id': item.id,
                'item_type': item.item_type,
                'selling_price': float(item.selling_price),
                'retail_price': float(item.retail_price) if item.retail_price else None,
                'discount_percentage': item.discount_percentage,
                'quantity': item.quantity,
                'thumbnail': thumbnail
            })
        
        return jsonify({'items': items_data})
    except Exception as e:
        print(f"Error in api_available_inventory: {e}")
        return jsonify({'error': 'Internal server error', 'items': []}), 500

@app.route('/reconciliation')
@login_required
def reconciliation():
    """Payment reconciliation dashboard - only unconfirmed payments"""
    if not current_user.has_permission('reconcile_payments'):
        flash('You do not have permission to view reconciliation', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get only pending sales that need reconciliation
    pending_sales = Sale.query.filter_by(payment_status='pending').order_by(Sale.sale_date.desc()).all()
    
    # Calculate summary stats for pending only
    total_pending = 0.0
    if pending_sales:
        for sale in pending_sales:
            sale_total = sale.final_price or sale.final_total_price or sale.total_sale_price or 0
            total_pending += float(sale_total) if sale_total is not None else 0.0
    pending_count = len(pending_sales)
    
    return render_template('reconciliation.html', 
                         pending_sales=pending_sales,
                         total_pending=total_pending,
                         pending_count=pending_count)

@app.route('/history')
@login_required
def history():
    """Sales and payment history - all confirmed transactions"""
    # Get search and filter parameters
    search_query = request.args.get('search', '').strip()
    payment_method_filter = request.args.get('payment_method', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Base query for confirmed sales
    query = Sale.query.filter_by(payment_status='received').join(Customer).join(InventoryItem).join(User, Sale.sold_by == User.id)
    
    # Apply search filter
    if search_query:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search_query}%'),
                Sale.invoice_number.ilike(f'%{search_query}%'),
                InventoryItem.item_type.ilike(f'%{search_query}%'),
                Sale.payment_method.ilike(f'%{search_query}%'),
                db.cast(Sale.final_price, db.String).ilike(f'%{search_query}%')
            )
        )
    
    # Apply payment method filter
    if payment_method_filter:
        query = query.filter(Sale.payment_method == payment_method_filter)
    
    # Apply date filters
    if date_from:
        try:
            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Sale.sale_date >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            from datetime import datetime, timedelta
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Sale.sale_date < date_to_obj)
        except ValueError:
            pass
    
    # Get filtered results
    confirmed_sales = query.order_by(Sale.payment_confirmed_at.desc()).all()
    
    # Calculate summary stats
    total_confirmed = float(sum(sale.final_price for sale in confirmed_sales)) if confirmed_sales else 0.0
    confirmed_count = len(confirmed_sales)
    
    # Get unique payment methods for filter dropdown
    payment_methods = db.session.query(Sale.payment_method).filter(Sale.payment_status == 'received').distinct().all()
    payment_methods = [method[0] for method in payment_methods if method[0]]
    
    return render_template('history.html',
                         confirmed_sales=confirmed_sales,
                         total_confirmed=total_confirmed,
                         confirmed_count=confirmed_count,
                         payment_methods=payment_methods,
                         search_query=search_query,
                         payment_method_filter=payment_method_filter,
                         date_from=date_from,
                         date_to=date_to)

@app.route('/reconciliation/confirm_payment/<int:sale_id>', methods=['GET', 'POST'])
@login_required
def confirm_payment(sale_id):
    """Confirm payment received with proof and timestamp"""
    if not current_user.has_permission('reconcile_payments'):
        flash('You do not have permission to reconcile payments', 'danger')
        return redirect(url_for('dashboard'))
    
    sale = Sale.query.get_or_404(sale_id)
    form = PaymentConfirmationForm()
    
    if form.validate_on_submit():
        # Handle file upload if provided
        proof_filename = None
        if form.payment_proof.data:
            file = form.payment_proof.data
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                proof_filename = f"payment_proof_{sale_id}_{timestamp}_{filename}"
                file_path = os.path.join('uploads', 'payment_proofs', proof_filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
        
        # Update sale with confirmation details
        old_status = sale.payment_status
        sale.payment_status = 'received'
        sale.payment_confirmed_at = datetime.utcnow()
        sale.payment_confirmed_by = current_user.id
        sale.payment_proof_file = proof_filename
        
        # Add confirmation notes to the sale notes
        if form.confirmation_notes.data:
            confirmation_note = f"\n[Payment Confirmed by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}]: {form.confirmation_notes.data}"
            if sale.notes:
                sale.notes += confirmation_note
            else:
                sale.notes = confirmation_note.strip()
        
        db.session.commit()
        
        # Log the action
        log_action('confirm_payment', 'sale', sale_id, request.remote_addr,
                   old_values={'payment_status': old_status},
                   new_values={'payment_status': 'received', 'confirmed_by': current_user.username})
        
        flash(f'Payment confirmed for Invoice #{sale.invoice_number}!', 'success')
        return redirect(url_for('reconciliation'))
    
    return render_template('confirm_payment.html', sale=sale, form=form)

@app.route('/reconciliation/mark_received/<int:sale_id>')
@login_required
def mark_payment_received(sale_id):
    """Quick mark payment as received (redirects to confirmation page)"""
    return redirect(url_for('confirm_payment', sale_id=sale_id))

@app.route('/reconciliation/download_proof/<int:sale_id>')
@login_required
def download_payment_proof(sale_id):
    """Download payment proof file"""
    if not current_user.has_permission('reconcile_payments'):
        flash('You do not have permission to access payment proofs', 'danger')
        return redirect(url_for('dashboard'))
    
    sale = Sale.query.get_or_404(sale_id)
    
    if not sale.payment_proof_file:
        flash('No payment proof file available for this sale', 'warning')
        return redirect(url_for('reconciliation'))
    
    file_path = os.path.join('uploads', 'payment_proofs', sale.payment_proof_file)
    
    if not os.path.exists(file_path):
        flash('Payment proof file not found', 'danger')
        return redirect(url_for('reconciliation'))
    
    return send_file(file_path, as_attachment=True, download_name=sale.payment_proof_file)

@app.route('/user_management')
@login_required
def user_management():
    if not current_user.has_permission('manage_users'):
        flash('You do not have permission to manage users', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    return render_template('user_management.html', users=users)

@app.route('/user_management/toggle_status/<int:user_id>')
@login_required
def toggle_user_status(user_id):
    if not current_user.has_permission('manage_users'):
        flash('You do not have permission to manage users', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account', 'danger')
        return redirect(url_for('user_management'))
    
    old_status = user.is_active
    user.is_active = not user.is_active
    db.session.commit()
    
    log_action('update', 'user', user.id, request.remote_addr,
               old_values={'is_active': old_status},
               new_values={'is_active': user.is_active})
    
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {status} successfully', 'success')
    return redirect(url_for('user_management'))

@app.route('/user_management/delete/<int:user_id>')
@login_required
def delete_user(user_id):
    """Delete a user account (only if no associated data)"""
    if not current_user.has_permission('manage_users'):
        flash('You do not have permission to manage users', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Prevent deleting your own account
    if user.id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('user_management'))
    
    # Check if user has any associated data
    inventory_count = len(user.inventory_items)
    sales_count = len(user.sales_made)
    
    if inventory_count > 0 or sales_count > 0:
        flash(f'Cannot delete user {user.username}. User has {inventory_count} inventory items and {sales_count} sales transactions. Please transfer or remove associated data first.', 'danger')
        return redirect(url_for('user_management'))
    
    # Safe to delete - no associated data
    username = user.username
    
    # Log the deletion before deleting the user
    log_action('delete', 'user', user.id, request.remote_addr,
               old_values={'username': user.username, 'email': user.email, 'role': user.role})
    
    # Delete associated audit logs to prevent foreign key constraint issues
    AuditLog.query.filter_by(user_id=user.id).delete()
    
    # Delete the user
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User "{username}" has been permanently deleted', 'success')
    return redirect(url_for('user_management'))

@app.route('/download_file/<int:file_id>')
@login_required
def download_file(file_id):
    file_record = InventoryFile.query.get_or_404(file_id)
    
    # Check permissions
    if not current_user.has_permission('view_inventory'):
        flash('You do not have permission to access this file', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if file exists
    if not os.path.exists(file_record.file_path):
        flash('File not found', 'danger')
        return redirect(url_for('inventory'))
    
    return send_file(file_record.file_path, as_attachment=True, 
                     download_name=file_record.original_filename)

@app.route('/public_image/<int:file_id>')
def public_image(file_id):
    """Public route to serve images for customer storefront"""
    try:
        file_record = InventoryFile.query.get_or_404(file_id)
        
        # Only serve images for available inventory items
        if file_record.inventory_item.status != 'available':
            abort(404)
        
        # Only serve photo files
        if file_record.file_type != 'photo':
            abort(404)
        
        # Check if file actually exists
        if not os.path.exists(file_record.file_path):
            app.logger.error(f"File not found: {file_record.file_path}")
            abort(404)
        
        # Read file content directly
        with open(file_record.file_path, 'rb') as f:
            file_content = f.read()
        
        # Determine proper MIME type based on file extension
        filename_lower = file_record.filename.lower()
        if filename_lower.endswith(('.jpg', '.jpeg')):
            mimetype = 'image/jpeg'
        elif filename_lower.endswith('.png'):
            mimetype = 'image/png'
        elif filename_lower.endswith('.gif'):
            mimetype = 'image/gif'
        else:
            mimetype = 'image/jpeg'  # Default fallback
        
        # Create response with file content
        response = make_response(file_content)
        response.headers['Content-Type'] = mimetype
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Length'] = len(file_content)
        response.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error serving image {file_id}: {str(e)}")
        # Return a 1x1 transparent PNG as fallback
        transparent_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
        response = make_response(transparent_png)
        response.headers['Content-Type'] = 'image/png'
        return response

@app.route('/logo')
def serve_logo():
    """Dedicated route for serving the ReVibe logo"""
    try:
        logo_path = os.path.join(app.static_folder, 'images', 'revibe-logo.png')
        if os.path.exists(logo_path):
            return send_file(logo_path, mimetype='image/png')
        else:
            # Fallback to alternative logo
            alt_logo_path = os.path.join(app.static_folder, 'images', 'ReVibe Logo.png')
            if os.path.exists(alt_logo_path):
                return send_file(alt_logo_path, mimetype='image/png')
            else:
                abort(404)
    except Exception as e:
        app.logger.error(f"Error serving logo: {str(e)}")
        abort(404)

@app.route('/uploads/<path:filename>')
def serve_upload_file(filename):
    """Serve files from the uploads directory"""
    try:
        # Security check - prevent path traversal
        if '..' in filename or filename.startswith('/'):
            abort(404)
        
        upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        file_path = os.path.join(upload_folder, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            abort(404)
        
        # Check file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.mp4', '.avi', '.mov'}
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in allowed_extensions:
            abort(404)
        
        return send_file(file_path)
        
    except Exception as e:
        app.logger.error(f"Error serving upload file {filename}: {str(e)}")
        abort(404)

@app.route('/public_image/<filename>')
def serve_image_by_filename(filename):
    """Serve images by filename for public access - simplified version"""
    app.logger.info(f"Serving image by filename: {filename}")
    try:
        return send_from_directory('uploads', filename)
    except Exception as e:
        app.logger.error(f"Error serving image {filename}: {str(e)}")
        abort(404)

@app.route('/images/<filename>')
def serve_public_image(filename):
    """Direct image serving for external access compatibility"""
    try:
        # Security check - only allow specific file extensions
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif'}
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in allowed_extensions:
            abort(404)
        
        file_path = os.path.join('uploads', filename)
        if not os.path.exists(file_path):
            abort(404)
        
        # Read and serve file directly with maximum compatibility headers
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Determine MIME type
        mime_type = 'image/jpeg'
        if file_ext == '.png':
            mime_type = 'image/png'
        elif file_ext == '.gif':
            mime_type = 'image/gif'
        
        app.logger.info(f"Successfully serving {filename} as {mime_type}, size: {len(file_data)} bytes")
        
        # Create response with headers optimized for external device access
        response = make_response(file_data)
        response.headers['Content-Type'] = mime_type
        response.headers['Content-Length'] = len(file_data)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'unsafe-none'
        response.headers['Content-Disposition'] = 'inline'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error serving image {filename}: {str(e)}")
        # Return a 1x1 transparent PNG as fallback
        transparent_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
        response = make_response(transparent_png)
        response.headers['Content-Type'] = 'image/png'
        return response

@app.route('/api/sale/<int:sale_id>')
@login_required
def get_sale_data(sale_id):
    """Get sale data for editing"""
    sale = Sale.query.get_or_404(sale_id)
    
    return jsonify({
        'id': sale.id,
        'customer_id': sale.customer_id,
        'payment_method': sale.payment_method,
        'payment_receiver': sale.payment_receiver,
        'notes': sale.notes,
        'zelle_payment': sale.zelle_payment
    })

@app.route('/sales/edit/<int:sale_id>', methods=['POST'])
@login_required
def edit_sale(sale_id):
    """Edit an existing sale"""
    if not current_user.has_permission('edit_sales'):
        flash('You do not have permission to edit sales', 'danger')
        return redirect(url_for('sales'))
    
    sale = Sale.query.get_or_404(sale_id)
    
    if sale.payment_status == 'voided':
        flash('Cannot edit a voided sale', 'danger')
        return redirect(url_for('sales'))
    
    try:
        # Update sale details
        old_values = {
            'customer_id': sale.customer_id,
            'payment_method': sale.payment_method,
            'payment_receiver': sale.payment_receiver,
            'notes': sale.notes,
            'zelle_payment': sale.zelle_payment
        }
        
        sale.customer_id = int(request.form.get('customer_id'))
        sale.payment_method = request.form.get('payment_method')
        sale.payment_receiver = request.form.get('payment_receiver')
        sale.notes = request.form.get('notes', '')
        sale.zelle_payment = bool(request.form.get('zelle_payment'))
        
        db.session.commit()
        
        # Log the action
        log_action('update', 'sale', sale.id, request.remote_addr,
                   old_values=old_values,
                   new_values={
                       'customer_id': sale.customer_id,
                       'payment_method': sale.payment_method,
                       'payment_receiver': sale.payment_receiver,
                       'notes': sale.notes,
                       'zelle_payment': sale.zelle_payment
                   })
        
        flash(f'Sale {sale.invoice_number} updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error editing sale {sale_id}: {str(e)}")
        flash('Error updating sale. Please try again.', 'danger')
    
    return redirect(url_for('sales'))

@app.route('/sales/void/<int:sale_id>', methods=['POST'])
@login_required
def void_sale(sale_id):
    """Void a sale"""
    if not current_user.has_permission('void_sales'):
        flash('You do not have permission to void sales', 'danger')
        return redirect(url_for('sales'))
    
    sale = Sale.query.get_or_404(sale_id)
    
    if sale.payment_status == 'voided':
        flash('Sale is already voided', 'warning')
        return redirect(url_for('sales'))
    
    void_reason = request.form.get('void_reason', '').strip()
    if not void_reason:
        flash('Void reason is required', 'danger')
        return redirect(url_for('sales'))
    
    try:
        # Store old values for audit
        old_values = {
            'payment_status': sale.payment_status,
            'voided_at': sale.voided_at,
            'voided_by': sale.voided_by,
            'void_reason': sale.void_reason
        }
        
        # Update sale status
        sale.payment_status = 'voided'
        sale.voided_at = datetime.utcnow()
        sale.voided_by = current_user.id
        sale.void_reason = void_reason
        
        # Return inventory items to available status AND restore quantities
        if sale.inventory_id:
            # Legacy single item
            inventory_item = InventoryItem.query.get(sale.inventory_id)
            if inventory_item:
                inventory_item.quantity += sale.quantity_sold
                inventory_item.status = 'available'
        
        # Handle multi-item sales
        for sale_item in sale.sale_items:
            inventory_item = sale_item.inventory_item
            if inventory_item:
                inventory_item.quantity += sale_item.quantity_sold
                inventory_item.status = 'available'
        
        db.session.commit()
        
        # Log the action
        log_action('void', 'sale', sale.id, request.remote_addr,
                   old_values=old_values,
                   new_values={
                       'payment_status': sale.payment_status,
                       'voided_at': sale.voided_at,
                       'voided_by': sale.voided_by,
                       'void_reason': sale.void_reason
                   })
        
        flash(f'Sale {sale.invoice_number} has been voided. Items returned to inventory.', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error voiding sale {sale_id}: {str(e)}")
        flash('Error voiding sale. Please try again.', 'danger')
    
    return redirect(url_for('sales'))

@app.route('/sales/multi-item', methods=['POST'])
@login_required
def create_multi_item_sale():
    """Create a multi-item sale"""
    if not current_user.has_permission('create_sales'):
        flash('You do not have permission to create sales', 'danger')
        return redirect(url_for('sales'))
    
    # Verify CSRF token
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.form.get('csrf_token'))
    except Exception as e:
        flash('Security token expired. Please try again.', 'danger')
        return redirect(url_for('sales'))
    
    try:
        # Handle customer creation or selection
        customer_id = request.form.get('customer_id')
        if customer_id == '0':
            # Create new customer
            customer_name = request.form.get('new_customer_name', '').strip()
            if not customer_name:
                flash('Customer name is required', 'danger')
                return redirect(url_for('sales'))
            
            customer = Customer()
            customer.name = customer_name
            customer.email = request.form.get('new_customer_email', '').strip()
            customer.phone = request.form.get('new_customer_phone', '').strip()
            db.session.add(customer)
            db.session.flush()  # Get the customer ID
            customer_id = customer.id
        else:
            customer_id = int(customer_id)
            customer = Customer.query.get_or_404(customer_id)
        
        # Create the sale - for multi-item sales, legacy fields are null
        sale = Sale()
        sale.customer_id = customer_id
        sale.payment_method = request.form.get('payment_method')
        sale.payment_receiver = request.form.get('payment_receiver')
        sale.notes = request.form.get('notes', '')
        sale.zelle_payment = bool(request.form.get('zelle_payment'))
        sale.sold_by = current_user.id
        sale.generate_invoice_number()
        
        # Multi-item sales use SaleItem table, not legacy single-item fields
        sale.inventory_id = None
        sale.quantity_sold = None
        sale.sale_price = None
        sale.discount_percentage = None
        sale.final_price = None
        
        # Initialize totals
        sale.total_sale_price = Decimal('0.00')
        sale.total_discount_amount = Decimal('0.00')
        sale.final_total_price = Decimal('0.00')
        
        db.session.add(sale)
        db.session.flush()  # Get the sale ID
        
        # Process sale items using new naming format: sale_items-INDEX-FIELD
        sale_items_data = {}
        # Handle both old and new form formats
        for key, value in request.form.items():
            if key.startswith('sale_items[') and '][' in key:
                # Parse sale_items[1][inventory_id] format (old format)
                parts = key.replace('sale_items[', '').replace(']', '').split('][')
                if len(parts) == 2:
                    item_index, field_name = parts
                    if item_index not in sale_items_data:
                        sale_items_data[item_index] = {}
                    sale_items_data[item_index][field_name] = value
            elif key.startswith('sale_items-') and key.count('-') >= 2:
                # Parse sale_items-1-inventory_id format (new format)
                parts = key.split('-')
                if len(parts) >= 3:
                    item_index = parts[1]
                    field_name = '-'.join(parts[2:])  # Handle field names with dashes
                    if item_index not in sale_items_data:
                        sale_items_data[item_index] = {}
                    sale_items_data[item_index][field_name] = value
        
        # Create sale items
        items_created = 0
        for item_index, item_data in sale_items_data.items():
            print(f"DEBUG: Processing item {item_index}: {item_data}")
            if not all(key in item_data for key in ['inventory_id', 'quantity', 'unit_price']):
                print(f"DEBUG: Skipping item {item_index} - missing required fields. Has: {list(item_data.keys())}")
                continue
                
            # Skip empty inventory_id values
            if not item_data['inventory_id'] or item_data['inventory_id'] == '':
                print(f"DEBUG: Skipping item {item_index} - empty inventory_id")
                continue
            
            # Skip empty or invalid unit_price values
            if not item_data['unit_price'] or item_data['unit_price'] == '':
                print(f"DEBUG: Skipping item {item_index} - empty unit_price")
                continue
                
            try:
                inventory_id = int(item_data['inventory_id'])
                quantity = int(item_data['quantity'])
                unit_price = Decimal(str(item_data['unit_price']))
                discount_percentage = Decimal(str(item_data.get('discount_percentage', '0')))
            except (ValueError, decimal.ConversionSyntax) as e:
                print(f"DEBUG: Skipping item {item_index} - invalid data format: {e}")
                continue
            
            # Create sale item
            sale_item = SaleItem()
            sale_item.sale_id = sale.id
            sale_item.inventory_id = inventory_id
            sale_item.quantity_sold = quantity
            sale_item.unit_price = unit_price
            sale_item.discount_percentage = discount_percentage
            sale_item.calculate_line_totals()
            
            db.session.add(sale_item)
            items_created += 1
            print(f"DEBUG: Created sale item for inventory ID {inventory_id}")
            
            # Update inventory quantity (don't mark as sold for multi-item sales)
            inventory_item = InventoryItem.query.get(inventory_id)
            if inventory_item:
                if inventory_item.quantity >= quantity:
                    inventory_item.quantity -= quantity
                    if inventory_item.quantity == 0:
                        inventory_item.status = 'sold'
                else:
                    flash(f'Warning: Not enough quantity for {inventory_item.item_type}', 'warning')
        
        print(f"DEBUG: Created {items_created} sale items")
        
        if items_created == 0:
            flash('Error: No valid sale items were processed. Please ensure items are selected properly.', 'danger')
            db.session.rollback()
            return redirect(url_for('sales'))
        
        # Calculate sale totals
        sale.calculate_totals()
        db.session.commit()
        
        # Log the action
        log_action('create', 'sale', sale.id, request.remote_addr,
                   new_values={
                       'invoice_number': sale.invoice_number,
                       'customer_id': sale.customer_id,
                       'total_price': float(sale.final_total_price),
                       'payment_method': sale.payment_method
                   })
        
        flash(f'Multi-item sale {sale.invoice_number} created successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating multi-item sale: {str(e)}")
        flash('Error creating sale. Please try again.', 'danger')
    
    return redirect(url_for('sales'))

@app.route('/share_receipt/<int:sale_id>')
@login_required
def share_receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    
    # Mark receipt as shared
    sale.receipt_shared = True
    sale.receipt_shared_at = datetime.utcnow()
    db.session.commit()
    
    # Receipt shared successfully - no email needed, just hyperlink access
    flash('Receipt shared successfully! Customer can access it via the provided link.', 'success')
    
    log_action('share_receipt', 'sale', sale.id, request.remote_addr)
    return redirect(url_for('sales'))

@app.route('/sales/<int:sale_id>/download')
@app.route('/sales/<int:sale_id>/download/<format_type>')
@login_required
def download_receipt(sale_id, format_type='standard'):
    """Download PDF receipt - supports 'standard' or 'thermal' format"""
    try:
        print(f"Receipt download requested - Sale ID: {sale_id}, Format: {format_type}")
        
        sale = Sale.query.get_or_404(sale_id)
        customer = Customer.query.get(sale.customer_id)
        
        print(f"Sale found: {sale.invoice_number}, Customer: {customer.name}")
        
        # For multi-item sales, pass None for single inventory item
        if sale.inventory_id:
            # Legacy single-item sale
            inventory_item = InventoryItem.query.get(sale.inventory_id)
            quantity_sold = sale.quantity_sold
            print("Single-item sale detected")
        else:
            # Multi-item sale
            inventory_item = None
            quantity_sold = None
            print(f"Multi-item sale detected with {len(sale.sale_items)} items")
        
        # Generate receipt PDF with specified format
        receipt_path = create_sale_receipt(sale, customer, inventory_item, quantity_sold, format_type)
        print(f"Receipt generated at: {receipt_path}")
        
        # Verify file exists
        import os
        if not os.path.exists(receipt_path):
            print(f"ERROR: Receipt file not found at {receipt_path}")
            flash(f'Receipt file could not be generated', 'error')
            return redirect(url_for('sales'))
        
        print(f"File exists, size: {os.path.getsize(receipt_path)} bytes")
        
        format_suffix = "_thermal" if format_type == 'thermal' else ""
        filename = f'Receipt_{sale.invoice_number}{format_suffix}.pdf'
        
        print(f"Sending file with name: {filename}")
        response = send_file(receipt_path, as_attachment=True, download_name=filename, mimetype='application/pdf')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"ERROR in download_receipt: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error generating receipt: {str(e)}', 'error')
        return redirect(url_for('sales'))

@app.route('/sales/<int:sale_id>/share/email', methods=['POST'])
@login_required
def share_receipt_email(sale_id):
    """Share receipt via email"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'message': 'Email address required'})
        
        sale = Sale.query.get_or_404(sale_id)
        receipt_url = url_for('public_receipt', sale_id=sale_id, _external=True)
        
        # Here you would send the email with the receipt link
        # For now, we'll just return success with the URL
        return jsonify({
            'success': True, 
            'message': f'Receipt link ready to send to {email}',
            'receipt_url': receipt_url
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/sales/<int:sale_id>/share/sms', methods=['POST'])
@login_required
def share_receipt_sms(sale_id):
    """Share receipt via SMS"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'message': 'Phone number required'})
        
        sale = Sale.query.get_or_404(sale_id)
        receipt_url = url_for('public_receipt', sale_id=sale_id, _external=True)
        
        # Here you would send the SMS with the receipt link
        # For now, we'll just return success with the URL
        return jsonify({
            'success': True, 
            'message': f'Receipt link ready to send to {phone}',
            'receipt_url': receipt_url
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/receipt/<int:sale_id>')
def public_receipt(sale_id):
    """Public receipt view - no login required"""
    sale = Sale.query.get_or_404(sale_id)
    customer = Customer.query.get(sale.customer_id)
    inventory_item = InventoryItem.query.get(sale.inventory_id)
    
    return render_template('public_receipt.html', 
                         sale=sale, 
                         customer=customer, 
                         inventory_item=inventory_item)

@app.route('/generate_product_flyer/<int:item_id>')
@login_required
def generate_product_flyer(item_id):
    """Generate a professional PDF flyer for an inventory item"""
    item = InventoryItem.query.get_or_404(item_id)
    
    try:
        base_url = request.url_root.rstrip('/')
        pdf_data = create_product_flyer(item, base_url)
        
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="product_{item.id}_flyer.pdf"'
        
        return response
    except Exception as e:
        flash(f'Error generating flyer: {str(e)}', 'error')
        return redirect(url_for('inventory'))

@app.route('/generate_product_image/<int:item_id>')
@login_required  
def generate_product_image(item_id):
    """Generate a product image with price overlay for sharing"""
    item = InventoryItem.query.get_or_404(item_id)
    
    try:
        base_url = request.url_root.rstrip('/')
        image_data = create_simple_product_image(item, base_url)
        
        if image_data:
            response = make_response(image_data)
            response.headers['Content-Type'] = 'image/jpeg'
            response.headers['Content-Disposition'] = f'attachment; filename="product_{item.id}_image.jpg"'
            return response
        else:
            flash('No image available for this item', 'warning')
            return redirect(url_for('inventory'))
            
    except Exception as e:
        flash(f'Error generating product image: {str(e)}', 'error')
        return redirect(url_for('inventory'))

@app.route('/view/<int:item_id>')
def public_view_item(item_id):
    """Public view of an inventory item - no login required"""
    item = InventoryItem.query.get_or_404(item_id)
    
    # Only show available items to the public
    if item.status != 'available':
        return render_template('public_item_unavailable.html'), 404
    
    return render_template('public_item_view.html', item=item)

# Mobile App Routes for Field Operations
@app.route('/mobile/dashboard')
@login_required
def mobile_dashboard():
    """Mobile dashboard for field operations"""
    from datetime import datetime, timedelta
    
    today = datetime.utcnow().date()
    
    # Get today's stats
    todays_items = InventoryItem.query.filter(
        db.func.date(InventoryItem.created_at) == today,
        InventoryItem.created_by == current_user.id
    ).count()
    
    todays_sales = db.session.query(db.func.sum(Sale.final_price)).filter(
        db.func.date(Sale.sale_date) == today,
        Sale.sold_by == current_user.id
    ).scalar() or 0
    
    # Get recent items added by current user
    recent_items = InventoryItem.query.filter_by(created_by=current_user.id)\
        .order_by(InventoryItem.created_at.desc()).limit(10).all()
    
    return render_template('mobile_dashboard.html', 
                         todays_items=todays_items,
                         todays_sales=todays_sales,
                         recent_items=recent_items)

@app.route('/mobile/camera_scan')
@login_required
def mobile_camera_scan():
    """Mobile camera scanning interface"""
    return render_template('mobile_camera_scan.html')

@app.route('/mobile/quick_sale')
@login_required
def mobile_quick_sale():
    """Mobile quick sale interface"""
    available_items = InventoryItem.query.filter_by(status='available')\
        .order_by(InventoryItem.created_at.desc()).limit(50).all()
    
    return render_template('mobile_quick_sale.html', available_items=available_items)

@app.route('/mobile/complete_sale', methods=['POST'])
@login_required
def mobile_complete_sale():
    """Complete a sale from mobile interface"""
    try:
        data = request.get_json()
        
        # Get or create customer
        customer_name = data.get('customer_name', '').strip()
        if not customer_name:
            return jsonify({'success': False, 'error': 'Customer name is required'})
        
        customer = Customer.query.filter_by(name=customer_name).first()
        if not customer:
            customer = Customer()
            customer.name = customer_name
            customer.email = data.get('customer_email', '').strip() or None
            customer.phone = data.get('customer_phone', '').strip() or None
            db.session.add(customer)
            db.session.flush()
        
        # Get inventory item
        inventory_item = InventoryItem.query.get(data.get('inventory_id'))
        if not inventory_item or inventory_item.status != 'available':
            return jsonify({'success': False, 'error': 'Item not available'})
        
        quantity_to_sell = int(data.get('quantity_to_sell', 1))
        if quantity_to_sell > inventory_item.quantity:
            return jsonify({'success': False, 'error': 'Not enough quantity available'})
        
        # Calculate prices
        discount_percentage = float(data.get('discount_percentage', 0))
        sale_price = float(inventory_item.selling_price)
        final_price = sale_price * quantity_to_sell * (1 - discount_percentage / 100)
        
        # Create sale
        sale = Sale()
        sale.customer_id = customer.id
        sale.inventory_id = inventory_item.id
        sale.quantity_sold = quantity_to_sell
        sale.sale_price = Decimal(str(sale_price))
        sale.discount_percentage = Decimal(str(discount_percentage))
        sale.final_price = Decimal(str(final_price))
        sale.payment_method = data.get('payment_method', 'cash')
        sale.payment_receiver = data.get('payment_receiver', current_user.username)
        sale.notes = data.get('notes', '')
        sale.zelle_payment = data.get('zelle_payment', False)
        sale.sold_by = current_user.id
        
        sale.generate_invoice_number()
        db.session.add(sale)
        
        # Update inventory
        inventory_item.quantity -= quantity_to_sell
        if inventory_item.quantity == 0:
            inventory_item.status = 'sold'
        
        db.session.commit()
        
        # Log the action
        log_action('mobile_sale', 'sale', sale.id, request.remote_addr)
        
        return jsonify({
            'success': True, 
            'sale_id': sale.id,
            'invoice_number': sale.invoice_number
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Mobile sale error: {str(e)}")
        return jsonify({'success': False, 'error': 'Sale processing failed'})

# Business Reports Routes
@app.route('/reports')
@login_required
def reports():
    """Business reports and analytics dashboard"""
    if not current_user.has_permission('view_reports'):
        flash('You do not have permission to view reports', 'danger')
        return redirect(url_for('dashboard'))
    
    from datetime import datetime, timedelta
    import csv
    import io
    
    # Get date filters from request
    end_date_str = request.args.get('end_date', datetime.utcnow().strftime('%Y-%m-%d'))
    start_date_str = request.args.get('start_date', (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d'))
    user_filter = request.args.get('user_filter', '')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)  # Include end date
    except ValueError:
        flash('Invalid date format', 'danger')
        return redirect(url_for('reports'))
    
    # Base queries with date filters
    sales_query = Sale.query.filter(Sale.sale_date >= start_date, Sale.sale_date < end_date)
    inventory_query = InventoryItem.query.filter(InventoryItem.created_at >= start_date, InventoryItem.created_at < end_date)
    
    # Apply user filter if specified
    if user_filter:
        try:
            user_id = int(user_filter)
            sales_query = sales_query.filter(Sale.sold_by == user_id)
            inventory_query = inventory_query.filter(InventoryItem.created_by == user_id)
        except ValueError:
            pass
    
    # Sales data
    sales_data = sales_query.order_by(Sale.sale_date.desc()).all()
    
    # Inventory data
    inventory_data = inventory_query.order_by(InventoryItem.created_at.desc()).all()
    
    # Reconciliation data (confirmed payments)
    reconciliation_data = Sale.query.filter(
        Sale.payment_confirmed_at.isnot(None),
        Sale.payment_confirmed_at >= start_date,
        Sale.payment_confirmed_at < end_date
    ).order_by(Sale.payment_confirmed_at.desc()).all()
    
    # Calculate summary statistics
    total_sales = float(sum(sale.final_price for sale in sales_data)) if sales_data else 0.0
    total_transactions = len(sales_data)
    items_added = len(inventory_data)
    inventory_value = float(sum(item.selling_price * item.quantity for item in inventory_data)) if inventory_data else 0.0
    
    # Calculate gross profit
    gross_profit = 0.0
    for sale in sales_data:
        if sale.inventory_item and sale.inventory_item.purchase_cost:
            profit = float(sale.final_price) - (float(sale.inventory_item.purchase_cost) * sale.quantity_sold)
            gross_profit += profit
    
    profit_margin = (gross_profit / total_sales * 100) if total_sales > 0 else 0.0
    
    # Pending payments
    pending_sales = Sale.query.filter_by(payment_status='pending').all()
    pending_payments = float(sum(sale.final_price for sale in pending_sales)) if pending_sales else 0.0
    pending_count = len(pending_sales)
    
    summary = {
        'total_sales': total_sales,
        'total_transactions': total_transactions,
        'items_added': items_added,
        'inventory_value': inventory_value,
        'gross_profit': gross_profit,
        'profit_margin': profit_margin,
        'pending_payments': pending_payments,
        'pending_count': pending_count
    }
    
    # User performance data
    users = User.query.filter_by(is_active=True).all()
    user_performance = []
    
    for user in users:
        user_sales = [sale for sale in sales_data if sale.sold_by == user.id]
        user_items = [item for item in inventory_data if item.created_by == user.id]
        user_confirmations = Sale.query.filter(
            Sale.payment_confirmed_by == user.id,
            Sale.payment_confirmed_at >= start_date,
            Sale.payment_confirmed_at < end_date
        ).count()
        
        # Last activity from audit logs or sales/inventory
        last_activity = None
        if user_sales:
            last_activity = max(sale.sale_date for sale in user_sales)
        if user_items:
            item_date = max(item.created_at for item in user_items)
            if not last_activity or item_date > last_activity:
                last_activity = item_date
        
        user_performance.append({
            'username': user.username,
            'role': user.role,
            'items_added': len(user_items),
            'sales_count': len(user_sales),
            'sales_revenue': float(sum(sale.final_price for sale in user_sales)) if user_sales else 0.0,
            'payments_confirmed': user_confirmations,
            'last_activity': last_activity
        })
    
    return render_template('reports.html',
                         current_date=datetime.utcnow(),
                         start_date=start_date_str,
                         end_date=end_date_str,
                         user_filter=user_filter,
                         users=users,
                         summary=summary,
                         sales_data=sales_data,
                         inventory_data=inventory_data,
                         reconciliation_data=reconciliation_data,
                         user_performance=user_performance)

@app.route('/export_reports')
@login_required 
def export_reports():
    """Export reports in CSV or PDF format"""
    if not current_user.has_permission('view_reports'):
        flash('You do not have permission to export reports', 'danger')
        return redirect(url_for('dashboard'))
    
    format_type = request.args.get('format', 'csv')
    report_type = request.args.get('report_type', 'sales')  # sales, inventory, reconciliation, users
    
    # Get same data as reports view with filters
    from datetime import datetime, timedelta
    import csv
    import io
    
    end_date_str = request.args.get('end_date', datetime.utcnow().strftime('%Y-%m-%d'))
    start_date_str = request.args.get('start_date', (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d'))
    user_filter = request.args.get('user_filter', '')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        flash('Invalid date format', 'danger')
        return redirect(url_for('reports'))
    
    # Base queries with date filters
    sales_query = Sale.query.filter(Sale.sale_date >= start_date, Sale.sale_date < end_date)
    inventory_query = InventoryItem.query.filter(InventoryItem.created_at >= start_date, InventoryItem.created_at < end_date)
    
    # Apply user filter if specified
    if user_filter:
        try:
            user_id = int(user_filter)
            sales_query = sales_query.filter(Sale.sold_by == user_id)
            inventory_query = inventory_query.filter(InventoryItem.created_by == user_id)
        except ValueError:
            pass
    
    # Get data based on report type
    if report_type == 'sales':
        sales_data = sales_query.order_by(Sale.sale_date.desc()).all()
        data_to_export = sales_data
    elif report_type == 'inventory':
        inventory_data = inventory_query.order_by(InventoryItem.created_at.desc()).all()
        data_to_export = inventory_data
    elif report_type == 'reconciliation':
        reconciliation_data = Sale.query.filter(
            Sale.payment_confirmed_at.isnot(None),
            Sale.payment_confirmed_at >= start_date,
            Sale.payment_confirmed_at < end_date
        ).order_by(Sale.payment_confirmed_at.desc()).all()
        data_to_export = reconciliation_data
    else:  # users
        users = User.query.filter_by(is_active=True).all()
        data_to_export = users
    
    if format_type == 'csv':
        # Create CSV export
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers and data based on report type
        if report_type == 'sales':
            writer.writerow(['Date', 'Invoice', 'Customer', 'Item', 'Amount', 'Payment Method', 'Status', 'Sold By', 'Confirmed By', 'Confirmed Date'])
            for sale in data_to_export:
                writer.writerow([
                    sale.sale_date.strftime('%Y-%m-%d %H:%M'),
                    sale.invoice_number,
                    sale.customer.name,
                    sale.inventory_item.item_type,
                    f"{sale.final_price:.2f}",
                    sale.payment_method,
                    sale.payment_status,
                    sale.sold_by_user.username,
                    sale.payment_confirmed_by_user.username if sale.payment_confirmed_by_user else '',
                    sale.payment_confirmed_at.strftime('%Y-%m-%d %H:%M') if sale.payment_confirmed_at else ''
                ])
            filename = f"sales_report_{start_date_str}_to_{end_date_str}.csv"
        
        elif report_type == 'inventory':
            writer.writerow(['Date Added', 'Item Type', 'Source', 'Quantity', 'Purchase Cost', 'Selling Price', 'Discount', 'Status', 'Added By'])
            for item in data_to_export:
                writer.writerow([
                    item.created_at.strftime('%Y-%m-%d %H:%M'),
                    item.item_type,
                    item.source_location,
                    item.quantity,
                    f"{item.purchase_cost:.2f}",
                    f"{item.selling_price:.2f}",
                    f"{item.discount_percentage}%" if item.discount_percentage > 0 else "No discount",
                    item.status,
                    item.created_by_user.username
                ])
            filename = f"inventory_report_{start_date_str}_to_{end_date_str}.csv"
        
        elif report_type == 'reconciliation':
            writer.writerow(['Invoice', 'Sale Date', 'Customer', 'Amount', 'Payment Method', 'Confirmed Date', 'Confirmed By'])
            for sale in data_to_export:
                writer.writerow([
                    sale.invoice_number,
                    sale.sale_date.strftime('%Y-%m-%d %H:%M'),
                    sale.customer.name,
                    f"{sale.final_price:.2f}",
                    sale.payment_method,
                    sale.payment_confirmed_at.strftime('%Y-%m-%d %H:%M') if sale.payment_confirmed_at else '',
                    sale.payment_confirmed_by_user.username if sale.payment_confirmed_by_user else ''
                ])
            filename = f"reconciliation_report_{start_date_str}_to_{end_date_str}.csv"
        
        else:  # users
            writer.writerow(['Username', 'Role', 'Email', 'Created', 'Status'])
            for user in data_to_export:
                writer.writerow([
                    user.username,
                    user.role.replace('_', ' ').title(),
                    user.email,
                    user.created_at.strftime('%Y-%m-%d'),
                    'Active' if user.is_active else 'Inactive'
                ])
            filename = f"user_report_{start_date_str}_to_{end_date_str}.csv"
        
        # Create response
        output.seek(0)
        return make_response(
            output.getvalue(),
            200,
            {
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'text/csv'
            }
        )
    
    else:  # PDF format
        # Create PDF export using ReportLab
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        import io
        
        # Create PDF buffer
        buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), 
                              rightMargin=0.5*inch, leftMargin=0.5*inch,
                              topMargin=0.5*inch, bottomMargin=0.5*inch)
        
        # Build story
        story = []
        styles = getSampleStyleSheet()
        
        # Title and table data based on report type
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            textColor=colors.darkblue
        )
        
        summary_style = ParagraphStyle(
            'Summary',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=12
        )
        
        if report_type == 'sales':
            story.append(Paragraph(f"Sales Report ({start_date_str} to {end_date_str})", title_style))
            story.append(Spacer(1, 12))
            
            total_amount = float(sum(sale.final_price for sale in data_to_export)) if data_to_export else 0.0
            story.append(Paragraph(f"Total Sales: ${total_amount:.2f} | Transactions: {len(data_to_export)}", summary_style))
            story.append(Spacer(1, 12))
            
            table_data = [['Date', 'Invoice', 'Customer', 'Item', 'Amount', 'Payment', 'Status', 'Sold By']]
            for sale in data_to_export:
                table_data.append([
                    sale.sale_date.strftime('%m/%d/%Y'),
                    sale.invoice_number,
                    sale.customer.name[:20],
                    sale.inventory_item.item_type[:25],
                    f"${sale.final_price:.2f}",
                    sale.payment_method,
                    sale.payment_status,
                    sale.sold_by_user.username
                ])
            filename = f"sales_report_{start_date_str}_to_{end_date_str}.pdf"
        
        elif report_type == 'inventory':
            story.append(Paragraph(f"Inventory Report ({start_date_str} to {end_date_str})", title_style))
            story.append(Spacer(1, 12))
            
            total_value = float(sum(item.selling_price * item.quantity for item in data_to_export)) if data_to_export else 0.0
            story.append(Paragraph(f"Total Inventory Value: ${total_value:.2f} | Items: {len(data_to_export)}", summary_style))
            story.append(Spacer(1, 12))
            
            table_data = [['Date', 'Item Type', 'Source', 'Qty', 'Cost', 'Price', 'Discount', 'Status']]
            for item in data_to_export:
                table_data.append([
                    item.created_at.strftime('%m/%d/%Y'),
                    item.item_type[:25],
                    item.source_location[:20],
                    str(item.quantity),
                    f"${item.purchase_cost:.2f}",
                    f"${item.selling_price:.2f}",
                    f"{item.discount_percentage}%" if item.discount_percentage > 0 else "-",
                    item.status
                ])
            filename = f"inventory_report_{start_date_str}_to_{end_date_str}.pdf"
        
        elif report_type == 'reconciliation':
            story.append(Paragraph(f"Reconciliation Report ({start_date_str} to {end_date_str})", title_style))
            story.append(Spacer(1, 12))
            
            total_confirmed = float(sum(sale.final_price for sale in data_to_export)) if data_to_export else 0.0
            story.append(Paragraph(f"Total Confirmed: ${total_confirmed:.2f} | Payments: {len(data_to_export)}", summary_style))
            story.append(Spacer(1, 12))
            
            table_data = [['Invoice', 'Sale Date', 'Customer', 'Amount', 'Payment Method', 'Confirmed By']]
            for sale in data_to_export:
                table_data.append([
                    sale.invoice_number,
                    sale.sale_date.strftime('%m/%d/%Y'),
                    sale.customer.name[:20],
                    f"${sale.final_price:.2f}",
                    sale.payment_method,
                    sale.payment_confirmed_by_user.username if sale.payment_confirmed_by_user else ''
                ])
            filename = f"reconciliation_report_{start_date_str}_to_{end_date_str}.pdf"
        
        else:  # users
            story.append(Paragraph(f"User Performance Report ({start_date_str} to {end_date_str})", title_style))
            story.append(Spacer(1, 12))
            
            story.append(Paragraph(f"Active Users: {len(data_to_export)}", summary_style))
            story.append(Spacer(1, 12))
            
            table_data = [['Username', 'Role', 'Email', 'Created', 'Status']]
            for user in data_to_export:
                table_data.append([
                    user.username,
                    user.role.replace('_', ' ').title(),
                    user.email[:30],
                    user.created_at.strftime('%m/%d/%Y'),
                    'Active' if user.is_active else 'Inactive'
                ])
            filename = f"user_report_{start_date_str}_to_{end_date_str}.pdf"
        
        # Create table
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        
        # Add footer
        story.append(Spacer(1, 20))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey
        )
        story.append(Paragraph(f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} | Recycling Business Manager", footer_style))
        
        # Build PDF
        doc.build(story)
        
        # Create response
        buffer.seek(0)
        
        return make_response(
            buffer.getvalue(),
            200,
            {
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/pdf'
            }
        )

# Admin-only Delete Routes
@app.route('/admin/delete_inventory/<int:item_id>', methods=['POST'])
@login_required
def admin_delete_inventory(item_id):
    """Admin-only: Delete an inventory item and all associated files"""
    if current_user.role != 'office_admin':
        flash('Only office administrators can delete inventory items', 'danger')
        return redirect(url_for('inventory'))
    
    item = InventoryItem.query.get_or_404(item_id)
    
    # Check if item has been sold
    if Sale.query.filter_by(inventory_id=item_id).first():
        flash('Cannot delete inventory item that has been sold', 'danger')
        return redirect(url_for('inventory'))
    
    try:
        # Delete associated files first
        for file in item.files:
            # Delete physical file if it exists
            if os.path.exists(file.file_path):
                os.remove(file.file_path)
            db.session.delete(file)
        
        # Log the deletion
        log_action('delete_inventory', 'inventory_item', item_id, request.remote_addr,
                   old_values={'item_type': item.item_type, 'selling_price': str(item.selling_price)})
        
        db.session.delete(item)
        db.session.commit()
        
        flash(f'Inventory item "{item.item_type}" has been permanently deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting inventory item', 'danger')
        app.logger.error(f"Error deleting inventory item {item_id}: {str(e)}")
    
    return redirect(url_for('inventory'))

@app.route('/admin/delete_sale/<int:sale_id>', methods=['POST'])
@login_required
def admin_delete_sale(sale_id):
    """Admin-only: Delete a sale transaction"""
    if current_user.role != 'office_admin':
        flash('Only office administrators can delete sale transactions', 'danger')
        return redirect(url_for('history'))
    
    sale = Sale.query.get_or_404(sale_id)
    
    try:
        # Restore inventory quantity - handle both single and multi-item sales
        if sale.inventory_item:
            # Legacy single-item sale
            sale.inventory_item.quantity += sale.quantity_sold
            if sale.inventory_item.status == 'sold':
                sale.inventory_item.status = 'available'
        elif sale.sale_items:
            # Multi-item sale - restore each item
            for sale_item in sale.sale_items:
                if sale_item.inventory_item:
                    sale_item.inventory_item.quantity += sale_item.quantity_sold
                    if sale_item.inventory_item.status == 'sold':
                        sale_item.inventory_item.status = 'available'
        
        # Delete payment proof file if it exists
        if sale.payment_proof_file:
            proof_path = os.path.join('uploads', 'payment_proofs', sale.payment_proof_file)
            if os.path.exists(proof_path):
                os.remove(proof_path)
        
        # Log the deletion
        log_action('delete_sale', 'sale', sale_id, request.remote_addr,
                   old_values={'invoice_number': sale.invoice_number, 'final_price': str(sale.final_price)})
        
        db.session.delete(sale)
        db.session.commit()
        
        flash(f'Sale transaction {sale.invoice_number} has been permanently deleted and inventory restored', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting sale transaction', 'danger')
        app.logger.error(f"Error deleting sale {sale_id}: {str(e)}")
    
    return redirect(url_for('history'))

@app.route('/admin/delete_customer/<int:customer_id>', methods=['POST'])
@login_required
def admin_delete_customer(customer_id):
    """Admin-only: Delete a customer (only if no sales exist)"""
    if current_user.role != 'office_admin':
        flash('Only office administrators can delete customers', 'danger')
        return redirect(url_for('sales'))
    
    customer = Customer.query.get_or_404(customer_id)
    
    # Check if customer has any sales
    if Sale.query.filter_by(customer_id=customer_id).first():
        flash('Cannot delete customer with existing sales transactions', 'danger')
        return redirect(url_for('sales'))
    
    try:
        # Log the deletion
        log_action('delete_customer', 'customer', customer_id, request.remote_addr,
                   old_values={'name': customer.name, 'email': customer.email})
        
        db.session.delete(customer)
        db.session.commit()
        
        flash(f'Customer "{customer.name}" has been permanently deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting customer', 'danger')
        app.logger.error(f"Error deleting customer {customer_id}: {str(e)}")
    
    return redirect(url_for('sales'))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error_message="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error_message="Internal server error"), 500
