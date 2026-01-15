### data connection
import gspread
from oauth2client.service_account import ServiceAccountCredentials

## filter the dataframe for plot exploration
import ipywidgets as widgets
from IPython.display import display
#############################

import matplotlib.pyplot as plt
import plotly
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import base64
from IPython.display import Image
#############################

import pandas as pd
import random, sys, requests, json
from datetime import datetime
from datetime import timedelta
#############################

##############################
#### CLASS DEFINITIONS #######
##############################

class acct:
    def __init__(self, name, status, date):       
        self.name = name
        self.status = status
        self.amount = 'nd'
        self.origin = origin
        self.target = target
        self.date_initiated = date
        self.date_resolved = 'tbd'

class invoice(acct):
    def __init__(self, name, status='billed', job_ls=[]):
        super().__init__(self, name, status=status, job_ls=[])
        self.job_ls = job_ls
        
    def pay(pay_date, amount):
        self.date_resolved = pay_date
        self.status = 'payed'
        self.amount = amount

    def add_job(pay_date, amount):
        self.date_resolved = pay_date
        self.status = 'payed'
        self.amount = amount
        

class job (acct):
    def __init__(self, name, status='requested', staff_ls=[]):
        super().__init__(self, name, status=status, staff_ls=staff_ls)
        self.staff_dict = staff_dict

    def add_staff(worker, event_lnk):
        self.staff_dict.append({worker:event_lnk})

    def complete_job(self):
        pass

    def add_staff():
        pass
    
class entity:
    def __init__(self, name, status):       
        self.name = name
        #self.status = status
        #self.amount = amount
        #self.origin = origin 
        #self.target = target
        self.inv_wk=[] ##inv_wk_ls
        self.inv_brkr=[] #inv_brkr_ls
        self.jobs=[] #Jobs_ls
 
    def request_job(job, target):
        # make the job appending the job to the target's list
        job
        target.jobs.append(job)
        
        # add details
        target.job.append(target)
        
    
    def accept_job(job, source):
        job.source.append(source)
        self.Jobs.append(job)
    
    def pay_invoice(invoice, amount, target, date):
        pass

    def make_invoice(invoice, jobs, target, date):
        pass

    def receive_pay(invoice, amount, source, date):
        pass


class edu_cont_co(entity):
    pass
    #+receive_job_request()
    #+job_request()

class talent_co(entity):
    pass
    #+Name
    #+Inv_Wk=[]
    #+Inv_Brkr=[]
    #+Jobs=[]
    # +receive_job()
    # +staff_job(worker, job)
    # +Pay_invoice()
    # +Make_invoice() 
    # -staff(worker, job
    def staff_job(worker, job):
        pass
    
class client_co(entity):
    def make_job():
        pass

# Define the worker class

# class worker{
#         +is_fully_paid
#     def complete_job():
#         pass
#     }

class Worker(entity):
    def __init__(self, name, status):
        self.is_fully_paid = False
        self.name = name
        self.status = status
        self.job_ls = []
    # def complete_job(self):
    #     pass
    # def accept_job(self):
    #     pass

class Broker(entity):
    def __init__(self, name, status):
        self.name = name
        self.status = status