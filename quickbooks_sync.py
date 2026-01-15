#!/usr/bin/env python3
"""QuickBooks Online sync worker for inv_tbl rows.

This module reads "inv_tbl" from the finance tracker Google Sheet, discovers
rows that are ready to invoice, and pushes them to QuickBooks Online via the
OAuth 2.0 API. After successfully creating an invoice it writes the
QuickBooks identifiers back onto the same sheet row and appends an audit trail
entry to finance_tracker.db.

Usage
-----
    python quickbooks_sync.py auth --open-browser      # Run OAuth consent flow
    python quickbooks_sync.py run-once --limit 5       # Sync at most 5 invoices
    python quickbooks_sync.py daemon --interval 600    # Loop every 10 minutes

The worker reads configuration from .env (loaded automatically) plus two JSON
files under finance_tracker/config/:
    * qb_directions.json (maps inv_from values to money_in / money_out)
    * quick Links config reused elsewhere

See QUICKBOOKS_INVOICE_SYNC_PLAN.md for the full rollout guide.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import gspread
import requests
from dotenv import load_dotenv
from gspread.utils import rowcol_to_a1
from oauth2client.service_account import ServiceAccountCredentials

import finance_db
import sheet_config

# ---------------------------------------------------------------------------
# Environment bootstrap & logging
# ---------------------------------------------------------------------------
load_dotenv()

LOGGER = logging.getLogger("quickbooks_sync")
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------
QB_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QB_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QB_ENV_SANDBOX = "Development"
QB_ENV_PRODUCTION = "Production"
QB_SCOPES = "com.intuit.quickbooks.accounting openid profile email"
QB_MINOR_VERSION = os.getenv("QB_MINOR_VERSION", "70")

DEFAULT_ELIGIBLE_STATUSES = {value.strip().casefold() for value in os.getenv(
    "QB_ELIGIBLE_STATUSES",
    "submitted,pending"
).split(',') if value.strip()}

DEFAULT_SERVICE_ACCOUNT = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    os.path.expanduser("~/.ssh/acd-internal-analytics-375db6d96d79.json")
)
GOOGLE_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

QB_REQUIRED_COLUMNS = [
    "qb_invoice_id", "qb_invoice_url", "qb_sync_status", "qb_synced_at", "qb_error"
]

SYNC_STATUSES = {"processing", "synced", "failed", "skipped"}

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize(value: Any) -> str:
    return clean_str(value).casefold()


def parse_decimal(value: Any) -> Decimal:
    try:
        if isinstance(value, Decimal):
            return value
        text = clean_str(value)
        if not text:
            return Decimal("0")
        # Remove commas/dollar signs if users keep formatting
        sanitized = text.replace(",", "").replace("$", "")
        return Decimal(sanitized)
    except (InvalidOperation, TypeError):
        raise ValueError(f"Unable to parse decimal from '{value}'")


def parse_date(value: Any) -> Optional[str]:
    text = clean_str(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Direction map handling
# ---------------------------------------------------------------------------

class DirectionMap:
    """Classify rows as money_in or money_out based on inv_from."""

    def __init__(self, path: str):
        self.path = path
        self.money_in: set[str] = set()
        self.money_out: set[str] = set()
        self.aliases: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            LOGGER.warning("Direction map %s not found; defaulting to money_in", self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:  # pragma: no cover - config errors
            LOGGER.error("Failed to load %s: %s", self.path, exc)
            return

        def _normalize_list(values) -> set[str]:
            result = set()
            for item in values or []:
                if isinstance(item, str) and item.strip():
                    result.add(item.strip().casefold())
            return result

        self.money_in = _normalize_list(data.get("money_in"))
        self.money_out = _normalize_list(data.get("money_out"))
        aliases = data.get("aliases", {}) or {}
        for key, value in aliases.items():
            if isinstance(key, str) and isinstance(value, str):
                self.aliases[key.strip().casefold()] = value.strip().casefold()

    def classify(self, inv_from: Any) -> str:
        normalized = normalize(inv_from)
        if not normalized:
            return "unknown"
        canonical = self.aliases.get(normalized, normalized)
        if canonical in self.money_out:
            return "money_out"
        if canonical in self.money_in:
            return "money_in"
        return "unknown"


# ---------------------------------------------------------------------------
# Google Sheets adapter
# ---------------------------------------------------------------------------

@dataclass
class InvoiceRow:
    row_number: int
    payload: Dict[str, Any]

    @property
    def invoice_number(self) -> str:
        return clean_str(self.payload.get("invoice")) or clean_str(self.payload.get("inv_link"))

    @property
    def status(self) -> str:
        return normalize(self.payload.get("status"))

    @property
    def sync_status(self) -> str:
        return normalize(self.payload.get("qb_sync_status"))

    @property
    def has_qb_id(self) -> bool:
        return bool(clean_str(self.payload.get("qb_invoice_id")))

    @property
    def inv_from(self) -> str:
        return clean_str(self.payload.get("inv_from"))


class GoogleSheetAdapter:
    def __init__(self, sheet_url: str, worksheet_name: str, service_account_path: str):
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(
                f"Google service account JSON not found: {service_account_path}. "
                "Set GOOGLE_SERVICE_ACCOUNT_JSON or update the default path."
            )
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            service_account_path, GOOGLE_SCOPE
        )
        self.client = gspread.authorize(credentials)
        self.sheet = self.client.open_by_url(sheet_url).worksheet(worksheet_name)
        self.expected_headers = sheet_config.EXPECTED_HEADERS[1]
        self.header_map = {
            header: idx + 1
            for idx, header in enumerate(self.expected_headers)
        }
        self._validate_columns()

    def _validate_columns(self) -> None:
        missing = [column for column in QB_REQUIRED_COLUMNS if column not in self.header_map]
        if missing:
            raise RuntimeError(
                f"Sheet '{self.sheet.title}' is missing required columns: {', '.join(missing)}"
            )

    def fetch_invoice_rows(self) -> List[InvoiceRow]:
        raw_records = self.sheet.get_all_records(expected_headers=self.expected_headers)
        rows: List[InvoiceRow] = []
        for idx, record in enumerate(raw_records, start=2):  # account for header row
            # Filter out rows with no invoice number
            invoice_value = clean_str(record.get("invoice")) or clean_str(record.get("inv_link"))
            if not invoice_value:
                continue
            rows.append(InvoiceRow(row_number=idx, payload=record))
        return rows

    def update_row(self, row_number: int, updates: Dict[str, Any]) -> None:
        requests_payload = []
        for header, value in updates.items():
            column_index = self.header_map.get(header)
            if not column_index:
                continue
            cell = rowcol_to_a1(row_number, column_index)
            requests_payload.append({
                "range": cell,
                "values": [[value]]
            })
        if not requests_payload:
            return
        self.sheet.batch_update(requests_payload, value_input_option="USER_ENTERED")

    def mark_processing(self, row_number: int) -> None:
        self.update_row(row_number, {"qb_sync_status": "processing", "qb_error": ""})

    def mark_result(self, row_number: int, status: str, updates: Dict[str, Any]) -> None:
        payload = {"qb_sync_status": status}
        payload.update(updates)
        self.update_row(row_number, payload)


# ---------------------------------------------------------------------------
# QuickBooks OAuth & API clients
# ---------------------------------------------------------------------------

class QuickBooksError(Exception):
    pass


class QuickBooksOAuthManager:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, realm_id: str, environment: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.realm_id = realm_id
        self.environment = environment or QB_ENV_SANDBOX

    def build_authorize_url(self, state: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": QB_SCOPES,
            "state": state,
        }
        return f"{QB_AUTH_URL}?{urlencode(params)}"

    def interactive_auth(self, open_browser: bool) -> None:
        import webbrowser
        state = f"sync-{int(time.time())}"
        auth_url = self.build_authorize_url(state)
        LOGGER.info("Opening Intuit consent page... If the browser does not open, copy this URL:\n%s", auth_url)
        if open_browser:
            webbrowser.open(auth_url)
        callback_url = input("\nAfter granting access, paste the FULL redirected URL here:\n> ").strip()
        if not callback_url:
            raise RuntimeError("Callback URL is required to finish OAuth flow")
        parsed = urlparse(callback_url)
        query = parse_qs(parsed.query)
        if query.get("state", [None])[0] != state:
            LOGGER.warning("OAuth state mismatch; continuing but verify the URL came from Intuit")
        auth_code = query.get("code", [None])[0]
        realm_id = query.get("realmId", [self.realm_id])[0]
        if not auth_code:
            raise RuntimeError("Authorization code missing from callback URL")
        self.exchange_code_for_tokens(auth_code, realm_id)
        LOGGER.info("OAuth tokens stored in finance_tracker.db")

    def exchange_code_for_tokens(self, code: str, realm_id: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        response = self._post_token(payload)
        self._persist_tokens(response, realm_id or self.realm_id)
        return response

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        response = self._post_token(payload)
        self._persist_tokens(response, self.realm_id)
        return response

    def _post_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        auth_header = requests.auth.HTTPBasicAuth(self.client_id, self.client_secret)
        headers = {"Accept": "application/json"}
        resp = requests.post(QB_TOKEN_URL, data=payload, auth=auth_header, headers=headers, timeout=30)
        if resp.status_code >= 400:
            raise QuickBooksError(f"Token endpoint error {resp.status_code}: {resp.text}")
        return resp.json()

    def _persist_tokens(self, data: Dict[str, Any], realm_id: str) -> None:
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        expires_at = utcnow() + timedelta(seconds=int(expires_in) - 30)
        finance_db.save_qb_tokens(access_token, refresh_token, expires_at, realm_id, self.environment)
        self.realm_id = realm_id

    def get_tokens(self) -> Optional[Dict[str, Any]]:
        return finance_db.get_qb_tokens()

    def get_access_token(self, force_refresh: bool = False) -> str:
        tokens = finance_db.get_qb_tokens()
        if not tokens:
            raise QuickBooksError("No stored OAuth tokens. Run 'python quickbooks_sync.py auth' first.")
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_at_raw = tokens.get("expires_at")
        expires_at = datetime.fromisoformat(expires_at_raw) if expires_at_raw else utcnow() - timedelta(seconds=1)
        if force_refresh or not access_token or expires_at <= utcnow():
            LOGGER.info("Refreshing QuickBooks access token…")
            refreshed = self.refresh_access_token(refresh_token)
            access_token = refreshed.get("access_token")
        if not access_token:
            raise QuickBooksError("Access token unavailable after refresh")
        return access_token


class QuickBooksClient:
    def __init__(self, oauth: QuickBooksOAuthManager, realm_id: str, environment: str):
        self.oauth = oauth
        self.realm_id = realm_id
        self.environment = environment or QB_ENV_SANDBOX
        self.api_base = (
            "https://sandbox-quickbooks.api.intuit.com"
            if self.environment.lower() in {"development", "sandbox"}
            else "https://quickbooks.api.intuit.com"
        )

    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
                 json_payload: Optional[Dict[str, Any]] = None, data: Optional[str] = None,
                 content_type: str = "application/json", retry: bool = True) -> Dict[str, Any]:
        token = self.oauth.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": content_type,
        }
        params = params or {}
        params.setdefault("minorversion", QB_MINOR_VERSION)
        url = f"{self.api_base}{path}"
        resp = requests.request(
            method,
            url,
            params=params,
            json=json_payload if content_type == "application/json" else None,
            data=data if content_type != "application/json" else None,
            headers=headers,
            timeout=45
        )
        if resp.status_code == 401 and retry:
            LOGGER.warning("Access token expired; retrying once after refresh")
            self.oauth.get_access_token(force_refresh=True)
            return self._request(method, path, params=params, json_payload=json_payload,
                                 data=data, content_type=content_type, retry=False)
        if resp.status_code >= 300:
            raise QuickBooksError(f"QuickBooks API error {resp.status_code}: {resp.text}")
        return resp.json()

    def create_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = f"/v3/company/{self.realm_id}/invoice"
        return self._request("POST", path, json_payload=payload)

    def query_customer(self, display_name: str) -> Optional[Dict[str, Any]]:
        escaped = display_name.replace("'", "\\'")
        query = f"select Id, DisplayName from Customer where DisplayName = '{escaped}'"  # nosec B608
        path = f"/v3/company/{self.realm_id}/query"
        result = self._request("POST", path, data=query, content_type="application/text")
        customers = result.get("QueryResponse", {}).get("Customer", [])
        return customers[0] if customers else None

    def create_customer(self, display_name: str) -> Dict[str, Any]:
        path = f"/v3/company/{self.realm_id}/customer"
        payload = {"DisplayName": display_name}
        result = self._request("POST", path, json_payload=payload)
        return result.get("Customer") or result

    def ensure_customer(self, display_name: str) -> Dict[str, str]:
        if not display_name:
            raise QuickBooksError("Cannot create invoice without a customer name")
        customer = self.query_customer(display_name)
        if not customer:
            LOGGER.info("Creating QuickBooks customer '%s'", display_name)
            customer = self.create_customer(display_name)
        return {
            "value": str(customer.get("Id")),
            "name": customer.get("DisplayName", display_name)
        }

    def build_invoice_url(self, invoice_id: str) -> str:
        base = "https://app.sandbox.qbo.intuit.com" if self.environment.lower() in {"development", "sandbox"} else "https://app.qbo.intuit.com"
        return f"{base}/app/invoice?txnId={invoice_id}"


# ---------------------------------------------------------------------------
# Sync processor
# ---------------------------------------------------------------------------

class SyncProcessor:
    def __init__(
        self,
        sheet: GoogleSheetAdapter,
        qb_client: QuickBooksClient,
        direction_map: DirectionMap,
        eligible_statuses: Iterable[str],
        sync_mode: str,
        enable_bills: bool,
        default_item_id: Optional[str],
        default_item_name: Optional[str],
    ):
        self.sheet = sheet
        self.qb_client = qb_client
        self.direction_map = direction_map
        self.eligible_statuses = {value.casefold() for value in eligible_statuses}
        self.sync_mode = sync_mode or "invoice_only"
        self.enable_bills = enable_bills
        self.default_item_id = default_item_id
        self.default_item_name = default_item_name or "Services"

    def _eligible(self, row: InvoiceRow, include_failed: bool) -> bool:
        if row.has_qb_id:
            return False
        if row.sync_status == "processing":
            return False
        if row.sync_status == "synced":
            return False
        if row.sync_status == "skipped":
            return False    
        if row.sync_status == "failed" and not include_failed:
            return False
        return row.status in self.eligible_statuses

    def gather_candidates(self, include_failed: bool) -> List[InvoiceRow]:
        rows = self.sheet.fetch_invoice_rows()
        return [row for row in rows if self._eligible(row, include_failed)]

    def process_rows(self, rows: List[InvoiceRow], *, dry_run: bool, limit: Optional[int]) -> None:
        processed = 0
        for row in rows:
            if limit and processed >= limit:
                break
            try:
                self.process_row(row, dry_run=dry_run)
                processed += 1
            except QuickBooksError as exc:
                LOGGER.error("Row %s failed: %s", row.row_number, exc)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.exception("Unexpected error with row %s: %s", row.row_number, exc)

    def process_row(self, row: InvoiceRow, *, dry_run: bool) -> None:
        direction = self.direction_map.classify(row.inv_from)
        if direction == "money_out" and (self.sync_mode != "dual" or not self.enable_bills):
            message = "Row requires bill sync (money_out) but bills are disabled"
            LOGGER.info("Skipping row %s: %s", row.row_number, message)
            if not dry_run:
                self.sheet.mark_result(row.row_number, "skipped", {
                    "qb_error": message,
                    "qb_synced_at": utcnow().isoformat()
                })
                finance_db.log_qb_invoice_sync(row.row_number, row.invoice_number, None, None, "skipped", row.payload, {"message": message}, message)
            return

        payload = self.build_invoice_payload(row)
        if dry_run:
            LOGGER.info("[dry-run] Would sync row %s with payload: %s", row.row_number, json.dumps(payload))
            return

        self.sheet.mark_processing(row.row_number)
        try:
            response = self.qb_client.create_invoice(payload)
        except Exception as exc:
            error_message = str(exc)
            LOGGER.error("QuickBooks error for row %s: %s", row.row_number, error_message)
            self.sheet.mark_result(row.row_number, "failed", {
                "qb_error": error_message,
                "qb_synced_at": utcnow().isoformat()
            })
            finance_db.log_qb_invoice_sync(row.row_number, row.invoice_number, None, None, "failed", payload, {"error": error_message}, error_message)
            return

        invoice = response.get("Invoice") or response.get("InvoiceResponse", {}).get("Invoice") or {}
        invoice_id = str(invoice.get("Id")) if invoice else None
        doc_number = invoice.get("DocNumber") or row.invoice_number
        invoice_url = self.qb_client.build_invoice_url(invoice_id) if invoice_id else ""
        LOGGER.info("Row %s synced as QuickBooks invoice %s", row.row_number, invoice_id)
        self.sheet.mark_result(row.row_number, "synced", {
            "qb_invoice_id": invoice_id or "",
            "qb_invoice_url": invoice_url,
            "qb_error": "",
            "qb_synced_at": utcnow().isoformat()
        })
        finance_db.log_qb_invoice_sync(row.row_number, doc_number, invoice_id, invoice_url, "synced", payload, response, None)

    def build_invoice_payload(self, row: InvoiceRow) -> Dict[str, Any]:
        customer_name = clean_str(row.payload.get("to_client")) or clean_str(row.payload.get("end_client"))
        customer = self.qb_client.ensure_customer(customer_name)
        try:
            amount = parse_decimal(row.payload.get("inv_dollars"))
        except ValueError as exc:
            raise QuickBooksError(str(exc)) from exc
        if amount <= Decimal("0"):
            raise QuickBooksError(f"Row {row.row_number} has non-positive inv_dollars")
        txn_date = parse_date(row.payload.get("submitted_date")) or datetime.utcnow().date().isoformat()
        due_date = parse_date(row.payload.get("Inv_paid_date"))
        description = clean_str(row.payload.get("task_descr")) or clean_str(row.payload.get("job_name")) or "Professional services"
        private_note = clean_str(row.payload.get("notes")) or clean_str(row.payload.get("thread"))
        doc_number = row.invoice_number or f"AUTO-{row.row_number}"
        if not self.default_item_id:
            raise QuickBooksError("QB_DEFAULT_ITEM_ID is required to build invoice line items")

        item_name = clean_str(row.payload.get("invoice")) or self.default_item_name

        line = {
            "DetailType": "SalesItemLineDetail",
            "Amount": float(amount),
            "Description": description,
            "SalesItemLineDetail": {
                "ItemRef": {
                    "value": self.default_item_id,
                    "name": item_name
                },
                "Qty": 1,
                "UnitPrice": float(amount)
            }
        }

        payload = {
            "DocNumber": doc_number,
            "TxnDate": txn_date,
            "CustomerRef": customer,
            "Line": [line],
            "PrivateNote": private_note[:2000] if private_note else None,
        }
        if due_date:
            payload["DueDate"] = due_date
        # Remove None values
        return {key: value for key, value in payload.items() if value not in (None, "")}


# ---------------------------------------------------------------------------
# CLI Entrypoints
# ---------------------------------------------------------------------------

def load_core_settings() -> Dict[str, Any]:
    settings = {
        "sheet_url": os.getenv("GOOGLE_SHEET_URL"),
        "qb_client_id": os.getenv("QB_CLIENT_ID"),
        "qb_client_secret": os.getenv("QB_CLIENT_SECRET"),
        "qb_redirect_uri": os.getenv("QB_REDIRECT_URI"),
        "qb_realm_id": os.getenv("QB_REALM_ID"),
        "qb_env": os.getenv("QB_ENV", QB_ENV_SANDBOX),
        "sheet_name": sheet_config.DATA_NAMES[1],
        "sync_mode": os.getenv("QB_SYNC_MODE", "invoice_only"),
        "enable_bills": os.getenv("QB_ENABLE_BILLS", "false").lower() == "true",
        "default_item_id": os.getenv("QB_DEFAULT_ITEM_ID"),
        "default_item_name": os.getenv("QB_DEFAULT_ITEM_NAME", "Services"),
    }
    missing = [key for key, value in settings.items() if key.startswith("qb_") and not value]
    if missing:
        raise RuntimeError(f"Missing required QuickBooks env vars: {', '.join(missing)}")
    if not settings["sheet_url"]:
        raise RuntimeError("GOOGLE_SHEET_URL must be set")
    if not settings["default_item_id"]:
        raise RuntimeError("QB_DEFAULT_ITEM_ID must be set before running the sync worker")
    return settings


def build_processor(settings: Dict[str, Any]) -> SyncProcessor:
    sheet_adapter = GoogleSheetAdapter(
        settings["sheet_url"],
        settings["sheet_name"],
        DEFAULT_SERVICE_ACCOUNT
    )
    oauth = QuickBooksOAuthManager(
        settings["qb_client_id"],
        settings["qb_client_secret"],
        settings["qb_redirect_uri"],
        settings["qb_realm_id"],
        settings["qb_env"],
    )
    qb_client = QuickBooksClient(oauth, settings["qb_realm_id"], settings["qb_env"])
    direction_map = DirectionMap(os.path.join(os.path.dirname(__file__), "config", "qb_directions.json"))
    processor = SyncProcessor(
        sheet_adapter,
        qb_client,
        direction_map,
        DEFAULT_ELIGIBLE_STATUSES,
        settings["sync_mode"],
        settings["enable_bills"],
        settings["default_item_id"],
        settings["default_item_name"],
    )
    return processor


def cmd_auth(open_browser: bool) -> None:
    settings = load_core_settings()
    oauth = QuickBooksOAuthManager(
        settings["qb_client_id"],
        settings["qb_client_secret"],
        settings["qb_redirect_uri"],
        settings["qb_realm_id"],
        settings["qb_env"],
    )
    oauth.interactive_auth(open_browser=open_browser)


def cmd_run_once(limit: Optional[int], include_failed: bool, dry_run: bool) -> None:
    settings = load_core_settings()
    processor = build_processor(settings)
    rows = processor.gather_candidates(include_failed=include_failed)
    LOGGER.info("Found %s candidate rows", len(rows))
    processor.process_rows(rows, dry_run=dry_run, limit=limit)


def cmd_daemon(interval: int, limit: Optional[int], include_failed: bool) -> None:
    settings = load_core_settings()
    processor = build_processor(settings)
    LOGGER.info("Starting daemon loop (interval=%s seconds)", interval)
    while True:
        try:
            rows = processor.gather_candidates(include_failed=include_failed)
            LOGGER.info("Daemon discovered %s rows needing sync", len(rows))
            processor.process_rows(rows, dry_run=False, limit=limit)
        except Exception as exc:  # pragma: no cover - background safety
            LOGGER.exception("Daemon iteration failed: %s", exc)
        time.sleep(interval)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="QuickBooks invoice sync worker")
    subparsers = parser.add_subparsers(dest="command")

    auth_parser = subparsers.add_parser("auth", help="Run OAuth consent flow")
    auth_parser.add_argument("--open-browser", action="store_true", default=False,
                             help="Automatically open the consent URL in the default browser")

    run_parser = subparsers.add_parser("run-once", help="Process eligible rows once")
    run_parser.add_argument("--limit", type=int, default=None, help="Maximum rows to process")
    run_parser.add_argument("--include-failed", action="store_true", help="Re-try rows marked failed")
    run_parser.add_argument("--dry-run", action="store_true", help="Log actions without API calls")

    daemon_parser = subparsers.add_parser("daemon", help="Loop forever with sleep intervals")
    daemon_parser.add_argument("--interval", type=int, default=600, help="Seconds between runs")
    daemon_parser.add_argument("--limit", type=int, default=None, help="Maximum rows per pass")
    daemon_parser.add_argument("--include-failed", action="store_true", help="Re-try rows marked failed")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return

    finance_db.init_database()

    if args.command == "auth":
        cmd_auth(open_browser=args.open_browser)
    elif args.command == "run-once":
        cmd_run_once(limit=args.limit, include_failed=args.include_failed, dry_run=args.dry_run)
    elif args.command == "daemon":
        cmd_daemon(interval=args.interval, limit=args.limit, include_failed=args.include_failed)
    else:
        parser.error(f"Unknown command {args.command}")


if __name__ == "__main__":
    main()
