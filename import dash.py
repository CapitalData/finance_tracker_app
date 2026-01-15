import dash
from dash import dcc, html, Input, Output
import acd

# your data & mappings
inv_df_kmart = acd.inv_df_kmart
entity_type_mappings = acd.entity_type_mappings
entity_type_ls = acd.entity_type_ls

app = dash.Dash(__name__)
server = app.server

app.layout = html.Div([
    html.H1("Stacked Sankey Diagram"),
    html.Label("Select entity types:"),
    dcc.Checklist(
        id="entity-type-checklist",
        options=[{"label": et, "value": et} for et in entity_type_ls],
        value=entity_type_ls,               # default: all checked
        inline=True
    ),
    dcc.Graph(id="sankey-diagram")
])

@app.callback(
    Output("sankey-diagram", "figure"),
    Input("entity-type-checklist", "value")
)
def update_figure(selected_types):
    # call your function with the selected subset
    fig = acd.update_stacked_sankey(
        [inv_df_kmart],
        entity_type_mappings,
        selected_types,
        verbose=False
    )
    return fig

if __name__ == "__main__":
    app.run_server(debug=False, port=8053)