"""
SQLite database module for tracking daily finance metrics
Captures invoice and job count snapshots once per day
Also includes user authentication and management
"""

import sqlite3
import pandas as pd
from datetime import datetime, date
import os
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import json

# Database file location (same directory as this script)
DB_PATH = Path(__file__).parent / 'finance_tracker.db'


def get_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


def init_database():
    """Initialize database with schema"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
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
    ''')
    
    # Create sessions table for tracking logged-in users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Create daily metrics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_metrics (
            date DATE PRIMARY KEY,
            
            -- Invoice metrics from inv_tbl
            total_invoices INTEGER,
            paid_invoices INTEGER,
            submitted_invoices INTEGER,
            pending_invoices INTEGER,
            other_invoices INTEGER,
            
            -- Financial metrics from inv_tbl
            total_owed_to_acd REAL,
            total_owed_to_workers REAL,
            avg_owed_to_acd REAL,
            avg_owed_to_workers REAL,
            
            -- Job metrics from jobs_tbl
            total_jobs INTEGER,
            acd_paid_jobs INTEGER,
            acd_submitted_jobs INTEGER,
            acd_pending_jobs INTEGER,
            worker_paid_jobs INTEGER,
            worker_submitted_jobs INTEGER,
            worker_pending_jobs INTEGER,
            
            -- Metadata
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_date ON daily_metrics(date)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_username ON users(username)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_email ON users(email)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_session_user ON user_sessions(user_id)
    ''')

    # QuickBooks OAuth token table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qb_tokens (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token TEXT,
            refresh_token TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            realm_id TEXT NOT NULL,
            environment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # QuickBooks invoice audit trail
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qb_invoice_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_row INTEGER,
            doc_number TEXT,
            invoice_id TEXT,
            invoice_url TEXT,
            status TEXT,
            error TEXT,
            payload TEXT,
            response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_PATH}")


def snapshot_exists_today():
    """Check if a snapshot already exists for today"""
    conn = get_connection()
    cursor = conn.cursor()
    
    today = date.today()
    cursor.execute('SELECT COUNT(*) as count FROM daily_metrics WHERE date = ?', (today,))
    result = cursor.fetchone()
    
    conn.close()
    return result['count'] > 0


def save_daily_snapshot(df_inv, df_jobs):
    """
    Save daily snapshot of metrics from dataframes
    Only saves once per day (updates if already exists)
    """
    today = date.today()
    
    # Calculate invoice metrics
    total_invoices = len(df_inv)
    
    # Normalize status for counting
    df_inv['status_norm'] = df_inv['status'].str.lower().str.strip()
    status_counts = df_inv['status_norm'].value_counts().to_dict()
    
    paid_invoices = status_counts.get('paid', 0)
    submitted_invoices = status_counts.get('submitted', 0)
    pending_invoices = status_counts.get('pending', 0)
    other_invoices = total_invoices - (paid_invoices + submitted_invoices + pending_invoices)
    
    # Financial metrics
    df_inv['owed2acd_num'] = pd.to_numeric(df_inv['owed2acd'], errors='coerce')
    df_inv['owed2workers_num'] = pd.to_numeric(df_inv['owed2workers'], errors='coerce')
    
    total_owed_to_acd = df_inv['owed2acd_num'].sum()
    total_owed_to_workers = df_inv['owed2workers_num'].sum()
    avg_owed_to_acd = df_inv['owed2acd_num'].mean()
    avg_owed_to_workers = df_inv['owed2workers_num'].mean()
    
    # Job metrics
    total_jobs = len(df_jobs)
    
    # ACD invoice status
    df_jobs['acd_status_norm'] = df_jobs['ACD_inv_status'].str.lower().str.strip()
    acd_status_counts = df_jobs['acd_status_norm'].value_counts().to_dict()
    
    acd_paid_jobs = acd_status_counts.get('paid', 0)
    acd_submitted_jobs = acd_status_counts.get('submitted', 0)
    acd_pending_jobs = acd_status_counts.get('pending', 0)
    
    # Worker invoice status
    df_jobs['wk_status_norm'] = df_jobs['Wk_inv_status'].str.lower().str.strip()
    wk_status_counts = df_jobs['wk_status_norm'].value_counts().to_dict()
    
    worker_paid_jobs = wk_status_counts.get('paid', 0)
    worker_submitted_jobs = wk_status_counts.get('submitted', 0)
    worker_pending_jobs = wk_status_counts.get('pending', 0)
    
    # Insert or update record
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO daily_metrics (
            date,
            total_invoices, paid_invoices, submitted_invoices, pending_invoices, other_invoices,
            total_owed_to_acd, total_owed_to_workers, avg_owed_to_acd, avg_owed_to_workers,
            total_jobs, acd_paid_jobs, acd_submitted_jobs, acd_pending_jobs,
            worker_paid_jobs, worker_submitted_jobs, worker_pending_jobs,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (
        today,
        total_invoices, paid_invoices, submitted_invoices, pending_invoices, other_invoices,
        total_owed_to_acd, total_owed_to_workers, avg_owed_to_acd, avg_owed_to_workers,
        total_jobs, acd_paid_jobs, acd_submitted_jobs, acd_pending_jobs,
        worker_paid_jobs, worker_submitted_jobs, worker_pending_jobs
    ))
    
    conn.commit()
    conn.close()
    
    print(f"Daily snapshot saved for {today}")
    return True


def get_historical_data(days=30):
    """
    Get historical metrics for the last N days
    Returns pandas DataFrame
    """
    conn = get_connection()
    
    query = '''
        SELECT * FROM daily_metrics
        ORDER BY date DESC
        LIMIT ?
    '''
    
    df = pd.read_sql_query(query, conn, params=(days,))
    conn.close()
    
    # Convert date column to datetime
    df['date'] = pd.to_datetime(df['date'])
    
    return df.sort_values('date')  # Sort ascending for charts


def get_date_range_data(start_date, end_date):
    """Get metrics for a specific date range"""
    conn = get_connection()
    
    query = '''
        SELECT * FROM daily_metrics
        WHERE date BETWEEN ? AND ?
        ORDER BY date ASC
    '''
    
    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()
    
    df['date'] = pd.to_datetime(df['date'])
    return df


def get_summary_stats():
    """Get summary statistics across all historical data"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as total_days,
            MIN(date) as first_date,
            MAX(date) as last_date,
            AVG(total_invoices) as avg_daily_invoices,
            AVG(total_jobs) as avg_daily_jobs,
            AVG(total_owed_to_acd) as avg_daily_owed_acd,
            AVG(total_owed_to_workers) as avg_daily_owed_workers
        FROM daily_metrics
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    return dict(result) if result else {}


def delete_old_data(days_to_keep=365):
    """Delete data older than specified days (for maintenance)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM daily_metrics
        WHERE date < date('now', '-' || ? || ' days')
    ''', (days_to_keep,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"Deleted {deleted} old records (keeping last {days_to_keep} days)")
    return deleted


# ===========================
# QUICKBOOKS TOKEN & AUDIT HELPERS
# ===========================

def save_qb_tokens(access_token, refresh_token, expires_at, realm_id, environment):
    """Persist the latest QuickBooks OAuth tokens."""
    if expires_at and isinstance(expires_at, datetime):
        expires_value = expires_at.isoformat()
    else:
        expires_value = expires_at

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO qb_tokens (id, access_token, refresh_token, expires_at, realm_id, environment, created_at, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at,
            realm_id = excluded.realm_id,
            environment = excluded.environment,
            updated_at = CURRENT_TIMESTAMP
    ''', (access_token, refresh_token, expires_value, realm_id, environment))
    conn.commit()
    conn.close()


def get_qb_tokens():
    """Fetch the cached QuickBooks OAuth tokens."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT access_token, refresh_token, expires_at, realm_id, environment FROM qb_tokens WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'access_token': row['access_token'],
        'refresh_token': row['refresh_token'],
        'expires_at': row['expires_at'],
        'realm_id': row['realm_id'],
        'environment': row['environment']
    }


def _truncate_for_storage(payload, limit=4000):
    if payload is None:
        return None
    serialized = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    if len(serialized) <= limit:
        return serialized
    return serialized[:limit] + '…'


def log_qb_invoice_sync(sheet_row, doc_number, invoice_id, invoice_url, status, payload=None, response=None, error=None):
    """Record each sync attempt for debugging and audits."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO qb_invoice_audit (
            sheet_row, doc_number, invoice_id, invoice_url, status, error, payload, response
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        sheet_row,
        doc_number,
        invoice_id,
        invoice_url,
        status,
        error,
        _truncate_for_storage(payload),
        _truncate_for_storage(response)
    ))
    conn.commit()
    conn.close()


if __name__ == '__main__':
    # Initialize database if running directly
    init_database()
    print("Database module ready!")
    
    # Show summary if data exists
    stats = get_summary_stats()
    if stats.get('total_days', 0) > 0:
        print(f"\nCurrent database stats:")
        print(f"  Days tracked: {stats['total_days']}")
        print(f"  Date range: {stats['first_date']} to {stats['last_date']}")
        print(f"  Avg daily invoices: {stats['avg_daily_invoices']:.1f}")
        print(f"  Avg daily jobs: {stats['avg_daily_jobs']:.1f}")


# ===========================
# USER AUTHENTICATION FUNCTIONS
# ===========================

def create_user(username, email, password, is_admin=False):
    """
    Create a new user account
    Returns: (success: bool, message: str, user_id: int or None)
    """
    # Validate inputs
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters", None
    
    if not email or '@' not in email:
        return False, "Invalid email address", None
    
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters", None
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Hash the password
        password_hash = generate_password_hash(password)
        
        # Insert user
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, is_admin)
            VALUES (?, ?, ?, ?)
        ''', (username.lower(), email.lower(), password_hash, is_admin))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return True, f"User '{username}' created successfully", user_id
        
    except sqlite3.IntegrityError as e:
        if 'username' in str(e):
            return False, "Username already exists", None
        elif 'email' in str(e):
            return False, "Email already exists", None
        else:
            return False, f"Database error: {str(e)}", None
    except Exception as e:
        return False, f"Error creating user: {str(e)}", None


def authenticate_user(username, password):
    """
    Authenticate user with username/password
    Returns: (success: bool, message: str, user_dict: dict or None)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, password_hash, is_admin, is_active, created_at, last_login
            FROM users
            WHERE username = ? OR email = ?
        ''', (username.lower(), username.lower()))
        
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return False, "Invalid username or password", None
        
        if not user['is_active']:
            conn.close()
            return False, "Account is disabled. Contact administrator.", None
        
        # Check password
        if not check_password_hash(user['password_hash'], password):
            conn.close()
            return False, "Invalid username or password", None
        
        # Update last login
        cursor.execute('''
            UPDATE users SET last_login = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (user['id'],))
        conn.commit()
        
        # Convert to dict
        user_dict = {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'is_admin': bool(user['is_admin']),
            'created_at': user['created_at'],
            'last_login': user['last_login']
        }
        
        conn.close()
        return True, "Login successful", user_dict
        
    except Exception as e:
        return False, f"Error during authentication: {str(e)}", None


def create_session(user_id, hours=24):
    """
    Create a session token for logged-in user
    Returns: session_id (str) or None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Generate secure random session ID
        session_id = secrets.token_urlsafe(32)
        
        # Calculate expiration
        from datetime import timedelta
        expires_at = datetime.now() + timedelta(hours=hours)
        
        cursor.execute('''
            INSERT INTO user_sessions (session_id, user_id, expires_at)
            VALUES (?, ?, ?)
        ''', (session_id, user_id, expires_at))
        
        conn.commit()
        conn.close()
        
        return session_id
        
    except Exception as e:
        print(f"Error creating session: {e}")
        return None


def validate_session(session_id):
    """
    Validate session token and return user info if valid
    Returns: (valid: bool, user_dict: dict or None)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT u.id, u.username, u.email, u.is_admin, u.is_active, s.expires_at
            FROM user_sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_id = ?
        ''', (session_id,))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False, None
        
        # Check if expired
        expires_at = datetime.fromisoformat(result['expires_at'])
        if datetime.now() > expires_at:
            # Clean up expired session
            cursor.execute('DELETE FROM user_sessions WHERE session_id = ?', (session_id,))
            conn.commit()
            conn.close()
            return False, None
        
        # Check if user is active
        if not result['is_active']:
            conn.close()
            return False, None
        
        user_dict = {
            'id': result['id'],
            'username': result['username'],
            'email': result['email'],
            'is_admin': bool(result['is_admin'])
        }
        
        conn.close()
        return True, user_dict
        
    except Exception as e:
        print(f"Error validating session: {e}")
        return False, None


def delete_session(session_id):
    """Delete a session (logout)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error deleting session: {e}")
        return False


def change_password(user_id, old_password, new_password):
    """
    Change user password
    Returns: (success: bool, message: str)
    """
    if len(new_password) < 6:
        return False, "New password must be at least 6 characters"
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get current password hash
        cursor.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return False, "User not found"
        
        # Verify old password
        if not check_password_hash(user['password_hash'], old_password):
            conn.close()
            return False, "Current password is incorrect"
        
        # Update password
        new_hash = generate_password_hash(new_password)
        cursor.execute('''
            UPDATE users SET password_hash = ?
            WHERE id = ?
        ''', (new_hash, user_id))
        
        conn.commit()
        conn.close()
        
        return True, "Password changed successfully"
        
    except Exception as e:
        return False, f"Error changing password: {str(e)}"


def get_user_by_id(user_id):
    """Get user information by ID"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, is_admin, is_active, created_at, last_login
            FROM users
            WHERE id = ?
        ''', (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'is_admin': bool(user['is_admin']),
                'is_active': bool(user['is_active']),
                'created_at': user['created_at'],
                'last_login': user['last_login']
            }
        return None
        
    except Exception as e:
        print(f"Error getting user: {e}")
        return None


def list_all_users():
    """List all users (admin function)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, is_admin, is_active, created_at, last_login
            FROM users
            ORDER BY created_at DESC
        ''')
        
        users = cursor.fetchall()
        conn.close()
        
        return [{
            'id': u['id'],
            'username': u['username'],
            'email': u['email'],
            'is_admin': bool(u['is_admin']),
            'is_active': bool(u['is_active']),
            'created_at': u['created_at'],
            'last_login': u['last_login']
        } for u in users]
        
    except Exception as e:
        print(f"Error listing users: {e}")
        return []


def toggle_user_status(user_id, is_active):
    """Enable or disable a user account (admin function)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET is_active = ?
            WHERE id = ?
        ''', (is_active, user_id))
        
        conn.commit()
        conn.close()
        
        status = "enabled" if is_active else "disabled"
        return True, f"User {status} successfully"
        
    except Exception as e:
        return False, f"Error updating user status: {str(e)}"


def admin_reset_password(user_id, new_password):
    """
    Admin function to reset user password
    Returns: (success: bool, message: str)
    """
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters"
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        new_hash = generate_password_hash(new_password)
        cursor.execute('''
            UPDATE users SET password_hash = ?
            WHERE id = ?
        ''', (new_hash, user_id))
        
        conn.commit()
        conn.close()
        
        return True, "Password reset successfully"
        
    except Exception as e:
        return False, f"Error resetting password: {str(e)}"


def cleanup_expired_sessions():
    """Remove expired sessions from database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM user_sessions
            WHERE expires_at < CURRENT_TIMESTAMP
        ''')
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
        
    except Exception as e:
        print(f"Error cleaning up sessions: {e}")
        return 0
