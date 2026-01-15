# Spyder Agents Reference

Spyder Agents are single-file diagnostics that run against the in-memory Google Sheet snapshots already loaded by `dash_app.py`. They never write back to Google Sheets and keep all processing local to your machine.

## Running Agents from the Dashboard

1. Open the **Spyder Agents** tab inside the Finance Tracker dashboard.
2. Pick an agent from the radio list to review its description and target dataset.
3. Click **Run Agent** to execute the script against the cached DataFrames (`jobs_df` and `inv_df`).
4. Review the status message, metric summary, and preview table (first 200 rows). Columns added by the agent stay in the in-memory DataFrame so you can re-run without losing context.

> Tip: The preview table is read-only. Export or copy rows directly from Google Sheets if you need to take further action.

## Available Agents

| Agent ID | Target Dataset | What It Checks | Output Columns |
|----------|----------------|----------------|----------------|
| `inv_spyagn` | `jobs_df` (Google Jobs tracker) | Ensures every job row links to both an ACD invoice and a worker invoice record. Rows missing either side get flagged. | Adds `invoice_chk` column with `acd_worker`, `acd_None`, `None_worker`, or `None` values. |
| `bill_spyagn` | `inv_df` (Google Invoice tracker) | Confirms that each invoice listed in `inv_df` exists somewhere inside `jobs_df` (`ACD_invoice`). Highlights invoices without job coverage. | Adds `job_matches` column with `match` or `missing`. |

## Creating New Agents

1. Drop a new Python file inside `finance_tracker/spyder_agents/` with a `run(**kwargs)` function.
2. Return a dictionary shaped like:
   ```python
   {
       "status": "success" | "error",
       "message": "Human friendly summary",
       "summary": {"metric": count, ...},
       "updated_jobs": jobs_df_optional,
       "updated_invoices": inv_df_optional,
       "target": "jobs_df" | "inv_df"
   }
   ```
3. Register the agent in `spyder_agents/__init__.py` by adding an entry to `AGENTS` with `id`, `label`, `target`, `target_label`, `description`, and `runner`.
4. Reload the Dash app. The new agent will appear automatically in the Spyder Agents tab.

Keep the scripts lightweight—each file should focus on a single responsibility so results remain simple to interpret.
