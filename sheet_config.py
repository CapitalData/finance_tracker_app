"""Google Sheets configuration constants.

This module contains the table names and expected headers for the finance tracker
Google Sheets. Extracted from sankey_helpers.py to avoid importing heavy Dash
dependencies in non-UI scripts.
"""

# Google Sheets table names
DATA_NAMES = ['jobs_tbl', 'inv_tbl']

# Expected headers for each table
EXPECTED_HEADERS = [
    # jobs_tbl headers
    ['Teacher', 'start_date', 'end_date', 'job', 'Task_Descr', 'subtask', 'type',
     'ACD_bill_dt', 'ACD_pay_dt', 'teacher_pay_dt', 'ACD_inv_status', 'ACD_invoice',
     'ACD_inv_link', 'Wk_inv_status', 'Worker_invoice', 'worker_inv_link',
     'Wk_Billed_dt', 'Inv_line_item', 'direct_client', 'End_client', 'project',
     'teacher_pay_amt', 'worker_item_rate', 'days', 'item_quantity',
     'ACD_billed_item_total', 'ACD_Item_Rate', 'ACD_overhead_Prc', 'ACD_day_rate',
     'notes', 'email thread', 'Kbflow_job_ID',
     'Composite_job_ID', 'JobID_external', 'process notes',
     'acc_work_order_id','acc_request_id','reggie_id'],
    # inv_tbl headers
    ['invoice', 'inv_link', 'submitted_date', 'year', 'Inv_paid_date',
     'inv_paid_link', 'job_start', 'Job_end', 'to_client', 'broker_chain',
     'inv_from', 'end_client', 'job_name', 'task_descr', 'worker', 'status',
     'inv_dollars', 'net_pay', 'payment_total', 'ACD_Account_delta',
     'ACD_Acct_date', 'owed2acd', 'owed2workers', 'Employer_taxes', 'total_taxes',
     'payment_fees', 'thread', 'follow_up', 'notes', 'eteam_id', 'reggie_id', 
     'qb_invoice_id', 'qb_invoice_url', 'qb_sync_status', 'qb_synced_at', 'qb_error']
]
