#!/usr/bin/env python3
"""
Finance Tracker Authentication Setup Script
Helps initialize the database and create the first admin user
"""

import os
import sys

# Add finance_tracker to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import finance_db

def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")

def generate_secret_key():
    """Generate a secure secret key"""
    import secrets
    return secrets.token_hex(24)

def setup_environment():
    """Create or update .env file"""
    print_header("Environment Setup")
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    env_exists = os.path.exists(env_path)
    
    if env_exists:
        print("✓ .env file already exists")
        update = input("Do you want to add/update SECRET_KEY? (y/n): ").lower().strip()
        if update != 'y':
            return
    
    # Generate secret key
    secret_key = generate_secret_key()
    
    if env_exists:
        # Append to existing file
        with open(env_path, 'a') as f:
            f.write(f"\n# Authentication (added by setup script)\nSECRET_KEY={secret_key}\n")
        print(f"\n✓ Added SECRET_KEY to .env file")
    else:
        # Create new file
        with open(env_path, 'w') as f:
            f.write("# Finance Tracker Environment Variables\n\n")
            f.write("# Google Sheets\n")
            f.write("GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit\n\n")
            f.write("# Linkwarden\n")
            f.write("LINKWARDEN_URL=http://localhost:3000\n\n")
            f.write("# Authentication\n")
            f.write(f"SECRET_KEY={secret_key}\n\n")
            f.write("# Legacy password (deprecated)\n")
            f.write("QUICKLINKS_PASSWORD=finance2025\n")
        print(f"\n✓ Created .env file with SECRET_KEY")
    
    print(f"   SECRET_KEY: {secret_key[:16]}... (hidden)")

def init_database():
    """Initialize the database"""
    print_header("Database Initialization")
    
    db_path = finance_db.DB_PATH
    db_exists = os.path.exists(db_path)
    
    if db_exists:
        print(f"✓ Database already exists at: {db_path}")
        reinit = input("Do you want to reinitialize tables? (y/n): ").lower().strip()
        if reinit != 'y':
            return True
    
    try:
        finance_db.init_database()
        print(f"\n✓ Database initialized successfully")
        print(f"   Location: {db_path}")
        return True
    except Exception as e:
        print(f"\n✗ Error initializing database: {e}")
        return False

def create_admin_user():
    """Create first admin user"""
    print_header("Create Admin User")
    
    # Check if any users exist
    users = finance_db.list_all_users()
    if users:
        print(f"✓ Database already has {len(users)} user(s)")
        admin_count = sum(1 for u in users if u['is_admin'])
        print(f"   Admin users: {admin_count}")
        
        create_another = input("\nDo you want to create another admin user? (y/n): ").lower().strip()
        if create_another != 'y':
            return
    
    print("\nEnter admin account details:")
    print("(Username: min 3 chars, Password: min 6 chars)")
    
    # Get username
    while True:
        username = input("\nUsername: ").strip()
        if len(username) < 3:
            print("  ✗ Username must be at least 3 characters")
            continue
        break
    
    # Get email
    while True:
        email = input("Email: ").strip()
        if '@' not in email or '.' not in email:
            print("  ✗ Invalid email format")
            continue
        break
    
    # Get password
    import getpass
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < 6:
            print("  ✗ Password must be at least 6 characters")
            continue
        
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("  ✗ Passwords do not match")
            continue
        break
    
    # Create user
    print("\nCreating admin user...")
    success, message, user_id = finance_db.create_user(
        username=username,
        email=email,
        password=password,
        is_admin=True
    )
    
    if success:
        print(f"\n✓ {message}")
        print(f"   User ID: {user_id}")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   Admin: Yes")
    else:
        print(f"\n✗ {message}")

def show_next_steps():
    """Display next steps"""
    print_header("Setup Complete!")
    
    print("Next steps:")
    print("\n1. Run the main dashboard:")
    print("   cd finance_tracker")
    print("   python dash_app.py")
    print("   Then open: http://localhost:8051")
    
    print("\n2. Run the admin dashboard (optional):")
    print("   cd finance_tracker")
    print("   python admin_dashboard.py")
    print("   Then open: http://localhost:8052")
    
    print("\n3. Access Quick Links tab:")
    print("   - Navigate to Quick Links tab")
    print("   - Login with admin credentials")
    print("   - Or register a new user account")
    
    print("\n4. Documentation:")
    print("   - README.md - General overview")
    print("   - AUTH.md - Authentication details")
    print("   - control_panel/README.md - Subprocess management")
    
    print("\n" + "=" * 60 + "\n")

def main():
    """Main setup flow"""
    print("\n" + "=" * 60)
    print("  Finance Tracker Authentication Setup")
    print("  v1.0")
    print("=" * 60)
    
    try:
        # Step 1: Environment
        setup_environment()
        
        # Step 2: Database
        if not init_database():
            print("\n✗ Setup failed - could not initialize database")
            return 1
        
        # Step 3: Admin user
        create_admin_user()
        
        # Step 4: Next steps
        show_next_steps()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n✗ Setup cancelled by user")
        return 1
    except Exception as e:
        print(f"\n\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
