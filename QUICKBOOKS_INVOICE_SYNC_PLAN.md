# QuickBooks Invoice Sync Plan

## Goal
Automate creation of QuickBooks Online invoices for each new row appended to `inv_tbl` in the Google Sheet, then persist the QuickBooks invoice URL back onto that same row so downstream dashboards immediately see the handshake status.

## Can We Use QuickBooks Online Simple Start?
Yes. Intuit exposes the same accounting API surface (v3) for all QuickBooks Online subscriptions, including **Simple Start**, so you can authenticate via OAuth 2.0, create invoices, and read them back. Feature gaps to note:
- Simple Start lacks multiple currency support—keep invoices in a single home currency.
- Only one user seat is included, so the integration should run under the single admin’s Intuit account or a dedicated shared login.
- Inventory features are limited; that is fine because this workflow posts non-inventory service lines.

## Current State
- `inv_tbl` already stores finalized invoice rows (`invoice`, `inv_link`, `status`, `owed2ACD`, `owed2workers`, etc.).
- The Dash app and SQLite snapshots read this sheet but do not push data back to external systems.
- There is no persistent identifier that proves a QuickBooks invoice was generated from a sheet row.

## Target Flow for Each New Row
1. Detect rows whose `qb_invoice_id` is blank (new rows) and whose `status` is one of `submitted`, `pending`, or another “ready to invoice” state.
2. Normalize the row into the QuickBooks invoice schema (customer, line items, memo, due dates, tax, payment terms).
3. Call the QuickBooks Online API to create the invoice.
4. Capture the returned `Id`, `DocNumber`, and `InvoiceLink`/`PdfDownloadLink`.
5. Write these fields plus metadata (`qb_invoice_id`, `qb_invoice_url`, `qb_sync_status`, `qb_synced_at`, `qb_error`) to the originating `inv_tbl` row.
6. Optionally store a shadow copy inside `finance_tracker.db` for auditing/backfill.

## Implementation Phases
### Phase 0 – Prerequisites
- Create/enable an Intuit Developer account and QuickBooks Online app; capture the **Client ID**, **Client Secret**, and **Realm ID**.
- Decide where to store OAuth tokens (recommended: new table `qb_tokens` in `finance_tracker.db` or a small encrypted JSON file referenced from `.env`).
- Add the following env vars: `QB_CLIENT_ID`, `QB_CLIENT_SECRET`, `QB_REDIRECT_URI`, `QB_REALM_ID`, `QB_ENV` (`Production` vs `Sandbox`).
- Capture a QuickBooks **Product/Service ID** for `QB_DEFAULT_ITEM_ID`. See the “Finding the Product/Service ID” note below.

### QuickBooks Tier & Owed Receipts Coverage
- **Outgoing invoices only (status quo):** Simple Start is sufficient when you only need to create invoices that ACD issues to clients.
- **Need to track bills/owed receipts:** Upgrade to at least **QuickBooks Online Essentials**. That unlocks the Vendors → Bills workflow, letting you enter incoming invoices, queue them in Accounts Payable, and mark them paid later.
- **Upgrade steps:**
  1. In QuickBooks Online, open **Gear → Account and settings → Billing & subscription**.
  2. Click **Upgrade**, pick **Essentials** (or Plus if you also need projects/inventory), confirm billing.
  3. Re-authorize the Intuit developer app after the tier change so the OAuth scope includes the bills API.
- **Owed receipts import:** Once on Essentials/Plus, the sync service can create `Bill` objects using the same OAuth credentials. The sheet will drive whether we POST `Invoice` (money in) or `Bill` (money out).

**Intuit Developer Account Quickstart**
1. Browse to https://developer.intuit.com/ and sign in with your existing QuickBooks Online admin credentials (or create a new Intuit ID and then link it to the company file).
2. Click **Dashboard → Create an app → QuickBooks Online and Payments**; name the app something like "Finance Tracker Invoice Sync".
3. Inside the app settings, copy the **Client ID** and **Client Secret** into your password manager immediately—these populate the env vars above.
4. Add a redirect URI (e.g., `http://localhost:8765/callback`) under both the Development and Production tabs so the OAuth helper can complete the code exchange locally.
5. Retrieve the **Realm ID** for the target QuickBooks company by opening the Development tab’s "Keys & OAuth" section or by clicking the gear icon → "Copy realm ID" inside QuickBooks Online.
6. Toggle the app to **Production** when you are ready, submit Intuit’s compliance checklist, and update the `.env` values with the production Client Secret once Intuit approves the app.

### Phase 1 – Instrument `inv_tbl`
- Add columns to the sheet (append to the far right so existing formulas survive):
  - `qb_invoice_id`
  - `qb_invoice_url`
  - `qb_sync_status` ("pending", "synced", "failed")
  - `qb_synced_at`
  - `qb_error` (last failure reason)
- Update `EXPECTED_HEADERS[1]` in `sankey_helpers.py` and any other header validation logic to include these new columns so the Dash app does not drop them.

### Phase 2 – Build Sync Service
- Create a dedicated module (e.g., `quickbooks_sync.py`) that encapsulates:
  - OAuth 2.0 token exchange + refresh (use `python-quickbooks` SDK or direct `requests`).
  - Payload builders that map sheet rows to QuickBooks invoice objects (see data mapping below).
  - Google Sheets read/write helpers (reuse `acd.load_google_sheet` for read; add write helper via gspread or Sheets API v4 for updates).
  - Idempotency guard: check if `qb_invoice_id` already exists before creating another invoice.
- Provide a CLI entry point or Dash background worker (similar to `daily_snapshot_worker`) that runs every N minutes to:
  1. Pull `inv_tbl` rows.
  2. Filter to `qb_sync_status` blank/"pending" and `status` in eligible states.
  3. Create invoices sequentially (or in small batches) with retry + exponential backoff.

**Direction-aware logic (inv_from):**
- Introduce a configuration map (e.g., `config/qb_directions.json`) that groups values found in `inv_from` into `money_out` vs `money_in` buckets:
  ```json
  {
    "money_in": ["ACD"],
    "money_out": ["Accelebrate", "BHanalytics", "VendorXYZ"]
  }
  ```
- When processing each row, look up `inv_from`:
  - If the normalized value is in `money_in`, build a QuickBooks **Invoice** payload (customer = `to_client`/`end_client`).
  - If it falls under `money_out`, build a **Bill** (vendor = `inv_from`, chart-of-account = expenses/COGS). This represents an “owed receipt” that someone else sent to us.
- Expose overrides in `.env` (e.g., `QB_DEFAULT_VENDOR_ACCOUNT`) so accounting can change routing without code edits.
- Store the QuickBooks IDs separately: keep `qb_invoice_id` for invoices and add `qb_bill_id`/`qb_bill_url` for incoming bills so downstream analytics can tell the difference while still referencing the same `inv_tbl` rows.

### Phase 3 – Writeback + Persistence
- After QuickBooks returns success, update the specific sheet row with:
  - `qb_invoice_id` (QuickBooks internal ID)
  - `qb_invoice_url` (from `Invoice.DocNumber` + `https://app.qbo.intuit.com/app/invoice?txnId=...`)
  - `qb_sync_status = "synced"`
  - `qb_synced_at = NOW()`
  - blank out `qb_error`
- On failure, set `qb_sync_status = "failed"` and capture the error message, so the operator can fix data issues directly in the sheet and let the worker retry later.
- Mirror this record (row primary key + QuickBooks response JSON) into a new SQLite table (`qb_invoice_audit`) for troubleshooting and to prevent duplicate pushes if sheet edits revert a row.

### Phase 4 – Monitoring & Rollout
- Emit structured logs from the sync worker (destination: console + rotating file under `logs/quickbooks_sync.log`).
- Add a lightweight Dash admin card that shows counts of `pending/synced/failed` rows and the timestamp of the last successful push.
- Dry-run in QuickBooks sandbox using a copy of the sheet, validate mappings, then switch credentials to production.

## Deployment Methods
### Mode A – Invoice Only (Simple Start)
- **Audience:** Keep current QBO Simple Start subscription.
- **Env toggle:** `QB_SYNC_MODE=invoice_only`.
- **What ships:**
  - `quickbooks_sync.py` only calls the Invoice endpoint.
  - `config/qb_directions.json` may still categorize vendors, but rows in `money_out` are skipped with a `qb_sync_status="skipped"` note referencing insufficient tier.
  - Columns required: `qb_invoice_id`, `qb_invoice_url`, `qb_sync_status`, `qb_synced_at`, `qb_error`.
- **Deployment:**
  1. Push the worker as a cron job on the same host that runs Dash (e.g., `*/10 * * * * source venv && python quickbooks_sync.py run-once`).
  2. Point `.env` to sandbox credentials first, flip to production when satisfied.
- **Monitoring:** rely on the new Dash card plus worker logs; data in `money_out` stays visible but clearly un-synced until upgrade.

### Mode B – Dual Flow (Invoices + Bills)
- **Audience:** After upgrading to Essentials/Plus.
- **Env toggle:** `QB_SYNC_MODE=dual` and `QB_ENABLE_BILLS=true`.
- **What ships:**
  - Same worker, but now the direction map is enforced. `money_in` rows create Invoices; `money_out` rows create Bills (owed receipts).
  - Additional sheet columns: `qb_bill_id`, `qb_bill_url`, `qb_bill_status`, `qb_bill_error` so analytics can differentiate payouts.
  - Config additions: `QB_DEFAULT_VENDOR_ACCOUNT`, `QB_DEFAULT_EXPENSE_ACCOUNT`, optional `QB_AUTO_MARK_BILL_PAID=false`.
- **Deployment:**
  1. Re-run OAuth consent so the token includes Bills scope.
  2. Recreate secrets in `.env` (production keys) and run `python quickbooks_sync.py migrate --mode dual` to add any missing sheet/database columns automatically.
  3. Enable a second cron entry or background thread dedicated to bill sync if you want separate cadence (e.g., invoices every 5 minutes, bills every hour).
- **Monitoring:** extend the Dash admin card to show both invoice and bill counts, plus last sync per direction; review `qb_invoice_audit` and a new `qb_bill_audit` table during rollout.

## End-to-End Quickstart & Test Plan
1. **Prep credentials**
  - Follow the developer quickstart to grab Client ID/Secret + Realm ID.
  - Populate `.env` with sandbox values (`QB_ENV=Development`, mode flag per above).
2. **Instrument the sheet**
  - Add the new tracking columns to `inv_tbl` (and optionally duplicate the sheet for testing).
  - Populate `config/qb_directions.json` with at least `{"money_in": ["ACD"], "money_out": []}` for invoice-only pilots.
3. **Dry-run locally**
  - `poetry run python quickbooks_sync.py auth --open-browser` (or equivalent) to capture the first refresh token.
  - `python quickbooks_sync.py run-once --limit 3 --dry-run` to log the payloads without creating QuickBooks objects; confirm invoices/bills are detected correctly based on `inv_from`.
4. **Sandbox execution**
  - Drop `--dry-run`, run `python quickbooks_sync.py run-once --limit 3` and verify records appear inside the QuickBooks sandbox company.
  - Check the sheet for `qb_*` columns populating, and inspect `finance_tracker.db` audit tables.
5. **Automate**
  - Configure cron/systemd (or a Dash background worker) to invoke `quickbooks_sync.py daemon --interval 600`.
  - Tail `logs/quickbooks_sync.log` and confirm the admin card shows “Last sync” times updating.
6. **Production cutover**
  - Swap `.env` to production credentials, rerun auth, and reset `qb_sync_status` for any rows you want re-pushed.
  - Monitor the first day closely; test both an outgoing invoice and (if on Essentials/Plus) an incoming bill.

  ## Finding the Product/Service ID for `QB_DEFAULT_ITEM_ID`
  1. In QuickBooks Online, click the ⚙️ **Gear** icon → **Products and Services**.
  2. Locate the Product/Service used for customer invoices (create one if needed) and click **Edit**.
  3. The browser URL ends with `itemId=<number>`; that number is the value for `QB_DEFAULT_ITEM_ID`.
  4. Alternatively, open the Intuit API Explorer (https://developer.intuit.com/app/developer/qbo/docs/api/tools/api-explorer) and run `SELECT Id, Name FROM Item` against your company. The `Id` column matches the same numeric value.
  5. Update `.env` with the numeric ID and, optionally, set `QB_DEFAULT_ITEM_NAME` to a friendly default (the worker already prefers the sheet’s `invoice` text for the ItemRef name).


## Data Mapping Snapshot
| Google Sheet Column | QuickBooks Field | Notes |
| --- | --- | --- |
| `invoice` (external ID) | `DocNumber` | Optionally prefix to avoid collisions. |
| `to_client` or `end_client` | `CustomerRef` | Maintain a lookup table to map sheet client names to QuickBooks Customer IDs. |
| `task_descr` / `job_name` | `Line.Description` | Combine if needed for clarity. |
| `inv_dollars` | `Line.Amount` | Should match `Amount` for the service item; convert to decimal. |
| `inv_from` | `SalesTermRef` or memo | Use to tag broker/reseller info. |
| `submitted_date` | `TxnDate` | Defaults to today if empty. |
| `Inv_paid_date` | `DueDate` (optional) | Only set when known; QuickBooks expects a future date for open invoices. |
| `owed2ACD`, `owed2workers` | Custom fields or memo | Useful for internal reconciliation but not exposed to client. |
| `notes` / `thread` | `PrivateNote` | Keep internal reminders here. |

Add custom fields in QuickBooks (Settings → Custom fields) if you must store `job_start`, `job_end`, or broker chain metadata.

## Error Handling Strategy
- **Validation gate**: Before hitting QuickBooks, confirm each required field; reject rows locally with descriptive `qb_error` so operators fix the sheet.
- **API retries**: Use exponential backoff for HTTP 429/500. Stop after ~3 attempts to avoid throttling.
- **Idempotency**: Store the QuickBooks `Id` immediately; future runs skip rows where `qb_invoice_id` is populated unless the operator empties it manually to force a re-sync.
- **Backfill**: Provide a CLI flag `--backfill` that reprocesses historical rows lacking QuickBooks IDs but already marked paid, ensuring parity.

## Security Considerations
- Persist OAuth refresh tokens encrypted at rest (e.g., Fernet key stored in `.env`).
- Restrict who can run the sync worker; if deploying to a VM or container, scope the Intuit app to production URL(s) only.
- Avoid writing secrets to Google Sheets; only write the public QuickBooks invoice URL.

## Open Questions / Decisions Needed
1. **Trigger cadence** – cron job, Dash background thread, or external Step Function/Lambda?
2. **Customer matching** – will the sheet always store exact QuickBooks customer names, or do we need a mapping tab?
3. **Multiple lines per invoice** – do certain rows need to collapse into one invoice (group by `invoice` column) or is it truly one row → one invoice?
4. **Attachments** – should PDFs be uploaded somewhere and linked in the sheet, or is the QuickBooks URL enough?

## Next Actions
1. Approve the sheet schema changes for `inv_tbl` and communicate them to sheet owners.
2. Register the QuickBooks app + gather credentials; add them to `.env`.
3. Scaffold `quickbooks_sync.py` with token handling and a single “create invoice” path against the sandbox.
4. Populate the customer/item lookup mappings (could live in `config/qb_customers.json`).
5. Run an end-to-end sandbox test, verify the link writes back correctly, and then schedule the worker for production use.
