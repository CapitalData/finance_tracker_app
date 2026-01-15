# Sankey Diagram Update Summary

## ✅ Changes Implemented

### 1. **Auto-Loading Google Sheets Data**
- The Sankey diagram now automatically loads your Google Sheets data when the page first loads
- Uses the same `acd.load_google_sheet()` function you provided
- Loads both `inv_tbl` and `jobs_tbl` sheets

### 2. **Two Button System**
- **"Load Google Sheets Data"** (Green button): Refreshes data from your Google Sheets
- **"Load Demo Data"** (Blue button): Loads the original demo dataset

### 3. **Smart Button Detection**
- Uses `ctx.triggered` to detect which button was clicked
- Initial page load automatically uses Google Sheets data
- Fallback to demo data if Google Sheets loading fails

### 4. **Data Transformation**
Your Google Sheets data is automatically converted to Sankey format:
```python
# Invoice data: inv_from → to_client (with status)
# Jobs data: Teacher → End_client (with ACD_inv_status)
```

### 5. **Fixed Configuration Issues**
- Completed the placeholder replacement code for Google Sheet URLs
- Fixed syntax errors in the configuration loading

## 🎯 How It Works

### Initial Load (Automatic)
1. Page loads → Sankey automatically loads Google Sheets data
2. Creates network diagrams from your invoice and job flows
3. If Google Sheets fail, falls back to demo data

### Manual Refresh
1. **Green Button**: Reload fresh data from Google Sheets
2. **Blue Button**: Switch back to demo data for comparison

## 📊 Data Mapping

Your Google Sheets columns are mapped as follows:

**Invoice Table (`inv_tbl`)**:
- Source: `inv_from` (who sent the invoice)
- Target: `to_client` (who received it)  
- Status: `status` (paid/pending/etc.)

**Jobs Table (`jobs_tbl`)**:
- Source: `Teacher` (who worked)
- Target: `End_client` (who paid)
- Status: `ACD_inv_status` (invoice status)

## 🛠️ Entity Classification
Entities are automatically classified as:
- **Worker**: Names appearing in `Teacher` column
- **Client**: Names appearing in `to_client` or `End_client` columns  
- **Other**: Everything else

## 🎨 Visual Features
- **Green Button**: Primary action (Google Sheets data)
- **Blue Button**: Secondary action (Demo data)
- Both buttons have 3D styling with hover effects
- Centered layout for better UX

## 🔄 Error Handling
- If Google Sheets fail to load, automatically falls back to demo data
- Error messages printed to console for debugging
- Robust exception handling prevents app crashes

## 🚀 Ready to Use!
1. Start your Dash app: `python dash_app.py`
2. Navigate to "Sankey Diagram" tab
3. Your Google Sheets data loads automatically!
4. Use buttons to switch between real and demo data

The Sankey diagram will now show the actual flow of invoices and jobs from your Google Sheets data, making it much more useful for analyzing your business workflows!