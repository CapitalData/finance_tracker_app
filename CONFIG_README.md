# Configuration Management

This document explains how configuration is managed in the Finance Tracker application.

## Overview

The application uses a **hybrid configuration approach**:
- **Environment Variables** (`.env` file) for secrets and URLs
- **JSON Configuration** (`config/quick_links.json`) for Quick Links
- **In-code Configuration** (`dash_app.py`) for data structures that rarely change

## Setup Instructions

### 1. Install Required Package

```bash
pip install python-dotenv
```

### 2. Create Your .env File

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:
```env
GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/...
LINKWARDEN_URL=http://localhost:3000
QUICKLINKS_PASSWORD=your_secure_password
```

**⚠️ IMPORTANT:** Never commit `.env` to version control! It's already in `.gitignore`.

### 3. Create Your Quick Links File

Copy the template, then edit the generated file:

```bash
cp config/quick_links.example.json config/quick_links.json
```

Update `config/quick_links.json` with your own categories and links:

```json
{
  "Your Category": [
    {
      "name": "Link Name",
      "url": "https://example.com"
    }
  ]
}
```

**Note:** `config/quick_links.json` is ignored by Git so that your private URLs never leave your machine.

### 4. Define QuickBooks Direction Mapping

The Sankey and finance views use `config/qb_directions.json` to normalize invoice directions.
Start from the template:

```bash
cp config/qb_directions.example.json config/qb_directions.json
```

Fill in the buckets that match your Google Sheet values (`inv_from`, `inv_to`, aliases, etc.).
This file is also `.gitignore`d.

## File Structure

```
finance_tracker/
├── .env                    # Your secrets (DO NOT COMMIT)
├── .env.example           # Template for other users
├── .gitignore             # Protects .env from being committed
├── config/
│   ├── quick_links.example.json  # Template (safe to commit)
│   ├── qb_directions.example.json
│   └── *.json              # Real configs copied from the templates (gitignored)
├── dash_app.py            # Main application
└── CONFIG_README.md       # This file
```

## Configuration Files

### .env (Environment Variables)
**Purpose:** Store sensitive information and environment-specific settings

**Contains:**
- `GOOGLE_SHEET_URL` - URL to your Google Sheet
- `LINKWARDEN_URL` - URL to your Linkwarden instance
- `QUICKLINKS_PASSWORD` - Password for Quick Links tab

**Security:** Protected by `.gitignore`, never committed to version control

### config/quick_links.json / config/quick_links.example.json
**Purpose:** Quick Links tab configuration - easy to edit without touching code

**Benefits:**
- Non-developers can update links
- No code changes needed to add/remove links
- JSON validation helps prevent syntax errors
- Can be version controlled safely (no secrets)

**Structure:**
```json
{
  "Category Name": [
    {"name": "Display Name", "url": "https://..."}
  ]
}
```

**Special placeholder:** Use `"GOOGLE_SHEET_URL_PLACEHOLDER"` to reference the Google Sheet URL from `.env`

`config/quick_links.example.json` ships with placeholder sections so you can copy/paste without exposing production links.

### config/qb_directions.json / config/qb_directions.example.json
**Purpose:** Normalize `inv_from` and `inv_to` values into "money in" and "money out" groups for Sankey diagrams.

**Setup:**
1. Copy `config/qb_directions.example.json` to `config/qb_directions.json`
2. Replace the placeholder vendor/client names with the ones from your sheet columns
3. Keep aliases lowercase to match case-insensitive comparisons

**Structure:**
```json
{
  "money_in": ["Client A", "Client B"],
  "money_out": ["Vendor X", "Vendor Y"],
  "aliases": {"client a": "Client A"},
  "__reference_inv_from": ["..."],
  "__reference_inv_to": ["..."]
}
```

Only the arrays/object names matter—the leading `__` keys are helpers to remind you which values still need to be categorized.

### dash_app.py (In-Code Config)
**Purpose:** Configuration that requires code logic or rarely changes

**Contains:**
- `expected_head` - Google Sheet column headers
- `data_names` - Sheet names to load
- Database configuration
- Layout constants

## Benefits of This Approach

✅ **Security:** Secrets stay in `.env`, not in code
✅ **Flexibility:** Easy to change URLs and links without code changes  
✅ **Team Collaboration:** `.env.example` helps onboard new users
✅ **Version Control:** Safely commit config files, keep secrets local
✅ **Maintainability:** Separation of concerns - configs vs. logic

## Troubleshooting

### "GOOGLE_SHEET_URL must be set in .env file"
- Make sure you created `.env` file (copy from `.env.example`)
- Check that `GOOGLE_SHEET_URL` is set in `.env`
- Ensure no extra spaces around the `=` sign

### "FileNotFoundError: config/quick_links.json"
- The `config/` directory should be in the same folder as `dash_app.py`
- Check file permissions

### Links not updating
- Restart the Dash application after editing `config/quick_links.json`
- Check JSON syntax using a JSON validator

## Adding New Configuration

### For Secrets/URLs:
1. Add to `.env` file: `NEW_CONFIG=value`
2. Add to `.env.example` as template: `NEW_CONFIG=your_value_here`
3. Load in `dash_app.py`: `NEW_CONFIG = os.getenv('NEW_CONFIG')`

### For Quick Links:
1. Edit `config/quick_links.json`
2. Add new category or link
3. Restart the application

### For Static Data:
- Keep in `dash_app.py` if it's code-related and rarely changes
