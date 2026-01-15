#!/usr/bin/env python3
"""
Minimal demo to showcase the Sankey dropdown functionality
"""

import dash
from dash import dcc, html, Input, Output, ctx
import pandas as pd
import plotly.graph_objs as go
import plotly.colors as pc
from plotly.subplots import make_subplots

# Initialize Dash app
app = dash.Dash(__name__)

# Demo data
def get_demo_datasets():
    return [
        # Job requests
        pd.DataFrame({
            "Source": ["McNeil", "Paramount_ins", "Miramax", "Netflix", "Accelebrate", "Accelebrate", "BHanalytics", "WebAge", "ACD", "ACD", "ACD", "ACD"],
            "Target": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge", "ACD", "ACD", "ACD", "ACD", "K.Martin", "G.Kleemann", "K.Kamerkar", "K.Martin"],
            "Status": ["Y", "Y", "Y", "N", "N", "N", "N", "N", "N", "N", "N", "N"],
        }),
        # Invoice/payments made
        pd.DataFrame({
            "Source": ["McNeil", "Paramount_ins", "Miramax", "Netflix", "Accelebrate", "Accelebrate", "BHanalytics", "WebAge", "ACD", "ACD", "ACD", "ACD"],
            "Target": ["Accelebrate", "Accelebrate", "BHanalytics", "WebAge", "ACD", "ACD", "ACD", "ACD", "K.Martin", "G.Kleemann", "K.Kamerkar", "K.Martin"],
            "Status": ["Y", "Y", "N", "N", "N", "N", "N", "N", "N", "N", "N", "N"],
        })
    ]

app.layout = html.Div([
    html.H1("Sankey Diagram with Maximum Links Control", style={"textAlign": "center"}),
    html.Div([
        html.Label("Maximum Links:", style={"fontWeight": "bold", "marginRight": "10px"}),
        dcc.Dropdown(
            id="max-links-dropdown",
            options=[
                {"label": "All", "value": "all"},
                {"label": "5", "value": "5"},
                {"label": "10", "value": "10"},
            ],
            value="all",
            clearable=False,
            style={"width": "200px", "display": "inline-block"}
        )
    ], style={"textAlign": "center", "marginBottom": "20px"}),
    dcc.Graph(id="sankey-graph", style={"height": "600px"}),
])

@app.callback(
    Output("max-links-dropdown", "options"),
    Input("sankey-graph", "id"),  # Dummy input to trigger on load
    prevent_initial_call=False
)
def update_dropdown_options(_):
    """Generate dropdown options based on demo data size"""
    datasets = get_demo_datasets()
    max_size = max(len(df) for df in datasets)
    
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

@app.callback(
    Output("sankey-graph", "figure"),
    Input("max-links-dropdown", "value"),
    prevent_initial_call=False
)
def update_sankey(max_links):
    """Update Sankey diagram based on maximum links selection"""
    
    # Get demo data
    datasets = get_demo_datasets()
    
    # Apply filtering
    if max_links != 'all' and max_links is not None:
        max_links_int = int(max_links)
        datasets = [df.head(max_links_int) if len(df) > max_links_int else df for df in datasets]
    
    # Entity mappings
    entity_type_mappings = {
        "McNeil": "client", "Paramount_ins": "client", "Netflix": "client", "Miramax": "client",
        "WebAge": "training_co", "BHanalytics": "training_co", "Accelebrate": "training_co",
        "ACD": "talent_co",
        "K.Martin": "worker", "K.Kamerkar": "worker", "G.Kleemann": "worker"
    }
    
    entity_type_ls = ["client", "training_co", "talent_co", "worker"]
    entity_type_order = {etype: i for i, etype in enumerate(entity_type_ls)}
    
    # Create subplots
    fig = make_subplots(
        rows=len(datasets), cols=1,
        specs=[[{"type": "domain"}] for _ in range(len(datasets))],
        shared_xaxes=False,
        vertical_spacing=0.1
    )
    
    # Process each dataset
    for i, demo_data in enumerate(datasets, start=1):
        # Get unique nodes
        unique_nodes = pd.concat([demo_data["Source"], demo_data["Target"]]).unique()
        unique_nodes = [node for node in unique_nodes if node in entity_type_mappings]
        
        # Calculate positions
        x_positions = []
        y_positions = []
        grouped_nodes = {etype: [] for etype in entity_type_order}
        
        for node in unique_nodes:
            entity_type = entity_type_mappings[node]
            grouped_nodes[entity_type].append(node)
            x_positions.append(entity_type_order[entity_type] / (len(entity_type_order) - 1))
        
        # Calculate y positions
        for etype in entity_type_order:
            group = grouped_nodes[etype]
            if group:
                spacing = 1 / (len(group) + 1)
                y_positions.extend([(j + 1) * spacing for j in range(len(group))])
        
        # Create indices
        node_indices = {node: idx for idx, node in enumerate(unique_nodes)}
        source_indices = demo_data["Source"].map(node_indices).dropna().astype(int).tolist()
        target_indices = demo_data["Target"].map(node_indices).dropna().astype(int).tolist()
        
        # Create colors
        colors = pc.qualitative.Set1
        status_ls = [status.lower() for status in demo_data["Status"][:len(source_indices)]]
        link_colors = [colors[2] if yn == 'y' else colors[0] for yn in status_ls]
        
        # Add Sankey trace
        fig.add_trace(
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=unique_nodes,
                    x=x_positions,
                    y=y_positions
                ),
                link=dict(
                    source=source_indices,
                    target=target_indices,
                    value=[1] * len(source_indices),
                    color=link_colors
                )
            ),
            row=i, col=1
        )
    
    # Add titles
    annotations = [
        dict(
            text=f"Dataset {i} - Links: {len(datasets[i-1])}",
            x=0.5, y=1 - (i-1) * 0.5 + 0.45,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=14)
        ) for i in range(1, len(datasets) + 1)
    ]
    
    fig.update_layout(
        annotations=annotations,
        height=400 * len(datasets),
        title=f"Sankey Diagrams - Max Links: {max_links if max_links != 'all' else 'All'}",
        font=dict(size=10),
        showlegend=False
    )
    
    return fig

if __name__ == "__main__":
    print("Starting demo Sankey app with dropdown functionality...")
    print("Navigate to http://127.0.0.1:8050/ to view the app")
    print("Use the dropdown to control maximum number of links!")
    app.run_server(debug=True, port=8050)