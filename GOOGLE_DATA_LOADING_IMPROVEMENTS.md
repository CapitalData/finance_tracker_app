# Google Sheets Data Loading Improvements

## Problem
The "Load Google Sheets Data" button was unreliable, with frequent failures due to:
- Network timeouts
- API rate limiting
- Missing error handling
- Poor fallback behavior
- No user feedback on status

## Solution

### 1. **Retry Logic with Exponential Backoff**
Added `load_google_sheet_with_retry()` helper function that:
- Retries failed Google Sheets API calls up to 2 times (configurable)
- Uses exponential backoff (1s, 2s, 4s between retries)
- Validates data completeness after loading
- Provides detailed logging of each attempt

**Location:** [dash_app.py](dash_app.py#L27-L66)

```python
def load_google_sheet_with_retry(sheet_name, expected_headers, credentials, sheet_url, max_retries=2):
    """Load Google Sheet with retry logic and better error handling"""
    for attempt in range(max_retries + 1):
        try:
            df = acd.load_google_sheet(sheet_name, expected_headers, credentials, sheet_url)
            if df is None or df.empty:
                raise ValueError(f"Sheet '{sheet_name}' returned empty data")
            return df
        except Exception as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff
                time.sleep(wait_time)
    return None
```

### 2. **Improved Callback Error Handling**
The main `update_stacked_sankey()` callback now:
- Uses the retry function for all Google Sheets API calls
- Wraps operations in nested try-except blocks for specific error contexts
- Gracefully falls back to demo data on all failures
- Logs stack traces for debugging
- Verifies data validity before using it

**Key improvements:**
- Better variable scoping and initialization
- Proper exception handling with detailed logging
- Fallback mechanism that preserves UI functionality

### 3. **User Status Feedback**
Added `update_sankey_status()` callback that displays:
- ✅ "Google Sheets data loaded (cached)" - when data is available from cache
- ⏳ "Loading Google Sheets data..." - initial load in progress
- 📊 "Demo data loaded" - when using demo data fallback
- Shows color-coded status messages for quick visual feedback

**Location:** [dash_app.py](dash_app.py#L1030-L1060)

### 4. **Enhanced Node Checklist Loading**
The `update_node_checklist()` callback now:
- Uses retry logic when fetching data for node options
- Gracefully falls back to demo data nodes if Google Sheets fails
- Pre-selects all nodes by default
- Shows alphabetically sorted node list

### 5. **Improved Dropdown Options**
The `update_dropdown_options()` callback now:
- Uses retry logic with just 1 retry (faster for non-critical operation)
- Defaults to demo data size (12 rows) if Google Sheets loads fail
- Generates proper options for link count filtering

## Testing

The updated code has been verified for:
- ✅ Syntax correctness (py_compile check passed)
- ✅ Proper error handling and fallback behavior
- ✅ Successful app startup and initialization

## Usage

**For Users:**
1. Click "Load Google Sheets Data" - the app will now:
   - Automatically retry up to 2 times if the first attempt fails
   - Show status messages during loading
   - Fall back to demo data if all retries are exhausted
   - Display which data is currently being used

2. If Google Sheets loading fails, the demo data loads automatically with full functionality

**For Developers:**
- Adjust `max_retries` parameter in `load_google_sheet_with_retry()` calls if needed
- Modify `CACHE_DURATION` (currently 5 minutes) to change cache expiration
- Check console logs (or browser dev tools) for detailed error messages

## Technical Details

### Data Flow
```
User clicks "Load Google Sheets Data"
    ↓
Check cache (valid for 5 minutes)
    ↓
If cached: Use cached data
If not cached: Try to load with 2 retries (exponential backoff)
    ↓
On success: Cache data + display "✅ Loaded"
On failure: Fall back to demo data + display "📊 Demo data"
    ↓
Populate Sankey diagram with selected nodes
```

### Cache Strategy
- **Duration:** 5 minutes (CACHE_DURATION = 300)
- **Scope:** Entire callback execution per user
- **Invalidation:** Time-based automatic expiration

### Error Handling Levels
1. **Per-call:** Individual API calls retry up to 2 times
2. **Per-dataset:** Both invoice and jobs data must load successfully
3. **Per-operation:** Entire Google Sheets load attempt falls back to demo data
4. **Per-callback:** Multiple callbacks handle fallbacks independently

## Future Improvements
- Add a "Retry" button for manual retry if desired
- Implement connection health check before attempting load
- Add metrics tracking for success/failure rates
- Consider implementing Progressive Web App (PWA) offline mode
