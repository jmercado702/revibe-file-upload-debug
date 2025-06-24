#!/usr/bin/env python3
"""
Script to create an initial admin user for the recycling business manager
"""

from app import app, db
from models import User

def create_admin_user():
    with app.app_context():
        # Check if admin already exists
        existing_admin = User.query.filter_by(username='admin').first()
        if existing_admin:
            print("Admin user already exists!")
            return
        
        # Create admin user
        admin = User(
            username='admin',
            email='admin@recycling.local',
            role='office_admin'
        )
        admin.set_password('admin123')
        
        db.session.add(admin)
        db.session.commit()
        
        print("Admin user created successfully!")
        print("Username: admin")
        print("Password: admin123")
        print("Role: Office Admin")

if __name__ == '__main__':
    create_admin_user()