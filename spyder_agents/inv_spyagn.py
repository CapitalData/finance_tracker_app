"""Invoice coverage spyder agent for the jobs dataframe."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

TARGET_COLUMNS = ("ACD_invoice", "Worker_invoice")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return pd.notna(value)


def run(*, jobs_df: pd.DataFrame | None = None, inv_df: pd.DataFrame | None = None) -> Dict[str, Any]:
    """Annotate ``jobs_df`` with invoice coverage details."""

    del inv_df  # not used in this agent
    if jobs_df is None or jobs_df.empty:
        return {
            "status": "error",
            "message": "jobs_df is empty – load data before running inv_spyagn.",
            "updated_jobs": jobs_df,
            "summary": {},
            "target": "jobs_df",
        }

    missing_columns = [col for col in TARGET_COLUMNS if col not in jobs_df.columns]
    if missing_columns:
        return {
            "status": "error",
            "message": f"jobs_df missing required columns: {', '.join(missing_columns)}",
            "updated_jobs": jobs_df,
            "summary": {},
            "target": "jobs_df",
        }

    annotated = jobs_df.copy()

    def classify(row: pd.Series) -> str:
        acd_present = _has_value(row.get("ACD_invoice"))
        worker_present = _has_value(row.get("Worker_invoice"))
        if acd_present and worker_present:
            return "acd_worker"
        if acd_present and not worker_present:
            return "acd_None"
        if worker_present and not acd_present:
            return "None_worker"
        return "None"

    annotated["invoice_chk"] = annotated.apply(classify, axis=1)
    summary = annotated["invoice_chk"].value_counts(dropna=False).to_dict()

    total_flagged = summary.get("None", 0) + summary.get("None_worker", 0) + summary.get("acd_None", 0)
    message = (
        f"Analyzed {len(annotated)} job rows. "
        f"Flagged {total_flagged} rows that need invoice attention."
    )

    return {
        "status": "success",
        "message": message,
        "summary": summary,
        "updated_jobs": annotated,
        "target": "jobs_df",
    }
