from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import pandas as pd

import gspread
from oauth2client.service_account import ServiceAccountCredentials

## filter the dataframe for plot exploration
import ipywidgets as widgets
from IPython.display import display

####### Main functions #######
def df_lower(df, tgt_type):
  """clean all of a certain type ot lower, these will come in as
  strings (object) without typecasting
  cleans the DF in place"""

  for x in df.columns:
      if df[x].dtype == tgt_type:
          #print('object - lowecase implemented')
          df[x] = df[x].str.lower()
      else:
          df[x] = df[x]

def load_method(method):
    """## local implies that you have the google sheets ssh key file on your local machine. 
    ## colab assumes that you are using colab with colab secrets"""

    if method == 'l' or 'L' or 'local':
        #Method 1 -  this loads the ssh key for the service account

        # Path to the credentials file
        filename = '/Users/gunnarkleemann/.ssh/financetrack-acd-aa2d12d1f346.json'

        # Define the scope
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

        # Load credentials from the file
        credentials = ServiceAccountCredentials.from_json_keyfile_name(filename, scope)
        g_conect = gspread.authorize(credentials)

    else:
        print("no valid method selected")
        sys.exit()

    return g_conect
    
def filter_df(status):
    """# Function to filter DataFrame based on payment status"""
    ## we cant pass dataframes or strings into the function since it is used in a IPwidget
    ## instead we define the dataframe and strings come in as GLOBAL variables

    global df_in
    global col_curr
    global new_df
    if status == 'No Filter':
        new_df = df_in
    else:
        new_df= df_in[df_in[col_curr].str.lower() == status.lower()]
    #return new_df


######## Load Data ##########

method = 'L'
g_conect=load_method(method)

# load the sheets with the sheet key
sheet_overview = g_conect.open_by_key('1QEgmIzrVF7pJzzpYyacGHpW5VF0T7dTSu5te3rq2UlI')#('FINANCE - invoices and payments')

### get the data row wise
inv_pay_rw=sheet_overview.worksheet('inv_payment').get_all_records()
jobs_rw=sheet_overview.worksheet('jobs_expense').get_all_records()

# get_all_values gives a list of rows
jobs_df=pd.DataFrame.from_records(jobs_rw)
inv_pay_df=pd.DataFrame.from_records(inv_pay_rw)

#clean the data - in
df_lower(jobs_df, "object")
df_lower(inv_pay_df, "object")

jobs_df.columns = jobs_df.columns.str.strip()
inv_pay_df.columns = inv_pay_df.columns.str.strip()
## gepminder - demodata.
df_gap = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminder_unfiltered.csv')

###### dropdown elements #######
df_in=inv_pay_df
status_inv= col_curr= 'status' 
entity_inv= 'to_client'
x_var_inv= 'inv_dollars'
title_inv= 'ACD invoice status by client'
opt = list(df_in.groupby(col_curr).groups.keys())+['No Filter']

dropdown_inv = widgets.Dropdown(
    options=opt,
    value='No Filter',
    description='Filter Inv By:',
    disabled=False,)

#display(dropdown_inv, widgets.interactive_output(filter_df, {'status': dropdown_inv,}))
new_df_inv=df_in#new_df
gp_dt_inv=new_df_inv.groupby(col_curr)
gp_ls_inv=list(gp_dt_inv.groups.keys())
##########################


df_in=jobs_df
status_job_wk= col_curr ='Wk_inv_status'
entity_job='Teacher'
x_var_job='teacher_pay_amt'
title_job = 'ACD Job status'
opt_inv = list(df_in.groupby(col_curr).groups.keys())+['No Filter']

dropdown_job = widgets.Dropdown(
    options=opt_inv,
    value='No Filter',
    description='Filter jobs by:',
    disabled=False,
)

#display(dropdown_job, widgets.interactive_output(filter_df, {'status': dropdown_job,}))
new_df_job=df_in #new_df
gp_dt_job=new_df_job.groupby(col_curr)
gp_ls_job=list(gp_dt_job.groups.keys())

#gp_sum_job=gp_dt_job.agg('sum')
#print(x_var_job, '\n', '-'*25)


#############
fig = make_subplots(rows=2, cols=1, subplot_titles=(title_inv, title_job))

colors = ['darkseagreen', 'crimson', 'chartreuse', 'cornflowerblue',
    'forestgreen', 'fuchsia',  'blanchedalmond',  'darkcyan']

# Add traces inv
for status,c in list(zip(gp_ls_inv, colors[0:4])):
    print(status)
    df=gp_dt_inv.get_group(status)
    fig.add_trace(go.Bar(x=df[x_var_inv],y=df[entity_inv],name=str(status),
        marker=dict(color=c,
            line=dict(color=f'rgba(0, 0, 0, 1.0)',width=1),),
        orientation='h'),row=1, col=1)

#Add traces job
for status,c in list(zip(gp_ls_job, colors[4:8])):
    print(status)
    df=gp_dt_job.get_group(status)
    fig.add_trace(go.Bar(x=df[x_var_job],y=df[entity_job],name=str(status),
        marker=dict(color=c,
            line=dict(color=f'rgba(0, 0, 0, 1.0)',width=1),),
        orientation='h'),row=2, col=1)

# # Update title and height
fig.update_layout(title_text="Customizing Subplot Axes", height=1100)
fig.update_layout(barmode='stack')
#fig.show()

app = Dash()

html.H1(children='Title of Dash App', style={'textAlign':'center'}),
    
@callback(
    Output('graph-content', 'figure'),
    Input('dropdown-selection', 'value')
)

def update_graph(value):
    dff = df_gap[df_gap['country']==value]
    return px.line(dff, x='year', y='pop')

app.layout = html.Div(children=[
    # All elements from the top of the page
    html.Div([
        html.H1(children='Hello Dash'),

        html.Div(children='''
            Dash: A web application framework for Python.
        '''),

        dcc.Graph(
            id='example-graph',
            figure=fig
        ),  
    ]),
    # New Div for all elements in the new 'row' of the page
    html.Div([ 
        dcc.Graph(id='graph-content'),
        html.Label([
            "colorscale",
            dcc.Dropdown(df_gap.country.unique(), '', id='dropdown-selection')
        ]),
    ])
])

if __name__ == '__main__':
    app.run(debug=True) 