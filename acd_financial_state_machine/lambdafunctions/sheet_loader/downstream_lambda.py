"""
Downstream Lambda Function for Step Functions
This function receives S3 keys from the sheet_loader Lambda and processes the DataFrames
"""
import json
import boto3
import pandas as pd
from io import StringIO
import acd_datatool as acd

def load_dataframes_from_s3(s3_keys):
    """Load DataFrames from S3 keys (passed from upstream Lambda)"""
    s3_client = boto3.client('s3')
    dataframes = {}
    
    for table_name, s3_info in s3_keys.items():
        if s3_info.get('key'):
            try:
                # Download CSV from S3
                response = s3_client.get_object(
                    Bucket=s3_info['bucket'],
                    Key=s3_info['key']
                )
                csv_content = response['Body'].read().decode('utf-8')
                
                # Convert to DataFrame
                df = pd.read_csv(StringIO(csv_content))
                dataframes[table_name] = df
                print(f"Loaded {table_name} from S3: {df.shape}")
            except Exception as e:
                print(f"Error loading {table_name} from S3: {e}")
                dataframes[table_name] = pd.DataFrame()
        else:
            dataframes[table_name] = pd.DataFrame()
    
    return dataframes

def process_data(jobs_df, inv_df):
    """
    Your custom data processing logic here
    """
    results = {}
    
    # Example processing
    if not jobs_df.empty:
        results['jobs_analysis'] = {
            'total_jobs': len(jobs_df),
            'unique_clients': jobs_df['client'].nunique() if 'client' in jobs_df.columns else 0,
            'total_value': jobs_df['amount'].sum() if 'amount' in jobs_df.columns else 0
        }
    
    if not inv_df.empty:
        results['invoice_analysis'] = {
            'total_invoices': len(inv_df),
            'total_amount': inv_df['amount'].sum() if 'amount' in inv_df.columns else 0,
            'average_amount': inv_df['amount'].mean() if 'amount' in inv_df.columns else 0
        }
    
    # Combined analysis
    if not jobs_df.empty and not inv_df.empty:
        # Example: merge data for combined analysis
        # combined = pd.merge(jobs_df, inv_df, on='job_id', how='inner')
        results['combined_analysis'] = {
            'message': 'Combined analysis would go here'
        }
    
    return results

def save_results_to_s3(results, execution_id, bucket_name):
    """Save processing results to S3"""
    s3_client = boto3.client('s3')
    
    # Save results as JSON
    results_key = f"step-functions-results/{execution_id}/analysis_results.json"
    
    s3_client.put_object(
        Bucket=bucket_name,
        Key=results_key,
        Body=json.dumps(results, default=str).encode('utf-8'),
        ContentType='application/json'
    )
    
    return {
        'bucket': bucket_name,
        'key': results_key
    }

def lambda_handler(event, context):
    """
    Downstream Lambda handler that processes data from upstream Lambda
    
    Expected event structure (from Step Functions):
    {
        "statusCode": 200,
        "s3_keys": {
            "jobs_tbl": {
                "bucket": "your-bucket",
                "key": "step-functions-data/execution-id/jobs_tbl.csv",
                "row_count": 750,
                "columns": [...]
            },
            "inv_tbl": {
                "bucket": "your-bucket", 
                "key": "step-functions-data/execution-id/inv_tbl.csv",
                "row_count": 500,
                "columns": [...]
            }
        },
        "execution_id": "abc-123-def",
        "processing_config": {
            "analysis_type": "financial_summary",
            "output_format": "json"
        }
    }
    """
    
    try:
        print(f"Processing downstream data for execution: {event.get('execution_id', 'unknown')}")
        
        # 1. Extract S3 keys from upstream Lambda output
        s3_keys = event.get('s3_keys', {})
        execution_id = event.get('execution_id', context.aws_request_id)
        
        if not s3_keys:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No S3 keys provided from upstream Lambda'})
            }
        
        # 2. Load DataFrames from S3
        dataframes = load_dataframes_from_s3(s3_keys)
        
        jobs_df = dataframes.get('jobs_tbl', pd.DataFrame())
        inv_df = dataframes.get('inv_tbl', pd.DataFrame())
        
        print(f"Loaded DataFrames - Jobs: {jobs_df.shape}, Invoices: {inv_df.shape}")
        
        # 3. Process the data using your custom logic
        results = process_data(jobs_df, inv_df)
        
        # 4. Save results to S3 (optional)
        save_results = event.get('processing_config', {}).get('save_results', True)
        results_location = None
        
        if save_results:
            bucket_name = event.get('s3_bucket', s3_keys.get('jobs_tbl', {}).get('bucket', 'default-bucket'))
            results_location = save_results_to_s3(results, execution_id, bucket_name)
            print(f"Results saved to: s3://{results_location['bucket']}/{results_location['key']}")
        
        # 5. Return processed results
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Data processing completed successfully',
                'execution_id': execution_id,
                'processed_tables': list(dataframes.keys()),
                'results': results,
                'results_location': results_location
            }, default=str)
        }
        
    except Exception as e:
        print(f"Error in downstream processing: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Failed to process downstream data'
            })
        }

# Test the downstream function locally
if __name__ == "__main__":
    # Mock event from upstream Lambda (via Step Functions)
    test_event = {
        "statusCode": 200,
        "s3_keys": {
            "jobs_tbl": {
                "bucket": "your-test-bucket",
                "key": "step-functions-data/test-execution/jobs_tbl.csv",
                "row_count": 100,
                "columns": ["job_id", "client", "amount", "date"]
            },
            "inv_tbl": {
                "bucket": "your-test-bucket",
                "key": "step-functions-data/test-execution/inv_tbl.csv", 
                "row_count": 75,
                "columns": ["invoice_id", "job_id", "amount", "date"]
            }
        },
        "execution_id": "test-execution-123",
        "processing_config": {
            "analysis_type": "financial_summary",
            "save_results": True
        }
    }
    
    class MockContext:
        aws_request_id = "test-request-123"
    
    # Test the function
    try:
        result = lambda_handler(test_event, MockContext())
        print("Downstream Lambda execution successful!")
        print(f"Status Code: {result['statusCode']}")
        print(f"Response: {result['body']}")
    except Exception as e:
        print(f"Downstream Lambda execution failed: {e}")
