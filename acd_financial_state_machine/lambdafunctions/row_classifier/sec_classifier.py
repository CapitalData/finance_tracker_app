import json
import boto3
import pandas as pd
from datetime import datetime
import re
from typing import Dict, Any, Optional

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Classify individual rows from batch data and route to appropriate downstream processing
    
    Expected input from Step Functions Map state:
    {
        "bucket": "acd-finance-pipeline",
        "key": "raw/step-functions-batches/{execution_id}/{table_name}/{batch_id}.json",
        "batch_id": "jobs_tbl_batch_0",
        "row_count": 100
    }
    
    Output for routing:
    {
        "classification": "invoice" | "job" | "default",
        "row_data": {...},
        "metadata": {...}
    }
    """
    
    try:
        # 1. Load batch data from S3
        s3_client = boto3.client('s3')
        
        bucket = event.get('bucket')
        key = event.get('key')
        batch_id = event.get('batch_id', 'unknown')
        
        if not bucket or not key:
            raise ValueError("Missing required S3 bucket or key in event")
        
        print(f"Loading batch from s3://{bucket}/{key}")
        
        # Get batch data from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        batch_data = json.loads(response['Body'].read().decode('utf-8'))
        
        # 2. Process each row in the batch
        classified_rows = []
        #counter=5

        #if counter > 0:
        for row in batch_data.get('rows', []):  
            classified_row = classify_single_row(row, batch_data.get('table_name', 'unknown'))
            classified_rows.append(classified_row)
            #counter -= 1
            
        # 3. Aggregate results for the batch
        classification_summary = aggregate_classifications(classified_rows)
        
        # 4. Return results for Step Functions routing
        return {
            'statusCode': 200,
            'batch_id': batch_id,
            'table_name': batch_data.get('table_name'),
            'execution_id': batch_data.get('execution_id'),
            'classification': classification_summary.get('dominant_classification', 'default'),
            'classified_rows': classified_rows,
            'classification_summary': classification_summary,
            'total_rows_processed': len(classified_rows)
        }
        
    except Exception as e:
        print(f"Error in row classifier: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'error': str(e),
            'batch_id': event.get('batch_id', 'unknown'),
            'classification': 'default'  # Route to default handler on error
        }

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
        'metadata': {
            'table_source': table_name,
            'classification_rules_applied': [],
            'processed_at': datetime.utcnow().isoformat()
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
    row_lower = {k.lower(): v for k, v in row_data.items() if v is not None}
    
    classification_result = {
        'classification': 'default',
        'state_classification': {},
        'confidence': 0.0,
        'metadata': {'classification_rules_applied': []}
    }

    # Rule 1: Table-based classification
    if table_name.lower() == 'inv_tbl':
        classification_result['state_classification'] = classify_invoice(row_lower)
        
        classification_result.update({
            'classification': 'invoice',
            'confidence': 1,
        })
        
        classification_result['metadata']['classification_rules_applied'].append('table_based_invoice')
    
    elif table_name.lower() == 'jobs_tbl':
        if classify_job(row_lower):
            classification_result.update({
                'classification': 'job',
                'confidence': 1,
            })

            classification_result['state_classification'] = classify_job(row_lower)

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

    if len(row_data["inv_paid_link"]) > 5:
        status['inv_status'] = 'paid'

    return status #field_matches or (has_amount and has_date)

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

    # determine worker invoice status
    if row_data["worker_inv_link"] or row_data["Worker_invoice"]:
        job_status['inv_wk'] = 'submitted'

    if row_data["teacher_pay_dt"]:
        job_status['inv_wk'] = 'paid'
    
    # determine ACD invoice status
    if row_data["subtask"]=='unbillable':
        job_status['inv_co'] = row_data["subtask"]

    if row_data["ACD_inv_link"] or row_data["ACD_inv_link"]:
        job_status['inv_co'] = 'submitted'

    if row_data["ACD_pay_dt"]:
        job_status['inv_co'] = 'paid'


    # check and update job status
    if row_data["subtask"]=='unbillable':
        job_status['inv_co'] = row_data["subtask"]

    if row_data["ACD_inv_link"] or row_data["ACD_inv_link"]:
        job_status['inv_co'] = 'submitted'

    if row_data["ACD_pay_dt"]:
        job_status['inv_co'] = 'paid'


    return job_status  #field_matches or (has_amount and has_date)

def aggregate_classifications(classified_rows: list) -> Dict[str, Any]:
    """Aggregate classification results for the batch with unique field combinations"""
    
    if not classified_rows:
        return {
            'total_rows': 0, 
            'classification_distribution': {}, 
            'dominant_classification': 'default',
            'unique_field_combinations': {},
            'field_value_counts': {}
        }
    
    # Count classifications
    classification_counts = {}
    total_confidence = 0
    
    # Track unique combinations of all fields
    unique_combinations = {}
    
    # Track individual field value counts
    field_counts = {
        'classification': {},
        'inv_status': {},
        'inv_from': {},
        'inv_wk': {},
        'inv_co': {},
        'job_status': {}
    }
    
    for row in classified_rows:
        classification = row.get('classification', 'default')
        confidence = row.get('confidence', 0.0)
        state_classification = row.get('state_classification', {})
        
        # Count basic classifications
        if classification not in classification_counts:
            classification_counts[classification] = {'count': 0, 'total_confidence': 0}
        
        classification_counts[classification]['count'] += 1
        classification_counts[classification]['total_confidence'] += confidence
        total_confidence += confidence
        
        # Extract all field values (flattening nested dictionaries)
        field_values = {
            'classification': classification,
            'inv_status': state_classification.get('inv_status'),
            'inv_from': state_classification.get('inv_from'),
            'inv_wk': state_classification.get('inv_wk'),
            'inv_co': state_classification.get('inv_co'),
            'job_status': state_classification.get('job_status')
        }
        
        # Create a combination key (only include non-None values)
        combo_parts = []
        for field, value in field_values.items():
            if value is not None:
                combo_parts.append(f"{field}:{value}")
                
                # Count individual field values
                if value not in field_counts[field]:
                    field_counts[field][value] = 0
                field_counts[field][value] += 1
        
        # Create unique combination signature
        combination_key = "|".join(sorted(combo_parts))
        
        # Count unique combinations
        if combination_key not in unique_combinations:
            unique_combinations[combination_key] = {
                'count': 0,
                'field_values': field_values,
                'sample_row_data': row.get('row_data', {})
            }
        unique_combinations[combination_key]['count'] += 1
    
    # Calculate percentages for basic classifications
    for classification, data in classification_counts.items():
        data['percentage'] = (data['count'] / len(classified_rows)) * 100
        data['avg_confidence'] = data['total_confidence'] / data['count'] if data['count'] > 0 else 0
    
    # Calculate percentages for unique combinations
    for combo_key, combo_data in unique_combinations.items():
        combo_data['percentage'] = (combo_data['count'] / len(classified_rows)) * 100
    
    # Sort combinations by count (most frequent first)
    sorted_combinations = dict(sorted(
        unique_combinations.items(), 
        key=lambda x: x[1]['count'], 
        reverse=True
    ))
    
    return {
        'total_rows': len(classified_rows),
        'classification_distribution': classification_counts,
        'batch_avg_confidence': total_confidence / len(classified_rows) if classified_rows else 0,
        'dominant_classification': max(classification_counts.keys(), key=lambda k: classification_counts[k]['count']) if classification_counts else 'default',
        'unique_field_combinations': sorted_combinations,
        'field_value_counts': field_counts,
        'total_unique_combinations': len(unique_combinations)
    }

# For local testing
if __name__ == "__main__":
    # Test event mimicking Step Functions Map input
    # test_event_job = {
    #     "bucket": "acd-finance-pipeline",
    #     "key": "raw/step-functions-batches/f0560621-0bec-419f-8cff-710e6de6c86e/jobs_tbl/jobs_tbl_batch_0.json",
    #     "batch_id": "jobs_tbl_batch_0",
    #     "row_count": 5        
    # }

    test_type ='jobs'#,'inv'

    test_event = {
        "bucket": "acd-finance-pipeline",
        "key": f"raw/step-functions-batches/f0560621-0bec-419f-8cff-710e6de6c86e/{test_type}_tbl/{test_type}_tbl_batch_0.json",
        "batch_id": f"{test_type}_tbl_batch_0",
        "row_count": 5        
    }
    
    # Mock context
    class MockContext:
        #aws_request_id = "test-request-123"
        aws_request_id = "f0560621-0bec-419f-8cff-710e6de6c86e"
    result = lambda_handler(test_event, MockContext())
    print("Test result:")
    print(json.dumps(result, indent=2, default=str))