import dash
from dash import dcc, html, Input, Output
import acd_datatool as acd
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import numpy as np
import os
# your data & mappings
##### credentials through google cloud #####

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
DEFAULT_CREDENTIALS = os.path.expanduser("~/.ssh/financetrack-acd-aa2d12d1f346.json")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_CREDENTIALS)
CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, SCOPE)
GOOGLE_SHEET_URL = 'https://docs.google.com/spreadsheets/d/1QEgmIzrVF7pJzzpYyacGHpW5VF0T7dTSu5te3rq2UlI/edit?gid=1122289088#gid=1122289088'

###########################################
# load and parse data

#data_names=['jobs_expense', 'inv_payment']
data_names=['jobs_tbl', 'inv_tbl']

expected_head=[
    ['Teacher',	'start_date',	'end_date',	'job',	'Task_Descr',	'subtask',	'type',	'ACD_bill_dt',	'ACD_pay_dt',	'teacher_pay_dt',	'ACD_inv_status',	'ACD_invoice',	'ACD_inv_link',	'Wk_inv_status',	'Worker_invoice',	'worker_inv_link',	'Wk_Billed_dt',	'Inv_line_item',	'direct_client',	'End_client',	'project',	'teacher_pay_amt',	'worker_item_rate',	'days',	'item_quantity',	'ACD_billed_item_total',	'ACD_Item_Rate',	'ACD_overhead_Prc',	'ACD_day_rate',	'notes',	'email thread',	'Kbflow_job_ID',	'training hub link',	'Reggie_ID',	'Composite_job_ID',	'JobID_external',	'process notes'],
    ['invoice',	'inv_link',	'submitted_date',	'year',	'Inv_paid_date',	'inv_paid_link',	'job_start',	'Job_end',	'to_client',	'broker_chain',	'inv_from',	'end_client',	'job_name',	'task_descr',	'worker',	'status',	'inv_dollars',	'net_pay',	'payment_total',	'ACD_Account_delta',	'ACD_Acct_date',	'owed2acd',	'owed2workers',	'Employer_taxes',	'total_taxes',	'payment_fees',	'thread',	'follow_up',	'blank1',	'blank2',	'owed to workers']
    ]

data_dict={}
verbose = False
i=0

for k in data_names:
    
    data_dict[k]=acd.load_google_sheet(k, expected_head[i], CREDENTIALS, GOOGLE_SHEET_URL)
    i+=1
    print(f"loaded {k} sucessfully")

    
# Assign the dataframes the right names
jobs_df= data_dict[data_names[0]]
inv_pay_df = data_dict[data_names[1]]
param_dict={}

param_dict['ex_column_ls']=['job', 'worker_item_rate', 'item_quantity',\
                    'start_date', 'end_date', 'Task_Descr','Worker_invoice']

param_dict['jb_df_type_dict']={
        'date_cols':['start_date', 'end_date', 'ACD_bill_dt',
        'ACD_pay_dt', 'teacher_pay_dt'],
        'num_cols':['teacher_pay_amt', 'worker_item_rate', 'days',
        'item quantity','ACD_Item_Rate','ACD_overhead_Prc','ACD_day_rate']}   
    
param_dict['inv_df_type_dict']={
        'date_cols':['submitted_date', 'Inv_paid_date', 'job_start', 
                    'Job_end', 'ACD_Acct_date'],
        'num_cols':['inv_dollars', 'total_invice_amt', 'ACD_Account_delta',
                    'Employer_taxes', 'total_taxes', 'payment_fees', 'thread']}      
   

inv_pay_df_mod, jobs_df_mod = acd.prep_job_inv2(jobs_df, inv_pay_df, param_dict)

###  TODO check typcast failure in first pass for start_date and  end_date?
jobs_df_mod['start_date']=pd.to_datetime(jobs_df_mod['start_date'], errors='coerce')
jobs_df_mod['end_date']=pd.to_datetime(jobs_df_mod['end_date'], errors='coerce')
### add a years column to the jobs_df_mod
jobs_df_mod['year'] = jobs_df_mod['start_date'].dt.year


# filter on year and worker 
#filt_inv, filt_job = acd.df_filter(inv_pay_df_mod, jobs_df_mod, year=2024, worker='k.martin')

#inv_df_kmart = acd.load_google_sheet('inv_kmart', CREDENTIALS, GOOGLE_SHEET_URL)
entity_type_mappings = acd.entity_type_mappings
entity_type_ls = acd.entity_type_ls

# derive lists of teachers and years from your invoice DataFrame
teacher_ls = inv_pay_df_mod['inv_from'].dropna().unique().tolist()
billed_ls = inv_pay_df_mod['to_client'].dropna().unique().tolist()

if verbose:
    print(f"teacher_ls {teacher_ls}")
    print(f"entity_type_mappings {entity_type_mappings}")
    print(f"entity_type_ls {entity_type_ls}")
    print(inv_pay_df_mod.columns)
    print(billed_ls)
# 
#year_ls = jobs_df_mod['year'].unique()
#year_ls =year_ls.dropna()

year_ls = jobs_df_mod['year'].dropna().unique()
year_ls = np.sort(year_ls.astype(int)) 

#year_ls =year_ls(~pd.isna(year_ls))
#min_year, max_year = min(year_ls), max(year_ls)
min_year, max_year = int(year_ls.min()), int(year_ls.max())
if verbose:
    print (f"year_ls {year_ls}, year range, {min_year, max_year}")

# datasets = [
#             #job_requests
#             pd.DataFrame({"Source": [],"Target": [],"Status": []}),
#             # payments made
#             pd.DataFrame({"Source": [],"Target": [],"Status": []}),
#             #invoicing transactions
#             pd.DataFrame({"Source": [],"Target": [],"Status": []})]

#conveys entity order onto the diagram

entity_type_exclude = ["other", "service"]

# jobs sankey

# filt data
#datasets[0]=inv_df_all

entity_type_ls=[ent for ent in entity_type_ls if ent not in entity_type_exclude]
#unique_nodes = pd.concat([datasets[0]["Source"], datasets[0]["Target"]]).unique()
# remove entities that are non being used  
#unique_nodes_cln=[ent for ent in unique_nodes if entity_type_mappings[0].get(ent) in entity_type_ls] 


#new_df=filt_job[['job', 'direct client','ACD invoice', 'Worker invoice','Teacher','ACD_inv_status', 'Wk_inv_status','start_date']]

## Append slots for the job report: 'inv_statuses','inv_txt_rept'
#df_app=pd.DataFrame(np.empty((len(new_df),2),dtype=object),columns=['inv_statuses','inv_txt_rept'])
#new_df = pd.concat([new_df, df_app], axis=1)

#mode_dict= {'teacher':None, 'transit_table':False, 'status':True, 'verbose':False}
#out_df, ttbl= acd.job_report(new_df, mode_dict)

#######################
## this is the filter for the final sankey diagram
mode_dict= {'teacher':None, 'year':None, 'transit_table':False, 'status':False, 'verbose':False}
out_df, set_dict, inv_df= acd.inv_report(inv_pay_df_mod, mode_dict)

#mode_dict= {'teacher':'k.martin', 'year':2024, 'transit_table':True, 'status':True, 'verbose':False}
#out_df, set_dict, inv_df_kmart= acd.inv_report(inv_pay_df_mod, mode_dict)

###########################################

app = dash.Dash(__name__)

server = app.server

def serve_layout():
    try:
        return html.Div([
            html.H1("Stacked Sankey Diagram"),

            # teacher selector
            html.Label("Select teacher:"),
            dcc.Dropdown(
                id="teacher-dropdown",
                options=[{"label": t, "value": t} for t in teacher_ls],
                value=None,            # default = all teachers
                clearable=True
            ),
            # billed selector
            html.Label("Select billed:"),
            dcc.Checklist(
                id="billed-checklist",
                options=[{"label": t, "value": t} for t in billed_ls],
                value=billed_ls,            # default = all teachers
                inline=True
            ),

            # year slider
            # html.Label("Select year:"),
            # dcc.Slider(
            #     id="year-slider",
            #     min=min_year,
            #     max=max_year,
            #     step=1,
            #     marks={y: str(y) for y in sorted(year_ls)},
            #     value=min_year        # default
            # ),

            html.Label("Select entity types:"),
            dcc.Checklist(
                id="entity-type-checklist",
                options=[{"label": et, "value": et} for et in entity_type_ls],
                value=entity_type_ls,               # default: all checked
                inline=True
            ),
            dcc.Graph(id="sankey-diagram")
        ])

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return html.Div([
            html.H2(f"EEEError loading layout {e}"),
            html.Pre(str(e))
        ])
app.layout = serve_layout

"""Now restart your app and browse again. The console (and the page) will show the actual Python traceback of whatever is failing inside your layout. Once you see the root error you can remove the try/except and fix the offending line."""

##Input("year-slider", "value"),

@app.callback(
    Output("sankey-diagram", "figure"),
    Input("teacher-dropdown", "value"),
    Input("billed-checklist", "value"),
    Input("entity-type-checklist", "value")
)

#selected_year,
#def update_figure(selected_teacher, selected_year, selected_billed, selected_types):
def update_figure(selected_teacher,  selected_billed, selected_types):
    
    # rebuild mode_dict based on controls
    #'year': selected_year,  # year is not used in this example #'year': selected_year,
    ## make a new mode dict to update filter
    mode_dict = {
        'teacher': selected_teacher,
        'transit_table': False,
        'year': None, # works try 2025... 'year': selected_year,  # year is not used in this example #'year': selected_year,
        'status': False,
        'verbose': False
    }

    if selected_billed:
        # filter the inv_pay_df_mod based on selected_billed
        inv_df = inv_pay_df_mod[inv_pay_df_mod['to_client'].isin(selected_billed)]


    # re-filter your data
    out_df, set_dict, inv_df = acd.inv_report(inv_pay_df_mod, mode_dict)
    
    # apply billed filter afterwards
    
    # re-generate sankey
    fig = acd.update_stacked_sankey(
        [inv_df],
        entity_type_mappings,
        selected_types,
        verbose=False
    )
    return fig

if __name__ == "__main__":
    app.run_server(debug=True, port=8054)