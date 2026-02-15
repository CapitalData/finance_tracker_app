# ---------------------------------------------------------------------------
# Demo Data Banner
# ---------------------------------------------------------------------------
def render_demo_data_banner():
    if sandbox_mode_enabled() or not GOOGLE_SHEET_URL:
        return html.Div([
            html.Strong("Demo Data Loaded: ", style={"color": "#d32f2f"}),
            html.Span("The app is currently displaying demo transactions from a local CSV file. "),
            html.A("Connect to real data by following these instructions.", href="https://github.com/your-org/your-repo/wiki/Finance-Tracker-Setup", target="_blank", style={"color": "#1976d2", "textDecoration": "underline"}),
        ], style={
            "backgroundColor": "#fff8e1",
            "border": "1px solid #ffecb3",
            "padding": "10px",
            "borderRadius": "6px",
            "marginBottom": "12px",
            "color": "#5d4037",
        })
    return None
# ---------------------------------------------------------------------------
# Demo CSV loader for sandbox or local mode
# ---------------------------------------------------------------------------
def load_demo_transactions_csv(csv_path=None):
    """Load demo transactions from a local CSV file for demo/sandbox mode."""
    if csv_path is None:
        # Default path relative to this file
        csv_path = os.path.join(os.path.dirname(__file__), '../control_panel_dist/demo_transactions.csv')
    try:
        df = pd.read_csv(csv_path)
        return df
    except Exception as e:
        print(f"Failed to load demo CSV: {e}")
        return pd.DataFrame()
import base64
import mimetypes
import os
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

import finance_db

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    def load_dotenv(*_args, **_kwargs):
        return None

load_dotenv()

# ---------------------------------------------------------------------------
# Google + QuickBooks related configuration
# ---------------------------------------------------------------------------
SERVICE_ACCOUNT_FILE = (
    os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    or "service-account.json"
)
INCOMING_FOLDER_ID = os.getenv(
    "INVOICE_INCOMING_FOLDER_ID", "1ZWgOIAsO7l3DeOB3BodM7ofs0g4wM6yU"
)
PROCESSED_ROOT_FOLDER_ID = os.getenv(
    "INVOICE_PROCESSED_ROOT_FOLDER_ID", "1AF8Q-HpDWco8859f7trb8juz-2hB9tVY"
)
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
INV_TBL_NAME = os.getenv("INV_TBL_NAME", "inv_tbl")
AUTO_REFRESH_ENABLED = os.getenv("INVOICE_AUTO_REFRESH", "true").lower() in {"true", "1", "yes", "on"}
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
STATUS_ORDER = ["submitted", "accepted", "paid"]
STATUS_LABELS = {
    "submitted": "Submitted",
    "accepted": "Accepted",
    "paid": "Paid",
}
STATUS_COLORS = {
    "submitted": "#FF9800",
    "accepted": "#2196F3",
    "paid": "#4CAF50",
}
SANDBOX_MODE_CONFIG = (os.getenv("INVOICE_SANDBOX_MODE") or "auto").strip().lower() or "auto"
TRACKED_FOLDERS_DB = os.getenv("TRACKED_FOLDERS_DB", "invoice_tracking.db")

_cached_credentials = None
_drive_service = None
_gspread_client = None
_tracked_folders = set()  # Folders that contain tracked files from incoming workflow

_sandbox_records: Dict[str, Dict[str, str]] = {}
_sandbox_processed_folders: List[Dict[str, str]] = [
    {"id": "sandbox-processing", "name": "Accepted / In Review"},
    {"id": "sandbox-archive", "name": "Paid Archive"},
]

# ---------------------------------------------------------------------------
# Sample analytics tab data
# ---------------------------------------------------------------------------
GAPMINDER_DF = pd.read_csv(
    "https://raw.githubusercontent.com/plotly/datasets/master/gapminder_unfiltered.csv"
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def get_db_connection():
    """Get a thread-safe database connection."""
    conn = sqlite3.connect(TRACKED_FOLDERS_DB, check_same_thread=False)
    return conn


def init_tracking_database() -> None:
    """Initialize SQLite database for tracking folders with invoice files."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_folders (
            folder_id TEXT PRIMARY KEY,
            folder_name TEXT,
            first_tracked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def load_tracked_folders() -> None:
    """Load tracked folders from database into memory."""
    global _tracked_folders
    init_tracking_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT folder_id FROM tracked_folders")
    _tracked_folders = {row[0] for row in cursor.fetchall()}
    conn.close()


def add_tracked_folder(folder_id: str, folder_name: str = "") -> None:
    """Add a folder to the tracked folders list and persist to database."""
    global _tracked_folders
    _tracked_folders.add(folder_id)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO tracked_folders (folder_id, folder_name, last_updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (folder_id, folder_name))
        conn.commit()
        conn.close()
    except Exception:
        # If database write fails, at least keep in memory for this session
        pass


def credentials_ready() -> bool:
    return Path(SERVICE_ACCOUNT_FILE).is_file()


def sandbox_mode_enabled() -> bool:
    if SANDBOX_MODE_CONFIG == "auto":
        return not credentials_ready()
    return SANDBOX_MODE_CONFIG in {"1", "true", "yes", "on"}


def get_credentials():
    global _cached_credentials
    if _cached_credentials is None:
        if not credentials_ready():
            raise FileNotFoundError(
                f"Google service account file not found at '{SERVICE_ACCOUNT_FILE}'."
            )
        _cached_credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
    return _cached_credentials


def get_drive_service():
    global _drive_service
    if _drive_service is None:
        _drive_service = build("drive", "v3", credentials=get_credentials())
    return _drive_service


def get_gspread_client():
    global _gspread_client
    if _gspread_client is None:
        _gspread_client = gspread.authorize(get_credentials())
    return _gspread_client


def _sandbox_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _sandbox_ensure_folder(folder_id: str, label: Optional[str] = None) -> None:
    if any(folder["id"] == folder_id for folder in _sandbox_processed_folders):
        return
    _sandbox_processed_folders.append({"id": folder_id, "name": label or folder_id})


def _sandbox_create_invoice_record(filename: str) -> Dict[str, str]:
    file_id = f"sandbox-{uuid.uuid4().hex}"
    timestamp = _sandbox_timestamp()
    record = {
        "id": file_id,
        "name": filename,
        "link": "#",
        "status": "submitted",
        "parent": "sandbox-incoming",
        "created": timestamp,
        "updated": timestamp,
    }
    _sandbox_records[file_id] = record
    return {
        "id": file_id,
        "name": filename,
        "webViewLink": record["link"],
        "appProperties": {"status": "submitted"},
    }


def _sandbox_fetch_invoice_data() -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    # Filter out archived records
    records = [r for r in _sandbox_records.values() if not r.get("archived", False)]
    records.sort(key=lambda r: r.get("created") or "", reverse=True)
    folder_options = [
        {"label": folder["name"], "value": folder["id"]}
        for folder in _sandbox_processed_folders
    ]
    return records, folder_options


def _sandbox_move_invoice(file_id: str, target_folder_id: str) -> Dict[str, str]:
    if file_id not in _sandbox_records:
        raise ValueError("Invoice not found in sandbox store.")
    _sandbox_ensure_folder(target_folder_id)
    record = _sandbox_records[file_id]
    record["status"] = "accepted"
    record["parent"] = target_folder_id
    record["updated"] = _sandbox_timestamp()
    return {
        "id": file_id,
        "name": record["name"],
        "webViewLink": record["link"],
        "appProperties": {"status": "accepted"},
    }


def _sandbox_mark_invoice_paid(file_id: str) -> Dict[str, str]:
    if file_id not in _sandbox_records:
        raise ValueError("Invoice not found in sandbox store.")
    record = _sandbox_records[file_id]
    record["status"] = "paid"
    record["updated"] = _sandbox_timestamp()
    return {
        "id": file_id,
        "name": record["name"],
        "webViewLink": record["link"],
        "appProperties": {"status": "paid"},
    }


def guess_mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def upload_invoice_to_drive(filename: str, content: bytes) -> Dict[str, str]:
    if sandbox_mode_enabled():
        return _sandbox_create_invoice_record(filename)
    service = get_drive_service()
    file_metadata = {
        "name": filename,
        "parents": [INCOMING_FOLDER_ID],
        "appProperties": {"status": "submitted", "tracked": "true"},
    }
    media = MediaInMemoryUpload(content, mimetype=guess_mime_type(filename), resumable=False)
    return (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink, appProperties",
            supportsAllDrives=True,
        )
        .execute()
    )


def list_processed_subfolders(service) -> List[Dict[str, str]]:
    response = (
        service.files()
        .list(
            q=(
                f"'{PROCESSED_ROOT_FOLDER_ID}' in parents and "
                "mimeType='application/vnd.google-apps.folder' and trashed=false"
            ),
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=200,
        )
        .execute()
    )
    folders = response.get("files", [])
    return sorted(folders, key=lambda item: item.get("name", "").casefold())


def _list_files_in_parent(service, parent_id: str) -> List[Dict[str, str]]:
    response = (
        service.files()
        .list(
            q=f"'{parent_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'",
            fields=(
                "files(id, name, webViewLink, parents, appProperties, createdTime, "
                "modifiedTime)"
            ),
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=500,
        )
        .execute()
    )
    return response.get("files", [])


def fetch_invoice_dashboard_data() -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, str]]:
    if sandbox_mode_enabled():
        records, folder_options = _sandbox_fetch_invoice_data()
        folder_map = {"sandbox-incoming": "Incoming"}
        for folder in _sandbox_processed_folders:
            folder_map[folder["id"]] = folder["name"]
        return records, folder_options, folder_map
    service = get_drive_service()
    processed_folders = list_processed_subfolders(service)
    records: List[Dict[str, str]] = []

    def append_records(raw_items: List[Dict[str, str]], fallback_status: str, from_incoming: bool = False) -> None:
        for item in raw_items:
            app_props = item.get("appProperties") or {}
            # Skip archived files
            if app_props.get("archived") == "true":
                continue
            # Only check tracked status for files in processed folders
            # Files in incoming folder are automatically tracked
            if not from_incoming and app_props.get("tracked") != "true":
                continue
            status = app_props.get("status") or fallback_status
            records.append(
                {
                    "id": item["id"],
                    "name": item.get("name", "Unnamed"),
                    "link": item.get("webViewLink"),
                    "status": status,
                    "parent": item.get("parents", [""])[0],
                    "created": item.get("createdTime"),
                    "updated": item.get("modifiedTime"),
                }
            )

    # Load ALL files from incoming folder (they're automatically tracked)
    incoming_files = _list_files_in_parent(service, INCOMING_FOLDER_ID)
    append_records(incoming_files, "submitted", from_incoming=True)
    
    # Mark any new files in incoming as tracked so they persist when moved
    for item in incoming_files:
        app_props = item.get("appProperties") or {}
        if app_props.get("tracked") != "true":
            try:
                service.files().update(
                    fileId=item["id"],
                    body={"appProperties": {"status": app_props.get("status", "submitted"), "tracked": "true"}},
                    fields="id",
                    supportsAllDrives=True,
                ).execute()
            except Exception:
                pass  # Continue if marking fails
    
    # Only load from processed folders that contain tracked files (much faster)
    # This avoids scanning every processed folder on every refresh
    for folder_id in _tracked_folders:
        # Verify folder still exists in processed list
        if any(f["id"] == folder_id for f in processed_folders):
            processed_files = _list_files_in_parent(service, folder_id)
            append_records(processed_files, "accepted", from_incoming=False)

    records.sort(key=lambda r: (r.get("created") or ""), reverse=True)
    dropdown_options = [
        {"label": folder["name"], "value": folder["id"]} for folder in processed_folders
    ]
    # Create a map of folder IDs to names for displaying on cards
    folder_map = {folder["id"]: folder["name"] for folder in processed_folders}
    folder_map[INCOMING_FOLDER_ID] = "Incoming"
    return records, dropdown_options


def move_invoice_to_processed(file_id: str, target_folder_id: str) -> Dict[str, str]:
    if sandbox_mode_enabled():
        return _sandbox_move_invoice(file_id, target_folder_id)
    service = get_drive_service()
    current_metadata = (
        service.files()
        .get(fileId=file_id, fields="parents", supportsAllDrives=True)
        .execute()
    )
    previous_parents = ",".join(current_metadata.get("parents", []))
    return (
        service.files()
        .update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=previous_parents,
            body={"appProperties": {"status": "accepted", "tracked": "true"}},
            fields="id, name, webViewLink, appProperties",
            supportsAllDrives=True,
        )
        .execute()
    )


def mark_invoice_paid(file_id: str) -> Dict[str, str]:
    if sandbox_mode_enabled():
        return _sandbox_mark_invoice_paid(file_id)
    service = get_drive_service()
    return (
        service.files()
        .update(
            fileId=file_id,
            body={"appProperties": {"status": "paid"}},
            fields="id, name, webViewLink, appProperties",
            supportsAllDrives=True,
        )
        .execute()
    )


def update_invoice_status(file_id: str, new_status: str) -> Dict[str, str]:
    """Update file status without moving it between folders."""
    if sandbox_mode_enabled():
        if file_id not in _sandbox_records:
            raise ValueError("Invoice not found in sandbox store.")
        record = _sandbox_records[file_id]
        record["status"] = new_status
        record["updated"] = _sandbox_timestamp()
        return {
            "id": file_id,
            "name": record["name"],
            "webViewLink": record["link"],
            "appProperties": {"status": new_status},
        }
    service = get_drive_service()
    return (
        service.files()
        .update(
            fileId=file_id,
            body={"appProperties": {"status": new_status}},
            fields="id, name, webViewLink, appProperties",
            supportsAllDrives=True,
        )
        .execute()
    )


def archive_invoice(file_id: str) -> Dict[str, str]:
    """Mark invoice as archived to stop tracking it without moving to trash."""
    if sandbox_mode_enabled():
        if file_id not in _sandbox_records:
            raise ValueError("Invoice not found in sandbox store.")
        # In sandbox mode, mark as archived instead of removing
        record = _sandbox_records[file_id]
        record["archived"] = True
        record["updated"] = _sandbox_timestamp()
        return {
            "id": file_id,
            "name": record["name"],
            "webViewLink": record["link"],
        }
    service = get_drive_service()
    return (
        service.files()
        .update(
            fileId=file_id,
            body={"appProperties": {"archived": "true"}},
            fields="id, name, webViewLink, appProperties",
            supportsAllDrives=True,
        )
        .execute()
    )


def append_invoice_to_sheet(name: str, link: str, folder_name: str = "", submitted_date: str = "") -> None:
    if sandbox_mode_enabled():
        # Sandbox mode skips Google Sheets writes but keeps the UX responsive.
        return None
    if not GOOGLE_SHEET_URL:
        raise RuntimeError("GOOGLE_SHEET_URL is not configured in the environment.")
    client = get_gspread_client()
    worksheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(INV_TBL_NAME)
    
    # Find the next empty row (by checking column A)
    all_values = worksheet.col_values(1)  # Get all values in column A
    next_row = len(all_values) + 1  # Next row after last non-empty row
    
    # Write entire row at once (much more efficient than cell-by-cell)
    row_data = [name, link, submitted_date, "", "", "", "", "", "", folder_name]
    range_notation = f"A{next_row}:J{next_row}"
    worksheet.update(range_notation, [row_data], value_input_option="USER_ENTERED")



def update_invoice_paid_in_sheet(name: str, paid_date: str, receipt_link: str) -> None:
    """Update existing invoice row with paid date and receipt link."""
    if sandbox_mode_enabled():
        return None
    if not GOOGLE_SHEET_URL:
        raise RuntimeError("GOOGLE_SHEET_URL is not configured in the environment.")
    client = get_gspread_client()
    worksheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(INV_TBL_NAME)
    
    # Find the row with matching invoice name (assuming name is in column A)
    try:
        cell = worksheet.find(name)
        if not cell:
            raise ValueError(f"Invoice '{name}' not found in sheet")
        
        # Get column headers to find the right columns
        headers = worksheet.row_values(1)
        
        # Find Inv_paid_date column
        paid_date_col = None
        if "Inv_paid_date" in headers:
            paid_date_col = headers.index("Inv_paid_date") + 1
        elif "inv_paid_date" in headers:  # Try lowercase
            paid_date_col = headers.index("inv_paid_date") + 1
            
        # Find inv_paid_link column
        paid_link_col = None
        if "inv_paid_link" in headers:
            paid_link_col = headers.index("inv_paid_link") + 1
        elif "Inv_paid_link" in headers:  # Try alternate case
            paid_link_col = headers.index("Inv_paid_link") + 1
        
        # Update cells if columns were found
        if paid_date_col:
            worksheet.update_cell(cell.row, paid_date_col, paid_date)
        else:
            raise ValueError("Column 'Inv_paid_date' not found in sheet headers")
            
        if paid_link_col:
            worksheet.update_cell(cell.row, paid_link_col, receipt_link)
        else:
            raise ValueError("Column 'inv_paid_link' not found in sheet headers")
            
    except Exception as e:
        # Re-raise the exception so we can see what went wrong
        raise RuntimeError(f"Failed to update paid info in sheet: {str(e)}")


def render_status_tracker(current_status: str) -> html.Div:
    current_index = STATUS_ORDER.index(current_status) if current_status in STATUS_ORDER else 0
    steps = []
    for idx, status in enumerate(STATUS_ORDER):
        completed = idx <= current_index
        steps.append(
            html.Div(
                STATUS_LABELS[status],
                style={
                    "padding": "4px 10px",
                    "borderRadius": "12px",
                    "border": f"1px solid {STATUS_COLORS[status]}",
                    "color": "#fff" if completed else STATUS_COLORS[status],
                    "backgroundColor": STATUS_COLORS[status] if completed else "transparent",
                    "fontSize": "12px",
                    "flex": "1",
                    "textAlign": "center",
                    "marginRight": "6px" if idx < len(STATUS_ORDER) - 1 else "0px",
                },
            )
        )
    return html.Div(steps, style={"display": "flex", "marginTop": "4px"})


def build_invoice_card(record: Dict[str, str], folder_options: List[Dict[str, str]], folder_map: Dict[str, str] = None):
    dropdown_disabled = not folder_options or record["status"] != "submitted"
    move_disabled = dropdown_disabled
    paid_disabled = record["status"] != "accepted"
    
    folder_map = folder_map or {}
    current_location = folder_map.get(record.get("parent", ""), "Unknown")

    status_options = [
        {"label": "Submitted", "value": "submitted"},
        {"label": "Accepted", "value": "accepted"},
        {"label": "Paid", "value": "paid"},
    ]

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(record["name"]),
                            html.Div(
                                html.A("Open in Drive", href=record["link"], target="_blank"),
                                style={"fontSize": "12px", "marginTop": "2px"},
                            ),
                            html.Div(
                                [
                                    html.Span("📁 ", style={"fontSize": "11px"}),
                                    html.Span(current_location, style={"fontSize": "11px", "color": "#666", "fontStyle": "italic"}),
                                ],
                                style={"marginTop": "4px", "marginBottom": "4px"},
                            ),
                            render_status_tracker(record["status"]),
                            html.Div(
                                [
                                    html.Span("Current: ", style={"fontSize": "11px", "color": "#666"}),
                                    html.Strong(STATUS_LABELS.get(record["status"], record["status"]), style={"fontSize": "11px"}),
                                ],
                                style={"marginTop": "4px"},
                            ),
                        ],
                        style={"flex": "2"},
                    ),
                    html.Div(
                        [
                            dcc.Dropdown(
                                id={"type": "processed-dropdown", "index": record["id"]},
                                options=folder_options,
                                placeholder="Select processed folder",
                                disabled=dropdown_disabled,
                                style={"marginBottom": "6px"},
                            ),
                            html.Button(
                                "Move & Log",
                                id={"type": "move-button", "index": record["id"]},
                                n_clicks=0,
                                disabled=move_disabled,
                                style={"width": "100%", "marginBottom": "4px"},
                            ),
                            html.Div(
                                [
                                    html.Label("Receipt Link (Required):", style={"fontSize": "11px", "color": "#666", "marginBottom": "2px"}),
                                    dcc.Input(
                                        id={"type": "receipt-link-input", "index": record["id"]},
                                        type="text",
                                        placeholder="Paste Google Drive receipt link",
                                        style={"width": "100%", "marginBottom": "4px", "fontSize": "11px", "padding": "4px"},
                                    ),
                                ],
                                style={"display": "none" if paid_disabled else "block", "marginBottom": "6px"},
                            ),
                            html.Button(
                                "Mark Paid",
                                id={"type": "paid-button", "index": record["id"]},
                                n_clicks=0,
                                disabled=paid_disabled,
                                style={"width": "100%", "marginBottom": "4px"},
                            ),
                            html.Button(
                                "🗑️ Archive",
                                id={"type": "archive-button", "index": record["id"]},
                                n_clicks=0,
                                style={
                                    "width": "100%",
                                    "marginBottom": "6px",
                                    "backgroundColor": "#ef9a9a",
                                    "color": "#333",
                                    "border": "1px solid #e57373",
                                    "cursor": "pointer",
                                    "fontSize": "11px",
                                    "padding": "4px 8px",
                                },
                                title="Stop tracking this invoice (file remains in Drive)",
                            ),
                            html.Hr(style={"margin": "8px 0", "borderColor": "#ddd"}),
                            html.Div("Manual Override:", style={"fontSize": "11px", "color": "#666", "marginBottom": "4px"}),
                            dcc.Dropdown(
                                id={"type": "status-dropdown", "index": record["id"]},
                                options=status_options,
                                value=record["status"],
                                clearable=False,
                                style={"marginBottom": "4px", "fontSize": "12px"},
                            ),
                            html.Button(
                                "Update Status",
                                id={"type": "status-button", "index": record["id"]},
                                n_clicks=0,
                                style={"width": "100%", "fontSize": "11px"},
                            ),
                        ],
                        style={"flex": "1", "marginLeft": "20px"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between"},
            )
        ],
        style={
            "border": "1px solid #ddd",
            "borderRadius": "8px",
            "padding": "12px",
            "marginBottom": "12px",
            "backgroundColor": "#fafafa",
        },
    )


def render_invoice_mode_banner():
    if sandbox_mode_enabled():
        return html.Div(
            "Sandbox mode is active. Uploaded files are stored in-memory so you can test the UI without Google Drive credentials.",
            style={
                "backgroundColor": "#fff8e1",
                "border": "1px solid #ffecb3",
                "padding": "10px",
                "borderRadius": "6px",
                "marginBottom": "12px",
                "color": "#5d4037",
            },
        )
    return None


# ---------------------------------------------------------------------------
# QuickBooks sync monitoring helpers
# ---------------------------------------------------------------------------
def get_qb_sync_stats() -> Dict[str, any]:
    """Get QuickBooks sync statistics from Google Sheet."""
    try:
        if not GOOGLE_SHEET_URL:
            return {"error": "GOOGLE_SHEET_URL not configured"}
        
        gc = get_gspread_client()
        spreadsheet = gc.open_by_url(GOOGLE_SHEET_URL)
        worksheet = spreadsheet.worksheet(INV_TBL_NAME)
        data = worksheet.get_all_records()
        
        if not data:
            return {
                "total_rows": 0,
                "pending": 0,
                "synced": 0,
                "failed": 0,
                "skipped": 0,
                "unprocessed": 0,
            }
        
        df = pd.DataFrame(data)
        
        # Handle missing columns gracefully
        if 'qb_sync_status' not in df.columns:
            return {
                "error": "Sheet missing QB columns",
                "total_rows": len(df),
                "needs_setup": True,
            }
        
        # Normalize status values
        df['qb_sync_status'] = df['qb_sync_status'].astype(str).str.lower().str.strip()
        
        stats = {
            "total_rows": len(df),
            "pending": len(df[df['qb_sync_status'] == 'processing']),
            "synced": len(df[df['qb_sync_status'] == 'synced']),
            "failed": len(df[df['qb_sync_status'] == 'failed']),
            "skipped": len(df[df['qb_sync_status'] == 'skipped']),
            "unprocessed": len(df[(df['qb_sync_status'] == '') | (df['qb_sync_status'] == 'nan')]),
        }
        
        return stats
    except Exception as e:
        return {"error": str(e)}


def get_qb_recent_syncs(limit: int = 20) -> List[Dict[str, any]]:
    """Get recent QuickBooks sync attempts from audit log."""
    try:
        conn = finance_db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                sheet_row,
                doc_number,
                invoice_id,
                invoice_url,
                status,
                error,
                created_at
            FROM qb_invoice_audit
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "sheet_row": row[0],
                "doc_number": row[1] or "N/A",
                "invoice_id": row[2] or "N/A",
                "invoice_url": row[3] or "",
                "status": row[4] or "unknown",
                "error": row[5] or "",
                "created_at": row[6],
            }
            for row in rows
        ]
    except Exception as e:
        return [{"error": str(e)}]


def get_last_sync_time() -> Optional[str]:
    """Get timestamp of most recent successful sync."""
    try:
        conn = finance_db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT created_at
            FROM qb_invoice_audit
            WHERE status = 'synced'
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            return result[0]
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dash layout
# ---------------------------------------------------------------------------

# Automatically load transactions from demo CSV if in sandbox mode or no Google Sheet
if sandbox_mode_enabled() or not GOOGLE_SHEET_URL:
    TRANSACTIONS_DF = load_demo_transactions_csv()
else:
    TRANSACTIONS_DF = None  # Real data will be loaded from Google Sheets as usual

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "Finance Tracker"

invoice_tab_layout = html.Div(
    [
        render_demo_data_banner(),
        html.Div(
            [
                html.H3("Invoice Intake & Status"),
                render_invoice_mode_banner(),
                html.P(
                    "Upload a new invoice by dragging a file into the dropzone or by "
                    "using the browse button. Newly uploaded invoices land in the "
                    "Submitted column."
                ),
                dcc.Upload(
                    id="invoice-upload",
                    children=html.Div([
                        "Drag & Drop or ",
                        html.A("Select Files"),
                    ]),
                    style={
                        "width": "100%",
                        "height": "80px",
                        "lineHeight": "80px",
                        "borderWidth": "1px",
                        "borderStyle": "dashed",
                        "borderRadius": "8px",
                        "textAlign": "center",
                        "marginBottom": "10px",
                    },
                    multiple=False,
                ),
                html.Div(id="invoice-upload-feedback", style={"marginBottom": "20px"}),
                html.Div(id="invoice-action-feedback", style={"marginBottom": "15px"}),
                dcc.Loading(html.Div(id="invoice-list"), type="circle"),
            ]
        )
    ]
)

qb_sync_tab_layout = html.Div(
    [
        html.H3("QuickBooks Sync Monitor"),
        html.P("Track the status of invoice syncs to QuickBooks Online."),
        html.Button(
            "Refresh Stats",
            id="qb-refresh-button",
            n_clicks=0,
            style={
                "marginBottom": "20px",
                "padding": "10px 20px",
                "backgroundColor": "#2196F3",
                "color": "white",
                "border": "none",
                "borderRadius": "4px",
                "cursor": "pointer",
            },
        ),
        dcc.Loading(
            html.Div(id="qb-stats-cards"),
            type="circle",
        ),
        html.Hr(style={"margin": "30px 0"}),
        html.H4("Recent Sync Activity"),
        dcc.Loading(
            html.Div(id="qb-recent-syncs"),
            type="circle",
        ),
        dcc.Interval(
            id="qb-auto-refresh",
            interval=60000,  # Refresh every 60 seconds
            n_intervals=0,
        ),
    ],
    style={"padding": "20px"},
)

app.layout = html.Div(
    [
        html.H1("Finance Tracker"),
        dcc.Tabs(
            id="main-tabs",
            value="tab-invoices",
            children=[
                dcc.Tab(
                    label="Analytics",
                    value="tab-dashboard",
                    children=[
                        html.H3("Gapminder Explorer"),
                        dcc.Dropdown(
                            GAPMINDER_DF.country.unique(),
                            "Canada",
                            id="dropdown-selection",
                        ),
                        dcc.Graph(id="graph-content"),
                    ],
                ),
                dcc.Tab(label="Invoice Manager", value="tab-invoices", children=invoice_tab_layout),
                dcc.Tab(label="QuickBooks Sync", value="tab-qb-sync", children=qb_sync_tab_layout),
            ],
        ),
        dcc.Store(id="invoice-refresh-store", data=str(time.time())),
        dcc.Interval(id="invoice-autorefresh", interval=600_000, n_intervals=0),  # 10 minutes
    ]
)


# ---------------------------------------------------------------------------
# Dash callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("graph-content", "figure"),
    Input("dropdown-selection", "value"),
)
def update_graph(value):
    dff = GAPMINDER_DF[GAPMINDER_DF.country == value]
    return px.line(dff, x="year", y="pop", title=f"Population for {value}")


@callback(
    Output("qb-stats-cards", "children"),
    Input("qb-refresh-button", "n_clicks"),
    Input("qb-auto-refresh", "n_intervals"),
)
def update_qb_stats(n_clicks, n_intervals):
    """Update QuickBooks sync statistics cards."""
    stats = get_qb_sync_stats()
    last_sync = get_last_sync_time()
    
    if "error" in stats:
        if stats.get("needs_setup"):
            return html.Div(
                [
                    html.Div(
                        "⚠️ QuickBooks columns not found in sheet",
                        style={"color": "#d32f2f", "fontWeight": "bold", "marginBottom": "10px"},
                    ),
                    html.P(
                        "The inv_tbl sheet needs these columns added: qb_invoice_id, "
                        "qb_invoice_url, qb_sync_status, qb_synced_at, qb_error"
                    ),
                ],
                style={
                    "padding": "20px",
                    "backgroundColor": "#fff8e1",
                    "border": "1px solid #ffecb3",
                    "borderRadius": "8px",
                },
            )
        return html.Div(
            f"Error loading stats: {stats['error']}",
            style={"color": "#d32f2f", "padding": "20px"},
        )
    
    # Create stat cards
    cards = [
        {
            "label": "Total Rows",
            "value": stats.get("total_rows", 0),
            "color": "#757575",
            "icon": "📊",
        },
        {
            "label": "Synced",
            "value": stats.get("synced", 0),
            "color": "#4CAF50",
            "icon": "✓",
        },
        {
            "label": "Pending",
            "value": stats.get("pending", 0),
            "color": "#FF9800",
            "icon": "⏳",
        },
        {
            "label": "Failed",
            "value": stats.get("failed", 0),
            "color": "#f44336",
            "icon": "✗",
        },
        {
            "label": "Skipped",
            "value": stats.get("skipped", 0),
            "color": "#9E9E9E",
            "icon": "⊘",
        },
        {
            "label": "Unprocessed",
            "value": stats.get("unprocessed", 0),
            "color": "#2196F3",
            "icon": "○",
        },
    ]
    
    card_elements = []
    for card in cards:
        card_elements.append(
            html.Div(
                [
                    html.Div(
                        card["icon"],
                        style={"fontSize": "32px", "marginBottom": "8px"},
                    ),
                    html.Div(
                        str(card["value"]),
                        style={
                            "fontSize": "28px",
                            "fontWeight": "bold",
                            "color": card["color"],
                            "marginBottom": "4px",
                        },
                    ),
                    html.Div(
                        card["label"],
                        style={"fontSize": "14px", "color": "#666"},
                    ),
                ],
                style={
                    "flex": "1",
                    "padding": "20px",
                    "border": "1px solid #e0e0e0",
                    "borderRadius": "8px",
                    "textAlign": "center",
                    "backgroundColor": "#fafafa",
                    "margin": "0 10px",
                    "minWidth": "140px",
                },
            )
        )
    
    # Last sync timestamp
    last_sync_text = "Never" if not last_sync else last_sync
    
    return html.Div(
        [
            html.Div(
                card_elements,
                style={
                    "display": "flex",
                    "flexWrap": "wrap",
                    "gap": "10px",
                    "marginBottom": "20px",
                },
            ),
            html.Div(
                f"Last successful sync: {last_sync_text}",
                style={
                    "padding": "10px",
                    "backgroundColor": "#e3f2fd",
                    "border": "1px solid #90caf9",
                    "borderRadius": "4px",
                    "textAlign": "center",
                    "fontSize": "14px",
                },
            ),
        ]
    )


@callback(
    Output("qb-recent-syncs", "children"),
    Input("qb-refresh-button", "n_clicks"),
    Input("qb-auto-refresh", "n_intervals"),
)
def update_qb_recent_syncs(n_clicks, n_intervals):
    """Update table of recent QuickBooks sync attempts."""
    syncs = get_qb_recent_syncs(limit=20)
    
    if not syncs:
        return html.Div(
            "No sync activity recorded yet.",
            style={"padding": "20px", "textAlign": "center", "color": "#666"},
        )
    
    if "error" in syncs[0]:
        return html.Div(
            f"Error loading sync history: {syncs[0]['error']}",
            style={"color": "#d32f2f", "padding": "20px"},
        )
    
    # Create table rows
    table_header = html.Thead(
        html.Tr(
            [
                html.Th("Time", style={"padding": "8px", "textAlign": "left"}),
                html.Th("Row #", style={"padding": "8px", "textAlign": "left"}),
                html.Th("Doc Number", style={"padding": "8px", "textAlign": "left"}),
                html.Th("QB ID", style={"padding": "8px", "textAlign": "left"}),
                html.Th("Status", style={"padding": "8px", "textAlign": "left"}),
                html.Th("Error", style={"padding": "8px", "textAlign": "left"}),
            ]
        )
    )
    
    table_rows = []
    for sync in syncs:
        status_color = {
            "synced": "#4CAF50",
            "failed": "#f44336",
            "processing": "#FF9800",
            "skipped": "#9E9E9E",
        }.get(sync["status"], "#757575")
        
        invoice_link = (
            html.A(
                sync["invoice_id"],
                href=sync["invoice_url"],
                target="_blank",
                style={"color": "#2196F3"},
            )
            if sync.get("invoice_url") and sync["invoice_id"] != "N/A"
            else sync["invoice_id"]
        )
        
        table_rows.append(
            html.Tr(
                [
                    html.Td(sync["created_at"][:19] if sync.get("created_at") else "N/A", style={"padding": "8px"}),
                    html.Td(sync["sheet_row"], style={"padding": "8px"}),
                    html.Td(sync["doc_number"], style={"padding": "8px"}),
                    html.Td(invoice_link, style={"padding": "8px"}),
                    html.Td(
                        sync["status"],
                        style={
                            "padding": "8px",
                            "color": status_color,
                            "fontWeight": "bold",
                        },
                    ),
                    html.Td(
                        sync["error"][:100] if sync.get("error") else "",
                        style={"padding": "8px", "fontSize": "12px", "color": "#666"},
                    ),
                ],
                style={"borderBottom": "1px solid #e0e0e0"},
            )
        )
    
    table_body = html.Tbody(table_rows)
    
    return html.Div(
        html.Table(
            [table_header, table_body],
            style={
                "width": "100%",
                "borderCollapse": "collapse",
                "backgroundColor": "white",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.12)",
            },
        ),
        style={"overflowX": "auto"},
    )


@callback(
    Output("invoice-upload-feedback", "children"),
    Output("invoice-refresh-store", "data", allow_duplicate=True),
    Input("invoice-upload", "contents"),
    State("invoice-upload", "filename"),
    State("invoice-refresh-store", "data"),
    prevent_initial_call=True,
)
def handle_invoice_upload(contents, filename, refresh_token):
    
    if contents is None:
        raise PreventUpdate
    if not filename:
        return "Upload failed: missing file name.", refresh_token
    sandbox_active = sandbox_mode_enabled()
    if not sandbox_active and not credentials_ready():
        return "Upload failed: Google credentials are not configured.", refresh_token

    try:
        content_string = contents.split(",", 1)[1]
        decoded = base64.b64decode(content_string)
        upload_invoice_to_drive(filename, decoded)
        suffix = " (sandbox demo)" if sandbox_active else ""
        return (f"Uploaded '{filename}' to the Submitted queue{suffix}.", str(time.time()))
    except Exception as exc:  # pragma: no cover - network/API errors
        return (f"Upload failed: {exc}", refresh_token)


@callback(
    Output("invoice-list", "children"),
    Input("invoice-refresh-store", "data"),
    Input("invoice-autorefresh", "n_intervals"),
)
def refresh_invoice_list(_refresh_token, n_intervals):
    # Skip auto-refresh if disabled and this was triggered by interval (not manual action)
    if not AUTO_REFRESH_ENABLED and n_intervals > 0 and ctx.triggered_id == "invoice-autorefresh":
        raise PreventUpdate
    
    sandbox_active = sandbox_mode_enabled()
    if not sandbox_active and not credentials_ready():
        return [
            html.Div(
                "Google Drive credentials are not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE first.",
                style={"color": "#d32f2f"},
            )
        ]

    try:
        result = fetch_invoice_dashboard_data()
        if len(result) == 3:
            records, folder_options, folder_map = result
        else:
            records, folder_options = result
            folder_map = {}
    except Exception as exc:  # pragma: no cover - API errors
        # If SSL error, try refreshing credentials
        if "SSL" in str(exc) or "decryption" in str(exc).lower():
            global _drive_service, _cached_credentials
            _drive_service = None
            _cached_credentials = None
            try:
                result = fetch_invoice_dashboard_data()
                if len(result) == 3:
                    records, folder_options, folder_map = result
                else:
                    records, folder_options = result
                    folder_map = {}
            except Exception as retry_exc:
                return [html.Div(f"Unable to load invoices after retry: {retry_exc}", style={"color": "#d32f2f"})]
        else:
            return [html.Div(f"Unable to load invoices: {exc}", style={"color": "#d32f2f"})]

    if not records:
        message = "No invoices found in the monitored folders."
        if sandbox_active:
            message = "No demo invoices yet. Upload a file to see sandbox cards."
        return [html.Div(message)]

    return [build_invoice_card(record, folder_options, folder_map) for record in records]


def _dropdown_value_for_index(index: str, dropdown_ids: List[Dict], dropdown_values: List[str]):
    for component_id, value in zip(dropdown_ids, dropdown_values):
        if component_id.get("index") == index:
            return value
    return None


@callback(
    Output("invoice-action-feedback", "children"),
    Output("invoice-refresh-store", "data", allow_duplicate=True),
    Input({"type": "move-button", "index": ALL}, "n_clicks"),
    Input({"type": "paid-button", "index": ALL}, "n_clicks"),
    Input({"type": "status-button", "index": ALL}, "n_clicks"),
    Input({"type": "archive-button", "index": ALL}, "n_clicks"),
    State({"type": "processed-dropdown", "index": ALL}, "value"),
    State({"type": "processed-dropdown", "index": ALL}, "id"),
    State({"type": "status-dropdown", "index": ALL}, "value"),
    State({"type": "status-dropdown", "index": ALL}, "id"),
    State({"type": "receipt-link-input", "index": ALL}, "value"),
    State({"type": "receipt-link-input", "index": ALL}, "id"),
    State("invoice-refresh-store", "data"),
    prevent_initial_call=True,
)
def handle_invoice_actions(move_clicks, paid_clicks, status_clicks, archive_clicks, dropdown_values, dropdown_ids, status_values, status_ids, receipt_links, receipt_link_ids, refresh_token):
    del move_clicks, paid_clicks, status_clicks, archive_clicks  # values not needed directly
    triggered = ctx.triggered_id
    if not triggered:
        raise PreventUpdate
    sandbox_active = sandbox_mode_enabled()
    if not sandbox_active and not credentials_ready():
        return "Action failed: Google credentials missing.", refresh_token

    try:
        if triggered.get("type") == "move-button":
            target_folder = _dropdown_value_for_index(
                triggered.get("index"), dropdown_ids, dropdown_values
            )
            if not target_folder:
                return "Select a processed folder before moving the invoice.", refresh_token
            
            # Find folder name from dropdown options
            folder_name = "Unknown"
            for dropdown_id, value in zip(dropdown_ids, dropdown_values):
                if dropdown_id.get("index") == triggered.get("index") and value == target_folder:
                    # Find the label for this value in folder options
                    # We need to get fresh folder list
                    if not sandbox_mode_enabled():
                        service = get_drive_service()
                        folders = list_processed_subfolders(service)
                        for f in folders:
                            if f["id"] == target_folder:
                                folder_name = f["name"]
                                break
                    break
            
            # Get current date
            from datetime import datetime
            submitted_date = datetime.now().strftime("%Y-%m-%d")
            
            metadata = move_invoice_to_processed(triggered.get("index"), target_folder)
            
            # Log to sheet first (critical operation)
            try:
                append_invoice_to_sheet(
                    metadata.get("name", "Unnamed"), 
                    metadata.get("webViewLink"),
                    folder_name,
                    submitted_date
                )
            except Exception as sheet_err:
                return f"File moved but sheet logging failed: {sheet_err}", refresh_token
            
            # Track this folder persistently so we query it on future refreshes
            # Do this after sheet write to avoid DB crash affecting sheet write
            try:
                add_tracked_folder(target_folder, folder_name)
            except Exception:
                pass  # DB tracking is non-critical, don't fail if it errors
            
            message = f"Moved '{metadata.get('name')}' to {folder_name} and logged to inv_tbl."
        elif triggered.get("type") == "paid-button":
            # Get receipt link for this invoice
            receipt_link = _dropdown_value_for_index(
                triggered.get("index"), receipt_link_ids, receipt_links
            )
            if not receipt_link or not receipt_link.strip():
                return "Please provide a receipt link before marking as paid.", refresh_token
            
            metadata = mark_invoice_paid(triggered.get("index"))
            
            # Update sheet with paid date and receipt link
            from datetime import datetime
            paid_date = datetime.now().strftime("%Y-%m-%d")
            update_invoice_paid_in_sheet(
                metadata.get("name", "Unnamed"),
                paid_date,
                receipt_link
            )
            message = f"Marked '{metadata.get('name')}' as paid and logged to inv_tbl."
        elif triggered.get("type") == "status-button":
            new_status = _dropdown_value_for_index(
                triggered.get("index"), status_ids, status_values
            )
            if not new_status:
                return "Select a status before updating.", refresh_token
            metadata = update_invoice_status(triggered.get("index"), new_status)
            message = f"Updated '{metadata.get('name')}' status to {STATUS_LABELS.get(new_status, new_status)}."
        elif triggered.get("type") == "archive-button":
            metadata = archive_invoice(triggered.get("index"))
            message = f"Archived '{metadata.get('name')}'. This invoice will no longer appear in the dashboard but remains in Drive."
        else:
            return "Unknown action.", refresh_token

        suffix = " (sandbox demo)" if sandbox_active else ""
        return f"{message}{suffix}", str(time.time())
    except Exception as exc:  # pragma: no cover - API errors
        return (f"Action failed: {exc}", refresh_token)


if __name__ == "__main__":
    # Load tracked folders from database on startup
    load_tracked_folders()
    app.run(debug=False, port=8049)