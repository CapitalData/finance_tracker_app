"""Invoice cross-check spyder agent."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

INVOICE_COLUMN = "invoice"
JOB_INVOICE_COLUMN = "ACD_invoice"


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def run(*, jobs_df: pd.DataFrame | None = None, inv_df: pd.DataFrame | None = None) -> Dict[str, Any]:
    """Mark invoices that are missing jobs and vice versa."""

    if inv_df is None or inv_df.empty:
        return {
            "status": "error",
            "message": "inv_df is empty – load data before running bill_spyagn.",
            "updated_invoices": inv_df,
            "summary": {},
            "target": "inv_df",
        }

    if INVOICE_COLUMN not in inv_df.columns:
        return {
            "status": "error",
            "message": f"inv_df missing required column: {INVOICE_COLUMN}",
            "updated_invoices": inv_df,
            "summary": {},
            "target": "inv_df",
        }

    if jobs_df is None or jobs_df.empty:
        unique_jobs = set()
    else:
        if JOB_INVOICE_COLUMN not in jobs_df.columns:
            return {
                "status": "error",
                "message": f"jobs_df missing required column: {JOB_INVOICE_COLUMN}",
                "updated_invoices": inv_df,
                "summary": {},
                "target": "inv_df",
            }
        unique_jobs = {
            _normalize(value) for value in jobs_df[JOB_INVOICE_COLUMN].dropna().unique()
        }

    annotated = inv_df.copy()
    annotated["job_matches"] = annotated[INVOICE_COLUMN].apply(
        lambda value: "match" if _normalize(value) in unique_jobs else "missing"
    )

    summary = annotated["job_matches"].value_counts(dropna=False).to_dict()
    missing_count = summary.get("missing", 0)
    message = (
        f"Analyzed {len(annotated)} invoices. "
        f"Found {missing_count} invoices without matching jobs."
    )

    return {
        "status": "success",
        "message": message,
        "summary": summary,
        "updated_invoices": annotated,
        "target": "inv_df",
    }
