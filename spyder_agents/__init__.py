"""Registry and helpers for Finance Tracker Spyder Agents.

Spyder Agents are lightweight, single-file scripts that can inspect the
live Google Sheet snapshots already loaded in memory. Each agent describes
which dataset it targets along with a callable that performs the work.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import bill_spyagn, inv_spyagn

AgentResult = Dict[str, Any]

AGENTS: Dict[str, Dict[str, Any]] = {
    "inv_spyagn": {
        "id": "inv_spyagn",
        "label": "Invoice Coverage (jobs_df)",
        "target": "jobs_df",
        "target_label": "jobs_df • Google Jobs tracker",
        "description": (
            "Adds an invoice_chk column that shows whether both worker and "
            "ACD invoice references are present for every job row."
        ),
        "runner": inv_spyagn.run,
    },
    "bill_spyagn": {
        "id": "bill_spyagn",
        "label": "Billing Cross-Check (inv_df)",
        "target": "inv_df",
        "target_label": "inv_df • Google Invoice tracker",
        "description": (
            "Verifies that each invoice recorded in inv_df is represented in "
            "jobs_df and annotates the invoice with the source row matches."
        ),
        "runner": bill_spyagn.run,
    },
}


def list_agents() -> List[Dict[str, Any]]:
    """Return agent metadata as a list."""

    return list(AGENTS.values())


def run_agent(agent_id: str, *, jobs_df=None, inv_df=None) -> AgentResult:
    """Execute an agent by id and enrich the returned payload."""

    agent = AGENTS.get(agent_id)
    if not agent:
        raise KeyError(f"Unknown spyder agent '{agent_id}'")

    result = agent["runner"](jobs_df=jobs_df, inv_df=inv_df)
    result.setdefault("agent_id", agent_id)
    result.setdefault("agent_label", agent["label"])
    result.setdefault("target", agent["target"])
    result.setdefault("target_label", agent.get("target_label", agent["target"]))
    return result


__all__ = ["AGENTS", "list_agents", "run_agent"]
