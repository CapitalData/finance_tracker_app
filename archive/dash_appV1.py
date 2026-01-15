import dash
from dash import dcc, html, Input, Output, State, ctx
from dash.dash_table import DataTable

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

# Import database module
import finance_db


##### TESTING FOR DASH_APP.py ##############
##### credentials through google cloud #####

# # Initialize Dash app
app = dash.Dash(__name__)

#print(g_conect)
home=os.path.expanduser('~')



#'acd-fin-data@acd-internal-analytics.iam.gserviceaccount.com'
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_name(home+"/.ssh/acd-internal-analytics-375db6d96d79.json", SCOPE)
GOOGLE_SHEET_URL = 'https://docs.google.com/spreadsheets/d/1QEgmIzrVF7pJzzpYyacGHpW5VF0T7dTSu5te3rq2UlI/edit?gid=1122289088#gid=1122289088'

# Configuration for Quick Links Tab
LINKWARDEN_URL = 'http://localhost:3000'  # Update with your Linkwarden instance URL
QUICKLINKS_PASSWORD = 'finance2025'  # Change this to your desired password

QUICK_LINKS_CONFIG = {
    'Invoice buckets': [
        {'name': 'ACD_graph', 'url': 'https://drive.google.com/drive/u/0/folders/0AKvBYKszvnoYUk9PVA'},
        {'name': 'invoice templates', 'url': 'https://drive.google.com/drive/u/0/folders/1rU8KzYcpyIWWASOdvyOwJP4s5tVZDg_z'},
        {'name': 'Pending invoices', 'url': 'https://drive.google.com/drive/u/0/folders/1ZWgOIAsO7l3DeOB3BodM7ofs0g4wM6yU'},
        {'name': 'processed worker invoices', 'url': 'https://drive.google.com/drive/u/0/folders/1AF8Q-HpDWco8859f7trb8juz-2hB9tVY'},
        {'name': 'processed ACD invoices', 'url': 'https://drive.google.com/drive/u/0/folders/1t31hmZUv9AauGruvFtNmx1x07mSrkaIx'},
    ],
    'Payment Systems': [
        {'name': 'PayPal', 'url': 'https://paypal.com'},
        {'name': 'Stripe Dashboard', 'url': 'https://dashboard.stripe.com'},
        {'name': 'Bank Portal', 'url': 'https://chase.com'},
    ],
    'Financial Documents': [
        {'name': 'Finance Tracker Sheet', 'url': GOOGLE_SHEET_URL},
        {'name': 'QuickBooks', 'url': 'https://quickbooks.intuit.com'},
        {'name': 'Google Drive', 'url': 'https://drive.google.com'},
    ],
    'Communication': [
        {'name': 'Gmail', 'url': 'https://mail.google.com'},
        {'name': 'Slack Workspace', 'url': 'https://slack.com'},
        {'name': 'Google Calendar', 'url': 'https://calendar.google.com'},
    ],
    'Training Resources': [
        {'name': 'Training Hub', 'url': 'https://traininghub.example.com'},
        {'name': 'Course Materials', 'url': 'https://materials.example.com'},
        {'name': 'Accelebrate', 'url': 'https://accelebrate.com'},
    ]
}

#data_names=['jobs_expense', 'inv_payment']
data_names=['jobs_tbl', 'inv_tbl']
expected_head=[
    ['Teacher',	'start_date',	'end_date',	'job',	'Task_Descr',	'subtask',	'type',	'ACD_bill_dt',	'ACD_pay_dt',	'teacher_pay_dt',	'ACD_inv_status',	'ACD_invoice',	'ACD_inv_link',	'Wk_inv_status',	'Worker_invoice',	'worker_inv_link',	'Wk_Billed_dt',	'Inv_line_item',	'direct_client',	'End_client',	'project',	'teacher_pay_amt',	'worker_item_rate',	'days',	'item_quantity',	'ACD_billed_item_total',	'ACD_Item_Rate',	'ACD_overhead_Prc',	'ACD_day_rate',	'notes',	'email thread',	'Kbflow_job_ID',	'training hub link',	'Reggie_ID',	'Composite_job_ID',	'JobID_external',	'process notes'],
    ['invoice',	'inv_link',	'submitted_date',	'year',	'Inv_paid_date',	'inv_paid_link',	'job_start',	'Job_end',	'to_client',	'broker_chain',	'inv_from',	'end_client',	'job_name',	'task_descr',	'worker',	'status',	'inv_dollars',	'net_pay',	'payment_total',	'ACD_Account_delta',	'ACD_Acct_date',	'owed2acd',	'owed2workers',	'Employer_taxes',	'total_taxes',	'payment_fees',	'thread',	'follow_up',	'blank1',	'blank2',	'owed to workers']
    ]


#print(CREDENTIALS)

def load_google_sheet(worksheet_nm, headers=None):
    client = gspread.authorize(CREDENTIALS)
    sheet_overview = client.open_by_url(GOOGLE_SHEET_URL)
    #worksheet = sheet_overview.get_worksheet(0)  # Load the first sheet
    
    ### get the data row-wise ###
    curr_wks=sheet_overview.worksheet(worksheet_nm).get_all_records(expected_headers=headers)

    # get_all_values gives a list of rows
    return pd.DataFrame.from_records(curr_wks)

try:
     df_google_sheet = load_google_sheet(data_names[0], headers=expected_head[0])  # Load `jobs_expense`
     print('loaded df_google_sheets')
except Exception as e:
     df_google_sheet = pd.DataFrame({"Error": [str(e)]})
     print('failed to load: df_google_sheets')

try:
    df_google_sheet2 = load_google_sheet(data_names[1], headers=expected_head[1])  # Load `inv_payment`
    print('loaded df_google_sheets 2')
    #display(df_google_sheet2.head())
except Exception as e:
    # Fallback in case of error
    df_google_sheet2 = pd.DataFrame({"Error": [str(e)]})
    print('failed to load: df_google_sheets 2', print(e))

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

# Helper functions for Quick Links Tab
def create_link_button(name, url, style_override=None):
    """Create a styled 3D button link"""
    default_style = {
        "margin": "10px",
        "padding": "12px 24px",
        "fontSize": "16px",
        "fontWeight": "bold",
        "backgroundColor": "#28a745",
        "color": "white",
        "border": "none",
        "borderRadius": "8px",
        "boxShadow": "0 4px 0 #1e7e34, 0 6px 8px rgba(0,0,0,0.3)",
        "cursor": "pointer",
        "textDecoration": "none",
        "display": "inline-block",
        "minWidth": "200px",
        "textAlign": "center"
    }
    
    if style_override:
        default_style.update(style_override)
    
    return html.A(
        html.Button(name, style=default_style),
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
        html.H3(f"{icon} {category_name}", style={
            "color": "white",
            "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
            "marginTop": "20px",
            "marginBottom": "15px"
        }),
        html.Div([
            create_link_button(link['name'], link['url'])
            for link in links
        ], style={"display": "flex", "flexWrap": "wrap", "gap": "10px"})
    ], style={
        "backgroundColor": "rgba(255,255,255,0.1)",
        "padding": "20px",
        "borderRadius": "10px",
        "marginBottom": "20px"
    })

def create_invoice_dag(category_name, links, icon=''):
    """Create a DAG visualization for invoice workflow"""
    # Define the workflow stages in order
    # ACD_graph -> invoice templates -> Pending invoices -> [processed worker invoices, processed ACD invoices]
    
    arrow_style = {
        "fontSize": "30px",
        "color": "#FFD700",
        "margin": "0 15px",
        "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
        "alignSelf": "center"
    }
    
    return html.Div([
        html.H3(f"{icon} {category_name}", style={
            "color": "white",
            "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
            "marginTop": "20px",
            "marginBottom": "25px",
            "textAlign": "center"
        }),
        
        # Stage 1: ACD_graph
        html.Div([
            create_link_button(links[0]['name'], links[0]['url'])
        ], style={"display": "flex", "justifyContent": "center", "marginBottom": "10px"}),
        
        # Arrow down
        html.Div("⬇", style={**arrow_style, "textAlign": "center", "fontSize": "40px"}),
        
        # Stage 2: invoice templates
        html.Div([
            create_link_button(links[1]['name'], links[1]['url'])
        ], style={"display": "flex", "justifyContent": "center", "marginBottom": "10px"}),
        
        # Arrow down
        html.Div("⬇", style={**arrow_style, "textAlign": "center", "fontSize": "40px"}),
        
        # Stage 3: Pending invoices
        html.Div([
            create_link_button(links[2]['name'], links[2]['url'])
        ], style={"display": "flex", "justifyContent": "center", "marginBottom": "10px"}),
        
        # Split arrows (fork)
        html.Div([
            html.Div("⬇", style={**arrow_style, "fontSize": "40px", "marginRight": "150px"}),
            html.Div("⬇", style={**arrow_style, "fontSize": "40px", "marginLeft": "150px"})
        ], style={"display": "flex", "justifyContent": "center", "gap": "20px"}),
        
        # Stage 4: Final processing (two parallel branches)
        html.Div([
            create_link_button(links[3]['name'], links[3]['url'], style_override={"backgroundColor": "#4A90E2", "boxShadow": "0 4px 0 #2E5C8A, 0 6px 8px rgba(0,0,0,0.3)"}),
            create_link_button(links[4]['name'], links[4]['url'], style_override={"backgroundColor": "#9B59B6", "boxShadow": "0 4px 0 #6C3483, 0 6px 8px rgba(0,0,0,0.3)"})
        ], style={"display": "flex", "justifyContent": "center", "gap": "30px"})
        
    ], style={
        "backgroundColor": "rgba(255,255,255,0.1)",
        "padding": "30px",
        "borderRadius": "10px",
        "marginBottom": "20px"
    })

# Demo Data: NetworkX
data = {
    "Entity": ["Node1", "Node2", "Node3", "Node4", "Node5"],
    "Next": ["Node2", "Node3", "Node4", "Node5", None],
    "Category": ["A", "A", "B", "B", "C"]
}
df_networkx = pd.DataFrame(data)

# Demo Data: Sankey Diagram and 3D Directed Force Graph
# '{client}-job->{edu_cont_co}-job->{talent_co}<-invoice/job->{worker}'
sankey_demo_data = pd.DataFrame({
    "Source1": ["McNeil", "Paramount_ins", "Miramax", "Netflix"],
    "Target1": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge"],
    "Source2": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge"],
    "Target2": ["ACD", "ACD", "ACD", "ACD"],
    "Source3": ["ACD", "ACD", "ACD", "ACD"],
    "Target3": ["K.Martin", "GKleemann", "K.Kamerkar", "K.Martin"],
    "Source4": ["K.Martin", "GKleemann", "K.Kamerkar", "K.Martin"],
    "Target4": ["ACD", "ACD", "ACD", "ACD"],
    "Source5": ["ACD", "ACD", "ACD", "ACD"],
    "Target5": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge"],
    "Source6": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge"],
    "Target6": ["McNeil", "Paramount_ins", "Miramax", "Netflix"]
    }) 

# Generate edges and nodes for Sankey and 3D Graph
def get_edges_from_sankey(df):
    edges = []
    for col_idx in range(0, len(df.columns), 2):
        source_col = df.columns[col_idx]
        target_col = df.columns[col_idx + 1]
        for src, tgt in zip(df[source_col], df[target_col]):
            edges.append((src, tgt, f"{src}->{tgt}"))
    return edges

edges_with_labels = get_edges_from_sankey(sankey_demo_data)
nodes = list(set([e[0] for e in edges_with_labels] + [e[1] for e in edges_with_labels]))

# Create 3D Directed Force Graph
G_3d = nx.DiGraph()
for src, tgt, label in edges_with_labels:
    G_3d.add_edge(src, tgt, label=label)

pos_3d = nx.spring_layout(G_3d, dim=3, seed=42)
node_x_3d = [pos_3d[node][0] for node in G_3d.nodes()]
node_y_3d = [pos_3d[node][1] for node in G_3d.nodes()]
node_z_3d = [pos_3d[node][2] for node in G_3d.nodes()]

edge_x_3d = []
edge_y_3d = []
edge_z_3d = []
edge_labels_3d = []
label_positions = []

for edge in G_3d.edges(data=True):
    x0, y0, z0 = pos_3d[edge[0]]
    x1, y1, z1 = pos_3d[edge[1]]
    edge_x_3d += [x0, x1, None]
    edge_y_3d += [y0, y1, None]
    edge_z_3d += [z0, z1, None]

    # Add labels halfway along the edge
    label_x = (x0 + x1) / 2
    label_y = (y0 + y1) / 2
    label_z = (z0 + z1) / 2
    label_positions.append((label_x, label_y, label_z))
    edge_labels_3d.append(edge[2]['label'])

# Quick Links Authentication Callback
@app.callback(
    [Output('quicklinks-auth-container', 'style'),
     Output('quicklinks-content-container', 'style'),
     Output('quicklinks-auth-message', 'children'),
     Output('quicklinks-password-input', 'value')],
    [Input('quicklinks-unlock-btn', 'n_clicks')],
    [State('quicklinks-password-input', 'value')]
)
def authenticate_quicklinks(n_clicks, password):
    if n_clicks == 0:
        # Initial state - show auth form
        return {'display': 'block'}, {'display': 'none'}, '', ''
    
    if password == QUICKLINKS_PASSWORD:
        # Correct password - hide auth, show content
        return {'display': 'none'}, {'display': 'block'}, '', ''
    else:
        # Wrong password - show error, keep auth visible
        return {'display': 'block'}, {'display': 'none'}, '❌ Incorrect password. Please try again.', ''

# NetworkX Visualization Tab
@app.callback(
    Output("network-graph", "figure"),
    [Input("category-filter", "value"),
     Input("node-checklist", "value")]
)
def update_graph(filter_category, selected_nodes):
    filtered_df = df_networkx[df_networkx['Entity'].isin(selected_nodes)]
    if filter_category:
        filtered_df = filtered_df[filtered_df['Category'] == filter_category]

    G_filtered = nx.DiGraph()
    for _, row in filtered_df.iterrows():
        if row['Next']:
            G_filtered.add_edge(row['Entity'], row['Next'])

    positions = nx.spring_layout(G_filtered)
    edge_trace = []
    for edge in G_filtered.edges(data=True):
        x0, y0 = positions[edge[0]]
        x1, y1 = positions[edge[1]]
        edge_trace.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            line=dict(width=1, color='gray'),
            hoverinfo='none',
            mode='lines'))

    node_trace = go.Scatter(
        x=[positions[node][0] for node in G_filtered.nodes()],
        y=[positions[node][1] for node in G_filtered.nodes()],
        text=[node for node in G_filtered.nodes()],
        mode='markers+text',
        textposition="top center",
        marker=dict(size=10, color='blue')
    )

    return go.Figure(data=edge_trace + [node_trace])
 
@app.callback(
    Output("sankey-graph", "figure"),
    [Input("load-demo", "n_clicks")],
    prevent_initial_call=True
)
def update_stacked_sankey(load_demo_clicks, datasets=None, 
    entity_type_mappings=None, entity_type_ls=None, 
    entity_type_exclude=['other'], verbose=False):
    """Makes a tiered sankey diagram, the number of tiers responds to the number of datasets 
    in the number if datasets submited in the datasets list"""
   
    ## if there are no datasets load the demo data stack
    if datasets==None:
        # the order defines with source is attached to which target in the diagram
        # Define three demo datasets (job_requests, payments made, invoicing transactions)
        datasets = [
            #job_requests
            pd.DataFrame({
            "Source": ["McNeil",     "Paramount_ins","Miramax",    "Netflix","Accelebrate","Accelebrate", "BHanalytics", "WebAge", "ACD",         "ACD",        "ACD",       "ACD"],
            "Target": ["Accelebrate","Accelebrate",  "BHanalytics","WebAge", "ACD",        "ACD",        "ACD",         "ACD",    "K.Martin",    "G.Kleemann", "K.Kamerkar","K.Martin"],
            "Status": ["Y",          "Y",            "Y",           "N",     "N",            "N",        "N",           "N",        "N",            "N",        "N",            "N"],
            }),
            # invoice/payments made
            pd.DataFrame({
            "Source": ["McNeil",     "Paramount_ins","Miramax",    "Netflix","Accelebrate","Accelebrate", "BHanalytics", "WebAge", "ACD",         "ACD",        "ACD",       "ACD"],
            "Target": ["Accelebrate","Accelebrate",  "BHanalytics","WebAge", "ACD",        "ACD",        "ACD",         "ACD",    "K.Martin",    "G.Kleemann", "K.Kamerkar","K.Martin"],
            "Status": ["Y",          "Y",            "N",           "N",     "N",            "N",        "N",           "N",        "N",            "N",        "N",            "N"],
            }),
            #invoicing transactions
            pd.DataFrame({
                "Source": ["Region1", "ProcessM", "ProcessN"],
                "Target": ["ProcessM", "ProcessN", "Product1"],
                "Status": ["N",          "Y",            "M",]
            })
        ]

        #conveys entity order onto the diagram
        entity_type_ls = ["client","training_co","talent_co","worker"]
        
        # Corresponding entity type mappings
        entity_type_mappings = [
            
            {"McNeil":"client", "Paramount_ins":"client", "Netflix":"client", "Miramax":"Client", 
            "WebAge":"training_co","BHanalytics":"training_co","Accelebrate":"training_co",
            "ACD":"talent_co",
            "K.Martin":"worker","K.Kamerkar":"worker","G.Kleemann":"worker"},
            
            {"McNeil":"Client", "Paramount_ins":"Client", "Netflix":"Client", "Miramax":"Client", 
            "WebAge":"training_co","BHanalytics":"training_co","Accelebrate":"training_co",
            "ACD":"talent_co",
            "K.Martin":"worker","K.Kamerkar":"worker","G.Kleemann":"worker"},
            
            {"Region1": "client", "ProcessM": "training_co", "ProcessN": "talent_co", "Product1": "worker"}
        ]

    # make the layers conditional based on number of dataframes in dataset list
    dataset_ct=len(datasets)
    # Create subplots with domain type for Sankey diagrams
    fig = make_subplots(
        rows=dataset_ct, cols=1,
        specs=[[{"type": "domain"}] for _ in range(dataset_ct)],  # Each subplot is of type 'domain'
        shared_xaxes=False,
        vertical_spacing=0.1
    )

    d=entity_type_mappings[0]
    entity_types={k.casefold(): v for k, v in d.items()}
    entity_type_ls=[k.casefold() for k in entity_type_ls]
    add_to_fig=True
    entity_type_ls=[ent for ent in entity_type_ls if ent not in entity_type_exclude]
    print(entity_type_ls)
    
    #for i, (demo_data, entity_types) in enumerate(zip(datasets, entity_type_mappings), start=1):
    for i, (demo_data) in enumerate(datasets, start=1):
        ## sanitize case
        print(i)
        
        # Determine unique nodes and assign x positions based on entity type
        unique_nodes = pd.concat([demo_data["Source"], demo_data["Target"]]).unique()
        unique_nodes_cln=[ent for ent in unique_nodes if entity_type_mappings[0].get(ent) in entity_type_ls] 
        unique_nodes=unique_nodes_cln

        # use the entity type list to explicitly control order
        entity_type_order = {etype: i for i, etype in enumerate(entity_type_ls)}
        
        if verbose:
            print(unique_nodes)
            print(entity_type_order)

        x_positions = []
        for node in unique_nodes:
            # skip entites that are not listed on in the current entity_type_ls
            try:
                x_positions.append([entity_type_order[entity_types[node]] / (len(entity_type_order) - 1) ])
                if verbose:
                    print(f"adding {node} for [entity_types[node] {entity_types[node]}")

            except Exception as e:
                if verbose:
                    print(f'not adding entity to x position {node} : {entity_types[node]} : {e}')
                continue


        # Group nodes by x position
        grouped_nodes = {etype: [] for etype in entity_type_order}
        for node in unique_nodes:
            # skip entites that are not listed on in the current entity_type_ls
            try:
                grouped_nodes[entity_types[node]].append(node)
                if verbose:
                    print(f"adding {node} for entity_types[node] {entity_types[node]}")
                    print(grouped_nodes)
            except Exception as e:
                if verbose:
                    print(f'not adding entity to node list {node}:{entity_types[node]}: {e}')
                continue

        # Assign vertical (y) positions
        y_positions = []
        
        for etype in entity_type_order:
            # skip entites that are not listed on in the current entity_type_ls
            try: 
                group = grouped_nodes[etype]
                spacing = 1 / (len(group) + 1)
                y_positions.extend([(j + 1) * spacing for j in range(len(group))])
                if verbose:
                    print(f"adding {etype} for grouped_nodes[etype] {grouped_nodes[etype]}")
            except Exception as e:
                #add_to_fig=False
                if verbose:
                    print(f'not adding entity to y position: {e}')
                continue
        if verbose:        
            print(y_positions)        

        # Generate indices for sources and targets
        node_indices = {node: idx for idx, node in enumerate(unique_nodes)}
        source_indices = demo_data["Source"].map(node_indices).tolist()
        target_indices = demo_data["Target"].map(node_indices).tolist()

        # Create link colors
        colors = pc.qualitative.Set1
        #link_colors = [colors[j % len(colors)] for j in range(len(source_indices))]
        status_ls = [i.lower() for i in demo_data["Status"]]
        link_colors=[colors[2] if yn == 'y' else colors[0] for yn in status_ls]
        
        #link_colors = [
        #colors[2] if status == 'paid' else (colors[3] if status == 'pending' else colors[0]) 
        #for status in status_ls
        #]

        print (f"status_ls: {status_ls}")
        print (f"link_colors: {link_colors}")

        node_dict=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=unique_nodes,
                    x=x_positions,
                    y=y_positions
                )

        link_dict=dict(
                    source=source_indices,
                    target=target_indices,
                    value=[1] * len(source_indices),  # Example values, can be adjusted
                    ## color these according to job status
                    color=link_colors
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

    # Update layout for subplots - make this conditional on datasets up to 3 rows
        annot_ls= [
            dict(
                text="job requests",  # Title for the first subplot
                x=0.5, y=1.05,  # Position above the first diagram
                xref="paper", yref="paper",
                showarrow=False,
                font=dict(size=14)
            ),
            dict(
                text="invoicing transactions",  # Title for the second subplot
                x=0.5, y=.65,  # Position above the second diagram
                xref="paper", yref="paper",
                showarrow=False,
                font=dict(size=14)
            ),
            dict(
                text="Payments made",  # Title for the second subplot
                x=0.5, y=.25,  # Position above the second diagram
                xref="paper", yref="paper",
                showarrow=False,
                font=dict(size=14)
            ) 
        ]

    #flexable sankey graph updater
    fig.update_layout(annotations=annot_ls[0:dataset_ct],
    
        height=800,  # Adjust height to fit all subplots
        title="Stacked Sankey Diagrams",
        font=dict(size=10),
        showlegend=False
    )
    return fig

# Google Sheet Tab
@app.callback(
    Output("script-output", "children"),
    [Input("run-script-btn", "n_clicks")],
    [State("worker-filter", "value")]
)

def execute_python_script(n_clicks, worker_filter):
    if n_clicks > 0:
        try:
            df = load_google_sheet(data_names[0], headers=expected_head[0])
        except Exception as e:
            return f"Error loading Google Sheet: {e}"

        if worker_filter and worker_filter != "All" and 'Teacher' in df.columns:
            filtered_df = df[df['Teacher'] == worker_filter]
        else:
            filtered_df = df

        result = f"Filtered Rows: {len(filtered_df)}"
        return result
    return "Press 'Run Script' to execute."

# Google Sheet Tab
@app.callback(
    Output("script-output2a", "children"),
    [Input("run-script-btn2a", "n_clicks")],
    [State("worker-filter2a", "value")]
)

def execute_python_script(n_clicks, worker_filter):
    if n_clicks > 0:
        try:
            df = load_google_sheet(data_names[0], headers=expected_head[0])
        except Exception as e:
            return f"Error loading Google Sheet: {e}"

        if worker_filter and worker_filter != "All" and 'Teacher' in df.columns:
            filtered_df = df[df['Teacher'] == worker_filter]
        else:
            filtered_df = df

        result = f"Filtered Rows: {len(filtered_df)}"
        return result
    return "Press 'Run Script' to execute."

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
            df_inv = load_google_sheet(data_names[1], headers=expected_head[1])  # Load `inv_tbl`
            df_jobs = load_google_sheet(data_names[0], headers=expected_head[0])  # Load `jobs_tbl`
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


# App Layout (Updated with the new tab)
app.layout = html.Div([
    html.H1("Unified Dashboard"),
    dcc.Tabs([

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
        dcc.Tab(label="NetworkX Visualization", children=[
            html.H4("NetworkX Graph"),
            dcc.Dropdown(
                id="category-filter",
                options=[{"label": cat, "value": cat} for cat in df_networkx['Category'].unique()],
                placeholder="Filter by Category",
            ),
            dcc.Checklist(
                id="node-checklist",
                options=[{"label": entity, "value": entity} for entity in df_networkx['Entity']],
                value=df_networkx['Entity'].tolist(),
                inline=True
            ),
            dcc.Graph(id="network-graph", style={"height": "600px"}),
        ]),
        dcc.Tab(label="Sankey Diagram", children=[
            html.H4("Sankey Diagram"),
            html.Button("Load Demo Data", id="load-demo", n_clicks=0),
            dcc.Graph(id="sankey-graph", style={"height": "600px"}),
        ]),
        dcc.Tab(label="3D Network Visualization", children=[
            html.H4("3D Directed Force Diagram"),
            dcc.Graph(
                id="force-3d-graph",
                style={"height": "600px"},
                figure=go.Figure(data=[
                    go.Scatter3d(
                        x=edge_x_3d, y=edge_y_3d, z=edge_z_3d,
                        mode='lines',
                        line=dict(color='gray', width=2),
                        hoverinfo='none'
                    ),
                    go.Scatter3d(
                        x=node_x_3d, y=node_y_3d, z=node_z_3d,
                        mode='markers+text',
                        text=list(G_3d.nodes()),
                        textposition="top center",
                        marker=dict(size=8, color='blue', opacity=0.8)
                    ),
                    go.Scatter3d(
                        x=[pos[0] for pos in label_positions],
                        y=[pos[1] for pos in label_positions],
                        z=[pos[2] for pos in label_positions],
                        mode='text',
                        text=edge_labels_3d,
                        textfont=dict(color='red', size=12),
                        hoverinfo='none'
                    )
                ]).update_layout(
                    title="3D Directed Force Diagram with Labeled Edges",
                    scene=dict(
                        xaxis=dict(showbackground=True),
                        yaxis=dict(showbackground=True),
                        zaxis=dict(showbackground=True)
                    ),
                    showlegend=False
                )
            )
        ]),
        dcc.Tab(label="Quick Links", children=[
            html.Div([
                # Authentication container
                html.Div(id='quicklinks-auth-container', children=[
                    html.Div([
                        html.H2("🔒 Quick Links Access", style={
                            "color": "white",
                            "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
                            "textAlign": "center",
                            "marginBottom": "20px"
                        }),
                        html.P("Please enter password to access Quick Links", style={
                            "color": "white",
                            "textShadow": "1px 1px 3px rgba(0,0,0,0.8)",
                            "textAlign": "center",
                            "fontSize": "16px"
                        }),
                        dcc.Input(
                            id='quicklinks-password-input',
                            type='password',
                            placeholder='Enter password',
                            style={
                                "width": "300px",
                                "padding": "12px",
                                "fontSize": "16px",
                                "borderRadius": "5px",
                                "border": "2px solid #ccc",
                                "marginBottom": "20px",
                                "display": "block",
                                "margin": "0 auto 20px auto"
                            }
                        ),
                        html.Button("Unlock", id="quicklinks-unlock-btn", n_clicks=0, style={
                            "padding": "12px 30px",
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "backgroundColor": "#4A90E2",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "8px",
                            "boxShadow": "0 4px 0 #2E5C8A, 0 6px 8px rgba(0,0,0,0.3)",
                            "cursor": "pointer",
                            "display": "block",
                            "margin": "0 auto"
                        }),
                        html.Div(id='quicklinks-auth-message', style={
                            "marginTop": "20px",
                            "textAlign": "center",
                            "color": "#ff6b6b",
                            "fontWeight": "bold",
                            "textShadow": "1px 1px 2px rgba(0,0,0,0.8)"
                        })
                    ], style={
                        "backgroundColor": "rgba(0,0,0,0.6)",
                        "padding": "50px",
                        "borderRadius": "15px",
                        "maxWidth": "500px",
                        "margin": "100px auto",
                        "border": "2px solid rgba(255,255,255,0.3)"
                    })
                ]),
                
                # Content container (hidden by default)
                html.Div(id='quicklinks-content-container', style={'display': 'none'}, children=[
                    html.H2("Quick Access Links", style={
                        "color": "white",
                        "textShadow": "2px 2px 4px rgba(0,0,0,0.8)",
                        "textAlign": "center",
                        "marginBottom": "30px"
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
                                style_override={
                                    "fontSize": "20px",
                                    "padding": "20px 40px",
                                    "backgroundColor": "#4A90E2",
                                    "boxShadow": "0 6px 0 #2E5C8A, 0 8px 12px rgba(0,0,0,0.4)",
                                    "minWidth": "300px"
                                }
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
                    create_link_category("Invoice buckets", QUICK_LINKS_CONFIG['Invoice buckets'], '�'),
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
        dcc.Tab(label="Google Sheet Viewer", children=[
            html.H4("Filter by Worker"),
            dcc.Dropdown(
                id="worker-filter",
                options=[
                    {"label": "All", "value": "All"}
                ] + [{"label": worker, "value": worker} for worker in df_google_sheet['Teacher'].unique()]
                if 'Teacher' in df_google_sheet.columns else [],
                value="All"
            ),
            html.Button("Run Script", id="run-script-btn", n_clicks=0),
            html.Div(id="script-output", style={"marginTop": "20px"}),
            html.H4("Google Sheet Data"),
        ]),
        dcc.Tab(label="Google Sheet Viewer2a", children=[  # New Tab
            html.H4("Filter by Worker2"),
            dcc.Dropdown(
                id="worker-filter2a",
                options=[
                    {"label": "All", "value": "All"}
                ] + [{"label": worker, "value": worker} for worker in df_google_sheet2['inv_from'].unique()]
                if 'inv_from' in df_google_sheet2.columns else [],
                value="All"
            ),
            html.Button("Run Script", id="run-script-btn2a", n_clicks=0),
            html.Div(id="script-output2a", style={"marginTop": "20px"}),
            html.H4("Summary Statistics"),
        ])

        # Updated Tab for Google Sheet Viewer2

        
    ])
])

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True, port=8051)