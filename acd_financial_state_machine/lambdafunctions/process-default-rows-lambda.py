import json
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, List

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Simple default row processing - reads from S3, saves processed data to S3
    
    Input: Classification metadata from row-classifier
    Output: Minimal metadata for Step Functions (no large data)
    """
    
    try:
        batch_id = event.get('batch_id', 'unknown')
        execution_id = event.get('execution_id', 'unknown')
        s3_location = event.get('s3_location', '')
        
        # Read classified data from S3
        classified_rows = read_classified_data_from_s3(s3_location, batch_id, execution_id)
        
        # Apply secondary classification to default/unclassified rows
        processed_rows = []
        
        for row in classified_rows:
            # Process rows that are not invoice or job (default classification)
            if row.get('classification') not in ['invoice', 'job']:
                # Add secondary classification
                row['sec_classification'] = create_default_sec_classification(row)
                processed_rows.append(row)
        
        # Save processed data to S3
        s3_result = save_processed_data_to_s3(
            processed_rows, 
            batch_id, 
            execution_id, 
            'default'
        )
        
        # Return MINIMAL data for Step Functions
        return {
            'statusCode': 200,
            'batch_id': batch_id,
            'execution_id': execution_id,
            'data_type': 'default',
            'processed_count': len(processed_rows),
            's3_location': s3_result.get('s3_uri'),
            'success': s3_result.get('success', False)
        }
        
    except Exception as e:
        print(f"Error in process-default-rows: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'batch_id': event.get('batch_id', 'unknown'),
            'execution_id': event.get('execution_id', 'unknown'),
            'data_type': 'default'
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

def create_default_sec_classification(classified_row: Dict[str, Any]) -> str:
    """
    Create secondary classification for default/unclassified rows
    
    Since these rows don't fit invoice or job patterns, we classify them by:
    - Source table
    - Data completeness
    - Confidence level
    
    Format: {table_source}_{data_quality}_{confidence_level}
    
    Examples:
    - inv_tbl_complete_high
    - jobs_tbl_partial_medium
    - unknown_minimal_low
    """
    
    # Get basic classification info
    classification = classified_row.get('classification', 'default')
    confidence = classified_row.get('confidence', 0.0)
    metadata = classified_row.get('metadata', {})
    row_data = classified_row.get('row_data', {})
    
    # Determine table source
    table_source = metadata.get('table_source', 'unknown')
    if table_source == 'unknown':
        # Try to infer from row data
        if any('inv' in str(key).lower() for key in row_data.keys()):
            table_source = 'inv_tbl'
        elif any('job' in str(key).lower() for key in row_data.keys()):
            table_source = 'jobs_tbl'
    
    # Determine data quality based on non-empty fields
    non_empty_fields = sum(1 for value in row_data.values() if value not in [None, '', 0])
    total_fields = len(row_data)
    
    if total_fields == 0:
        data_quality = 'empty'
    elif non_empty_fields / total_fields >= 0.7:
        data_quality = 'complete'
    elif non_empty_fields / total_fields >= 0.4:
        data_quality = 'partial'
    else:
        data_quality = 'minimal'
    
    # Determine confidence level
    if confidence >= 0.8:
        confidence_level = 'high'
    elif confidence >= 0.5:
        confidence_level = 'medium'
    else:
        confidence_level = 'low'
    
    # Create secondary classification
    return f"{table_source}_{data_quality}_{confidence_level}"

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
        "batch_id": "mixed_batch_0",
        "execution_id": "test-123",
        "classification": "default",
        "classified_count": 10,
        "s3_location": "s3://acd-finance-pipeline/classified/test-123/mixed_batch_0_20250821_143000.json",
        "success": True
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))