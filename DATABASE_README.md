# Finance Tracker Database Documentation

## Overview
The finance tracker now includes SQLite database functionality to capture and persist daily metrics snapshots. This enables historical trend analysis and time-series visualization of invoice and job data.

## Features

### Automatic Daily Snapshots
- **When**: Captures data once per day automatically while the dashboard is running
- **What**: Records invoice counts, job counts, financial metrics, and status breakdowns
- **Where**: Stored in `finance_tracker.db` in the same directory as `dash_app.py`

### Historical Trends Tab
A new dashboard tab displays:
- 📊 Invoice status trends over time (Paid, Pending, Submitted)
- 💼 Job status trends (Total jobs, ACD paid, Worker paid)
- 💰 Financial metrics (Owed to ACD, Owed to Workers)
- 📈 Summary statistics across all tracked days

### Time Range Selection
View historical data for:
- Last 7 days
- Last 14 days
- Last 30 days (default)
- Last 60 days
- Last 90 days
- All time

## Database Schema

### Table: `daily_metrics`
```sql
CREATE TABLE daily_metrics (
    date DATE PRIMARY KEY,
    
    -- Invoice metrics from inv_tbl
    total_invoices INTEGER,
    paid_invoices INTEGER,
    submitted_invoices INTEGER,
    pending_invoices INTEGER,
    other_invoices INTEGER,
    
    -- Financial metrics
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
);
```

## Files

### `finance_db.py`
Core database module with functions:
- `init_database()` - Initialize schema
- `save_daily_snapshot(df_inv, df_jobs)` - Capture daily metrics
- `get_historical_data(days)` - Retrieve time-series data
- `get_summary_stats()` - Calculate aggregate statistics
- `snapshot_exists_today()` - Check if today's snapshot exists
- `delete_old_data(days_to_keep)` - Cleanup old records

### `dash_app.py` Integration
- Background thread captures daily snapshot automatically
- Runs every hour to check if new snapshot needed
- Only captures once per day (idempotent)

## Usage

### Running the Dashboard
Simply start the dashboard as normal:
```bash
python dash_app.py
```

The database will:
1. Initialize automatically on first run
2. Capture first snapshot when data loads
3. Continue capturing daily snapshots while running
4. Persist data even when dashboard is shut down

### Manual Database Operations

#### Initialize Database
```python
import finance_db
finance_db.init_database()
```

#### View Current Stats
```python
stats = finance_db.get_summary_stats()
print(f"Days tracked: {stats['total_days']}")
```

#### Get Historical Data
```python
df = finance_db.get_historical_data(days=30)
print(df.head())
```

#### Manual Snapshot
```python
from dash_app import df_google_sheet, df_google_sheet2
finance_db.save_daily_snapshot(df_google_sheet2, df_google_sheet)
```

#### Cleanup Old Data
```python
# Keep only last year of data
finance_db.delete_old_data(days_to_keep=365)
```

## Data Persistence

### Backup
The database is a single file that can be easily backed up:
```bash
# Manual backup
cp finance_tracker.db finance_tracker_backup_$(date +%Y%m%d).db

# Copy to Google Drive (automatic if in sync folder)
```

### Restore
```bash
# Restore from backup
cp finance_tracker_backup_20250111.db finance_tracker.db
```

### Export to CSV
```python
import sqlite3
import pandas as pd

conn = sqlite3.connect('finance_tracker.db')
df = pd.read_sql_query('SELECT * FROM daily_metrics', conn)
df.to_csv('historical_metrics.csv', index=False)
conn.close()
```

## Best Practices

### Running Schedule
For consistent daily snapshots:
- Run dashboard daily (or keep running continuously)
- Data captures at first run each day
- Background thread checks hourly for new day

### Data Retention
By default, all data is kept indefinitely. To manage size:
```python
# Delete data older than 1 year
finance_db.delete_old_data(days_to_keep=365)
```

### Monitoring
Check database status:
```bash
# View database info
python finance_db.py

# Check file size
ls -lh finance_tracker.db
```

## Troubleshooting

### No Historical Data Showing
- **Cause**: Dashboard hasn't run for a full day yet
- **Solution**: Wait until next day, or manually capture snapshot

### Database Locked Error
- **Cause**: Multiple processes accessing database
- **Solution**: Close other connections, restart dashboard

### Missing Data Points
- **Cause**: Dashboard wasn't running on those days
- **Solution**: Run dashboard continuously or on daily schedule

### Reset Database
```bash
# Delete database file to start fresh
rm finance_tracker.db

# Restart dashboard to recreate
python dash_app.py
```

## Future Enhancements

Potential additions:
- Email/Slack notifications for metric thresholds
- Automated weekly/monthly reports
- Trend prediction using historical data
- Export to Excel with charts
- Integration with scheduling tools (cron, Task Scheduler)
- Alert system for anomaly detection

## Finance State Snapshot Database

### Database Type and Connection
The finance tracker uses **SQLite** - a serverless, file-based database that requires no configuration or connection strings.

**Database Location:**
```
finance_tracker/finance_tracker.db
```

**Connection Method:**
Unlike server-based databases (PostgreSQL, MySQL), SQLite doesn't need a connection string. It's accessed directly via file path:

```python
import sqlite3
from pathlib import Path

# Simple file path - no connection string needed
DB_PATH = Path(__file__).parent / 'finance_tracker.db'

# Open database
conn = sqlite3.connect(DB_PATH)
```

**Benefits of SQLite:**
- No server setup required
- No authentication needed
- Single file contains entire database
- Easy to backup (just copy the .db file)
- Perfect for local dashboards and small-to-medium datasets

### Snapshot Structure

Each daily snapshot captures a comprehensive view of the financial state:

**Primary Key:**
- `date` - Date of snapshot (YYYY-MM-DD format)
- Only one snapshot per day (INSERT OR REPLACE ensures uniqueness)

**Invoice Metrics** (from `inv_tbl` Google Sheet):
- `total_invoices` - Total count of all invoices
- `paid_invoices` - Invoices with status='paid'
- `submitted_invoices` - Invoices with status='submitted'
- `pending_invoices` - Invoices with status='pending'
- `other_invoices` - All other invoice statuses

**Financial Metrics** (calculated from `inv_tbl`):
- `total_owed_to_acd` - Sum of all `owed2acd` amounts
- `total_owed_to_workers` - Sum of all `owed2workers` amounts
- `avg_owed_to_acd` - Average owed per invoice to ACD
- `avg_owed_to_workers` - Average owed per invoice to workers

**Job Metrics** (from `jobs_tbl` Google Sheet):
- `total_jobs` - Total count of all jobs
- `acd_paid_jobs` - Jobs with `ACD_inv_status='paid'`
- `acd_submitted_jobs` - Jobs with `ACD_inv_status='submitted'`
- `acd_pending_jobs` - Jobs with `ACD_inv_status='pending'`
- `worker_paid_jobs` - Jobs with `Wk_inv_status='paid'`
- `worker_submitted_jobs` - Jobs with `Wk_inv_status='submitted'`
- `worker_pending_jobs` - Jobs with `Wk_inv_status='pending'`

**Metadata:**
- `created_at` - Timestamp when record first created
- `updated_at` - Timestamp of last update

### How Snapshots Are Captured

**Background Worker Thread:**
Located in [dash_app.py](dash_app.py#L132-L156), a daemon thread runs continuously:

```python
def daily_snapshot_worker():
    """Background worker to capture daily snapshot once per day"""
    last_snapshot_date = None
    
    while True:
        try:
            today = datetime.now().date()
            
            # Check if we need to take a snapshot (once per day)
            if last_snapshot_date != today:
                # Check if both dataframes loaded successfully
                if not df_google_sheet2.empty and 'Error' not in df_google_sheet2.columns:
                    if not df_google_sheet.empty and 'Error' not in df_google_sheet.columns:
                        # Take snapshot
                        finance_db.save_daily_snapshot(df_google_sheet2, df_google_sheet)
                        last_snapshot_date = today
            
            # Check again in 1 hour
            time.sleep(3600)
```

**Snapshot Process:**
1. Thread checks every hour if it's a new day
2. Validates Google Sheets data is loaded successfully
3. Calls `save_daily_snapshot()` which:
   - Normalizes status values (lowercase, stripped)
   - Counts invoices by status using `.value_counts()`
   - Converts financial columns to numeric (handles errors)
   - Aggregates job metrics from both tables
   - Executes `INSERT OR REPLACE` SQL (overwrites if exists)

**Idempotency:**
- Only one snapshot per day (date is PRIMARY KEY)
- If app runs multiple times per day, data is updated not duplicated
- Safe to restart dashboard without creating duplicate entries

### Accessing the Database

**From Command Line:**
```bash
# View database info
sqlite3 finance_tracker.db ".schema"

# Query recent snapshots
sqlite3 finance_tracker.db "SELECT date, total_invoices, total_jobs FROM daily_metrics ORDER BY date DESC LIMIT 5;"

# Export to CSV
sqlite3 -header -csv finance_tracker.db "SELECT * FROM daily_metrics;" > snapshots.csv
```

**From Python:**
```python
import sqlite3
import pandas as pd

# Connect
conn = sqlite3.connect('finance_tracker.db')

# Query as DataFrame
df = pd.read_sql_query("""
    SELECT date, total_invoices, total_owed_to_acd 
    FROM daily_metrics 
    WHERE date >= date('now', '-30 days')
    ORDER BY date
""", conn)

# Close
conn.close()
```

**Current Database State:**
As of December 11, 2025:
- **Size**: 52KB
- **Snapshots**: 10 days of data
- **Latest Entry**: 483 invoices, $253,771 owed to ACD, $309,927 owed to workers

### No Connection String Required

Unlike traditional databases, SQLite requires no configuration:

**PostgreSQL Example (NOT needed for SQLite):**
```python
# This is what you DON'T need for SQLite
connection_string = "postgresql://user:password@localhost:5432/database"
```

**SQLite Simplicity:**
```python
# This is all you need
db_path = 'finance_tracker.db'
conn = sqlite3.connect(db_path)
```

**Why This Works:**
- SQLite is embedded in Python (no server process)
- Database is a local file with .db extension
- No network configuration needed
- No user authentication required
- Perfect for single-user applications and dashboards

## Technical Notes

### Thread Safety
- Background thread runs as daemon
- SQLite handles concurrent reads/writes
- Single write per day minimizes lock contention

### Performance
- Database size: ~1KB per day (~365KB per year)
- Query performance: Sub-millisecond for typical queries
- Memory footprint: Minimal (connection pooling not needed)

### Dependencies
- Python 3.7+
- pandas
- sqlite3 (built-in)
- No additional packages required

## Support

For issues or questions:
1. Check this README
2. Review `finance_db.py` docstrings
3. Test with `python finance_db.py`
4. Check database file exists and has recent timestamp
