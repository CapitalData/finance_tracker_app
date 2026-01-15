import json
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, List

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Simple invoice secondary classification - reads from S3, saves processed data to S3
    
    Input: Classification metadata from row-classifier
    Output: Minimal metadata for Step Functions (no large data)
    """
    
    try:
        batch_id = event.get('batch_id', 'unknown')
        execution_id = event.get('execution_id', 'unknown')
        s3_location = event.get('s3_location', '')
        
        # Read classified data from S3
        classified_rows = read_classified_data_from_s3(s3_location, batch_id, execution_id)
        
        # Apply secondary classification to invoice rows only
        processed_rows = []
        
        for row in classified_rows:
            if row.get('classification') == 'invoice':
                # Add secondary classification
                row['sec_classification'] = create_invoice_sec_classification(row)
                processed_rows.append(row)
        
        # Save processed data to S3
        s3_result = save_processed_data_to_s3(
            processed_rows, 
            batch_id, 
            execution_id, 
            'invoice'
        )
        
        # Return MINIMAL data for Step Functions
        return {
            'statusCode': 200,
            'batch_id': batch_id,
            'execution_id': execution_id,
            'data_type': 'invoice',
            'processed_count': len(processed_rows),
            's3_location': s3_result.get('s3_uri'),
            'success': s3_result.get('success', False)
        }
        
    except Exception as e:
        print(f"Error in process-invoice-rows: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'batch_id': event.get('batch_id', 'unknown'),
            'execution_id': event.get('execution_id', 'unknown'),
            'data_type': 'invoice'
        }

def read_classified_data_from_s3(s3_location: str, batch_id: str, execution_id: str) -> List[Dict]:
    """Read classified data from S3"""
    
    if s3_location and s3_location.startswith('s3://'):
        # Parse S3 URI
        parts = s3_location.replace('s3://', '').split('/', 1)
        bucket = parts[0]
        key = parts[1]
    else:
        # Fallback: construct path from batch info
        bucket = 'acd-finance-pipeline'
        # Look for most recent classified file for this batch
        s3_client = boto3.client('s3')
        prefix = f"classified/{execution_id}/{batch_id}"
        
        try:
            response = s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix
            )
            
            if not response.get('Contents'):
                print(f"No classified data found for batch {batch_id}")
                return []
            
            # Get the most recent file
            latest_file = max(response['Contents'], key=lambda x: x['LastModified'])
            key = latest_file['Key']
            
        except Exception as e:
            print(f"Error finding classified data: {e}")
            return []
    
    try:
        s3_client = boto3.client('s3')
        response = s3_client.get_object(Bucket=bucket, Key=key)
        data = json.loads(response['Body'].read().decode('utf-8'))
        
        return data.get('classified_rows', [])
        
    except Exception as e:
        print(f"Error reading classified data from S3: {e}")
        return []

def create_invoice_sec_classification(classified_row: Dict[str, Any]) -> str:
    """
    Create secondary classification for invoices
    
    Format: {from}_{status}
    - from: worker | company | comp_(ACD)  
    - status: unsubmitted | submitted | paid
    
    Examples: worker_submitted, company_paid, comp_(ACD)_unsubmitted
    """
    
    state_classification = classified_row.get('state_classification', {})
    
    # Get from and status from existing classification
    inv_from = state_classification.get('inv_from', 'unknown')
    inv_status = state_classification.get('inv_status', 'unsubmitted')
    
    # Create secondary classification
    return f"{inv_from}_{inv_status}"

def save_processed_data_to_s3(processed_rows: List[Dict], batch_id: str, execution_id: str, data_type: str) -> Dict[str, Any]:
    """Save processed data to S3 for later aggregation"""
    
    if not processed_rows:
        return {'success': True, 'message': 'No data to save', 'record_count': 0}
    
    s3_client = boto3.client('s3')
    bucket = 'acd-finance-pipeline'
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    
    # Create S3 key for this batch
    s3_key = f"processed/{data_type}/{execution_id}/{batch_id}_{timestamp}.json"
    
    # Prepare data for storage
    storage_data = {
        'execution_id': execution_id,
        'batch_id': batch_id,
        'data_type': data_type,
        'processed_at': datetime.now(timezone.utc).isoformat(),
        'record_count': len(processed_rows),
        'processed_records': processed_rows
    }
    
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=json.dumps(storage_data, default=str),
            ContentType='application/json'
        )
        
        print(f"Saved {len(processed_rows)} processed {data_type} records to s3://{bucket}/{s3_key}")
        
        return {
            'success': True,
            'bucket': bucket,
            'key': s3_key,
            'record_count': len(processed_rows),
            's3_uri': f"s3://{bucket}/{s3_key}"
        }
        
    except Exception as e:
        print(f"Error saving processed {data_type} data to S3: {e}")
        return {
            'success': False,
            'error': str(e),
            'record_count': len(processed_rows)
        }

# For local testing
if __name__ == "__main__":
    test_event = {
        "statusCode": 200,
        "batch_id": "inv_tbl_batch_0",
        "execution_id": "test-123",
        "classification": "invoice",
        "classified_count": 25,
        "s3_location": "s3://acd-finance-pipeline/classified/test-123/inv_tbl_batch_0_20250821_143000.json",
        "success": True
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))