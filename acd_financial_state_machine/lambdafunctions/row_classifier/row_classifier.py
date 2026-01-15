import json
import boto3
import pandas as pd
from datetime import datetime, timezone
import re
from typing import Dict, Any, Optional, List

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Classify rows and save results to S3
    
    Input: Batch metadata from Step Functions
    Output: Minimal classification metadata (no large data)
    """
    
    try:
        print(f"Processing event: {json.dumps(event, default=str)}")
        
        # Load data from S3 based on batch metadata
        batch_data = load_batch_from_s3(event)
        print(f"Loaded {len(batch_data)} rows from S3")
        
        # Get table name from batch_id or source_table
        table_name = event.get('source_table', event.get('table_name', ''))
        if not table_name and 'batch_id' in event:
            # Extract table name from batch_id (e.g., "jobs_tbl_batch_0" -> "jobs_tbl")
            table_name = event['batch_id'].split('_batch_')[0]
        
        print(f"Using table_name: {table_name}")
        
        # Classify the rows
        classified_rows = []
        for i, row in enumerate(batch_data):
            try:
                classified_row = classify_single_row(row, table_name)
                classified_rows.append(classified_row)
                print(f"Classified row {i+1}: {classified_row.get('classification', 'unknown')}")
            except Exception as row_error:
                print(f"Error classifying row {i+1}: {row_error}")
                # Add failed classification
                classified_rows.append({
                    'row_data': row,
                    'classification': 'default',
                    'confidence': 0.0,
                    'metadata': {
                        'table_source': table_name,
                        'classification_error': str(row_error),
                        'processed_at': datetime.now(timezone.utc).isoformat()
                    }
                })
        
        print(f"Successfully classified {len(classified_rows)} rows")
        
        # Save classified results to S3
        s3_result = save_classified_data_to_s3(
            classified_rows,
            event.get('batch_id'),
            event.get('execution_id')
        )
        
        if not s3_result.get('success', False):
            raise Exception(f"Failed to save to S3: {s3_result.get('error', 'Unknown error')}")
        
        # Determine primary classification for routing
        primary_classification = determine_primary_classification(classified_rows)
        print(f"Primary classification determined: {primary_classification}")
        
        # Return MINIMAL data for Step Functions
        result = {
            'statusCode': 200,
            'batch_id': event.get('batch_id'),
            'execution_id': event.get('execution_id'),
            'classification': primary_classification,
            'classified_count': len(classified_rows),
            's3_location': s3_result.get('s3_uri'),
            'success': s3_result.get('success', False)
        }
        
        print(f"Returning successful result: {json.dumps(result, default=str)}")
        return result
        
    except Exception as e:
        print(f"Error in row-classifier: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'error': str(e),
            'batch_id': event.get('batch_id', 'unknown'),
            'execution_id': event.get('execution_id', 'unknown'),
            'classification': 'default'  # Add default classification for routing
        }

def load_batch_from_s3(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load batch data from S3"""
    
    s3_client = boto3.client('s3')
    
    bucket = event.get('bucket')
    key = event.get('key')
    
    if not bucket or not key:
        raise ValueError("Missing required S3 bucket or key in event")
    
    print(f"Loading batch from s3://{bucket}/{key}")
    
    try:
        # Get batch data from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        batch_data = json.loads(response['Body'].read().decode('utf-8'))
        
        rows = batch_data.get('rows', [])
        if not rows:
            print("Warning: No rows found in batch data")
        
        return rows
    except Exception as e:
        print(f"Error loading batch from S3: {e}")
        raise

def classify_single_row(row_data: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    """
    Classify a single row based on its content and table source
    
    Returns:
    {
        "classification": "invoice" | "job" | "default",
        "row_data": {...},
        "metadata": {...}
    }
    """
    
    # Initialize classification result
    result = {
        'row_data': row_data,
        'classification': 'default',
        'confidence': 0.0,
        'state_classification': {},
        'metadata': {
            'table_source': table_name,
            'classification_rules_applied': [],
            'processed_at': datetime.now(timezone.utc).isoformat()
        }
    }
    
    try:
        # Rule-based classification logic
        classification = determine_row_classification(row_data, table_name) 
        result.update(classification)
        
    except Exception as e:
        print(f"Error classifying row: {e}")
        result['metadata']['error'] = str(e)
        result['classification'] = 'default'
    
    return result

def determine_row_classification(row_data: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    """
    Apply business rules to determine row classification
    """
    
    # Convert all keys to lowercase for consistent matching
    row_lower = {k.lower(): v for k, v in row_data.items() if v is not None and v != ''}
    
    classification_result = {
        'classification': 'default',
        'state_classification': {},
        'confidence': 0.0,
        'metadata': {'classification_rules_applied': []}
    }

    # Rule 1: Table-based classification
    if table_name.lower() in ['inv_tbl', 'inv']:
        state_classification = classify_invoice(row_lower)
        
        classification_result.update({
            'classification': 'invoice',
            'confidence': 0.9,
            'state_classification': state_classification
        })
        
        classification_result['metadata']['classification_rules_applied'].append('table_based_invoice')
    
    elif table_name.lower() in ['jobs_tbl', 'jobs']:
        state_classification = classify_job(row_lower)
        
        classification_result.update({
            'classification': 'job',
            'confidence': 0.9,
            'state_classification': state_classification
        })

        classification_result['metadata']['classification_rules_applied'].append('table_based_job')
    
    return classification_result

def classify_invoice(row_data: Dict[str, Any]) -> Dict[str, Any]:
    """Classify invoice direction and payment status
    invoices are of three types
    from    |worker     |comp_(ACD) | 
    --------|-----------|-----------|
    status  |unsubmitted|unsubmitted|
            |submitted  |submitted  |
            |paid       |paid       |
    """

    status={'inv_status':'unsubmitted', 'inv_from':row_data["inv_from"]}

    if len(row_data["inv_link"]) > 5:
        status['inv_status'] = 'submitted'

    # Check if invoice is paid (has paid link)
    inv_paid_link = row_data.get("inv_paid_link", "")
    if inv_paid_link and len(str(inv_paid_link).strip()) > 5:
        status['inv_status'] = 'paid'

    return status

def classify_job(row_data: Dict[str, Any]) -> Dict[str, Any]:
    
    """Classify job in terms of its completion status and its invoice status
    invoices are of three types
    entity  |inv_wk     |inv_co     |Job Status | 
    --------|-----------|-----------|-----------|
    status  |           |           |requested  |
            |           |unbillable |staffed    |
            |unsubmitted|unsubmitted|completed  |
            |submitted  |submitted  |           |
            |paid       |paid       |           |
    """
    # set the three stateful entities
    job_status={'inv_wk':'unsubmitted', 'inv_co':'unsubmitted', 'job_status':'requested'}

    # Determine worker invoice status
    worker_inv_link = row_data.get("worker_inv_link", "") or row_data.get("worker_invoice", "")
    if worker_inv_link and len(str(worker_inv_link).strip()) > 5:
        job_status['inv_wk'] = 'submitted'

    teacher_pay_dt = row_data.get("teacher_pay_dt", "")
    if teacher_pay_dt and str(teacher_pay_dt).strip():
        job_status['inv_wk'] = 'paid'
    
    # Determine ACD invoice status
    subtask = row_data.get("subtask", "")
    if subtask and str(subtask).lower() == 'unbillable':
        job_status['inv_co'] = 'unbillable'
    else:
        acd_inv_link = row_data.get("acd_inv_link", "")
        if acd_inv_link and len(str(acd_inv_link).strip()) > 5:
            job_status['inv_co'] = 'submitted'

        acd_pay_dt = row_data.get("acd_pay_dt", "")
        if acd_pay_dt and str(acd_pay_dt).strip():
            job_status['inv_co'] = 'paid'

    # Determine job completion status
    # Check if job is staffed or completed
    if any(field in row_data for field in ["worker_inv_link", "worker_invoice", "teacher_pay_dt"]):
        job_status['job_status'] = 'staffed'
    
    # If there's completion data, mark as completed
    completion_date = row_data.get("completion_date", "")
    if completion_date and str(completion_date).strip():
        job_status['job_status'] = 'completed'

    return job_status

def save_classified_data_to_s3(classified_rows: List[Dict], batch_id: str, execution_id: str) -> Dict[str, Any]:
    """Save classified data to S3"""
    
    if not classified_rows:
        return {'success': True, 'message': 'No data to save', 'record_count': 0}
    
    s3_client = boto3.client('s3')
    bucket = 'acd-finance-pipeline'
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    
    s3_key = f"classified/{execution_id}/{batch_id}_{timestamp}.json"
    
    storage_data = {
        'execution_id': execution_id,
        'batch_id': batch_id,
        'classified_at': datetime.now(timezone.utc).isoformat(),
        'record_count': len(classified_rows),
        'classified_rows': classified_rows
    }
    
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=json.dumps(storage_data, default=str),
            ContentType='application/json'
        )
        
        print(f"Successfully saved {len(classified_rows)} classified rows to s3://{bucket}/{s3_key}")
        
        return {
            'success': True,
            'bucket': bucket,
            'key': s3_key,
            's3_uri': f"s3://{bucket}/{s3_key}"
        }
        
    except Exception as e:
        print(f"Error saving classified data: {e}")
        return {'success': False, 'error': str(e)}

def determine_primary_classification(classified_rows: List[Dict[str, Any]]) -> str:
    """Determine the primary classification for routing"""
    
    if not classified_rows:
        return 'default'
    
    # Count classifications
    classification_counts = {}
    
    for row in classified_rows:
        classification = row.get('classification', 'default')
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
    
    # Find the classification with the highest count
    if classification_counts:
        primary_classification = max(classification_counts.keys(), key=lambda k: classification_counts[k])
        print(f"Classification counts: {classification_counts}, Primary: {primary_classification}")
        return primary_classification
    
    return 'default'

# For local testing
if __name__ == "__main__":
    test_type = 'jobs'  # 'jobs' or 'inv'

    test_event = {
        "bucket": "acd-finance-pipeline",
        "key": f"raw/step-functions-batches/f0560621-0bec-419f-8cff-710e6de6c86e/{test_type}_tbl/{test_type}_tbl_batch_0.json",
        "batch_id": f"{test_type}_tbl_batch_0",
        "row_count": 5,
        "execution_id": "f0560621-0bec-419f-8cff-710e6de6c86e"
    }
    
    # Mock context
    class MockContext:
        aws_request_id = "f0560621-0bec-419f-8cff-710e6de6c86e"
    
    result = lambda_handler(test_event, MockContext())
    print("Test result:")
    print(json.dumps(result, indent=2, default=str))