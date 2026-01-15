#step functions financial workflow 2

# Mapper logic 
{
  "Type": "Map",
  "ItemsPath": "$.s3_keys.jobs_tbl.batches",
  "ItemProcessor": {
    "ProcessorConfig": {
      "Mode": "INLINE"
    },
    "StartAt": "ClassifyRow",
    "States": {
      "ClassifyRow": {
        "Type": "Task",
        "Resource": "arn:aws:lambda:us-east-1:923029763609:function:row-classifier",
        "Next": "RouteByClassification"
      },
      "RouteByClassification": {
        "Type": "Choice",
        "Choices": [
          {
            "Variable": "$.classification",
            "StringEquals": "invoice",
            "Next": "ProcessInvoice"
          },
          {
            "Variable": "$.classification", 
            "StringEquals": "job",
            "Next": "ProcessJob"
          }
        ],
        "Default": "ProcessGeneric"
      }
    }
  }
}

{
  "Comment": "Financial workflow with job-dependent invoice classification",
  "StartAt": "LoadGoogleSheetsData",
  "States": {
    "LoadGoogleSheetsData": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:us-east-1:923029763609:function:sheet-loader",
      "Next": "ProcessJobsTable"
    },
    "ProcessJobsTable": {
      "Type": "Map",
      "ItemsPath": "$.s3_keys.jobs_tbl.batches",
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "INLINE"
        },
        "StartAt": "ClassifyAndProcessJob",
        "States": {
          "ClassifyAndProcessJob": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:923029763609:function:process-job-row",
            "End": true
          }
        }
      },
      "ResultPath": "$.job_processing_results",
      "Next": "AggregateJobData"
    },
    "AggregateJobData": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:us-east-1:923029763609:function:aggregate-job-data",
      "InputPath": "$",
      "ResultPath": "$.aggregated_jobs",
      "Next": "ProcessInvoicesWithJobContext"
    },
    "ProcessInvoicesWithJobContext": {
      "Type": "Map",
      "ItemsPath": "$.s3_keys.inv_tbl.batches",
      "ItemProcessor": {
        "ProcessorConfig": {
          "Mode": "INLINE"
        },
        "StartAt": "ClassifyInvoiceWithJobLookup",
        "States": {
          "ClassifyInvoiceWithJobLookup": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:923029763609:function:invoice-classifier-with-jobs",
            "Next": "RouteInvoiceByClassification"
          },
          "RouteInvoiceByClassification": {
            "Type": "Choice",
            "Choices": [
              {
                "Variable": "$.invoice_classification.status",
                "StringEquals": "paid",
                "Next": "ProcessPaidInvoice"
              },
              {
                "Variable": "$.invoice_classification.status",
                "StringEquals": "pending",
                "Next": "ProcessPendingInvoice"
              },
              {
                "Variable": "$.invoice_classification.status",
                "StringEquals": "overdue",
                "Next": "ProcessOverdueInvoice"
              },
              {
                "Variable": "$.invoice_classification.job_status",
                "StringEquals": "completed",
                "Next": "ProcessCompletedJobInvoice"
              }
            ],
            "Default": "ProcessGenericInvoice"
          },
          "ProcessPaidInvoice": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:923029763609:function:process-paid-invoice",
            "End": true
          },
          "ProcessPendingInvoice": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:923029763609:function:process-pending-invoice",
            "End": true
          },
          "ProcessOverdueInvoice": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:923029763609:function:process-overdue-invoice",
            "End": true
          },
          "ProcessCompletedJobInvoice": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:923029763609:function:process-completed-job-invoice",
            "End": true
          },
          "ProcessGenericInvoice": {
            "Type": "Task",
            "Resource": "arn:aws:us-east-1:923029763609:account:function:process-generic-invoice",
            "End": true
          }
        }
      },
      "ResultPath": "$.invoice_processing_results",
      "Next": "FinalAggregateResults"
    },
    "FinalAggregateResults": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:us-east-1:923029763609:function:final-aggregate-results",
      "End": true
    }
  }
}
