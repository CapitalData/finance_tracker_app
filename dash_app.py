import dash
from dash import dcc, html, Input, Output, State, ctx, ALL, no_update
from dash.dash_table import DataTable
import flask

import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import networkx as nx
import plotly.graph_objs as go
import io
import base64
import plotly.colors as pc
from plotly.subplots import make_subplots
import os
from datetime import datetime, timedelta
import threading
import time
import json
from dotenv import load_dotenv
from functools import lru_cache

# Import database module
import finance_db
import acd_datatool as acd
import sankey_helpers as sankey_utils
from spyder_agents import list_agents as spyder_list_agents, run_agent as spyder_run_agent

# Load environment variables from .env file
load_dotenv()

SPYDER_AGENT_LIST = spyder_list_agents()
SPYDER_AGENT_LOOKUP = {agent["id"]: agent for agent in SPYDER_AGENT_LIST}
SPYDER_AGENT_OPTIONS = [
    {"label": agent["label"], "value": agent["id"]}
    for agent in SPYDER_AGENT_LIST
]
DEFAULT_SPYDER_AGENT_ID = SPYDER_AGENT_LIST[0]["id"] if SPYDER_AGENT_LIST else None


##### TESTING FOR DASH_APP.py ##############
##### credentials through google cloud #####

# Initialize Flask server for session management
server = flask.Flask(__name__)
server.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Initialize Dash app with Flask server
app = dash.Dash(__name__, server=server)

#print(g_conect)
home=os.path.expanduser('~')

# Load environment variables
GOOGLE_SHEET_URL = os.getenv('GOOGLE_SHEET_URL')
LINKWARDEN_URL = os.getenv('LINKWARDEN_URL', 'http://localhost:3000')
QUICKLINKS_PASSWORD = os.getenv('QUICKLINKS_PASSWORD', 'finance2025')  # Legacy - will be deprecated

##for debugging just hardcode - <remove>.
GOOGLE_SHEET_URL ='https://docs.google.com/spreadsheets/d/1QEgmIzrVF7pJzzpYyacGHpW5VF0T7dTSu5te3rq2UlI/edit?gid=1122289088#gid=1122289088'


# Validate required environment variables
if not GOOGLE_SHEET_URL:
    
    raise ValueError("GOOGLE_SHEET_URL must be set in .env file")

# Load Quick Links configuration from JSON file
config_path = os.path.join(os.path.dirname(__file__), 'config', 'quick_links.json')
with open(config_path, 'r') as f:
    QUICK_LINKS_CONFIG = json.load(f)

# Replace placeholder with actual Google Sheet URL in config
for category in QUICK_LINKS_CONFIG.values():
    for link in category:
        if link['url'] == 'GOOGLE_SHEET_URL_PLACEHOLDER':
            link['url'] = GOOGLE_SHEET_URL

#'acd-fin-data@acd-internal-analytics.iam.gserviceaccount.com'
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_name(home+"/.ssh/acd-internal-analytics-375db6d96d79.json", SCOPE)


#print(CREDENTIALS)

try:
    df_google_sheet = acd.load_google_sheet(
        sankey_utils.DATA_NAMES[0],
        sankey_utils.EXPECTED_HEADERS[0],
        CREDENTIALS,
        GOOGLE_SHEET_URL,
    )  # Load `jobs_expense`
    print('loaded df_google_sheets')
except Exception as e:
    df_google_sheet = pd.DataFrame({"Error": [str(e)]})
    print('failed to load: df_google_sheets')

try:
    df_google_sheet2 = acd.load_google_sheet(
        sankey_utils.DATA_NAMES[1],
        sankey_utils.EXPECTED_HEADERS[1],
        CREDENTIALS,
        GOOGLE_SHEET_URL,
    )  # Load `inv_payment`
    print('loaded df_google_sheets 2')
    #display(df_google_sheet2.head())
except Exception as e:
    # Fallback in case of error
    df_google_sheet2 = pd.DataFrame({"Error": [str(e)]})
    print('failed to load: df_google_sheets 2', e)

# Initialize database
finance_db.init_database()

# Background thread for daily snapshot
def daily_snapshot_worker():
    """Background worker to capture daily snapshot once per day"""
    last_snapshot_date = None
    
    while True:
        try:
            today = datetime.now().date()
            
            # Check if we need to take a snapshot (once per day)
            if last_snapshot_date != today:
                # Check if both dataframes loaded successfully
                if not df_google_sheet2.empty and 'Error' not in df_google_sheet2.columns:
                    if not df_google_sheet.empty and 'Error' not in df_google_sheet.columns:
                        # Take snapshot
                        finance_db.save_daily_snapshot(df_google_sheet2, df_google_sheet)
                        last_snapshot_date = today
                        print(f"Daily snapshot captured for {today}")
            
            # Check again in 1 hour
            time.sleep(3600)
            
        except Exception as e:
            print(f"Error in daily snapshot worker: {e}")
            time.sleep(3600)  # Wait an hour before retrying

# Start background thread (daemon so it closes with main app)
snapshot_thread = threading.Thread(target=daily_snapshot_worker, daemon=True)
snapshot_thread.start()

# Status tracking for Sankey data loads
LAST_SANKEY_STATUS = {"message": "⏳ Waiting for data...", "level": "info"}


def set_sankey_status(message, level="info"):
    """Update the shared status banner text for the Sankey tab."""
    global LAST_SANKEY_STATUS
    LAST_SANKEY_STATUS = {"message": message, "level": level}

# Helper functions for Quick Links Tab
def create_link_button(name, url, featured=False):
    """Create a styled 3D button link"""
    button_class = "link-button featured" if featured else "link-button"
    
    return html.A(
        html.Button(name, className=button_class),
        href=url,
        target="_blank",
        style={"textDecoration": "none"}
    )

def create_link_category(category_name, links, icon=''):
    """Create a category section with multiple links"""
    # Special handling for Invoice buckets to create DAG visualization
    if category_name.lower() == 'invoice buckets':
        return create_invoice_dag(category_name, links, icon)
    
    # Default category layout for non-DAG categories
    return html.Div([
        html.H3(f"{icon} {category_name}", className="category-title"),
        html.Div([
            create_link_button(link['name'], link['url'])
            for link in links
        ], className="link-grid")
    ], className="link-category")

def create_invoice_dag(category_name, links, icon=''):
    """Create a DAG visualization for invoice workflow with clickable visual flowchart"""
    
    return html.Div([
        html.H3(f"{icon} {category_name}", className="dag-title"),
        
        # Clickable CSS-based flowchart
        html.Div([
            html.H4("🖱️ Interactive Workflow", className="dag-subtitle"),
            
            # Visual flowchart using CSS boxes and arrows - now clickable
            html.Div([
                # Top clickable box
                html.A(
                    html.Div("ACD Graph", className="dag-box"),
                    href=links[0]['url'],
                    target="_blank",
                    style={"textDecoration": "none"}
                ),
                
                # Arrow down
                html.Div("⬇", className="dag-arrow"),
                
                # Second clickable box
                html.A(
                    html.Div("Invoice Templates", className="dag-box"),
                    href=links[1]['url'],
                    target="_blank",
                    style={"textDecoration": "none"}
                ),
                
                # Arrow down
                html.Div("⬇", className="dag-arrow"),
                
                # Third clickable box
                html.A(
                    html.Div("Pending Invoices", className="dag-box"),
                    href=links[2]['url'],
                    target="_blank",
                    style={"textDecoration": "none"}
                ),
                
                # Split arrows
                html.Div([
                    html.Div("↙", className="dag-arrow"),
                    html.Div("↘", className="dag-arrow")
                ], className="dag-split-arrows"),
                
                # Bottom clickable boxes
                html.Div([
                    html.A(
                        html.Div("Processed Worker Invoices", className="dag-box blue"),
                        href=links[3]['url'],
                        target="_blank",
                        style={"textDecoration": "none"}
                    ),
                    html.A(
                        html.Div("Processed ACD Invoices", className="dag-box purple"),
                        href=links[4]['url'],
                        target="_blank",
                        style={"textDecoration": "none"}
                    )
                ], className="dag-bottom-boxes")
                
            ], className="dag-flowchart")
        ], style={
            "backgroundColor": "rgba(255,255,255,0.1)",
            "padding": "20px",
            "borderRadius": "10px"
        })
        
    ], className="invoice-dag-container")


# ===========================
# AUTHENTICATION UI COMPONENTS
# ===========================

def create_auth_form():
    """Create the login/register form"""
    return html.Div([
        html.Div([
            html.H2("🔒 Quick Links Access", style={
                "color": "white",
                "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
                "textAlign": "center",
                "marginBottom": "20px"
            }),
            
            # Mode switcher
            html.Div([
                html.Button("Login", id="switch-to-login", n_clicks=0, style={
                    "padding": "10px 20px",
                    "fontSize": "14px",
                    "fontWeight": "bold",
                    "backgroundColor": "#4A90E2",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "5px 0 0 5px",
                    "cursor": "pointer",
                    "flex": "1"
                }),
                html.Button("Register", id="switch-to-register", n_clicks=0, style={
                    "padding": "10px 20px",
                    "fontSize": "14px",
                    "fontWeight": "bold",
                    "backgroundColor": "#6c757d",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "0 5px 5px 0",
                    "cursor": "pointer",
                    "flex": "1"
                })
            ], style={"display": "flex", "marginBottom": "25px"}),
            
            # Login form
            html.Div(id='login-form', children=[
                html.P("Please login to access Quick Links", style={
                    "color": "white",
                    "textShadow": "1px 1px 3px rgba(0,0,0,0.8)",
                    "textAlign": "center",
                    "fontSize": "16px",
                    "marginBottom": "20px"
                }),
                dcc.Input(
                    id='login-username-input',
                    type='text',
                    placeholder='Username or email',
                    style={
                        "width": "100%",
                        "padding": "12px",
                        "fontSize": "16px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "15px",
                        "boxSizing": "border-box"
                    }
                ),
                dcc.Input(
                    id='login-password-input',
                    type='password',
                    placeholder='Password',
                    style={
                        "width": "100%",
                        "padding": "12px",
                        "fontSize": "16px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "20px",
                        "boxSizing": "border-box"
                    }
                ),
                html.Button("Login", id="login-submit-btn", n_clicks=0, style={
                    "width": "100%",
                    "padding": "12px 30px",
                    "fontSize": "16px",
                    "fontWeight": "bold",
                    "backgroundColor": "#28a745",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "8px",
                    "boxShadow": "0 4px 0 #1e7e34, 0 6px 8px rgba(0,0,0,0.3)",
                    "cursor": "pointer"
                })
            ]),
            
            # Register form (hidden by default)
            html.Div(id='register-form', style={'display': 'none'}, children=[
                html.P("Create a new account", style={
                    "color": "white",
                    "textShadow": "1px 1px 3px rgba(0,0,0,0.8)",
                    "textAlign": "center",
                    "fontSize": "16px",
                    "marginBottom": "20px"
                }),
                dcc.Input(
                    id='register-username-input',
                    type='text',
                    placeholder='Username (min 3 characters)',
                    style={
                        "width": "100%",
                        "padding": "12px",
                        "fontSize": "16px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "15px",
                        "boxSizing": "border-box"
                    }
                ),
                dcc.Input(
                    id='register-email-input',
                    type='email',
                    placeholder='Email address',
                    style={
                        "width": "100%",
                        "padding": "12px",
                        "fontSize": "16px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "15px",
                        "boxSizing": "border-box"
                    }
                ),
                dcc.Input(
                    id='register-password-input',
                    type='password',
                    placeholder='Password (min 6 characters)',
                    style={
                        "width": "100%",
                        "padding": "12px",
                        "fontSize": "16px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "15px",
                        "boxSizing": "border-box"
                    }
                ),
                dcc.Input(
                    id='register-password-confirm-input',
                    type='password',
                    placeholder='Confirm password',
                    style={
                        "width": "100%",
                        "padding": "12px",
                        "fontSize": "16px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "20px",
                        "boxSizing": "border-box"
                    }
                ),
                html.Button("Create Account", id="register-submit-btn", n_clicks=0, style={
                    "width": "100%",
                    "padding": "12px 30px",
                    "fontSize": "16px",
                    "fontWeight": "bold",
                    "backgroundColor": "#28a745",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "8px",
                    "boxShadow": "0 4px 0 #1e7e34, 0 6px 8px rgba(0,0,0,0.3)",
                    "cursor": "pointer"
                })
            ]),
            
            # Message area
            html.Div(id='auth-message', style={
                "marginTop": "20px",
                "textAlign": "center",
                "fontWeight": "bold",
                "textShadow": "1px 1px 2px rgba(0,0,0,0.8)",
                "minHeight": "24px"
            }),
            
            # Hidden store for session
            dcc.Store(id='user-session-store', storage_type='session'),
            
            # Hidden logout button (placeholder for callback)
            html.Button(id='logout-btn', n_clicks=0, style={'display': 'none'}),
            html.Button(id='show-password-change-btn', n_clicks=0, style={'display': 'none'}),
            html.Button(id='update-password-btn', n_clicks=0, style={'display': 'none'}),
            html.Div(id='password-change-form', style={'display': 'none'}),
            dcc.Input(id='current-password-input', type='password', style={'display': 'none'}),
            dcc.Input(id='new-password-input', type='password', style={'display': 'none'}),
            dcc.Input(id='confirm-new-password-input', type='password', style={'display': 'none'}),
            html.Div(id='password-change-message', style={'display': 'none'})
            
        ], style={
            "backgroundColor": "rgba(0,0,0,0.6)",
            "padding": "50px",
            "borderRadius": "15px",
            "maxWidth": "500px",
            "margin": "100px auto",
            "border": "2px solid rgba(255,255,255,0.3)"
        })
    ])


def create_user_profile_panel(user_info):
    """Create user profile and account management panel"""
    return html.Div([
        html.Div([
            # User info header
            html.Div([
                html.H3(f"👤 Welcome, {user_info['username']}!", style={
                    "color": "white",
                    "margin": "0",
                    "textShadow": "2px 2px 4px rgba(0,0,0,0.8)"
                }),
                html.P(f"📧 {user_info['email']}", style={
                    "color": "rgba(255,255,255,0.8)",
                    "margin": "5px 0",
                    "textShadow": "1px 1px 3px rgba(0,0,0,0.8)"
                }),
                html.P(f"🔐 Account created: {user_info.get('created_at', 'N/A')[:10]}", style={
                    "color": "rgba(255,255,255,0.7)",
                    "margin": "5px 0",
                    "textShadow": "1px 1px 3px rgba(0,0,0,0.8)",
                    "fontSize": "14px"
                })
            ], style={
                "backgroundColor": "rgba(255,255,255,0.1)",
                "padding": "20px",
                "borderRadius": "10px",
                "marginBottom": "20px"
            }),
            
            # Account actions
            html.Div([
                html.Button("🔄 Change Password", id="show-password-change-btn", n_clicks=0, style={
                    "padding": "10px 20px",
                    "fontSize": "14px",
                    "fontWeight": "bold",
                    "backgroundColor": "#4A90E2",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "5px",
                    "cursor": "pointer",
                    "marginRight": "10px"
                }),
                html.Button("🚪 Logout", id="logout-btn", n_clicks=0, style={
                    "padding": "10px 20px",
                    "fontSize": "14px",
                    "fontWeight": "bold",
                    "backgroundColor": "#dc3545",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "5px",
                    "cursor": "pointer"
                })
            ], style={"marginBottom": "20px"}),
            
            # Password change form (hidden by default)
            html.Div(id='password-change-form', style={'display': 'none'}, children=[
                html.H4("Change Password", style={"color": "white", "textShadow": "2px 2px 4px rgba(0,0,0,0.8)"}),
                dcc.Input(
                    id='current-password-input',
                    type='password',
                    placeholder='Current password',
                    style={
                        "width": "100%",
                        "padding": "10px",
                        "fontSize": "14px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "10px",
                        "boxSizing": "border-box"
                    }
                ),
                dcc.Input(
                    id='new-password-input',
                    type='password',
                    placeholder='New password (min 6 characters)',
                    style={
                        "width": "100%",
                        "padding": "10px",
                        "fontSize": "14px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "10px",
                        "boxSizing": "border-box"
                    }
                ),
                dcc.Input(
                    id='confirm-new-password-input',
                    type='password',
                    placeholder='Confirm new password',
                    style={
                        "width": "100%",
                        "padding": "10px",
                        "fontSize": "14px",
                        "borderRadius": "5px",
                        "border": "2px solid #ccc",
                        "marginBottom": "15px",
                        "boxSizing": "border-box"
                    }
                ),
                html.Button("Update Password", id="update-password-btn", n_clicks=0, style={
                    "padding": "10px 20px",
                    "fontSize": "14px",
                    "fontWeight": "bold",
                    "backgroundColor": "#28a745",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "5px",
                    "cursor": "pointer"
                }),
                html.Div(id='password-change-message', style={
                    "marginTop": "10px",
                    "textAlign": "center",
                    "fontWeight": "bold"
                })
            ])
            
        ], style={
            "backgroundColor": "rgba(0,0,0,0.6)",
            "padding": "30px",
            "borderRadius": "10px",
            "maxWidth": "500px",
            "margin": "20px auto",
            "border": "2px solid rgba(255,255,255,0.3)"
        })
    ])


@app.callback(
    Output("sankey-graph", "figure"),
    [Input("load-demo", "n_clicks"),
     Input("load-google-data", "n_clicks"),
     Input("max-links-dropdown", "value"),
     Input({"type": "node-checkbox", "index": ALL}, "value")],
    prevent_initial_call=True  # Wait for pattern-matched checkboxes to be created first
)
def update_stacked_sankey(load_demo_clicks, load_google_clicks, max_links, selected_nodes_lists, datasets=None, 
    entity_type_mappings=None, entity_type_ls=None, 
    entity_type_exclude=['other'], verbose=False):
    """Makes a tiered sankey diagram, the number of tiers responds to the number of datasets 
    in the number if datasets submited in the datasets list"""
   
    # Flatten selected nodes from checkboxes
    selected_nodes = []
    if selected_nodes_lists:
        for node_list in selected_nodes_lists:
            if isinstance(node_list, list):
                selected_nodes.extend(node_list)
            elif node_list:
                selected_nodes.append(node_list)
    
    # Handle None max_links on initial load
    if max_links is None:
        max_links = 'all'
   
    # Determine which button was clicked or if it's initial load
    ctx_triggered = ctx.triggered

    button_id = ctx_triggered[0]['prop_id'].split('.')[0] if ctx_triggered else 'initial'
    
    cache_key = 'google_sheets_data'
    current_time = time.time()
    cache_entry = sankey_utils.GOOGLE_SHEETS_CACHE.get(cache_key)
    cached_datasets = cached_entity_list = cached_mappings = None
    cached_timestamp = None
    if cache_entry:
        cached_datasets, cached_entity_list, cached_mappings = cache_entry[0]
        cached_timestamp = cache_entry[1]
    
    is_google_request = button_id in ['initial', 'load-google-data'] or (load_demo_clicks == 0 and load_google_clicks == 0)
    force_demo = button_id == 'load-demo'
    error_message = None

    if force_demo:
        datasets, entity_type_ls, entity_type_mappings = sankey_utils.get_demo_datasets_and_mappings()
        set_sankey_status("📊 Demo data loaded", "info")
    else:
        used_cache_directly = False
        if cached_datasets is not None:
            cache_age = int(current_time - (cached_timestamp or current_time))
            if not is_google_request or cache_age < sankey_utils.CACHE_DURATION:
                datasets, entity_type_ls, entity_type_mappings = cached_datasets, cached_entity_list, cached_mappings
                used_cache_directly = True
                set_sankey_status(f"✅ Google Sheets data loaded (cached {cache_age}s old)", "success")

        if is_google_request and not used_cache_directly:
            try:
                df_inv = sankey_utils.load_google_sheet_with_retry(
                    sankey_utils.DATA_NAMES[1],
                    sankey_utils.EXPECTED_HEADERS[1],
                    CREDENTIALS,
                    GOOGLE_SHEET_URL,
                )
                if df_inv is None:
                    raise ValueError("Failed to load invoice data after retries")

                df_jobs = sankey_utils.load_google_sheet_with_retry(
                    sankey_utils.DATA_NAMES[0],
                    sankey_utils.EXPECTED_HEADERS[0],
                    CREDENTIALS,
                    GOOGLE_SHEET_URL,
                )
                if df_jobs is None:
                    raise ValueError("Failed to load jobs data after retries")

                datasets = [
                    pd.DataFrame({
                        "Source": df_inv['inv_from'].fillna('Unknown') if 'inv_from' in df_inv.columns else pd.Series(['Unknown'] * len(df_inv)),
                        "Target": df_inv['to_client'].fillna('Unknown') if 'to_client' in df_inv.columns else pd.Series(['Unknown'] * len(df_inv)),
                        "Status": df_inv['status'].fillna('N') if 'status' in df_inv.columns else pd.Series(['N'] * len(df_inv)),
                        "Tooltip": df_inv['invoice'].fillna('N/A') if 'invoice' in df_inv.columns else pd.Series(['N/A'] * len(df_inv))
                    }),
                    pd.DataFrame({
                        "Source": df_jobs['Teacher'].fillna('Unknown') if 'Teacher' in df_jobs.columns else pd.Series(['Unknown'] * len(df_jobs)),
                        "Target": df_jobs['End_client'].fillna('Unknown') if 'End_client' in df_jobs.columns else pd.Series(['Unknown'] * len(df_jobs)),
                        "Status": df_jobs['ACD_inv_status'].fillna('N') if 'ACD_inv_status' in df_jobs.columns else pd.Series(['N'] * len(df_jobs)),
                        "Tooltip": df_jobs['composite_job_ID'].fillna('N/A') if 'composite_job_ID' in df_jobs.columns else pd.Series(['N/A'] * len(df_jobs))
                    })
                ]

                entity_type_ls = ["worker", "training_co", "client", "other"]
                entity_mapping = sankey_utils.build_entity_mapping(df_inv, df_jobs)
                entity_type_mappings = [entity_mapping] * len(datasets)

                sankey_utils.GOOGLE_SHEETS_CACHE[cache_key] = ((datasets, entity_type_ls, entity_type_mappings), current_time)
                set_sankey_status("✅ Google Sheets data refreshed from source", "success")

            except Exception as e:
                error_message = str(e)
                print(f"Error loading Google Sheets data: {error_message}")
                import traceback
                traceback.print_exc()

                if cached_datasets is not None:
                    cache_age = int(current_time - (cached_timestamp or current_time))
                    datasets, entity_type_ls, entity_type_mappings = cached_datasets, cached_entity_list, cached_mappings
                    set_sankey_status(
                        f"⚠️ Showing cached Google Sheets data ({cache_age}s old) after error: {error_message}",
                        "warning"
                    )
                else:
                    set_sankey_status(f"❌ Error loading Google Sheets data: {error_message}", "error")

        if datasets is None and not is_google_request and cached_datasets is not None:
            datasets, entity_type_ls, entity_type_mappings = cached_datasets, cached_entity_list, cached_mappings

    if datasets is None:
        placeholder_msg = error_message or "No Google Sheets data available. Click 'Load Google Sheets Data'."
        fig = go.Figure()
        fig.add_annotation(
            text=placeholder_msg,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=16, color="#b22222"),
            align="center"
        )
        fig.update_layout(
            title="Sankey data unavailable",
            height=400,
            margin=dict(l=40, r=40, t=80, b=40)
        )
        return fig
        
    # Apply max_links filtering to all datasets
    if max_links != 'all' and max_links is not None:
        max_links_int = int(max_links)
        datasets = [df.head(max_links_int) if len(df) > max_links_int else df for df in datasets]
    
    # Apply node filtering ONLY if we have selected nodes AND there are nodes to filter
    # Skip filtering on initial load if selected_nodes is empty or contains empty lists
    has_selected_nodes = False
    if selected_nodes is not None and len(selected_nodes) > 0:
        # Check if we have actual node values (not just empty lists)
        has_selected_nodes = any(node for node in selected_nodes if node)
    
    if has_selected_nodes:
        filtered_datasets = []
        for df in datasets:
            # Filter rows where both Source and Target are in selected_nodes
            filtered_df = df[(df['Source'].isin(selected_nodes)) & (df['Target'].isin(selected_nodes))]
            # Only keep this filtered dataset if it has rows; otherwise keep original
            if len(filtered_df) > 0:
                filtered_datasets.append(filtered_df)
            else:
                filtered_datasets.append(df)  # Keep original if filter results in empty
        datasets = filtered_datasets

    # Ensure entity_type_ls and entity_type_mappings are always defined
    if 'entity_type_ls' not in locals() or entity_type_ls is None:
        _, entity_type_ls, _ = sankey_utils.get_demo_datasets_and_mappings()
    
    if 'entity_type_mappings' not in locals() or entity_type_mappings is None:
        _, _, demo_mappings = sankey_utils.get_demo_datasets_and_mappings()
        default_mapping = demo_mappings[0] if demo_mappings else {}
        entity_type_mappings = [default_mapping] * len(datasets)

    # make the layers conditional based on number of dataframes in dataset list
    dataset_ct=len(datasets)
    
    # Calculate dynamic height based on data complexity
    total_links = sum(len(df) for df in datasets)
    total_unique_nodes = len(set().union(*[set(df['Source']).union(set(df['Target'])) for df in datasets]))
    
    # Base height calculation: minimum 400px, then scale with data
    base_height = 400
    max_height =2000 # 1000 

    link_factor = max(1, total_links / 10) #50 # Scale factor based on number of links
    node_factor = max(1, total_unique_nodes / 20)  # Scale factor based on unique nodes
    dataset_factor = dataset_ct * 0.8  # Additional height per dataset
    dynamic_height = int(base_height * (link_factor + node_factor + dataset_factor))
    # Cap maximum height to prevent excessive sizes
    
    dynamic_height = min(dynamic_height, max_height)
    print(f"Dynamic height calculation: {total_links} links, {total_unique_nodes} nodes, {dataset_ct} datasets -> {dynamic_height}px")
    
    # Create subplots with domain type for Sankey diagrams
    fig = make_subplots(
        rows=dataset_ct, cols=1,
        specs=[[{"type": "domain"}] for _ in range(dataset_ct)],  # Each subplot is of type 'domain'
        shared_xaxes=False,
        vertical_spacing=0.08  # Reduced spacing to fit more content
    )

    d=entity_type_mappings[0]
    entity_types={k.casefold(): v for k, v in d.items()}
    entity_type_ls=[k.casefold() for k in entity_type_ls]
    add_to_fig=True
    entity_type_ls=[ent for ent in entity_type_ls if ent not in entity_type_exclude]
    #print(entity_type_ls)
    
    # Use the original entity mapping for node lookups
    entity_mapping = entity_type_mappings[0]
    
    #for i, (demo_data, entity_types) in enumerate(zip(datasets, entity_type_mappings), start=1):
    for i, (demo_data) in enumerate(datasets, start=1):
        ## sanitize case
        #print(i)
        
        # Determine unique nodes and assign x positions based on entity type
        unique_nodes = pd.concat([demo_data["Source"], demo_data["Target"]]).unique()
        unique_nodes_cln = []
        for ent in unique_nodes:
            entity_type = sankey_utils.get_entity_type(entity_mapping, ent)
            if entity_type and entity_type.casefold() in entity_type_ls:
                unique_nodes_cln.append(ent)
        unique_nodes = unique_nodes_cln

        # use the entity type list to explicitly control order
        entity_type_order = {etype: i for i, etype in enumerate(entity_type_ls)}
        
        if verbose:
            print(unique_nodes)
            print(entity_type_order)

        x_positions = []
        for node in unique_nodes:
            # skip entites that are not listed on in the current entity_type_ls
            try:
                entity_type = sankey_utils.get_entity_type(entity_mapping, node)
                if entity_type:
                    entity_type = entity_type.casefold()
                if entity_type in entity_type_order:
                    # Prevent division by zero when there's only one entity type
                    if len(entity_type_order) == 1:
                        x_positions.append(0.5)  # Center position for single entity type
                    else:
                        x_positions.append(entity_type_order[entity_type] / (len(entity_type_order) - 1))
                    if verbose:
                        print(f"adding {node} for entity_type {entity_type}")
            except Exception as e:
                if verbose:
                    print(f'not adding entity to x position {node} : {e}')
                continue


        # Group nodes by x position
        grouped_nodes = {etype: [] for etype in entity_type_order}
        for node in unique_nodes:
            # skip entites that are not listed on in the current entity_type_ls
            try:
                entity_type = sankey_utils.get_entity_type(entity_mapping, node)
                if entity_type:
                    entity_type = entity_type.casefold()
                if entity_type in grouped_nodes:
                    grouped_nodes[entity_type].append(node)
                    if verbose:
                        print(f"adding {node} for entity_type {entity_type}")
                        print(grouped_nodes)
            except Exception as e:
                if verbose:
                    print(f'not adding entity to node list {node}: {e}')
                continue

        # Assign vertical (y) positions with improved spacing for many nodes
        y_positions = []
        
        for etype in entity_type_order:
            # skip entites that are not listed on in the current entity_type_ls
            try: 
                group = grouped_nodes[etype]
                group_size = len(group)
                
                # Improved spacing calculation for crowded diagrams
                if group_size <= 5:
                    spacing = 1 / (group_size + 1)
                    positions = [(j + 1) * spacing for j in range(group_size)]
                else:
                    # For larger groups, use more compact spacing
                    margin = 0.1  # Leave some margin at top and bottom
                    available_space = 1 - 2 * margin
                    spacing = available_space / (group_size - 1) if group_size > 1 else 0
                    positions = [margin + j * spacing for j in range(group_size)]
                
                y_positions.extend(positions)
                if verbose:
                    print(f"adding {etype} for grouped_nodes[etype] {grouped_nodes[etype]} with positions {positions}")
            except Exception as e:
                #add_to_fig=False
                if verbose:
                    print(f'not adding entity to y position: {e}')
                continue
    
        # Generate indices for sources and targets
        print(f"demo data __*50 __*50 {demo_data.head}")
        node_indices = {node: idx for idx, node in enumerate(unique_nodes)}
        source_indices = demo_data["Source"].map(node_indices).tolist()
        target_indices = demo_data["Target"].map(node_indices).tolist()

        if verbose:
            print(f"datasets /n {datasets} /n entity type mappings /n {entity_type_mappings}")
            print(f"node_indices /n {node_indices} /n source_indices /n {source_indices}\
              target_indices /n {target_indices}, y_positions /n, {y_positions}")        
        
        # Create link colors
        colors = pc.qualitative.Set1
        status_ls = [i.lower() for i in demo_data["Status"]]
        #translate status to y/n
        ynmap={'':'n','?':'n', 'nd':'n', 'submitted':'n', 'paid':'y', 'unsubmitted':'n', 'pending':'n', 'void':'n'}
        status_ls = [ynmap.get(k, 'N') for k in status_ls]


        link_colors=[colors[2] if yn == 'y' else colors[0] for yn in status_ls]
    
        node_dict=dict(
                    pad=max(10, min(25, 300 // max(1, len(unique_nodes)))),  # Prevent division by zero
                    thickness=max(15, min(30, 500 // max(1, len(unique_nodes)))),  # Prevent division by zero
                    line=dict(color="black", width=0.5),
                    label=unique_nodes,
                    x=x_positions,
                    y=y_positions
                )

        # Extract tooltip data if available
        tooltip_data = demo_data["Tooltip"].tolist() if "Tooltip" in demo_data.columns else ["N/A"] * len(source_indices)
        
        link_dict=dict(
                    source=source_indices,
                    target=target_indices,
                    value=[1] * len(source_indices),  # Example values, can be adjusted
                    ## color these according to job status
                    color=link_colors,
                    customdata=tooltip_data,
                    hovertemplate='%{source.label} → %{target.label}<br>ID: %{customdata}<extra></extra>'
                )

        # Add Sankey diagram to the subplot
        fig.add_trace(
            go.Sankey(
                node=node_dict,
                link=link_dict
            ),
            row=i,
            col=1
        )

    # Update layout for subplots - dynamically calculate annotation positions
    dataset_titles = ["job requests", "invoicing transactions", "payments made", "additional data"]
    
    # Calculate dynamic y positions for annotations based on number of datasets
    annot_ls = []
    for idx in range(dataset_ct):
        # Calculate y position: start from top and distribute evenly
        if dataset_ct == 1:
            y_pos = 1.05  # Single dataset - place above
        else:
            # Multiple datasets - distribute from top to bottom with proper spacing
            y_spacing = 0.9 / dataset_ct  # 90% of height divided by number of datasets
            y_pos = 1.0 - (idx * y_spacing) + 0.05  # Start from top with small margin
        
        # Adjust font size based on available space
        font_size = max(10, min(14, 40 // max(1, dataset_ct)))  # Prevent division by zero
        
        annot_ls.append(dict(
            text=dataset_titles[idx] if idx < len(dataset_titles) else f"Dataset {idx + 1}",
            x=0.5, 
            y=y_pos,
            xref="paper", 
            yref="paper",
            showarrow=False,
            font=dict(size=font_size, color="darkblue", family="Arial Black")
        ))

    #flexable sankey graph updater
    fig.update_layout(annotations=annot_ls[0:dataset_ct],
    
        height=dynamic_height,  # Use dynamic height based on data complexity
        title="Stacked Sankey Diagrams",
        font=dict(size=max(8, min(12, 200 // max(1, total_unique_nodes)))),  # Prevent division by zero
        showlegend=False,
        margin=dict(l=50, r=50, t=80, b=50)  # Better margins for larger diagrams
    )
    return fig

# Initial load callback - creates initial sankey figure without node filters
@app.callback(
    Output("sankey-graph", "figure", allow_duplicate=True),
    [Input("load-demo", "n_clicks"),
     Input("load-google-data", "n_clicks")],
    prevent_initial_call='initial_duplicate'
)
def load_initial_sankey(load_demo_clicks, load_google_clicks):
    """Load sankey on initial page load with all data - no node filtering yet"""
    # Simply call the main function but without node filtering
    # by passing empty selected_nodes_lists and max_links='all'
    return update_stacked_sankey(
        load_demo_clicks, 
        load_google_clicks, 
        'all',  # Always load all links initially
        selected_nodes_lists=None  # No filtering on initial load
    )

# Callback to populate dropdown options based on data size
@app.callback(
    Output("max-links-dropdown", "options"),
    [Input("load-demo", "n_clicks"),
     Input("load-google-data", "n_clicks")],
    prevent_initial_call=False
)
def update_dropdown_options(load_demo_clicks, load_google_clicks):
    """Generate dropdown options based on the size of loaded data"""
    
    # Determine which button was clicked or if it's initial load
    ctx_triggered = ctx.triggered
    button_id = ctx_triggered[0]['prop_id'].split('.')[0] if ctx_triggered else 'initial'
    
    # Load data to determine size
    if button_id in ['initial', 'load-google-data'] or (load_demo_clicks == 0 and load_google_clicks == 0):
        try:
            # Load Google Sheets data to determine size with retry logic
            df_inv = sankey_utils.load_google_sheet_with_retry(
                sankey_utils.DATA_NAMES[1],
                sankey_utils.EXPECTED_HEADERS[1],
                CREDENTIALS,
                GOOGLE_SHEET_URL,
                max_retries=1,
            )
            df_jobs = sankey_utils.load_google_sheet_with_retry(
                sankey_utils.DATA_NAMES[0],
                sankey_utils.EXPECTED_HEADERS[0],
                CREDENTIALS,
                GOOGLE_SHEET_URL,
                max_retries=1,
            )
            
            if df_inv is not None and df_jobs is not None:
                # Use the larger dataset for dropdown options
                max_size = max(len(df_inv), len(df_jobs))
            else:
                raise ValueError("Failed to load data after retries")
        except Exception as e:
            # Fall back to demo data size if Google Sheets fail
            max_size = 12  # Demo data has 12 rows
    else:
        # Demo data size
        max_size = 12
    
    # Generate dropdown options: 5, 10, 20, 40, doubling up to data size
    options = [{"label": "All", "value": "all"}]
    
    current = 5
    while current <= max_size:
        options.append({"label": str(current), "value": str(current)})
        if current < 10:
            current = 10
        elif current < 20:
            current = 20
        elif current < 40:
            current = 40
        else:
            current *= 2
    
    return options

# Callback to populate node filter checklist with grouped nodes
@app.callback(
    [Output("node-filter-groups-container", "children"),
     Output("node-groups-store", "data")],
    [Input("load-demo", "n_clicks"),
     Input("load-google-data", "n_clicks")],
    prevent_initial_call=False
)
def update_node_checklist(load_demo_clicks, load_google_clicks):
    """Populate grouped nodes organized by column and role"""
    
    # Determine which button was clicked or if it's initial load
    ctx_triggered = ctx.triggered
    button_id = ctx_triggered[0]['prop_id'].split('.')[0] if ctx_triggered else 'initial'
    
    node_groups_data = {}
    
    # Load Google Sheets data by default (initial load) or when Google button clicked
    if button_id in ['initial', 'load-google-data'] or (load_demo_clicks == 0 and load_google_clicks == 0):
        try:
            # Load Google Sheets data with retry logic
            df_inv = sankey_utils.load_google_sheet_with_retry(
                sankey_utils.DATA_NAMES[1],
                sankey_utils.EXPECTED_HEADERS[1],
                CREDENTIALS,
                GOOGLE_SHEET_URL,
            )
            df_jobs = sankey_utils.load_google_sheet_with_retry(
                sankey_utils.DATA_NAMES[0],
                sankey_utils.EXPECTED_HEADERS[0],
                CREDENTIALS,
                GOOGLE_SHEET_URL,
            )
            
            if df_inv is not None and df_jobs is not None:
                # Group 1: Invoice Source (inv_from) - used in "invoicing transactions"
                if 'inv_from' in df_inv.columns:
                    inv_from_nodes = sorted([n for n in df_inv['inv_from'].dropna().unique() if str(n) != 'Unknown'])
                    if inv_from_nodes:
                        node_groups_data['Invoice Sources'] = {
                            'column': 'inv_from',
                            'role': 'Source',
                            'diagram': 'invoicing transactions',
                            'nodes': inv_from_nodes
                        }
                
                # Group 2: Invoice Target (to_client) - used in "invoicing transactions"
                if 'to_client' in df_inv.columns:
                    to_client_nodes = sorted([n for n in df_inv['to_client'].dropna().unique() if str(n) != 'Unknown'])
                    if to_client_nodes:
                        node_groups_data['Invoice Targets'] = {
                            'column': 'to_client',
                            'role': 'Target',
                            'diagram': 'invoicing transactions',
                            'nodes': to_client_nodes
                        }
                
                # Group 3: Job Source (Teacher) - used in "job requests"
                if 'Teacher' in df_jobs.columns:
                    teacher_nodes = sorted([n for n in df_jobs['Teacher'].dropna().unique() if str(n) != 'Unknown'])
                    if teacher_nodes:
                        node_groups_data['Job Sources'] = {
                            'column': 'Teacher',
                            'role': 'Source',
                            'diagram': 'job requests',
                            'nodes': teacher_nodes
                        }
                
                # Group 4: Job Target (End_client) - used in "job requests"
                if 'End_client' in df_jobs.columns:
                    end_client_nodes = sorted([n for n in df_jobs['End_client'].dropna().unique() if str(n) != 'Unknown'])
                    if end_client_nodes:
                        node_groups_data['Job Targets'] = {
                            'column': 'End_client',
                            'role': 'Target',
                            'diagram': 'job requests',
                            'nodes': end_client_nodes
                        }
            
            if not node_groups_data:
                raise ValueError("No nodes found in Google Sheets data")
            else:
                sankey_utils.set_last_google_node_groups(node_groups_data)
                
        except Exception as e:
            print(f"Error loading Google Sheets for node list: {e}")
            # Use last successful Google data if available
            cached_groups = sankey_utils.get_last_google_node_groups()
            if cached_groups:
                node_groups_data = cached_groups
            else:
                node_groups_data = {}
    
    demo_node_groups = sankey_utils.get_demo_node_groups()
    
    if button_id == 'load-demo':
        node_groups_data = demo_node_groups
    elif not node_groups_data:
        # If no Google data available, keep last cached Google data before falling back to demo
        cached_groups = sankey_utils.get_last_google_node_groups()
        if cached_groups:
            node_groups_data = cached_groups
        else:
            node_groups_data = demo_node_groups
    
    # Create the grouped UI elements
    ui_elements = sankey_utils.create_grouped_node_filter_ui(node_groups_data)
    
    return ui_elements, node_groups_data

# Callback to show loading status
@app.callback(
    Output("sankey-status-message", "children"),
    [Input("load-demo", "n_clicks"),
     Input("load-google-data", "n_clicks"),
     Input("sankey-graph", "figure")],
    prevent_initial_call=False
)
def update_sankey_status(load_demo_clicks, load_google_clicks, figure):
    """Display the latest Sankey data load status or error."""
    del load_demo_clicks, load_google_clicks, figure
    status = LAST_SANKEY_STATUS or {"message": "⏳ Initializing data...", "level": "info"}
    color_map = {
        "success": "#28a745",
        "info": "#007bff",
        "warning": "#d39e00",
        "error": "#dc3545"
    }
    style = {
        "color": color_map.get(status.get("level"), "#6c757d"),
        "fontWeight": "bold"
    }
    return html.Span(status.get("message", ""), style=style)

# Callback to handle select/deselect all buttons for grouped nodes
@app.callback(
    Output({"type": "node-checkbox", "index": ALL}, "value"),
    [Input("select-all-nodes-btn", "n_clicks"),
     Input("deselect-all-nodes-btn", "n_clicks")],
    prevent_initial_call=True
)
def update_node_selection(select_clicks, deselect_clicks):
    """Handle select all / deselect all button clicks"""
    ctx_triggered = ctx.triggered
    if not ctx_triggered:
        return no_update
    
    button_id = ctx_triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'select-all-nodes-btn':
        # Return list with node value for each checkbox (checked state)
        return [ctx.states_list[i]['id']['index'] for i in range(len(ctx.states_list))] if hasattr(ctx, 'states_list') else []
    elif button_id == 'deselect-all-nodes-btn':
        # Return empty list for each checkbox (unchecked state)
        return [[] for _ in range(len(ctx.triggered_id) if hasattr(ctx, 'triggered_id') else 0)]
    
    return no_update

# Callback to collect all selected nodes and apply filtering
@app.callback(
    Output("sankey-graph", "figure", allow_duplicate=True),
    [Input({"type": "node-checkbox", "index": ALL}, "value")],
    [State("sankey-graph", "figure")],
    prevent_initial_call=True
)
def apply_node_filter(selected_nodes_lists, current_figure):
    """Collect selected nodes from all checkboxes and trigger Sankey update"""
    # Flatten the list of selected nodes (each checkbox returns a list)
    selected_nodes = []
    if selected_nodes_lists:
        for node_list in selected_nodes_lists:
            if isinstance(node_list, list):
                selected_nodes.extend(node_list)
            elif node_list:
                selected_nodes.append(node_list)
    
    # If no nodes selected, return current figure (no update)
    if not selected_nodes:
        return current_figure if current_figure else no_update
    
    # Otherwise, trigger the Sankey graph update
    # The graph will be updated through the existing update_stacked_sankey callback
    # which reads from the node-filter-checklist value
    return current_figure if current_figure else no_update


@app.callback(
    [Output("owed2acd-summary", "children"), 
     Output("owed2worker-summary", "children"),
     Output("status-summary", "children")],
    [Input("run-script-btn2", "n_clicks"),
     Input("worker-filter2", "value")],  # Trigger on filter change too
    [State("worker-filter2", "value")]
)
def execute_python_script2(n_clicks, filter_trigger, worker_filter):
    # Always run (removed the n_clicks > 0 check to run on page load)
    if True:
        try:
            df_inv = acd.load_google_sheet(
                sankey_utils.DATA_NAMES[1],
                sankey_utils.EXPECTED_HEADERS[1],
                CREDENTIALS,
                GOOGLE_SHEET_URL,
            )  # Load `inv_tbl`
            df_jobs = acd.load_google_sheet(
                sankey_utils.DATA_NAMES[0],
                sankey_utils.EXPECTED_HEADERS[0],
                CREDENTIALS,
                GOOGLE_SHEET_URL,
            )  # Load `jobs_tbl`
        except Exception as e:
            return f"Error loading Google Sheet: {e}", f"Error loading Google Sheet: {e}", f"Error loading Google Sheet: {e}"
        
        df = df_inv  # Keep df for backward compatibility

        if worker_filter and worker_filter != "All" and 'inv_from' in df.columns:
            filtered_df = df[df['inv_from'] == worker_filter]
        else:
            filtered_df = df

        if 'owed2acd' in filtered_df.columns and 'owed2workers' in filtered_df.columns:
            # Calculate additional statistics
            filtered_df['owed2acd'] = pd.to_numeric(filtered_df['owed2acd'], errors='coerce')
            filtered_df['owed2workers'] = pd.to_numeric(filtered_df['owed2workers'], errors='coerce')

            # Drop NaN values (non-numeric entries)
            filtered_df = filtered_df.dropna(subset=['owed2acd', 'owed2workers'])

            owed2acd_stats = filtered_df['owed2acd'].describe()
            owed2acd_stats['Sum'] = filtered_df['owed2acd'].sum()
            owed2acd_stats['Average'] = filtered_df['owed2acd'].mean()

            owed2worker_stats = filtered_df['owed2workers'].describe()
            owed2worker_stats['Sum'] = filtered_df['owed2workers'].sum()
            owed2worker_stats['Average'] = filtered_df['owed2workers'].mean()

            # Format data for display
            owed2acd_summary = DataTable(
                columns=[{"name": col, "id": col} for col in owed2acd_stats.index],
                data=[{stat: f"{value:,.2f}" for stat, value in owed2acd_stats.items()}],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'fontSize': '16px'},
                style_header={'fontWeight': 'bold', 'backgroundColor': '#f4f4f4'},
                style_data_conditional=[{
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#f9f9f9'
                }]
            )

            owed2worker_summary = DataTable(
                columns=[{"name": col, "id": col} for col in owed2worker_stats.index],
                data=[{stat: f"{value:,.2f}" for stat, value in owed2worker_stats.items()}],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'fontSize': '16px'},
                style_header={'fontWeight': 'bold', 'backgroundColor': '#f4f4f4'},
                style_data_conditional=[{
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#f9f9f9'
                }]
            )
            
            # Collect status counts from all three sources
            inv_status_dict = {}
            acd_status_dict = {}
            wk_status_dict = {}
            
            # Get Invoices Status counts (normalize case)
            if 'status' in df_inv.columns:
                df_inv['status_normalized'] = df_inv['status'].str.lower().str.strip()
                inv_status_counts = df_inv['status_normalized'].value_counts()
                inv_status_total = len(df_inv['status_normalized'])
                for status, count in inv_status_counts.items():
                    percent = (count / inv_status_total) * 100 if inv_status_total > 0 else 0
                    inv_status_dict[str(status).capitalize()] = {'count': count, 'percent': percent}
            
            # Get Jobs ACD Invoice Status counts (normalize case)
            if 'ACD_inv_status' in df_jobs.columns:
                df_jobs['ACD_inv_status_normalized'] = df_jobs['ACD_inv_status'].str.lower().str.strip()
                acd_inv_status_counts = df_jobs['ACD_inv_status_normalized'].value_counts()
                acd_inv_status_total = len(df_jobs['ACD_inv_status_normalized'])
                for status, count in acd_inv_status_counts.items():
                    percent = (count / acd_inv_status_total) * 100 if acd_inv_status_total > 0 else 0
                    acd_status_dict[str(status).capitalize()] = {'count': count, 'percent': percent}
            
            # Get Jobs Worker Invoice Status counts (normalize case)
            if 'Wk_inv_status' in df_jobs.columns:
                df_jobs['Wk_inv_status_normalized'] = df_jobs['Wk_inv_status'].str.lower().str.strip()
                wk_inv_status_counts = df_jobs['Wk_inv_status_normalized'].value_counts()
                wk_inv_status_total = len(df_jobs['Wk_inv_status_normalized'])
                for status, count in wk_inv_status_counts.items():
                    percent = (count / wk_inv_status_total) * 100 if wk_inv_status_total > 0 else 0
                    wk_status_dict[str(status).capitalize()] = {'count': count, 'percent': percent}
            
            # Get all unique statuses across all three sources
            all_statuses = sorted(set(list(inv_status_dict.keys()) + list(acd_status_dict.keys()) + list(wk_status_dict.keys())))
            
            # Build combined table data
            combined_status_data = []
            for status in all_statuses:
                row = {'Status': status}
                
                # Invoices: Status
                if status in inv_status_dict:
                    row['Inv_Count'] = inv_status_dict[status]['count']
                    row['Inv_Percent'] = f"{inv_status_dict[status]['percent']:.1f}%"
                else:
                    row['Inv_Count'] = 'N/A'
                    row['Inv_Percent'] = 'N/A'
                
                # Jobs: ACD Invoice Status
                if status in acd_status_dict:
                    row['ACD_Count'] = acd_status_dict[status]['count']
                    row['ACD_Percent'] = f"{acd_status_dict[status]['percent']:.1f}%"
                else:
                    row['ACD_Count'] = 'N/A'
                    row['ACD_Percent'] = 'N/A'
                
                # Jobs: Worker Invoice Status
                if status in wk_status_dict:
                    row['Wk_Count'] = wk_status_dict[status]['count']
                    row['Wk_Percent'] = f"{wk_status_dict[status]['percent']:.1f}%"
                else:
                    row['Wk_Count'] = 'N/A'
                    row['Wk_Percent'] = 'N/A'
                
                combined_status_data.append(row)
            
            # Create single combined table with delimiters
            status_summary = DataTable(
                columns=[
                    {"name": "Status", "id": "Status"},
                    {"name": ["📄 Invoices: Status", "Count"], "id": "Inv_Count"},
                    {"name": ["📄 Invoices: Status", "Percent"], "id": "Inv_Percent"},
                    {"name": ["💼 Jobs: ACD Inv Status", "Count"], "id": "ACD_Count"},
                    {"name": ["💼 Jobs: ACD Inv Status", "Percent"], "id": "ACD_Percent"},
                    {"name": ["👥 Jobs: Worker Inv Status", "Count"], "id": "Wk_Count"},
                    {"name": ["👥 Jobs: Worker Inv Status", "Percent"], "id": "Wk_Percent"}
                ],
                data=combined_status_data,
                merge_duplicate_headers=True,
                style_table={'overflowX': 'auto'},
                style_cell={
                    'textAlign': 'center', 
                    'fontSize': '14px', 
                    'padding': '10px',
                    'minWidth': '80px',
                    'borderRight': '2px solid #BDC3C7'  # Add delimiter between sections
                },
                style_header={
                    'fontWeight': 'bold', 
                    'backgroundColor': '#34495E', 
                    'color': 'white',
                    'textAlign': 'center',
                    'borderRight': '2px solid #7F8C8D'  # Delimiter in header too
                },
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': '#F8F9FA'},
                    {'if': {'column_id': 'Status'}, 'fontWeight': 'bold', 'textAlign': 'left', 'borderRight': '3px solid #34495E'},
                    # Make section delimiters more prominent
                    {'if': {'column_id': 'Inv_Percent'}, 'borderRight': '3px solid #34495E'},
                    {'if': {'column_id': 'ACD_Percent'}, 'borderRight': '3px solid #34495E'},
                    
                    # Color N/A cells dark grey
                    {'if': {'filter_query': '{Inv_Count} = "N/A"', 'column_id': 'Inv_Count'}, 'backgroundColor': '#95A5A6', 'color': 'white'},
                    {'if': {'filter_query': '{Inv_Percent} = "N/A"', 'column_id': 'Inv_Percent'}, 'backgroundColor': '#95A5A6', 'color': 'white'},
                    {'if': {'filter_query': '{ACD_Count} = "N/A"', 'column_id': 'ACD_Count'}, 'backgroundColor': '#95A5A6', 'color': 'white'},
                    {'if': {'filter_query': '{ACD_Percent} = "N/A"', 'column_id': 'ACD_Percent'}, 'backgroundColor': '#95A5A6', 'color': 'white'},
                    {'if': {'filter_query': '{Wk_Count} = "N/A"', 'column_id': 'Wk_Count'}, 'backgroundColor': '#95A5A6', 'color': 'white'},
                    {'if': {'filter_query': '{Wk_Percent} = "N/A"', 'column_id': 'Wk_Percent'}, 'backgroundColor': '#95A5A6', 'color': 'white'},
                    
                    # Color "Paid" status green
                    {'if': {'filter_query': '{Status} = "Paid"'}, 'backgroundColor': '#D5F4E6', 'color': '#145A32'},
                    
                    # Color "Submitted" and "Pending" status light yellow
                    {'if': {'filter_query': '{Status} = "Submitted"'}, 'backgroundColor': '#FCF3CF', 'color': '#7D6608'},
                    {'if': {'filter_query': '{Status} = "Pending"'}, 'backgroundColor': '#FCF3CF', 'color': '#7D6608'},
                    
                    # Color other statuses light red with stripes (using repeating-linear-gradient effect)
                    {'if': {'filter_query': '{Status} != "Paid" && {Status} != "Submitted" && {Status} != "Pending" && {Status} != "N/A"'}, 
                     'backgroundColor': '#FADBD8', 
                     'backgroundImage': 'repeating-linear-gradient(45deg, transparent, transparent 10px, rgba(0,0,0,.03) 10px, rgba(0,0,0,.03) 20px)',
                     'color': '#943126'}
                ]
            )

            return owed2acd_summary, owed2worker_summary, status_summary

        else:
            return "Columns `owed2acd` or `owed2worker` not found in the data.", \
                   "Columns `owed2acd` or `owed2worker` not found in the data.", \
                   "Status columns not found."

    return "Press 'Run Script' to execute.", "Press 'Run Script' to execute.", "Press 'Run Script' to execute."

# Historical Trends Callback
@app.callback(
    [Output("historical-invoice-chart", "figure"),
     Output("historical-job-chart", "figure"),
     Output("historical-financial-chart", "figure"),
     Output("historical-summary", "children")],
    [Input("historical-days-dropdown", "value")]
)
def update_historical_charts(days):
    """Update historical trend charts based on selected timeframe"""
    try:
        # Get historical data
        df_hist = finance_db.get_historical_data(days=days)
        
        if df_hist.empty:
            empty_fig = go.Figure()
            empty_fig.add_annotation(
                text="No historical data yet. Data will be captured daily while the app runs.",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16)
            )
            return empty_fig, empty_fig, empty_fig, "No data available yet."
        
        # Invoice Status Chart
        invoice_fig = go.Figure()
        invoice_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['total_invoices'],
            name='Total Invoices', mode='lines+markers',
            line=dict(color='#3498DB', width=3)
        ))
        invoice_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['paid_invoices'],
            name='Paid', mode='lines+markers',
            line=dict(color='#28a745', width=2)
        ))
        invoice_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['pending_invoices'],
            name='Pending', mode='lines+markers',
            line=dict(color='#FFC300', width=2)
        ))
        invoice_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['submitted_invoices'],
            name='Submitted', mode='lines+markers',
            line=dict(color='#FF5733', width=2)
        ))
        invoice_fig.update_layout(
            title='Invoice Status Trends',
            xaxis_title='Date',
            yaxis_title='Count',
            hovermode='x unified',
            template='plotly_white'
        )
        
        # Job Status Chart
        job_fig = go.Figure()
        job_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['total_jobs'],
            name='Total Jobs', mode='lines+markers',
            line=dict(color='#9B59B6', width=3)
        ))
        job_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['acd_paid_jobs'],
            name='ACD Paid', mode='lines+markers',
            line=dict(color='#28a745', width=2)
        ))
        job_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['worker_paid_jobs'],
            name='Worker Paid', mode='lines+markers',
            line=dict(color='#1ABC9C', width=2)
        ))
        job_fig.update_layout(
            title='Job Status Trends',
            xaxis_title='Date',
            yaxis_title='Count',
            hovermode='x unified',
            template='plotly_white'
        )
        
        # Financial Metrics Chart
        financial_fig = go.Figure()
        financial_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['total_owed_to_acd'],
            name='Owed to ACD', mode='lines+markers',
            line=dict(color='#E74C3C', width=3)
        ))
        financial_fig.add_trace(go.Scatter(
            x=df_hist['date'], y=df_hist['total_owed_to_workers'],
            name='Owed to Workers', mode='lines+markers',
            line=dict(color='#3498DB', width=3)
        ))
        financial_fig.update_layout(
            title='Financial Trends',
            xaxis_title='Date',
            yaxis_title='Amount ($)',
            hovermode='x unified',
            template='plotly_white'
        )
        
        # Summary stats
        stats = finance_db.get_summary_stats()
        summary = html.Div([
            html.H4("Database Summary", style={"marginBottom": "15px"}),
            html.P(f"📊 Total days tracked: {stats.get('total_days', 0)}"),
            html.P(f"📅 Date range: {stats.get('first_date', 'N/A')} to {stats.get('last_date', 'N/A')}"),
            html.P(f"📄 Avg daily invoices: {stats.get('avg_daily_invoices', 0):.1f}"),
            html.P(f"💼 Avg daily jobs: {stats.get('avg_daily_jobs', 0):.1f}"),
            html.P(f"💰 Avg owed to ACD: ${stats.get('avg_daily_owed_acd', 0):,.2f}"),
            html.P(f"👥 Avg owed to workers: ${stats.get('avg_daily_owed_workers', 0):,.2f}"),
        ], style={
            "backgroundColor": "#F8F9FA",
            "padding": "20px",
            "borderRadius": "10px",
            "border": "2px solid #DEE2E6"
        })
        
        return invoice_fig, job_fig, financial_fig, summary
        
    except Exception as e:
        error_fig = go.Figure()
        error_fig.add_annotation(
            text=f"Error loading historical data: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color='red')
        )
        return error_fig, error_fig, error_fig, f"Error: {str(e)}"

# Time Series Callback for Google Sheet Viewer2
@app.callback(
    [Output("timeseries-inv-chart", "figure"),
     Output("timeseries-acd-chart", "figure"),
     Output("timeseries-wk-chart", "figure")],
    [Input("timeseries-window-slider", "value")]
)
def update_timeseries_charts(window_months):
    """Generate time-series charts with color-matched status lines"""
    try:
        # Get historical data
        days = window_months * 30  # Convert months to days
        df_hist = finance_db.get_historical_data(days=days)
        
        if df_hist.empty:
            empty_fig = go.Figure()
            empty_fig.add_annotation(
                text="No historical data yet. Data will be captured daily.",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=14)
            )
            empty_fig.update_layout(height=300)
            return empty_fig, empty_fig, empty_fig
        
        # Color mapping matching the table styling
        status_colors = {
            'paid': '#D5F4E6',        # Light green background
            'paid_line': '#145A32',   # Dark green line
            'submitted': '#FCF3CF',    # Light yellow background
            'submitted_line': '#7D6608',  # Brown line
            'pending': '#FCF3CF',      # Light yellow background
            'pending_line': '#7D6608', # Brown line
            'other': '#FADBD8',        # Light red background
            'other_line': '#943126'    # Dark red line
        }
        
        # Invoice Status Time Series
        inv_fig = go.Figure()
        inv_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['paid_invoices'],
            name='Paid',
            mode='lines+markers',
            line=dict(color=status_colors['paid_line'], width=3),
            marker=dict(size=6)
        ))
        inv_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['submitted_invoices'],
            name='Submitted',
            mode='lines+markers',
            line=dict(color=status_colors['submitted_line'], width=3),
            marker=dict(size=6)
        ))
        inv_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['pending_invoices'],
            name='Pending',
            mode='lines+markers',
            line=dict(color=status_colors['pending_line'], width=3, dash='dot'),
            marker=dict(size=6)
        ))
        inv_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['other_invoices'],
            name='Other',
            mode='lines+markers',
            line=dict(color=status_colors['other_line'], width=3),
            marker=dict(size=6)
        ))
        inv_fig.update_layout(
            title='📄 Invoice Status Trends',
            xaxis_title='Date',
            yaxis_title='Count',
            hovermode='x unified',
            template='plotly_white',
            height=350,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # ACD Job Status Time Series
        acd_fig = go.Figure()
        acd_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['acd_paid_jobs'],
            name='Paid',
            mode='lines+markers',
            line=dict(color=status_colors['paid_line'], width=3),
            marker=dict(size=6)
        ))
        acd_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['acd_submitted_jobs'],
            name='Submitted',
            mode='lines+markers',
            line=dict(color=status_colors['submitted_line'], width=3),
            marker=dict(size=6)
        ))
        acd_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['acd_pending_jobs'],
            name='Pending',
            mode='lines+markers',
            line=dict(color=status_colors['pending_line'], width=3, dash='dot'),
            marker=dict(size=6)
        ))
        acd_fig.update_layout(
            title='💼 Jobs: ACD Invoice Status Trends',
            xaxis_title='Date',
            yaxis_title='Count',
            hovermode='x unified',
            template='plotly_white',
            height=350,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # Worker Job Status Time Series
        wk_fig = go.Figure()
        wk_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['worker_paid_jobs'],
            name='Paid',
            mode='lines+markers',
            line=dict(color=status_colors['paid_line'], width=3),
            marker=dict(size=6)
        ))
        wk_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['worker_submitted_jobs'],
            name='Submitted',
            mode='lines+markers',
            line=dict(color=status_colors['submitted_line'], width=3),
            marker=dict(size=6)
        ))
        wk_fig.add_trace(go.Scatter(
            x=df_hist['date'], 
            y=df_hist['worker_pending_jobs'],
            name='Pending',
            mode='lines+markers',
            line=dict(color=status_colors['pending_line'], width=3, dash='dot'),
            marker=dict(size=6)
        ))
        wk_fig.update_layout(
            title='👥 Jobs: Worker Invoice Status Trends',
            xaxis_title='Date',
            yaxis_title='Count',
            hovermode='x unified',
            template='plotly_white',
            height=350,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        return inv_fig, acd_fig, wk_fig
        
    except Exception as e:
        error_fig = go.Figure()
        error_fig.add_annotation(
            text=f"Error loading time-series data: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=12, color='red')
        )
        error_fig.update_layout(height=300)
        return error_fig, error_fig, error_fig


@app.callback(
    Output("spyder-agent-description", "children"),
    [Input("spyder-agent-selector", "value")]
)
def update_spyder_agent_description(agent_id):
    agent = SPYDER_AGENT_LOOKUP.get(agent_id)
    if not agent:
        return html.Div(
            "Select one of the agents to see what data it inspects.",
            style={"fontStyle": "italic", "color": "#6c757d"}
        )

    return html.Div([
        html.H4(agent.get("label", "Spyder Agent"), style={"marginBottom": "8px"}),
        html.P(agent.get("description", ""), style={"marginBottom": "6px"}),
        html.Div([
            html.Span("Dataset: ", style={"fontWeight": "bold"}),
            html.Span(agent.get("target_label", agent.get("target", "")))
        ], style={"marginBottom": "4px"}),
        html.P(
            "Outputs stay inside the dashboard – no data leaves your machine.",
            style={"fontSize": "13px", "color": "#555"}
        )
    ], style={
        "backgroundColor": "rgba(255,255,255,0.92)",
        "padding": "15px",
        "borderRadius": "10px",
        "border": "1px solid #e0e0e0"
    })


@app.callback(
    [
        Output("spyder-agent-status", "children"),
        Output("spyder-agent-summary", "children"),
        Output("spyder-agent-table-title", "children"),
        Output("spyder-agent-table", "columns"),
        Output("spyder-agent-table", "data"),
        Output("spyder-std-out", "children"),
    ],
    [Input("spyder-agent-run-btn", "n_clicks")],
    [State("spyder-agent-selector", "value")],
    prevent_initial_call=False,
)
def execute_spyder_agent(n_clicks, agent_id):
    global df_google_sheet, df_google_sheet2
    agent = SPYDER_AGENT_LOOKUP.get(agent_id)
    if not agent:
        return (
            html.Span("No Spyder Agents registered.", style={"color": "#dc3545"}),
            html.Div("Add an agent under finance_tracker/spyder_agents to get started."),
            "No preview available",
            [],
            [],
            "Spyder std_out is idle because no agents are registered.",
        )

    if not n_clicks:
        return (
            html.Span(
                "Choose an agent and click 'Run Agent' to generate diagnostics.",
                style={"color": "#6c757d"}
            ),
            html.Div("Summary output will appear here."),
            "Awaiting agent run",
            [],
            [],
            "Spyder std_out will display agent logs after you run one.",
        )

    try:
        result = spyder_run_agent(
            agent_id,
            jobs_df=df_google_sheet,
            inv_df=df_google_sheet2,
        )
    except Exception as exc:
        return (
            html.Span(f"Error running agent: {exc}", style={"color": "#dc3545"}),
            html.Div("No summary produced."),
            "No preview available",
            [],
            [],
            f"Spyder std_out caught an exception while running {agent_id}: {exc}",
        )

    status = result.get("status", "success")
    status_color = "#28a745" if status == "success" else "#dc3545"
    status_children = html.Span(result.get("message", ""), style={
        "color": status_color,
        "fontWeight": "bold"
    })

    summary_dict = result.get("summary") or {}
    if summary_dict:
        summary_children = html.Ul([
            html.Li(f"{key}: {value}") for key, value in summary_dict.items()
        ], style={"margin": 0, "paddingLeft": "20px"})
    else:
        summary_children = html.Div("No summary metrics returned.")

    target_label = result.get("target_label", agent.get("target_label"))
    preview_columns = []
    preview_data = []
    table_title = f"{target_label} preview"

    updated_df = None
    if result.get("target") == "jobs_df" and result.get("updated_jobs") is not None:
        df_google_sheet = result["updated_jobs"]
        updated_df = df_google_sheet
    elif result.get("target") == "inv_df" and result.get("updated_invoices") is not None:
        df_google_sheet2 = result["updated_invoices"]
        updated_df = df_google_sheet2

    if updated_df is not None and not updated_df.empty:
        preview = updated_df.head(200)
        preview_columns = [{"name": col, "id": col} for col in preview.columns]
        preview_data = preview.to_dict("records")
        table_title = f"{target_label} preview (showing {len(preview_data)} of {len(updated_df)} rows)"
    else:
        preview_columns = []
        preview_data = []
        table_title = f"{target_label} returned no rows"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    agent_label = agent.get("label", agent_id)
    if updated_df is not None and not updated_df.empty:
        stdout_preview = updated_df.head(5)
        stdout_children = "\n".join([
            f"{timestamp} :: {agent_label} finished with status '{status}'.",
            f"Target {target_label} • showing top {len(stdout_preview)} of {len(updated_df)} rows:",
            stdout_preview.to_string(index=False),
        ])
    else:
        stdout_children = (
            f"{timestamp} :: {agent_label} finished with status '{status}' but no dataframe preview was produced."
        )

    return (
        status_children,
        summary_children,
        table_title,
        preview_columns,
        preview_data,
        stdout_children,
    )

# App Layout (Updated with the new tab)
app.layout = html.Div([
    html.H1("Unified Dashboard"),
    dcc.Tabs([
        dcc.Tab(label="Quick Links", children=[
            html.Div([
                # Authentication container - shows login/register forms
                html.Div(id='quicklinks-auth-container', children=[
                    create_auth_form()
                ]),
                
                # Content container (hidden until authenticated)
                html.Div(id='quicklinks-content-container', style={'display': 'none'}, children=[
                    # User profile panel (populated after login)
                    html.Div(id='quicklinks-user-profile'),
                    
                    html.H2("Quick Access Links", style={
                        "color": "white",
                        "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
                        "textAlign": "center",
                        "marginBottom": "30px",
                        "marginTop": "30px"
                    }),
                    
                    # Featured Link - Linkwarden
                    html.Div([
                        html.H3("🔖 Bookmark Manager", style={
                            "color": "white",
                            "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
                            "textAlign": "center"
                        }),
                        html.Div([
                            create_link_button(
                                "Open Linkwarden Dashboard",
                                LINKWARDEN_URL,
                                featured=True
                            )
                        ], style={"textAlign": "center", "marginBottom": "40px"})
                    ], style={
                        "backgroundColor": "rgba(74,144,226,0.2)",
                        "padding": "30px",
                        "borderRadius": "15px",
                        "marginBottom": "30px",
                        "border": "2px solid rgba(255,255,255,0.3)"
                    }),
                    
                    # Category Sections
                    create_link_category("Invoice buckets", QUICK_LINKS_CONFIG['Invoice buckets'], '📋'),
                    create_link_category("Payment Systems", QUICK_LINKS_CONFIG['Payment Systems'], '💳'),
                    create_link_category("Financial Documents", QUICK_LINKS_CONFIG['Financial Documents'], '📊'),
                    create_link_category("Communication", QUICK_LINKS_CONFIG['Communication'], '💬'),
                    create_link_category("Training Resources", QUICK_LINKS_CONFIG['Training Resources'], '📚'),
                ])
                
            ], style={
                "backgroundImage": "url('https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1600&q=80')",
                "backgroundSize": "cover",
                "backgroundPosition": "center",
                "backgroundRepeat": "no-repeat",
                "minHeight": "800px",
                "padding": "30px"
            })
        ]),
        dcc.Tab(label="Google Sheet Viewer2", children=[
            html.Div([
                html.H4("Filter by Worker2", style={"color": "white", "textShadow": "2px 2px 4px rgba(0,0,0,0.8)"}),
                dcc.Dropdown(
                    id="worker-filter2",
                    options=[
                        {"label": "All", "value": "All"}
                    ] + [{"label": worker, "value": worker} for worker in df_google_sheet2['inv_from'].unique()]
                    if 'inv_from' in df_google_sheet2.columns else [],
                    value="All"
                ),
                html.Button("Run Script", id="run-script-btn2", n_clicks=0),
                html.Div([
                    html.Div([
                        html.H5("Summary Statistics for owed2acd", style={"color": "white", "textShadow": "2px 2px 4px rgba(0,0,0,0.8)"}),
                        html.Div(id="owed2acd-summary")
                    ], style={"margin": "10px", "padding": "10px", "border": "1px solid #ccc", "borderRadius": "5px", "width": "45%", "display": "inline-block", "verticalAlign": "top", "backgroundColor": "rgba(255,255,255,0.9)"}),
                    html.Div([
                        html.H5("Summary Statistics for owed2worker", style={"color": "white", "textShadow": "2px 2px 4px rgba(0,0,0,0.8)"}),
                        html.Div(id="owed2worker-summary")
                    ], style={"margin": "10px", "padding": "10px", "border": "1px solid #ccc", "borderRadius": "5px", "width": "45%", "display": "inline-block", "verticalAlign": "top", "backgroundColor": "rgba(255,255,255,0.9)"}),
                ]),
                html.Div([
                    html.H5("Status Distribution Summary", style={"color": "white", "textShadow": "2px 2px 4px rgba(0,0,0,0.8)", "marginTop": "20px"}),
                    html.Div(id="status-summary")
                ], style={"margin": "10px", "padding": "15px", "border": "2px solid #4A90E2", "borderRadius": "5px", "backgroundColor": "rgba(255,255,255,0.95)"}),
                
                # Time Series Charts Section
                html.Div([
                    html.H4("📈 Historical Status Trends", style={
                        "color": "white", 
                        "textShadow": "2px 2px 4px rgba(0,0,0,0.8)", 
                        "marginTop": "30px",
                        "marginBottom": "20px",
                        "textAlign": "center"
                    }),
                    
                    # Slider for time window
                    html.Div([
                        html.Label("Time Window (Months):", style={
                            "color": "white",
                            "textShadow": "1px 1px 3px rgba(0,0,0,0.8)",
                            "fontWeight": "bold",
                            "marginRight": "15px",
                            "fontSize": "16px"
                        }),
                        dcc.Slider(
                            id="timeseries-window-slider",
                            min=1,
                            max=12,
                            step=1,
                            value=6,
                            marks={
                                1: {'label': '1mo', 'style': {'color': 'white', 'textShadow': '1px 1px 2px rgba(0,0,0,0.8)'}},
                                3: {'label': '3mo', 'style': {'color': 'white', 'textShadow': '1px 1px 2px rgba(0,0,0,0.8)'}},
                                6: {'label': '6mo', 'style': {'color': 'white', 'textShadow': '1px 1px 2px rgba(0,0,0,0.8)'}},
                                9: {'label': '9mo', 'style': {'color': 'white', 'textShadow': '1px 1px 2px rgba(0,0,0,0.8)'}},
                                12: {'label': '12mo', 'style': {'color': 'white', 'textShadow': '1px 1px 2px rgba(0,0,0,0.8)'}}
                            },
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], style={
                        "margin": "20px auto",
                        "padding": "20px",
                        "backgroundColor": "rgba(255,255,255,0.1)",
                        "borderRadius": "10px",
                        "maxWidth": "800px"
                    }),
                    
                    # Time series charts
                    html.Div([
                        dcc.Graph(id="timeseries-inv-chart", style={"backgroundColor": "white", "borderRadius": "10px", "padding": "10px", "marginBottom": "20px"}),
                        dcc.Graph(id="timeseries-acd-chart", style={"backgroundColor": "white", "borderRadius": "10px", "padding": "10px", "marginBottom": "20px"}),
                        dcc.Graph(id="timeseries-wk-chart", style={"backgroundColor": "white", "borderRadius": "10px", "padding": "10px", "marginBottom": "20px"})
                    ], style={"margin": "20px 10px"})
                    
                ], style={"marginTop": "30px"}),
                
                html.A(
                    html.Button("Finance Sheet", style={
                        "marginTop": "20px", 
                        "padding": "15px 30px", 
                        "fontSize": "18px",
                        "fontWeight": "bold",
                        "backgroundColor": "#28a745",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "8px",
                        "boxShadow": "0 6px 0 #1e7e34, 0 8px 10px rgba(0,0,0,0.3)",
                        "cursor": "pointer",
                        "transition": "all 0.1s",
                        "transform": "translateY(0)"
                    }),
                    href=GOOGLE_SHEET_URL,
                    target="_blank"
                )
            ], style={
                "backgroundImage": "url('https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1600&q=80')",
                "backgroundSize": "cover",
                "backgroundPosition": "center",
                "backgroundRepeat": "no-repeat",
                "minHeight": "800px",
                "padding": "20px"
            })
        ]),
        dcc.Tab(label="Historical Trends", children=[
            html.Div([
                html.H3("📈 Historical Metrics Dashboard", style={
                    "textAlign": "center",
                    "marginBottom": "20px",
                    "color": "#2C3E50"
                }),
                
                html.Div([
                    html.Label("Select Time Range:", style={"fontWeight": "bold", "marginRight": "10px"}),
                    dcc.Dropdown(
                        id="historical-days-dropdown",
                        options=[
                            {"label": "Last 7 Days", "value": 7},
                            {"label": "Last 14 Days", "value": 14},
                            {"label": "Last 30 Days", "value": 30},
                            {"label": "Last 60 Days", "value": 60},
                            {"label": "Last 90 Days", "value": 90},
                            {"label": "All Time", "value": 365}
                        ],
                        value=30,
                        style={"width": "200px", "display": "inline-block"}
                    )
                ], style={"textAlign": "center", "marginBottom": "30px"}),
                
                # Summary Stats Box
                html.Div(id="historical-summary", style={"marginBottom": "30px"}),
                
                # Charts
                html.Div([
                    dcc.Graph(id="historical-invoice-chart", style={"marginBottom": "30px"}),
                    dcc.Graph(id="historical-job-chart", style={"marginBottom": "30px"}),
                    dcc.Graph(id="historical-financial-chart")
                ]),
                
                html.Div([
                    html.P("💡 Data is automatically captured once per day while the dashboard is running.", 
                           style={"fontStyle": "italic", "color": "#7F8C8D", "textAlign": "center"}),
                    html.P("📍 Database location: finance_tracker.db", 
                           style={"fontStyle": "italic", "color": "#7F8C8D", "textAlign": "center"})
                ], style={"marginTop": "30px", "padding": "20px", "backgroundColor": "#ECF0F1", "borderRadius": "5px"})
                
            ], style={"padding": "20px"})
        ]),
                        dcc.Tab(label="Spyder Agents", children=[
                            html.Div([
                                html.H3("🕷️ Spyder Agents Lab", style={
                                    "textAlign": "center",
                                    "marginBottom": "5px",
                                    "color": "#222"
                                }),
                                html.P(
                                    "Run lightweight dataframe diagnostics without leaving the dashboard.",
                                    style={"textAlign": "center", "color": "#555", "marginBottom": "25px"}
                                ),
                                html.Div([
                                    html.Label("Select an agent:", style={"fontWeight": "bold", "marginBottom": "8px"}),
                                    dcc.RadioItems(
                                        id="spyder-agent-selector",
                                        options=SPYDER_AGENT_OPTIONS,
                                        value=DEFAULT_SPYDER_AGENT_ID,
                                        inputStyle={"marginRight": "8px"},
                                        labelStyle={"display": "block", "marginBottom": "6px", "fontWeight": "500"}
                                    )
                                ], style={
                                    "backgroundColor": "rgba(255,255,255,0.9)",
                                    "padding": "20px",
                                    "borderRadius": "10px",
                                    "border": "1px solid #e0e0e0",
                                    "marginBottom": "20px"
                                }),
                                html.Div(id="spyder-agent-description", style={"marginBottom": "20px"}),
                                html.Div([
                                    html.Button(
                                        "Run Agent",
                                        id="spyder-agent-run-btn",
                                        n_clicks=0,
                                        style={
                                            "padding": "12px 28px",
                                            "fontSize": "16px",
                                            "fontWeight": "bold",
                                            "backgroundColor": "#4A90E2",
                                            "color": "white",
                                            "border": "none",
                                            "borderRadius": "8px",
                                            "cursor": "pointer",
                                            "boxShadow": "0 4px 10px rgba(0,0,0,0.15)"
                                        }
                                    ),
                                    html.Span(
                                        "Preview limited to first 200 rows to keep the UI responsive.",
                                        style={"marginLeft": "15px", "color": "#6c757d"}
                                    )
                                ], style={"marginBottom": "15px"}),
                                html.Div(id="spyder-agent-status", style={
                                    "minHeight": "24px",
                                    "marginBottom": "15px"
                                }),
                                html.Div([
                                    html.H5("Agent Summary", style={"marginBottom": "10px"}),
                                    html.Div(id="spyder-agent-summary")
                                ], style={
                                    "backgroundColor": "rgba(248,249,250,0.95)",
                                    "padding": "15px",
                                    "borderRadius": "10px",
                                    "border": "1px solid #dee2e6",
                                    "marginBottom": "20px"
                                }),
                                html.Div([
                                    html.H5("Preview Table", id="spyder-agent-table-title", style={"marginBottom": "10px"}),
                                    DataTable(
                                        id="spyder-agent-table",
                                        data=[],
                                        columns=[],
                                        page_size=10,
                                        sort_action="native",
                                        filter_action="native",
                                        style_table={"overflowX": "auto"},
                                        style_cell={"textAlign": "left", "fontSize": "13px"},
                                        style_header={"fontWeight": "bold", "backgroundColor": "#f1f3f5"}
                                    )
                                ], style={
                                    "backgroundColor": "rgba(255,255,255,0.95)",
                                    "padding": "15px",
                                    "borderRadius": "10px",
                                    "border": "1px solid #e0e0e0",
                                    "marginBottom": "20px"
                                }),
                                html.Div([
                                    html.H5("Spyder std_out", style={"marginBottom": "10px"}),
                                    html.Pre(
                                        "Spyder std_out will display agent logs here.",
                                        id="spyder-std-out",
                                        style={
                                            "backgroundColor": "#0f172a",
                                            "color": "#e2e8f0",
                                            "padding": "15px",
                                            "borderRadius": "8px",
                                            "minHeight": "140px",
                                            "whiteSpace": "pre-wrap",
                                            "margin": 0,
                                            "fontSize": "13px",
                                            "fontFamily": "SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace",
                                        }
                                    )
                                ], style={
                                    "backgroundColor": "rgba(15,23,42,0.85)",
                                    "padding": "15px",
                                    "borderRadius": "10px",
                                    "border": "1px solid #0ea5e9",
                                    "marginBottom": "20px",
                                }),
                                html.Div([
                                    html.H5("How it works", style={"marginBottom": "10px"}),
                                    html.Ol([
                                        html.Li("Pick an agent to load its description."),
                                        html.Li("Click Run Agent to execute the script against in-memory Google Sheet data."),
                                        html.Li("Review the summary counts and preview table, then export directly from Google Sheets if needed.")
                                    ], style={"lineHeight": "1.6"})
                                ], style={
                                    "backgroundColor": "rgba(248,248,255,0.8)",
                                    "padding": "15px",
                                    "borderRadius": "10px",
                                    "border": "1px dashed #c5d0ff"
                                })
                            ], style={
                                "padding": "25px",
                                "maxWidth": "960px",
                                "margin": "0 auto",
                                "background": "linear-gradient(135deg, #f8fbff 0%, #eef5ff 100%)"
                            })
                        ]),
        dcc.Tab(label="Sankey Diagram", children=[
            html.H4("Sankey Diagram", style={"textAlign": "center", "marginBottom": "20px"}),
            html.Div([
                html.Button("Load Google Sheets Data", id="load-google-data", n_clicks=0, style={
                    "margin": "10px",
                    "padding": "12px 24px",
                    "fontSize": "16px",
                    "fontWeight": "bold",
                    "backgroundColor": "#28a745",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "8px",
                    "boxShadow": "0 4px 0 #1e7e34, 0 6px 8px rgba(0,0,0,0.3)",
                    "cursor": "pointer"
                }),
                html.Button("Load Demo Data", id="load-demo", n_clicks=0, style={
                    "margin": "10px",
                    "padding": "12px 24px",
                    "fontSize": "16px",
                    "fontWeight": "bold",
                    "backgroundColor": "#007bff",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "8px",
                    "boxShadow": "0 4px 0 #0056b3, 0 6px 8px rgba(0,0,0,0.3)",
                    "cursor": "pointer"
                })
            ], style={"textAlign": "center", "marginBottom": "20px"}),
            # Status message for data loading
            html.Div(id="sankey-status-message", style={
                "textAlign": "center", 
                "marginBottom": "20px",
                "padding": "10px",
                "minHeight": "20px",
                "fontSize": "14px"
            }),
            html.Div([
                html.Label("Maximum Links:", style={"fontWeight": "bold", "marginRight": "10px"}),
                dcc.Dropdown(
                    id="max-links-dropdown",
                    value="all",
                    clearable=False,
                    style={"width": "200px", "display": "inline-block"}
                )
            ], style={"textAlign": "center", "marginBottom": "20px"}),
            
            # Node filter checklist - organized by column groups
            html.Div([
                html.H5("🔍 Filter Nodes:", style={"fontWeight": "bold", "marginBottom": "10px"}),
                html.Div([
                    html.Button("Select All", id="select-all-nodes-btn", n_clicks=0, style={
                        "margin": "5px",
                        "padding": "8px 16px",
                        "fontSize": "14px",
                        "backgroundColor": "#007bff",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "5px",
                        "cursor": "pointer"
                    }),
                    html.Button("Deselect All", id="deselect-all-nodes-btn", n_clicks=0, style={
                        "margin": "5px",
                        "padding": "8px 16px",
                        "fontSize": "14px",
                        "backgroundColor": "#6c757d",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "5px",
                        "cursor": "pointer"
                    })
                ], style={"marginBottom": "10px"}),
                # Container for grouped nodes (will be populated by callback)
                html.Div(
                    id="node-filter-groups-container",
                    style={
                        "display": "flex",
                        "flexWrap": "nowrap",
                        "alignItems": "flex-start",
                        "gap": "12px",
                        "overflowX": "auto",
                        "overflowY": "hidden",
                        "padding": "1px", 
                        "border": "1px solid #ddd", 
                        "borderRadius": "5px", 
                        "backgroundColor": "#f9f9f9"
                    }
                ),
                # Hidden store for node groups metadata
                dcc.Store(id="node-groups-store", data={})
            ], style={"textAlign": "left", "marginBottom": "20px", "padding": "15px", 
                      "border": "2px solid #007bff", "borderRadius": "10px", "backgroundColor": "#f0f8ff"}),
            
            dcc.Graph(id="sankey-graph", style={"height": "600px"}),
        ]),
        
    ])
])

# ===========================
# REGISTER AUTHENTICATION CALLBACKS
# ===========================
import auth_callbacks
auth_callbacks.register_auth_callbacks(app)

# Run the app
if __name__ == "__main__":
    # Initialize database on startup
    print("Initializing finance tracker database...")
    finance_db.init_database()
    
    # Clean up any expired sessions
    expired = finance_db.cleanup_expired_sessions()
    if expired > 0:
        print(f"Cleaned up {expired} expired sessions")
    
    # Disable debug mode entirely if running from control panel
    from_control_panel = os.environ.get('LAUNCHED_FROM_CONTROL_PANEL') == 'true'
    app.run(
        debug=not from_control_panel,  # Disable debug when from control panel
        port=8051
    )