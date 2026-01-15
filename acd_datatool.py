### imports
#############################
## data operations
#############################
import gspread
from oauth2client.service_account import ServiceAccountCredentials

## filter the dataframe for plot exploration
import ipywidgets as widgets
from IPython.display import display
import ast

import smtplib
from oauth2client.service_account import ServiceAccountCredentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


#############################
## parsing
#############################
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: pdfplumber not available. PDF parsing functions will be disabled.")
import pandas as pd
import re
import random, sys, requests, json
from datetime import datetime
from datetime import timedelta

#############################
## visualization
#############################

import plotly.colors as pc
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import base64
from IPython.display import Image
import copy

#>>from finance_tracker.dash_sankey import GOOGLE_SHEET_URL

##########################################
################ constants ###############
##########################################

entity_type_ls = ["other", "service", "client","training_co","talent_co","worker"]

# Corresponding entity type mappings
## CASE sanitized and we only need one overall mapping
entity_type_mappings = [
    
    {"webage":"training_co","bhanalyitcs":"training_co","accelebrate":"training_co",
    'axcel':"training_co", 'data_society':"training_co", 'exit_certifed':"training_co",
    
    'changecx':'client', 'perl health':'client', 'pma':'client', 
    'rancho_biosciences':'client','grakn':'client','iqumulus':'client',
    'omicia':'client', 'spectre':'client',  't.gerbino':'client', 'family_acct':'client', 

    "acd":"talent_co",

    'owner donation':'other', 'square inc o':'service','asmbly':'service',
    '':'other','nd':'other','other':'other','na':'other',

    "k.martin":"worker","g.kleemann":"worker",
    "a.martinez":"worker","c.healey":"worker",
    "g.cahal":"worker","g.mein":"worker","h.jang":"worker",
    "j.ying":"worker","k.kamerkar":"worker",
    "l.matheson":"worker","l.yurica":"worker","m.castro":"worker",
    "m.labowitz":"worker","m.laturney":"worker","o.darwish":"worker",
    "p.denkabe":"worker","r.lee":"worker","s.panesar":"worker",
    "t.alabi":"worker","y.mirza":"worker" }
    ]

## Functions#
############################
##### data parsing and ETL 
############################

def df_filter(df_inv, df_job, year, worker):
    filt_inv=df_inv[(df_inv['submitted_date'].dt.year == year) & (df_inv['inv_from']==worker)]
    filt_job=df_job[(df_job['start_date'].dt.year == year) & (df_job['Teacher']==worker)]
    return filt_inv, filt_job

def prep_job_inv(jobs_df, inv_pay_df):
    """   """
    jb_df_type_dict={
        'date_cols':['start_date', 'end_date', 'ACD_bill_dt',
        'ACD_pay_dt', 'teacher_pay_dt'],
        'num_cols':['teacher_pay_amt', 'worker item rate', 'days',
        'item quantity','ACD_Item_Rate','ACD overhead Prc','ACD day rate']}      

    batch_typecast(jobs_df, jb_df_type_dict, verbose=False)

    inv_df_type_dict={
        'date_cols':['submitted_date', 'Inv_paid_date', 'job_start', 
                    'Job_end', 'ACD_Acct_date'],
        'num_cols':['inv_dollars', 'total invice amt', 'ACD_Account_delta',
                    'Employer taxes', 'total taxes', 'payment_fees', 'thread']}      

    batch_typecast(inv_pay_df, inv_df_type_dict, verbose=False)

    jobs_df=clean_n_rpt(jobs_df)  # (jobs_df, verbose = False, sheet_overview=None)
    inv_pay_df=clean_n_rpt(inv_pay_df)  #
    jobs_df_mod = copy.deepcopy(jobs_df)
    inv_pay_df_mod = copy.deepcopy(inv_pay_df)

    # for expansion we need to make list of lists. this might better be handled on the ingestion step
    # invoices probably should stay as single items even if they link multiple jobs

    # for these columns cast any lists in these into true lists
    ex_column_ls = ['job', 'worker item rate', 'item quantity',\
                    'start_date', 'end_date', 'Task_Descr','Worker invoice']

    jobs_df_mod= appl_strls(jobs_df_mod, ex_column_ls)

    #ex_column_ls = ['job', 'worker item rate', 'item quantity']
    #print(new_jobs_lsts_mod.head())

    ### check every cell and fix lists where required. 
    for col in ex_column_ls:
        jobs_df_mod[col] = jobs_df[col].astype(str).apply(strls_as_ls)

        ## do each row in turn, 
        jobs_df_mod[col] = jobs_df_mod[col].astype(str).apply(strls_as_ls)

    #print(new_jobs_lsts_mod.iloc[8:11,-4:-2])
    #type(jobs_df_mod.columns)#['teacher_pay_amt'][0])
    #to_list(new_jobs_lsts_mod['teacher_pay_amt'][0])

    return (inv_pay_df_mod, jobs_df_mod)

def prep_job_inv2(jobs_df, inv_pay_df, param_dict):
    """prep both job and invoice dataframes for analysis, this version takes in columns to process as variables"""
    
    ex_column_ls=param_dict['ex_column_ls']
    jb_df_type_dict=param_dict['jb_df_type_dict']
    inv_df_type_dict=param_dict['inv_df_type_dict']

    batch_typecast(jobs_df, jb_df_type_dict, verbose=False)
    batch_typecast(inv_pay_df, inv_df_type_dict, verbose=False)

    jobs_df=clean_n_rpt(jobs_df)  # (jobs_df, verbose = False, sheet_overview=None)
    inv_pay_df=clean_n_rpt(inv_pay_df)  #
    jobs_df_mod = copy.deepcopy(jobs_df)
    inv_pay_df_mod = copy.deepcopy(inv_pay_df)

    # for expansion we need to make list of lists. this might better be handled on the ingestion step
    # invoices probably should stay as single items even if they link multiple jobs

    # for these columns cast any lists in these into true lists
    jobs_df_mod= appl_strls(jobs_df_mod, ex_column_ls)

    ### check every cell and fix lists where required. 
    for col in ex_column_ls:
        jobs_df_mod[col] = jobs_df[col].astype(str).apply(strls_as_ls)

        ## do each row in turn, 
        jobs_df_mod[col] = jobs_df_mod[col].astype(str).apply(strls_as_ls)

    #print(new_jobs_lsts_mod.iloc[8:11,-4:-2])
    #type(jobs_df_mod.columns)#['teacher_pay_amt'][0])
    #to_list(new_jobs_lsts_mod['teacher_pay_amt'][0])

    return (inv_pay_df_mod, jobs_df_mod)

def load_google_sheet(worksheet_nm, expected_headers, CREDENTIALS, GOOGLE_SHEET_URL):
    """
    Loads data from a specified worksheet in a Google Sheet and returns it as a pandas DataFrame.
    Args:
        worksheet_nm (str): The name of the worksheet to load from the Google Sheet.
        expected_headers (list): A list of expected header names to use when parsing the worksheet records.
        CREDENTIALS (object): Google API credentials object used for authentication with gspread.
        GOOGLE_SHEET_URL (str): The URL of the Google Sheet to access.
    Returns:
        pandas.DataFrame: A DataFrame containing the data from the specified worksheet.
    Raises:
        gspread.exceptions.APIError: If there is an issue accessing the Google Sheet.
        ValueError: If the worksheet name does not exist in the Google Sheet.
    """
    client = gspread.authorize(CREDENTIALS)
    sheet_overview = client.open_by_url(GOOGLE_SHEET_URL)
    worksheet = sheet_overview.get_worksheet(0)  # Load the first sheet
    
    ### get the data row-wise ###
    worksheet_rw=sheet_overview.worksheet(worksheet_nm).get_all_records(expected_headers=expected_headers)

    # get_all_values gives a list of rows
    return pd.DataFrame.from_records(worksheet_rw)

# def load_google_sheet(worksheet_nm, headers=None):
#     client = gspread.authorize(CREDENTIALS)
#     sheet_overview = client.open_by_url(GOOGLE_SHEET_URL)
#     #worksheet = sheet_overview.get_worksheet(0)  # Load the first sheet
    
#     ### get the data row-wise ###
#     curr_wks=sheet_overview.worksheet(worksheet_nm).get_all_records(expected_headers=headers)

#     # get_all_values gives a list of rows
#     return pd.DataFrame.from_records(curr_wks)



def batch_typecast(df, type_dict, verbose=False):
    """for each column typecast it if it is listed in typedict"""
    for col in df.columns:
        if verbose:
            print(f"checking {col}")

        if col in type_dict['date_cols']:
            df[col]=pd.to_datetime(df[col], errors='coerce')

        elif col in type_dict['num_cols']:
            df[col]=pd.to_numeric(df[col], errors='coerce')

        else:
            if verbose:
                print(f"{col} was not in the typedict")
    if verbose:
        df.info()

def expand_lsts (df, out_nm = 'expanded.csv', ignore_idx = False):
    """ take in a dataframe with nested lists, based on the ex_colum expand the dataframe 
    explode based on a list of columns
    """
    df = df.apply(pd.Series.explode, ignore_index = ignore_idx)
    #df=df.explode(ex_column_ls)
    df.to_csv(out_nm)
    return df

def load_method(method, secrets_ls):
    """## local implies that you have the google sheets ssh key file on your local machine. 
    ## colab assumes that you are using colab with colab secrets
    # e.g. for secrets API locally
    # """

    #Method 1 -  this loads the ssh key for the service account
    if method == 'l' or 'L' or 'local':
  
        #For colab use secrets
        ## *** get API code from secrets or use server side key file

        # api secrets file
        with open (secrets_ls[1], 'r') as f:
            api_dict= json.loads(f.read())

        # google secrets account Path to the credentials file
        filename = secrets_ls[0]
        
        # Define the scope
        scope = ['https://spreadsheets.google.com/feeds', 
            'https://www.googleapis.com/auth/drive']

        # Load credentials from the file
        credentials = ServiceAccountCredentials.from_json_keyfile_name(filename, scope)

        g_conect = gspread.authorize(credentials)

    #Method 2 use on colab - this injects the credential from the user authentication
    elif method == 'c' or 'C' or 'colab_auth':

        ### this will step you thourgh an authentication routine thorugh popup windows
        from google.colab import auth
        auth.authenticate_user()

        from google.auth import default

        creds, _ = default()
        g_conect = gspread.authorize(creds)

        from google.colab import drive
        drive.mount('/content/gdrive')
        # Load the Google Sheets
        # gc = gspread.service_account(filename=filename)  # Replace with your credentials file
    else:
        print("no valid method selected")
        sys.exit()
    return (g_conect, api_dict)

def create_google_sheet(sheet_name, dataframe, credentials_file, share_with_emails):
    """
    Creates a new Google Sheet, populates it with DataFrame content, and shares it with specified users.
    """
    # Authenticate with Google Sheets API
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(credentials)
    
    # Create a new Google Sheet
    sheet = client.create(sheet_name)
    
    # Open the first worksheet and populate it with DataFrame content
    worksheet = sheet.get_worksheet(0)
    worksheet.update([dataframe.columns.values.tolist()] + dataframe.values.tolist())
    
    # Share the Google Sheet with specified users
    for email in share_with_emails:
        sheet.share(email, perm_type='user', role='writer')
    
    return sheet.url  # Return the URL of the created sheet

def send_email_notification(sender_email, sender_password, recipients, sheet_links):
    """
    Sends email notifications to recipients with links to the created Google Sheets.
    """
    subject = "New Google Sheets Created for Review"
    body = f"""
    Dear Reviewer,

    The following Google Sheets have been created for your review:
    
    - Invoices Review Sheet: {sheet_links['invoices']}
    - Jobs Review Sheet: {sheet_links['jobs']}

    Please review them at your earliest convenience.

    Best regards,
    Automated System
    """
    
    # Set up the email
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Send the email
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipients, msg.as_string())

def extract_text_locally(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() for page in pdf.pages)
    return text

############################
##### visualization #######
############################

def mm(graph):
  graphbytes = graph.encode("ascii")
  base64_bytes = base64.b64encode(graphbytes)
  base64_string = base64_bytes.decode("ascii")
  display(
    Image(
      url="https://mermaid.ink/img/"
      + base64_string
    )
  )

def show_named_plotly_colours():
    """
    function to display to user the colours to match plotly's named
    css colours.

    Reference:
        #https://community.plotly.com/t/plotly-colours-list/11730/3


    Returns:
        plotly dataframe with cell colour to match named colour name

    """
    s='''
        aliceblue, antiquewhite, aqua, aquamarine, azure,
        beige, bisque, black, blanchedalmond, blue,
        blueviolet, brown, burlywood, cadetblue,
        chartreuse, chocolate, coral, cornflowerblue,
        cornsilk, crimson, cyan, darkblue, darkcyan,
        darkgoldenrod, darkgray, darkgrey, darkgreen,
        darkkhaki, darkmagenta, darkolivegreen, darkorange,
        darkorchid, darkred, darksalmon, darkseagreen,
        darkslateblue, darkslategray, darkslategrey,
        darkturquoise, darkviolet, deeppink, deepskyblue,
        dimgray, dimgrey, dodgerblue, firebrick,
        floralwhite, forestgreen, fuchsia, gainsboro,
        ghostwhite, gold, goldenrod, gray, grey, green,
        greenyellow, honeydew, hotpink, indianred, indigo,
        ivory, khaki, lavender, lavenderblush, lawngreen,
        lemonchiffon, lightblue, lightcoral, lightcyan,
        lightgoldenrodyellow, lightgray, lightgrey,
        lightgreen, lightpink, lightsalmon, lightseagreen,
        lightskyblue, lightslategray, lightslategrey,
        lightsteelblue, lightyellow, lime, limegreen,
        linen, magenta, maroon, mediumaquamarine,
        mediumblue, mediumorchid, mediumpurple,
        mediumseagreen, mediumslateblue, mediumspringgreen,
        mediumturquoise, mediumvioletred, midnightblue,
        mintcream, mistyrose, moccasin, navajowhite, navy,
        oldlace, olive, olivedrab, orange, orangered,
        orchid, palegoldenrod, palegreen, paleturquoise,
        palevioletred, papayawhip, peachpuff, peru, pink,
        plum, powderblue, purple, red, rosybrown,
        royalblue, saddlebrown, salmon, sandybrown,
        seagreen, seashell, sienna, silver, skyblue,
        slateblue, slategray, slategrey, snow, springgreen,
        steelblue, tan, teal, thistle, tomato, turquoise,
        violet, wheat, white, whitesmoke, yellow,
        yellowgreen
        '''
    li=s.split(',')
    li=[l.replace('\n','') for l in li]
    li=[l.replace(' ','') for l in li]

    import pandas as pd
    import plotly.graph_objects as go

    df=pd.DataFrame.from_dict({'colour': li})
    fig = go.Figure(data=[go.Table(
      header=dict(
        values=["Plotly Named CSS colours"],
        line_color='black', fill_color='white',
        align='center', font=dict(color='black', size=14)
      ),
      cells=dict(
        values=[df.colour],
        line_color=[df.colour], fill_color=[df.colour],
        align='center', font=dict(color='black', size=11)
      ))
    ])

    fig.show()

############################
##### Main Functions #######
############################

def wk_inv_stat():
  """dataframe of submitted invoices; with, invoiced, pending, paid
  Output:
  summary stats table
  bar chart
  """

def jb_stat():
  """dataframe of jobs with status, pending, invoiced completed
  Output:
  summary stats table
  bar chart
  """

def df_lower(df, tgt_type, verbose=False):
    """clean all of a certain type ot lower, these will come in as
    strings (object) without typecasting
    cleans the DF in place"""

    for x in df.columns:
        if df[x].dtype == tgt_type:
            if verbose:
                print('object - lowercase implemented')
            df[x] = df[x].str.lower()
        else:
            df[x] = df[x]
    
    return df

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

## mar plot exploration
def expl(df, col, category, verbose=True, stacked=False, title='add_title'):
    """count crosstab for col by category"""
    df=pd.crosstab(df[col], df[category])
    if verbose==True:
        print(df)

    #fig, ax1 = plt.subplots(figsize=(3, 7), layout='constrained')
    #df = pd.DataFrame({'speed': jobs_df[col_1[0]]},index=jobs_df[col_1[1]])
    ax1 = df.plot.barh(figsize=(10,12), stacked=stacked) # subplots=True
    ax1.legend(loc=1)
    ax1.set_title(title)
    # add number on top of each bar
    ax1.bar_label(ax1.containers[0], label_type='edge', color='red', rotation=90, fontsize=7, padding=3)

# # Dropdown widget
# dropdown = widgets.Dropdown(
#     #options=['No filter', 'Paid', 'submitted', 'unsubmitted'],
#     #options=['No Filter', 'paid', 'unpaid', 'unsubmitted'],
#     value='No Filter',
#     description='Filter by:',
#     disabled=False,
# )

##############################
#### CLASS DEFINITIONS #######
##############################

# Define the worker class
class Worker:
    def __init__(self, name, status):
        self.name = name
        self.status = status

class Broker:
    def __init__(self, name, status):
        self.name = name
        self.status = status

class invoice:
    def __init__(self, name, status):
        self.name = name
        self.status = 'billed'
        self.bill_date = bill_date
        self.data = {}

    def pay():
        self.pay_date = pay_date
        self.status = 'payed'

#### Kanbanflow data tools ####
# get user list from all boards
def get_kanabndata(query, api_token, base64mode=False):
    """basic and base64 encoded modes, base 64 fails now but basic does not
    """
    if base64mode==True:
        encoded_token = base64.b64encode(api_token.encode()).decode()

    for q in queries:
        # Make the API call
        # Define the API endpoint and token
        if base64mode==True:
            api_url = f"https://kanbanflow.com/api/v1/{q}"
            # Set up the headers with the encoded token
            headers = {
                'Authorization': f'Basic {encoded_token}'
            }
            response = requests.get(api_url, headers=headers)
        else:
            api_url = f"https://kanbanflow.com/api/v1/{q}apiToken={api_token}"
            print(api_url)
            response = requests.get(api_url)

        # Check if the request was successful
        if response.status_code == 200:
            # Parse the JSON response
            data = response.json()
            print(data)
            
            try:
                # Convert the JSON data to a DataFrame
                df = pd.DataFrame(data)
                
                # Display the DataFrame
                print(df.head())
            except Exception as e:
                print(f'could not make a DF {e}')
            
        else:
            print(f"Failed to retrieve data: {response.status_code}")
    return df


# #clean the data - in  _________do this for all three...
# def clean_n_rpt(sheet_overview, df, verbose = False):
#     df=acd.df_lower(df, "object")
#     df.columns = df.columns.str.strip()

#     # inv_pay_df.columns = inv_pay_df.columns.str.strip()
#     if verbose == True:
#         sheet_overview.worksheets()
#         display(df.head())
#         display(df)
#     return df


######### methods #########
def determine_inv_status(row, col ='inv_statuses',  val=['X', 'X', 'X', 'X']):
    if type(val) == 'str':
        return str.lower(row[col]) == str.lower(val)
    else:
        return row[col] == val


#clean the data - in  _________do this for all three...
def clean_n_rpt(df, verbose = False, sheet_overview=None):
    """"""
    df=df_lower(df, "object")
    df.columns = df.columns.str.strip()

    if sheet_overview is not None and verbose == True:
        sheet_overview.worksheets()
        display(df.head())
        display(df)
    return df


def strls_as_ls(strls):
    """ fix a list cast as a string if it has [] inside else do nothing"""
    
    # for all of the liststrings
    if len(re.findall(r"[\[\]]", strls)) == 2:
        ls = [item.strip() for item in strls.strip('[]').split(',') if item != "  "]
        cleaned_list = [item for item in ls if item.strip()]
        return cleaned_list
    else:
        return strls

### check every cell and fix lists where required.
# 
def appl_strls(df, ex_column_ls):
    """apply the itemwise list-cast to selected columns"""
    for col in ex_column_ls:
         ## do each row in the current col 
        df[col] = df[col].astype(str).apply(strls_as_ls)
    return df


def appl_explode(df, ex_column_ls, col_mode = 'all', verbose = False):
    """ this is a wrapper for df.explode that allows you to run multiple 
    columns one at a time
    
    col_mode = {'all', 'cart_prod'}
    when nested item count differs by row, we can take the there is an issue need to do these one at a time or suffer index mismatch!
    
    ########### References ################
    import pandas as pd

    # Example DataFrame
    data = {
        'A': [[1, 2, 3], [4, 5], [6]],
        'B': [['a', 'b', 'c'], ['d', 'e'], ['f']],
        'C': [10, 20, 30]  # A column without lists
    }

    df = pd.DataFrame(data)
    print("Original DataFrame:")

    # Explode both columns 'A' and 'B'
    df_exploded = df.apply(pd.Series.explode)

    print("\nExploded DataFrame:")
    print(df_exploded)

    https://stackoverflow.com/questions/63139154/pandas-explode-cannot-reindex-from-a-duplicate-axis
    https://sparkbyexamples.com/pandas/pandas-explode-multiple-columns/#:~:text=Alternatively%2C%20You%20can%20also%20use,be%20duplicated%20for%20these%20rows.
    """

    if verbose == True:
        print(f'shape before {df.shape}')
        display(df.head(10))

    if col_mode == 'all':
        try: 
            df = df.apply(pd.Series.explode).reset_index().drop(labels="index", axis =1)
            #df = df.apply(pd.Series.explode)
            #df = df.explode(ex_column_ls, ignore_index = True)
        except Exception as e: 
            mssg= f'There was an error \n\n ERROR: {e} \n\n Make sure that across rows, nested item count matches \n'
            print ('#'*50+ '\n',mssg,'#'*50+ '\n')

    if col_mode == 'cart_prod':
        for col in ex_column_ls:
            if verbose:
                print(f'testing this colwise: {col}')
                #df= appl_explode(df, col)
            try: 
                df= df.explode(col).reset_index().drop("index",1)
                #df = df.explode(ex_column_ls, ignore_index = True)
            except Exception as e: 
                mssg= f'There was an error \n\n ERROR: {e} \n\n Make sure that across rows, nested item count matches \n'
                print ('#'*50+ '\n',mssg,'#'*50+ '\n')
                
    if verbose == True:
        print(f'shape after {df.shape}')
        display(df.head(10))
    return df

def get_pay_amt(row, verbose=False):
    "get pay amount per job from job_df format"
    rate = row['worker item rate']
    quantity = row['item quantity']

    if verbose == True:
        for i in [rate, quantity]:
            print(f"{type(i)} value {i} is none {i== 'None'}")
        print(f" both none? {(rate or quantity) == 'None'}")
        
    #this gives true when either or both == none
    if (quantity or rate) == 'None':
        if verbose == True: print('found a none')
        
        return 'None'
        
    else:
        if verbose == True: print('not a none')
        rate=float(ast.literal_eval(row['worker item rate']))
        quantity=float(ast.literal_eval(row['item quantity']))
        
        return quantity * rate 


def check_rowbyrow(df, funct=appl_explode, start=0, stop=0, error_free=True, verbose=True):
    """Check a function by continually expanding the stopping row of the input; 
    don't use for huge datasets need to break on first error
    use the optional start to narrow down which rows are failing"""    
    #while error_free == True: 
    # we need to slice it or it will take the whole thing
    
    df=df.iloc[start:stop]
    
    for stp in range(start, stop):
        if verbose ==True:
            print (f'going to row{stp}')
        try:
            new_jobs_multrow_df_exp=funct(df.iloc[0:stp], [], col_mode = 'all', verbose = False)
        
        ### it looks like the except is from inside the fucntion. so it never gets here
        except Exception as e:
            print(f"failed on row {stp} /n with error code: {e}")
            #error_free = False 


def job_report(new_df, mode_dict):
    """ Iterate over each row, add the status code also instantiate the object 

    mode_dict= {teacher=None or name, transit_table=True, status=True, verbose=False}
    
    LEGEND 
    #status=[ACD, ACD,'||', WK, WK]

    #status=[{job} ; {client} > , > , {ACD} || {ACD} > > {WK} ]
    #status=#status=[{job} ; {client} > , > , {ACD} || {ACD} >  {WK} ] ['X','X/>','||','</X','</X']
    #print(f"Row {index}: {row.to_dict()}")
    
    EXPECTED DATA FRAME COLUMNS
    'job', 'direct client','ACD invoice', 
    'Worker invoice','Teacher','ACD_inv_status', 
    'Wk_inv_status','start_date', 'inv_statuses','inv_txt_rept'

    """
    
    # set a null version of the status
    status=['X','X','||','X','X']

    # filter by worker if selected
    if mode_dict['teacher']:
        new_df = new_df[new_df['Teacher'] == mode_dict['teacher']]

    for index, row in new_df.iterrows():
    ## chart the entities
        
        jb=row.iloc[0]
        clnt=row.iloc[1]
        inv1=row.iloc[2]
        hm_co='ACD'
        inv2=row.iloc[3]
        wk=row.iloc[4]

        ## print fails if this is blank (NaT)
        stdt=pd.to_datetime(row.iloc[7])
        if pd.isnull(stdt):
            stdt=pd.to_datetime('1/1/1970') 
        stdt = stdt.strftime('%Y-%m-%d')


        # update the statuses from the dict
        respon_dct={'unsubmitted':['X','X'], 
                    'submitted':['X','-'], 
                    'paid':['-','-']}
        
        if row['ACD_inv_status'] in respon_dct.keys():
            #status[0:2]=respon_dct[row['ACD_inv_status']]
            s1,s2=respon_dct[row['ACD_inv_status']][0],respon_dct[row['ACD_inv_status']][1]
        
        if row['Wk_inv_status'] in respon_dct.keys():
            #status[2:4]=respon_dct[row['Wk_inv_status']]
            s3,s4=respon_dct[row['Wk_inv_status']][0],respon_dct[row['Wk_inv_status']][1]
        
        try:
            status=\
            f"{stdt:>{10}.{10}}|{clnt:>{5}.{5}}-{s1}->{inv1:>{7}.{7}}-{s2}->{hm_co:<{7}.{7}}-{s3}->{inv2:>{15}.{15}}-{s4}-> {wk:>{7}.{7}}| {jb:>{15}.{15}}"
            print(f'*******parsed status sucessfully {status}')
        
        except Exception as e:
            if mode_dict['verbose']:
                print (f"***** failed parse at:\n index: {index} ****** \n row:{row} \n error {e}")

        if mode_dict['status']==True:
            #status=mode_dict['status']
            print(status)
            
        ## This draws the job invoice status ASCII "text report"
        new_df.at[index, 'inv_statuses'] = status
        text_report = f'{jb} Job: {clnt} {status[0]} {inv1} {status[1]}\
        {hm_co} {status[2]} {inv2} {status[3]} {wk}'
       
        new_df.at[index, 'inv_txt_rept'] = text_report
    
    # report out
        if mode_dict['verbose']: 
            print(f"ACD_inv_status: {row['ACD_inv_status']} Wk_inv_status: {row['Wk_inv_status']}")
            print(status, '\n'+'#'*50+'\n',  text_report)
            #print(colorize_status(status, text_report))
            print('-'*50)
    
    transit_table = new_df['inv_statuses'].value_counts()
    if mode_dict['transit_table']:
        print(transit_table)
        
    
    print ('########'*10+'\n\n') 
    #return transit_table
    return(new_df, transit_table)

# Function to safely format values
def safe_format(val, default=""):
    """ Safely format values, replacing NaT or NaN with a default value """
    if isinstance(val, pd.Timestamp) and pd.isna(val):  # Check for NaT
        return default
    if isinstance(val, float) and pd.isna(val):  # Check for NaN
        return default
    return val  # Return original if not NaT or NaN

def inv_report(new_df, mode_dict, verbose=False):
    """ Iterate over each row, add the status code also instantiate the object 
    mode_dict= {teacher=None or name, transit_table=True, status=True, verbose=False}
    
    LEGEND 
    #status=[ACD, ACD,'||', WK, WK]
    #status=[{job} ; {client} > , > , {ACD} || {ACD} > > {WK} ]
    #status=#status=[{job} ; {client} > , > , {ACD} || {ACD} >  {WK} ] ['X','X/>','||','</X','</X']
    #print(f"Row {index}: {row.to_dict()}")
    
    EXPECTED DATA FRAME COLUMNS
    'invoice', 'job_start','job_name',
    'workers','status','inv_from',
    'to_client','inv_dollars'
    """
    
    inv_dict={
            "Source": [],
            "Target": [],
            "Status": [],
            "Inv_name": [],
            }

    set_dict={'jobs':set(), 'inv':set()}
    
    # filter by worker and year if called out in dictionary
    if mode_dict['teacher']:
        new_df = new_df[new_df['inv_from'] == mode_dict['teacher']]
   
    if mode_dict['year']:
        year=mode_dict['year']
        new_df=new_df[new_df['submitted_date'].dt.year == year]

    for index, row in new_df.iterrows():
    ## chart the entities
        ## completion mesures - 

        # proof of transactios
        inv_nm = row.iloc[0]        
        invlnk='-->' if row.iloc[1] else '-X>' #'inv_link', 
        pdlnk='-->' if row.iloc[3] else '-X>' #'Inv_paid_date',
        
        # timing
        #inv_dt=row.iloc[2]#'submitted_date', 
        #pd_dt=row.iloc[3]#'inv_paid_link',
        
        invto=row.iloc[8]
        invfr=row.iloc[10]
        stat=row.iloc[15] #status {'paid', 'nd', '', 'pending', 'void', '?'}
        inv_amt=row.iloc[16] 
        delta=row.iloc[18]
        deposit_dt=row.iloc[19]
        jb=row.iloc[12]
    
        #f"{inv_pay_df.iloc[2,2]:%Y-%m-%d}" # %H:%M
        #status=f"{inv_dt::%Y-%m-%d >{9}.{9}}|
        bill_dt=row.iloc[2]
        pay_dt=row.iloc[4]#'inv_paid_link',
        
        bill = f'{bill_dt}' if pd.isnull(bill_dt) else f'{bill_dt:%Y%m%d}'
        pay = f'{pay_dt}' if pd.isnull(pay_dt) else f'{pay_dt:%Y%m%d}'


        # Replace NaT/NaN values with default strings
        bill = safe_format(bill, "N/A")
        stat = safe_format(stat, "N/A")
        pay = safe_format(pay, "N/A")
        inv_nm = safe_format(inv_nm, "Unknown")
        invfr = safe_format(invfr, "N/A")
        invlnk = safe_format(invlnk, "N/A")
        invto = safe_format(invto, "N/A")
        pdlnk = safe_format(pdlnk, "N/A")
        inv_amt = safe_format(inv_amt, "0.00")

        try:
            status_output=f"{bill:>{8}.{8}}|{stat:>{5}.{5}}|{pay:>{8}.{8}}|{inv_nm:<{15}.{15}} fr:{invfr:>{7}.{7}} {invlnk:>{4}.{4}} to:{invto:>{5}.{5}} {pdlnk:>{4}.{4}} || amt:{inv_amt:>{10}.{10}}"
        except Exception as e:
            if verbose:
                print(f'**failed to parse: {row}**')
                print(f'**failed to parse: exception {e}**')
            continue

        #collect the entities
        set_dict['jobs'].add(jb)
        set_dict['inv'].add(invto)
        set_dict['inv'].add(invfr)
        
        if mode_dict['status']==True:
            if verbose:
                print(status_output)
            
        ## This draws the job invoice status ASCII "text report"
        try:
            new_df.at[index, 'inv_statuses'] = status_output
        except Exception as e:
            print(f"{e} unable to get status at index:{index} value:{status_output}")
            continue
    #inv_rept - makes three lists in a data frame
        inv_dict["Source"].append(invfr)  
        inv_dict["Target"].append(invto)
        inv_dict["Status"].append(stat)
        inv_dict["Inv_name"].append(inv_nm)

            # cast the dictionary as a dataframe for ingestion into the sankey
    inv_rept_df = pd.DataFrame({"Source":inv_dict["Source"],
        "Target":inv_dict["Target"],
        "Status":inv_dict["Status"],
        "Inv_name":inv_dict["Inv_name"]})


    #transit_table = new_df['inv_statuses'].value_counts()
    # toggleable printout
    #if mode_dict['transit_table']:
    #    print(transit_table)
    print ('########'*10+'\n\n') 

    #return transit_table
    return(new_df, set_dict,inv_rept_df) #
    
#def update_stacked_sankey(load_demo_clicks):

def update_stacked_sankey(datasets=None, entity_type_mappings=None, entity_type_ls=None, verbose=True):
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
    #entity_type_ls=[ent for ent in entity_type_ls if ent not in entity_type_exclude]
    #print(entity_type_ls)
    
    #for i, (demo_data, entity_types) in enumerate(zip(datasets, entity_type_mappings), start=1):
    for i, (demo_data) in enumerate(datasets, start=1):
        ## sanitize case
        print(i)
        
        # Determine unique nodes and assign x positions based on entity type
        try:
            unique_nodes = pd.concat([demo_data["Source"], demo_data["Target"]]).unique()
            unique_nodes_cln=[ent for ent in unique_nodes if entity_type_mappings[0].get(ent) in entity_type_ls] 
            unique_nodes=unique_nodes_cln
        except Exception as e:
            print(f'*** Failed to parse node {e}')

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
                    print(f'*** not adding entity to x position {node} : {entity_types[node]} : {e}')
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
                    print(f'*** not adding entity to node list {node}:{entity_types[node]}: {e}')
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
                    print(f'*** Not adding entity to y position: {e}')
                continue
        if verbose:        
            display(y_positions)        

        # Generate indices for sources and targets
        node_indices = {node: idx for idx, node in enumerate(unique_nodes)}
        source_indices = demo_data["Source"].map(node_indices).tolist()
        target_indices = demo_data["Target"].map(node_indices).tolist()
        
        #'Status', 'Inv_name'

        # Create link colors
        colors = pc.qualitative.Set1
        #link_colors = [colors[j % len(colors)] for j in range(len(source_indices))]
        status_ls = [i.lower() for i in demo_data["Status"]]
        inv_ls = [i.lower() for i in demo_data["Inv_name"]]

        #link_colors=[colors[2] if yn == 'y' colors[0] for yn in status_ls]
        link_colors = [colors[2] if status == 'paid' else (colors[3] if status == 'pending' else colors[0]) 
        for status in status_ls]

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
                    color=link_colors,
                    #inv=inv_ls,
                    customdata=list(zip(inv_ls, status_ls)),
                    hovertemplate = 'Source: %{source.label}<br>Target: %{target.label}<br>status: %{customdata[1]} <br>invoice name: %{customdata[0]}'
 
                )
        
        #fig.data[0].link.customdata = inv_ls

        #print(link_dict)
        #print(link_dict)

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

    #if add_to_fig==True:
    fig.update_layout(annotations=annot_ls[0:dataset_ct],
        height=800,  # Adjust height to fit all subplots
        title="Stacked Sankey Diagrams",
        font=dict(size=10),
        showlegend=False
    )
    return fig
