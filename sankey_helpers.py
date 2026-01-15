"""Utility helpers for Sankey visualizations and Google Sheet integrations."""

from __future__ import annotations

import copy
import time
from typing import Dict, List, Tuple

import pandas as pd
from dash import dcc, html

import acd_datatool as acd

# ---------------------------------------------------------------------------
# Google Sheets configuration
# ---------------------------------------------------------------------------
DATA_NAMES = ['jobs_tbl', 'inv_tbl']
EXPECTED_HEADERS = [
    ['Teacher', 'start_date', 'end_date', 'job', 'Task_Descr', 'subtask', 'type',
     'ACD_bill_dt', 'ACD_pay_dt', 'teacher_pay_dt', 'ACD_inv_status', 'ACD_invoice',
     'ACD_inv_link', 'Wk_inv_status', 'Worker_invoice', 'worker_inv_link',
     'Wk_Billed_dt', 'Inv_line_item', 'direct_client', 'End_client', 'project',
     'teacher_pay_amt', 'worker_item_rate', 'days', 'item_quantity',
     'ACD_billed_item_total', 'ACD_Item_Rate', 'ACD_overhead_Prc', 'ACD_day_rate',
     'notes', 'email thread', 'Kbflow_job_ID',
     'Composite_job_ID', 'JobID_external', 'process notes',
     'acc_work_order_id','acc_request_id','reggie_id'],
    ['invoice', 'inv_link', 'submitted_date', 'year', 'Inv_paid_date',
     'inv_paid_link', 'job_start', 'Job_end', 'to_client', 'broker_chain',
     'inv_from', 'end_client', 'job_name', 'task_descr', 'worker', 'status',
     'inv_dollars', 'net_pay', 'payment_total', 'ACD_Account_delta',
     'ACD_Acct_date', 'owed2acd', 'owed2workers', 'Employer_taxes', 'total_taxes',
     'payment_fees', 'thread', 'follow_up', 'notes', 'eteam_id', 'reggie_id', 
     'qb_invoice_id', 'qb_invoice_url', 'qb_sync_status', 'qb_synced_at', 'qb_error']
]

# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------
_DEMO_NODE_GROUPS = {
    'Clients (Sources)': {
        'column': 'Source',
        'role': 'Source',
        'diagram': 'job requests',
        'nodes': ["McNeil", "Paramount_ins", "Miramax", "Netflix"]
    },
    'Training Companies': {
        'column': 'Intermediate',
        'role': 'Source & Target',
        'diagram': 'job requests / payments',
        'nodes': ["Accelebrate", "BHanalytics", "WebAge"]
    },
    'ACD (Talent Co)': {
        'column': 'ACD',
        'role': 'Source & Target',
        'diagram': 'job requests / payments',
        'nodes': ["ACD"]
    },
    'Workers (Targets)': {
        'column': 'Target',
        'role': 'Target',
        'diagram': 'payments made',
        'nodes': ["K.Martin", "G.Kleemann", "K.Kamerkar"]
    },
    'Process Nodes': {
        'column': 'Demo',
        'role': 'Mixed',
        'diagram': 'additional data',
        'nodes': ["Region1", "ProcessM", "ProcessN", "Product1"]
    }
}

_DEMO_DATASETS_RAW = [
    {
        "Source": ["McNeil", "Paramount_ins", "Miramax", "Netflix", "Accelebrate",
                    "Accelebrate", "BHanalytics", "WebAge", "ACD", "ACD", "ACD", "ACD"],
        "Target": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge", "ACD",
                    "ACD", "ACD", "ACD", "K.Martin", "G.Kleemann", "K.Kamerkar",
                    "K.Martin"],
        "Status": ["Y", "Y", "Y", "N", "N", "N", "N", "N", "N", "N", "N", "N"],
        "Tooltip": ["JOB-001", "JOB-002", "JOB-003", "JOB-004", "JOB-005",
                     "JOB-006", "JOB-007", "JOB-008", "JOB-009", "JOB-010",
                     "JOB-011", "JOB-012"]
    },
    {
        "Source": ["McNeil", "Paramount_ins", "Miramax", "Netflix", "Accelebrate",
                    "Accelebrate", "BHanalytics", "WebAge", "ACD", "ACD", "ACD", "ACD"],
        "Target": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge", "ACD",
                    "ACD", "ACD", "ACD", "K.Martin", "G.Kleemann", "K.Kamerkar",
                    "K.Martin"],
        "Status": ["Y", "Y", "N", "N", "N", "N", "N", "N", "N", "N", "N", "N"],
        "Tooltip": ["INV-2401", "INV-2402", "INV-2403", "INV-2404", "INV-2405",
                     "INV-2406", "INV-2407", "INV-2408", "INV-2409", "INV-2410",
                     "INV-2411", "INV-2412"]
    },
    {
        "Source": ["McNeil", "Paramount_ins", "Miramax", "Netflix", "Accelebrate",
                    "Accelebrate", "BHanalytics", "WebAge", "ACD", "ACD", "ACD", "ACD"],
        "Target": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge", "ACD",
                    "ACD", "ACD", "ACD", "K.Martin", "G.Kleemann", "K.Kamerkar",
                    "K.Martin"],
        "Status": ["Y", "Y", "N", "N", "N", "N", "N", "N", "N", "N", "N", "N"],
        "Tooltip": ["INV-2501", "INV-2502", "INV-2503", "INV-2504", "INV-2505",
                     "INV-2506", "INV-2507", "INV-2508", "INV-2509", "INV-2510",
                     "INV-2511", "INV-2512"]
    },
    {
        "Source": ["Region1", "ProcessM", "ProcessN"],
        "Target": ["ProcessM", "ProcessN", "Product1"],
        "Status": ["N", "Y", "N"],
        "Tooltip": ["DEMO-001", "DEMO-002", "DEMO-003"]
    }
]

_DEMO_ENTITY_TYPE_LIST = ["client", "training_co", "talent_co", "worker"]
_DEMO_ENTITY_MAPPINGS = [
    {"McNeil": "client", "Paramount_ins": "client", "Netflix": "client",
     "Miramax": "client", "WebAge": "training_co", "BHanalytics": "training_co",
     "Accelebrate": "training_co", "ACD": "talent_co", "K.Martin": "worker",
     "K.Kamerkar": "worker", "G.Kleemann": "worker"},
    {"McNeil": "client", "Paramount_ins": "client", "Netflix": "client",
     "Miramax": "client", "WebAge": "training_co", "BHanalytics": "training_co",
     "Accelebrate": "training_co", "ACD": "talent_co", "K.Martin": "worker",
     "K.Kamerkar": "worker", "G.Kleemann": "worker"},
    {"McNeil": "client", "Paramount_ins": "client", "Netflix": "client",
     "Miramax": "client", "WebAge": "training_co", "BHanalytics": "training_co",
     "Accelebrate": "training_co", "ACD": "talent_co", "K.Martin": "worker",
     "K.Kamerkar": "worker", "G.Kleemann": "worker"},
    {"Region1": "client", "ProcessM": "training_co", "ProcessN": "talent_co",
     "Product1": "worker"}
]

# ---------------------------------------------------------------------------
# Global caches
# ---------------------------------------------------------------------------
GOOGLE_SHEETS_CACHE: Dict[str, Tuple[Tuple[List[pd.DataFrame], List[str], List[Dict[str, str]]], float]] = {}
CACHE_DURATION = 300  # seconds
_LAST_GOOGLE_NODE_GROUPS: Dict[str, Dict[str, str]] | None = None

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_entity_name(value):
    """Return a normalized key for case/whitespace-insensitive comparisons."""
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def normalize_mapping_keys(mapping):
    """Normalize all keys in an entity mapping dict."""
    return {normalize_entity_name(k): v for k, v in mapping.items()}


def get_entity_type(entity_mapping, node_name):
    """Helper to fetch an entity type for a node regardless of casing."""
    return entity_mapping.get(normalize_entity_name(node_name))

# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------

def load_google_sheet_with_retry(sheet_name, expected_headers, credentials, sheet_url, max_retries=2):
    """Load a Google Sheet with retry logic and better logging."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            print(f"Attempt {attempt + 1}/{max_retries + 1}: Loading '{sheet_name}' from Google Sheets...")
            df = acd.load_google_sheet(sheet_name, expected_headers, credentials, sheet_url)
            if df is None or df.empty:
                raise ValueError(f"Sheet '{sheet_name}' returned empty data")
            print(f"✓ Successfully loaded '{sheet_name}' ({len(df)} rows, {len(df.columns)} columns)")
            return df
        except Exception as exc:  # pragma: no cover - logging path
            last_error = str(exc)
            print(f"✗ Attempt {attempt + 1} failed: {last_error}")
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"  Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
    print(f"✗ Failed to load '{sheet_name}' after {max_retries + 1} attempts: {last_error}")
    return None

# ---------------------------------------------------------------------------
# Sankey UI helpers
# ---------------------------------------------------------------------------
def hex_to_rgba(hex_color, alpha=0.15):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def create_grouped_node_filter_ui(node_groups_data):
    """Create nested HTML structure for node filtering with groups."""
    group_elements = []
    sorted_groups = sorted(node_groups_data.items())
    for group_key, group_info in sorted_groups:
        column = group_info.get('column', 'Unknown')
        role = group_info.get('role', 'Unknown')
        diagram = group_info.get('diagram', 'Unknown')
        nodes = group_info.get('nodes', [])
        role_color = "#4CAF50" if role == "Source" else "#2196F3"
        role_bg = "rgba(76, 175, 80, 0.1)" if role == "Source" else "rgba(33, 150, 243, 0.1)"
        header = html.Div([
            html.Div([
                html.Span(f"{diagram}", style={"marginLeft": "10px", "color": "#666", "fontSize": "12px", "fontStyle": "italic", "display": "block"}),
                html.Span(f"📋 {column}", style={"fontWeight": "bold", "fontSize": "14px"}),
                html.Span(f"  [{role}]", style={"marginLeft": "10px", "color": role_color, "fontWeight": "bold"}),
            ], style={"marginBottom": "8px"})
        ], style={
            "backgroundColor": role_bg,
            "padding": "10px",
            "borderRadius": "5px",
            "borderLeft": f"4px solid {role_color}"
        })
        node_checkboxes = []
        for node in sorted(nodes):
            checkbox = html.Label([
                dcc.Checklist(
                    id={"type": "node-checkbox", "index": node},
                    options=[{"label": f"  {node}", "value": node}],
                    value=[node],
                    style={"display": "inline-block", "marginRight": "15px"}
                )
            ], style={"margin": "5px 0", "fontSize": "13px"})
            node_checkboxes.append(checkbox)
        group_box = html.Div([
            header,
            *node_checkboxes
        
        ], style={
            "backgroundColor": hex_to_rgba(role_color, 0.15),
            "border": f"1px solid {role_color}",
            "borderRadius": "8px",
            "padding": "12px",
            "marginBottom": "12px",
            "minWidth": "200px",
            "flex": "0 0 auto",
            "display": "flex",
            "flexDirection": "column"
        })
        group_elements.append(group_box)
    return group_elements if group_elements else [html.P("No nodes available", style={"color": "#999", "fontStyle": "italic"})]

# ---------------------------------------------------------------------------
# Demo data accessors
# ---------------------------------------------------------------------------

def get_demo_node_groups():
    return copy.deepcopy(_DEMO_NODE_GROUPS)


def get_demo_datasets_and_mappings():
    datasets = [pd.DataFrame(data) for data in _DEMO_DATASETS_RAW]
    entity_type_ls = list(_DEMO_ENTITY_TYPE_LIST)
    mappings = [normalize_mapping_keys(mapping.copy()) for mapping in _DEMO_ENTITY_MAPPINGS]
    return datasets, entity_type_ls, mappings

# ---------------------------------------------------------------------------
# Cached node grouping helpers
# ---------------------------------------------------------------------------

def set_last_google_node_groups(node_groups):
    global _LAST_GOOGLE_NODE_GROUPS
    _LAST_GOOGLE_NODE_GROUPS = copy.deepcopy(node_groups)


def get_last_google_node_groups():
    return copy.deepcopy(_LAST_GOOGLE_NODE_GROUPS)

# ---------------------------------------------------------------------------
# Entity mapping helpers
# ---------------------------------------------------------------------------

def build_entity_mapping(df_inv: pd.DataFrame, df_jobs: pd.DataFrame) -> Dict[str, str]:
    """Return normalized entity mapping from Google Sheet dataframes."""
    normalize = normalize_entity_name
    frames = []
    if 'inv_from' in df_inv.columns:
        frames.append(df_inv['inv_from'].dropna())
    if 'to_client' in df_inv.columns:
        frames.append(df_inv['to_client'].dropna())
    if 'Teacher' in df_jobs.columns:
        frames.append(df_jobs['Teacher'].dropna())
    if 'End_client' in df_jobs.columns:
        frames.append(df_jobs['End_client'].dropna())
    all_entities = pd.concat(frames).dropna().unique() if frames else []
    unique_teachers = {normalize(n) for n in df_jobs['Teacher'].dropna().unique()} if 'Teacher' in df_jobs.columns else set()
    unique_clients = {normalize(n) for n in df_inv['to_client'].dropna().unique()} if 'to_client' in df_inv.columns else set()
    entity_mapping = {}
    for name in all_entities:
        norm_name = normalize(name)
        if not norm_name:
            continue
        if norm_name in unique_teachers:
            entity_mapping[norm_name] = "worker"
        elif norm_name in unique_clients:
            entity_mapping[norm_name] = "client"
        else:
            entity_mapping[norm_name] = "other"
    return entity_mapping