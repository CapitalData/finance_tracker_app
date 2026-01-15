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
data_names=['jobs_expense', 'inv_payment']
#print(CREDENTIALS)

def load_google_sheet(worksheet_nm):
    client = gspread.authorize(CREDENTIALS)
    sheet_overview = client.open_by_url(GOOGLE_SHEET_URL)
    #worksheet = sheet_overview.get_worksheet(0)  # Load the first sheet
    
    ### get the data row-wise ###
    curr_wks=sheet_overview.worksheet(worksheet_nm).get_all_records()

    # get_all_values gives a list of rows
    return pd.DataFrame.from_records(curr_wks)

try:
     df_google_sheet = load_google_sheet(data_names[0])
     print('loaded df_google_sheets')
except Exception as e:
     df_google_sheet = pd.DataFrame({"Error": [str(e)]})
     print('failed to load: df_google_sheets')

try:
    df_google_sheet2 = load_google_sheet(data_names[1])  # Load `inv_payment`
    print('loaded df_google_sheets 2')
    #display(df_google_sheet2.head())
except Exception as e:
    # Fallback in case of error
    df_google_sheet2 = pd.DataFrame({"Error": [str(e)]})
    print('failed to load: df_google_sheets 2')

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

# def update_stacked_sankey(load_demo_clicks):
#     # Define three demo datasets
#     datasets = [
#         pd.DataFrame({
#         "Source": ["McNeil",     "Paramount_ins","Miramax",    "Netflix","Accelebrate","Accelebrate", "BHanalytics", "WebAge", "ACD",         "ACD",        "ACD",       "ACD"],
#         "Target": ["Accelebrate","Accelebrate",  "BHanalytics","WebAge", "ACD",        "ACD",        "ACD",         "ACD",    "K.Martin",    "G.Kleemann", "K.Kamerkar","K.Martin"],
#         "Status": ["Y",          "Y",            "N",           "N",     "N",            "N",        "N",           "N",        "N",            "N",        "N",            "N"],
#         }),
#         pd.DataFrame({
#             "Source": ["Team1", "ProcessX", "ProcessY"],
#             "Target": ["ProcessX", "ProcessY", "Outcome1"],
#             "Status": ["Y",          "Y",            "N",] 
#         }),
#         pd.DataFrame({
#             "Source": ["Region1", "ProcessM", "ProcessN"],
#             "Target": ["ProcessM", "ProcessN", "Product1"],
#             "Status": ["Y",          "N",            "N",]
#         })
#     ]

#     entity_type_ls = ["Client","training_co","talent_co","worker"]
#     # Corresponding entity type mappings
#     entity_type_mappings = [{"McNeil":"Client", 
#         "Paramount_ins":"Client", 
#         "Netflix":"Client", 
#         "Miramax":"Client", 
#         "WebAge":"training_co",
#         "BHanalytics":"training_co",
#         "Accelebrate":"training_co",
#         "ACD":"talent_co",
#         "K.Martin":"worker",
#         "K.Kamerkar":"worker",
#         "G.Kleemann":"worker"},
#         {"Team1": "Client", "ProcessX": "training_co", "ProcessY": "training_co", "Outcome1": "worker"},
#         {"Region1": "Client", "ProcessM": "training_co", "ProcessN": "talent_co", "Product1": "worker"}
#     ]

#     # Create subplots with domain type for Sankey diagrams
#     fig = make_subplots(
#         rows=3, cols=1,
#         specs=[[{"type": "domain"}] for _ in range(3)],  # Each subplot is of type 'domain'
#         shared_xaxes=False,
#         vertical_spacing=0.1
#     )

#     for i, (demo_data, entity_types) in enumerate(zip(datasets, entity_type_mappings), start=1):
#         # Determine unique nodes and assign x positions based on entity type
#         unique_nodes = pd.concat([demo_data["Source"], demo_data["Target"]]).unique()
#         # use the entity type list to explicitly control order
#         entity_type_order = {etype: i for i, etype in enumerate(entity_type_ls)}
#         x_positions = [entity_type_order[entity_types[node]] / (len(entity_type_order) - 1) for node in unique_nodes]

#         # Group nodes by x position
#         grouped_nodes = {etype: [] for etype in entity_type_order}
#         for node in unique_nodes:
#             grouped_nodes[entity_types[node]].append(node)

#         # Assign vertical (y) positions
#         y_positions = []
#         for etype in entity_type_order:
#             group = grouped_nodes[etype]
#             spacing = 1 / (len(group) + 1)
#             y_positions.extend([(j + 1) * spacing for j in range(len(group))])

#         # Generate indices for sources and targets
#         node_indices = {node: idx for idx, node in enumerate(unique_nodes)}
#         source_indices = demo_data["Source"].map(node_indices).tolist()
#         target_indices = demo_data["Target"].map(node_indices).tolist()

#         # Create link colors
#         colors = pc.qualitative.Set1
#         link_colors = [colors[j % len(colors)] for j in range(len(source_indices))]

#         # Add Sankey diagram to the subplot
#         fig.add_trace(
#             go.Sankey(
#                 node=dict(
#                     pad=15,
#                     thickness=20,
#                     line=dict(color="black", width=0.5),
#                     label=unique_nodes,
#                     x=x_positions,
#                     y=y_positions
#                 ),
#                 link=dict(
#                     source=source_indices,
#                     target=target_indices,
#                     value=[1] * len(source_indices),  # Example values, can be adjusted
#                     ## color these according to job status
#                     #color=link_colors
#                 )
#             ),
#             row=i,
#             col=1
#         )

#     # Update layout for subplots
#     fig.update_layout(annotations=[
#             dict(
#                 text="job requests",  # Title for the first subplot
#                 x=0.5, y=1.05,  # Position above the first diagram
#                 xref="paper", yref="paper",
#                 showarrow=False,
#                 font=dict(size=14)
#             ),
#             dict(
#                 text="invoicing transactions",  # Title for the second subplot
#                 x=0.5, y=.65,  # Position above the second diagram
#                 xref="paper", yref="paper",
#                 showarrow=False,
#                 font=dict(size=14)
#             ),
#             dict(
#                 text="Payments made",  # Title for the second subplot
#                 x=0.5, y=.25,  # Position above the second diagram
#                 xref="paper", yref="paper",
#                 showarrow=False,
#                 font=dict(size=14)
#             )
#         ],
#         height=800,  # Adjust height to fit all subplots
#         title="Stacked Sankey Diagrams",
#         font=dict(size=10),
#         showlegend=False
#     )
#     return fig




def update_stacked_sankey(load_demo_clicks, datasets=None, 
    entity_type_mappings=None, entity_type_ls=None, 
    entity_type_exclude=['other'], verbose=False):
    """Makes a tiered sankey diagram, the number of tiers responds to the number of datasets 
    in the number if datasets submited in the datasets list"""
   
    ## if there are no datasets load the demo data stack
    if datasets==None:
        # Define three demo datasets (job_requests, payments made, invoicing transactions)
        datasets = [
            #job_requests
            pd.DataFrame({
            "Source": ["McNeil",     "Paramount_ins","Miramax",    "Netflix","Accelebrate","Accelebrate", "BHanalytics", "WebAge", "ACD",         "ACD",        "ACD",       "ACD"],
            "Target": ["Accelebrate","Accelebrate",  "BHanalytics","WebAge", "ACD",        "ACD",        "ACD",         "ACD",    "K.Martin",    "G.Kleemann", "K.Kamerkar","K.Martin"],
            "Status": ["Y",          "Y",            "N",           "N",     "N",            "N",        "N",           "N",        "N",            "N",        "N",            "N"],
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
                "Status": ["Y",          "Y",            "M",]
            })
        ]

        #conveys entity order onto the diagram
        entity_type_ls = ["Client","training_co","talent_co","worker"]
        
        # Corresponding entity type mappings
        entity_type_mappings = [
            
            {"McNeil":"Client", "Paramount_ins":"Client", "Netflix":"Client", "Miramax":"Client", 
            "WebAge":"training_co","BHanalytics":"training_co","Accelebrate":"training_co",
            "ACD":"talent_co",
            "K.Martin":"worker","K.Kamerkar":"worker","G.Kleemann":"worker"},
            
            {"McNeil":"Client", "Paramount_ins":"Client", "Netflix":"Client", "Miramax":"Client", 
            "WebAge":"training_co","BHanalytics":"training_co","Accelebrate":"training_co",
            "ACD":"talent_co",
            "K.Martin":"worker","K.Kamerkar":"worker","G.Kleemann":"worker"},
            
            {"Region1": "Client", "ProcessM": "training_co", "ProcessN": "talent_co", "Product1": "worker"}
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
            display(y_positions)        

        # Generate indices for sources and targets
        node_indices = {node: idx for idx, node in enumerate(unique_nodes)}
        source_indices = demo_data["Source"].map(node_indices).tolist()
        target_indices = demo_data["Target"].map(node_indices).tolist()

        # Create link colors
        colors = pc.qualitative.Set1
        #link_colors = [colors[j % len(colors)] for j in range(len(source_indices))]
        status_ls = [i.lower() for i in demo_data["Status"]]
        #link_colors=[colors[2] if yn == 'y' colors[0] for yn in status_ls]
        link_colors = [
        colors[2] if status == 'paid' else (colors[3] if status == 'pending' else colors[0]) 
        for status in status_ls
        ]

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
            df = load_google_sheet(data_names[0])
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
            df = load_google_sheet(data_names[0])
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
     Output("owed2worker-summary", "children")],
    [Input("run-script-btn2", "n_clicks")],
    [State("worker-filter2", "value")]
)
def execute_python_script2(n_clicks, worker_filter):
    if n_clicks > 0:
        try:
            df = load_google_sheet(data_names[1])  # Load `inv_payment`
        except Exception as e:
            return f"Error loading Google Sheet: {e}", f"Error loading Google Sheet: {e}"

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

            return owed2acd_summary, owed2worker_summary

        else:
            return "Columns `owed2acd` or `owed2worker` not found in the data.", \
                   "Columns `owed2acd` or `owed2worker` not found in the data."

    return "Press 'Run Script' to execute.", "Press 'Run Script' to execute."


# App Layout (Updated with the new tab)
app.layout = html.Div([
    html.H1("Unified Dashboard"),
    dcc.Tabs([
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
        ]),
        # Updated Tab for Google Sheet Viewer2
        # Updated Tab for Google Sheet Viewer2
        dcc.Tab(label="Google Sheet Viewer2", children=[
            html.H4("Filter by Worker2"),
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
                    html.H5("Summary Statistics for owed2acd"),
                    html.Div(id="owed2acd-summary")
                ], style={"margin": "10px", "padding": "10px", "border": "1px solid #ccc", "borderRadius": "5px", "width": "45%", "display": "inline-block", "verticalAlign": "top"}),
                html.Div([
                    html.H5("Summary Statistics for owed2worker"),
                    html.Div(id="owed2worker-summary")
                ], style={"margin": "10px", "padding": "10px", "border": "1px solid #ccc", "borderRadius": "5px", "width": "45%", "display": "inline-block", "verticalAlign": "top"}),
            ])
        ])
    ])
])

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)