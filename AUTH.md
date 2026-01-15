# Finance Tracker Authentication System

## Overview

The Finance Tracker now includes a comprehensive user authentication system that protects the Quick Links tab with individual user accounts, session management, and admin controls.

## Features

### User Features
- **User Registration**: Create new accounts with username, email, and password
- **Login/Logout**: Secure authentication with session tokens
- **Password Management**: Users can change their own passwords
- **Profile Viewing**: See account creation date and last login time
- **Session Persistence**: Sessions last 24 hours by default
- **Secure Storage**: Passwords hashed using werkzeug.security

### Admin Features
- **User Management Dashboard**: Separate admin interface on port 8052
- **View All Users**: See complete user list with statistics
- **Enable/Disable Accounts**: Activate or deactivate user accounts
- **Password Reset**: Administrators can reset user passwords
- **User Statistics**: Real-time view of total, active, and admin users

## Architecture

### Database Schema

#### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    CONSTRAINT username_length CHECK (length(username) >= 3),
    CONSTRAINT email_format CHECK (email LIKE '%_@__%.__%')
)
```

#### Sessions Table
```sql
CREATE TABLE user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
```

### Files

- **finance_db.py**: Database functions including:
  - `create_user()`: Register new users
  - `authenticate_user()`: Validate credentials
  - `create_session()`: Generate session tokens
  - `validate_session()`: Check session validity
  - `change_password()`: User password changes
  - `list_all_users()`: Admin user listing
  - `toggle_user_status()`: Enable/disable accounts
  - `admin_reset_password()`: Admin password resets
  - `cleanup_expired_sessions()`: Remove old sessions

- **auth_callbacks.py**: Dash callbacks for authentication UI:
  - Form switching (login/register)
  - User registration handler
  - Login handler
  - Quick Links access control
  - Password change functionality
  - Session validation

- **dash_app.py**: Main dashboard with:
  - Flask server for session management
  - Authentication UI components
  - Quick Links tab protection
  - User profile display

- **admin_dashboard.py**: Separate admin interface:
  - Admin authentication
  - User list table
  - User statistics
  - Account enable/disable
  - Password reset tools

## Getting Started

### 1. Initialize Database

The database is automatically initialized when you run the app:

```bash
cd finance_tracker
python dash_app.py
```

### 2. Create First Admin User

Use Python to create an admin account:

```python
import finance_db

# Initialize database
finance_db.init_database()

# Create admin user
success, message, user_id = finance_db.create_user(
    username='admin',
    email='admin@example.com',
    password='admin123',
    is_admin=True
)

print(message)
```

### 3. Access the Applications

- **Main Dashboard**: http://localhost:8051
  - Navigate to "Quick Links" tab
  - Register a new account or login
  - Access protected links after authentication

- **Admin Dashboard**: http://localhost:8052
  - Login with admin credentials
  - Manage user accounts
  - View statistics and activity

### 4. Environment Configuration

Add to `.env` file:

```bash
# Required for session management
SECRET_KEY=your-secret-key-here

# Optional: Legacy password (deprecated)
QUICKLINKS_PASSWORD=finance2025
```

Generate a secret key:
```python
import os
print(os.urandom(24).hex())
```

## User Workflows

### New User Registration

1. Open Finance Tracker dashboard
2. Navigate to Quick Links tab
3. Click "Register" button
4. Fill in:
   - Username (min 3 characters)
   - Email address
   - Password (min 6 characters)
   - Confirm password
5. Click "Create Account"
6. Login with new credentials

### Changing Password

1. Login to Quick Links tab
2. Click "🔄 Change Password"
3. Enter:
   - Current password
   - New password (min 6 characters)
   - Confirm new password
4. Click "Update Password"

### Admin User Management

1. Run admin dashboard: `python admin_dashboard.py`
2. Login with admin credentials
3. View user list and statistics
4. Perform actions:
   - **Disable User**: Enter User ID, click "Disable User"
   - **Enable User**: Enter User ID, click "Enable User"
   - **Reset Password**: Enter User ID and new password, click "Reset Password"
5. Click "🔄 Refresh List" to update table

## Security Features

### Password Security
- **Hashing**: werkzeug.security with PBKDF2-SHA256
- **Minimum Length**: 6 characters required
- **Never Stored**: Passwords hashed before database storage
- **Salt**: Automatic per-password salting

### Session Security
- **Secure Tokens**: 32-byte URL-safe random tokens
- **Time-Limited**: 24-hour expiration (configurable)
- **Database-Backed**: Sessions stored in SQLite
- **Automatic Cleanup**: Expired sessions removed on startup
- **Logout Support**: Immediate session invalidation

### Access Control
- **Authentication Required**: Quick Links tab protected
- **Admin Privileges**: Separate admin dashboard
- **Account Status**: Enable/disable user access
- **Session Validation**: Every request checked

## API Reference

### User Management Functions

```python
# Create new user
success, message, user_id = finance_db.create_user(
    username='john',
    email='john@example.com',
    password='secret123',
    is_admin=False  # Optional, default False
)

# Authenticate user
success, message, user_dict = finance_db.authenticate_user(
    username='john',  # Can be username or email
    password='secret123'
)
# Returns: {'id': 1, 'username': 'john', 'email': 'john@example.com', 
#           'is_admin': False, 'created_at': '...', 'last_login': '...'}

# Create session
session_id = finance_db.create_session(
    user_id=1,
    hours=24  # Optional, default 24
)

# Validate session
valid, user_dict = finance_db.validate_session(session_id)

# Delete session (logout)
finance_db.delete_session(session_id)

# Change password
success, message = finance_db.change_password(
    user_id=1,
    old_password='secret123',
    new_password='newsecret456'
)

# Get user by ID
user_dict = finance_db.get_user_by_id(user_id=1)

# List all users (admin)
users_list = finance_db.list_all_users()

# Enable/disable user (admin)
success, message = finance_db.toggle_user_status(
    user_id=1,
    is_active=True  # or False to disable
)

# Reset password (admin)
success, message = finance_db.admin_reset_password(
    user_id=1,
    new_password='resetpass123'
)

# Cleanup expired sessions
deleted_count = finance_db.cleanup_expired_sessions()
```

## Alternative Authentication Strategies

The current system uses a custom SQLite-based authentication. Here are alternative approaches:

### 1. OAuth 2.0 / Social Login

**Pros:**
- No password management
- Trusted identity providers (Google, Microsoft, GitHub)
- User convenience
- Reduced security liability

**Cons:**
- Requires external service
- Internet dependency
- More complex setup
- User privacy concerns

**Implementation:**
```python
# Using authlib
from authlib.integrations.flask_client import OAuth

oauth = OAuth(server)
oauth.register(
    'google',
    client_id='YOUR_CLIENT_ID',
    client_secret='YOUR_CLIENT_SECRET',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)
```

### 2. LDAP / Active Directory

**Pros:**
- Enterprise integration
- Centralized user management
- Single sign-on (SSO)
- Existing infrastructure

**Cons:**
- Requires LDAP server
- Network dependency
- Complex configuration
- Overkill for small teams

**Implementation:**
```python
# Using python-ldap
import ldap

def ldap_authenticate(username, password):
    conn = ldap.initialize('ldap://ldap.example.com')
    dn = f'uid={username},ou=users,dc=example,dc=com'
    try:
        conn.simple_bind_s(dn, password)
        return True
    except ldap.INVALID_CREDENTIALS:
        return False
```

### 3. Flask-Login Extension

**Pros:**
- Industry standard
- Well-documented
- Session management included
- "Remember me" functionality

**Cons:**
- Additional dependency
- Dash integration complexity
- More boilerplate code

**Implementation:**
```python
from flask_login import LoginManager, UserMixin, login_user

login_manager = LoginManager()
login_manager.init_app(server)

class User(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict['id']
        self.username = user_dict['username']
        # ...
```

### 4. JWT (JSON Web Tokens)

**Pros:**
- Stateless authentication
- API-friendly
- Scalable across services
- No server-side session storage

**Cons:**
- Cannot revoke tokens easily
- Larger token size
- Clock synchronization needed
- Complexity for simple apps

**Implementation:**
```python
import jwt
from datetime import datetime, timedelta

def create_jwt_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')
```

### 5. Dash-Auth (Basic/OAuth)

**Pros:**
- Built for Dash
- Simple configuration
- OAuth2 support
- Minimal code

**Cons:**
- Limited features
- Basic auth not secure over HTTP
- No user management UI
- All-or-nothing protection

**Implementation:**
```python
import dash_auth

# Basic Auth
VALID_USERNAME_PASSWORD_PAIRS = {
    'user1': 'pass1',
    'user2': 'pass2'
}

dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)
```

## Recommended Strategy for Different Use Cases

### Small Team (2-10 users)
**Current Implementation** - Simple, no external dependencies

### Medium Team (10-50 users)
**Flask-Login** - Better session management, "remember me"

### Enterprise (50+ users)
**LDAP/AD Integration** - Centralized management, SSO

### Public-Facing App
**OAuth 2.0** - Social login, no password management

### Microservices Architecture
**JWT** - Stateless, scalable across services

## Maintenance

### Regular Tasks

**Daily:**
- Monitor failed login attempts (future enhancement)
- Check for unusual session activity

**Weekly:**
- Review active user accounts
- Clean up disabled accounts if needed

**Monthly:**
- Update password hashing parameters if needed
- Review and update dependencies
- Backup user database

### Database Backup

```bash
# Backup finance tracker database
cp finance_tracker.db finance_tracker_backup_$(date +%Y%m%d).db

# Restore from backup
cp finance_tracker_backup_YYYYMMDD.db finance_tracker.db
```

### Session Cleanup

Expired sessions are automatically cleaned up on app startup. For manual cleanup:

```python
import finance_db
deleted = finance_db.cleanup_expired_sessions()
print(f"Removed {deleted} expired sessions")
```

## Troubleshooting

### "Invalid username or password"
- Check username/email spelling
- Ensure account is active
- Verify password is correct
- Check if caps lock is on

### "Session expired"
- Login again (sessions last 24 hours)
- Check system clock is correct
- Clear browser cache if issues persist

### "Access denied. Admin privileges required"
- Only admin users can access admin dashboard
- Contact existing admin to grant privileges

### Database Locked Error
- Only one process can write to SQLite at a time
- Close other instances of the app
- Check for hung processes

### Import Errors
- Ensure werkzeug is installed: `pip install werkzeug`
- Verify all files are in finance_tracker directory
- Check Python path includes current directory

## Future Enhancements

Potential improvements for the authentication system:

1. **Two-Factor Authentication (2FA)**
   - TOTP support (Google Authenticator)
   - SMS verification
   - Backup codes

2. **Password Recovery**
   - Email-based reset links
   - Security questions
   - Admin-initiated resets (already implemented)

3. **Enhanced Security**
   - Failed login tracking
   - Account lockout after N attempts
   - IP-based restrictions
   - Session activity logging

4. **User Experience**
   - "Remember me" functionality
   - Last login notification
   - Password strength meter
   - Email verification

5. **Audit Logging**
   - User activity tracking
   - Login/logout events
   - Password changes
   - Admin actions

6. **Role-Based Access Control (RBAC)**
   - Multiple permission levels
   - Resource-specific permissions
   - Role assignment UI

## Support

For issues or questions:
1. Check this documentation
2. Review error messages carefully
3. Check database file permissions
4. Verify environment variables are set
5. Review application logs

## License & Credits

This authentication system was built using:
- **Dash**: Web framework
- **Flask**: HTTP server
- **werkzeug**: Password hashing
- **SQLite**: Database
- **secrets**: Token generation

All code is part of the Finance Tracker project.
