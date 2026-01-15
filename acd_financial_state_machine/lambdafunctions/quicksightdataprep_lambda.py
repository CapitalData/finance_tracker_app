import json
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, List
import re

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Prepare aggregated data for QuickSight visualization
    
    This function:
    1. Reads all processed batches from S3 (saved by processing functions)
    2. Aggregates data by type (invoice, jobs, default)
    3. Creates flattened datasets optimized for QuickSight
    4. Saves to quicksight-ready/ S3 location
    """
    
    try:
        execution_id = event.get('execution_id', context.aws_request_id)
        s3_bucket = 'acd-finance-pipeline'
        
        print(f"Starting QuickSight data preparation for execution: {execution_id}")
        
        # Read and aggregate all processed data from S3
        invoice_data = read_processed_data_from_s3('invoice', execution_id, s3_bucket)
        job_data = read_processed_data_from_s3('jobs', execution_id, s3_bucket)
        default_data = read_processed_data_from_s3('default', execution_id, s3_bucket)
        
        # Create QuickSight datasets
        quicksight_datasets = create_quicksight_datasets(
            invoice_data, 
            job_data,
            default_data,
            execution_id, 
            s3_bucket
        )
        
        return {
            'statusCode': 200,
            'execution_id': execution_id,
            'quicksight_datasets': quicksight_datasets,
            'data_summary': {
                'invoice_record_count': len(invoice_data),
                'job_record_count': len(job_data),
                'default_record_count': len(default_data),
                'total_records': len(invoice_data) + len(job_data) + len(default_data)
            },
            'prepared_at': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        print(f"Error preparing QuickSight data: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'error': str(e),
            'execution_id': event.get('execution_id', 'unknown')
        }

def read_processed_data_from_s3(data_type: str, execution_id: str, s3_bucket: str) -> List[Dict]:
    """Read all processed batches for a data type from S3"""
    
    s3_client = boto3.client('s3')
    prefix = f"processed/{data_type}/{execution_id}/"
    
    all_records = []
    
    try:
        print(f"Reading {data_type} data from S3 prefix: {prefix}")
        
        # List all batch files for this execution and data type
        response = s3_client.list_objects_v2(
            Bucket=s3_bucket,
            Prefix=prefix
        )
        
        batch_files = response.get('Contents', [])
        print(f"Found {len(batch_files)} batch files for {data_type}")
        
        for obj in batch_files:
            try:
                # Load each batch file
                batch_response = s3_client.get_object(Bucket=s3_bucket, Key=obj['Key'])
                batch_data = json.loads(batch_response['Body'].read().decode('utf-8'))
                
                # Extract processed records
                records = batch_data.get('processed_records', [])
                all_records.extend(records)
                
                print(f"Loaded {len(records)} records from {obj['Key']}")
                
            except Exception as e:
                print(f"Error loading batch file {obj['Key']}: {e}")
                continue
        
        print(f"Total {data_type} records aggregated: {len(all_records)}")
        
    except Exception as e:
        print(f"Error reading {data_type} data from S3: {e}")
        # Return empty list if no data found (not an error for some data types)
        if "NoSuchKey" in str(e) or "does not exist" in str(e):
            print(f"No {data_type} data found - this may be expected")
            return []
        else:
            raise e
    
    return all_records

def create_quicksight_datasets(
    invoice_data: List, 
    job_data: List, 
    default_data: List,
    execution_id: str, 
    s3_bucket: str
) -> Dict[str, str]:
    """Create flattened datasets optimized for QuickSight with proper date formatting"""
    
    s3_client = boto3.client('s3')
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    
    datasets = {}
    
    # 1. Create flattened invoice dataset
    if invoice_data:
        flattened_invoices = []
        for record in invoice_data:
            flat_record = flatten_invoice_record(record, execution_id)
            flattened_invoices.append(flat_record)
        
        # Clean up old files and save invoice dataset
        cleanup_old_files(s3_client, s3_bucket, 'invoices')
        invoice_key = f"quicksight-ready/invoices/latest_invoices.json"
        save_dataset_to_s3(s3_client, s3_bucket, invoice_key, flattened_invoices)
        datasets['invoices'] = f"s3://{s3_bucket}/{invoice_key}"
        print(f"Created invoice dataset: {len(flattened_invoices)} records")
    
    # 2. Create flattened job dataset
    if job_data:
        flattened_jobs = []
        for record in job_data:
            flat_record = flatten_job_record(record, execution_id)
            flattened_jobs.append(flat_record)
        
        # Clean up old files and save job dataset
        cleanup_old_files(s3_client, s3_bucket, 'jobs')
        job_key = f"quicksight-ready/jobs/latest_jobs.json"
        save_dataset_to_s3(s3_client, s3_bucket, job_key, flattened_jobs)
        datasets['jobs'] = f"s3://{s3_bucket}/{job_key}"
        print(f"Created job dataset: {len(flattened_jobs)} records")
    
    # 3. Create flattened default dataset
    if default_data:
        flattened_defaults = []
        for record in default_data:
            flat_record = flatten_default_record(record, execution_id)
            flattened_defaults.append(flat_record)
        
        # Clean up old files and save default dataset
        cleanup_old_files(s3_client, s3_bucket, 'default')
        default_key = f"quicksight-ready/default/latest_default.json"
        save_dataset_to_s3(s3_client, s3_bucket, default_key, flattened_defaults)
        datasets['default'] = f"s3://{s3_bucket}/{default_key}"
        print(f"Created default dataset: {len(flattened_defaults)} records")
    
    # 4. Create summary dataset
    summary_data = create_summary_dataset(invoice_data, job_data, default_data, execution_id)
    cleanup_old_files(s3_client, s3_bucket, 'summary')
    summary_key = f"quicksight-ready/summary/latest_summary.json"
    save_dataset_to_s3(s3_client, s3_bucket, summary_key, summary_data)
    datasets['summary'] = f"s3://{s3_bucket}/{summary_key}"
    print(f"Created summary dataset: {len(summary_data)} records")
    
    return datasets

def cleanup_old_files(s3_client, bucket: str, data_type: str):
    """Remove old files before saving new ones"""
    
    prefix = f"quicksight-ready/{data_type}/"
    
    try:
        # List existing files
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        if 'Contents' in response:
            # Delete old files
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
            
            if objects_to_delete:
                s3_client.delete_objects(
                    Bucket=bucket,
                    Delete={'Objects': objects_to_delete}
                )
                print(f"Deleted {len(objects_to_delete)} old files from {prefix}")
    
    except Exception as e:
        print(f"Warning: Could not cleanup old files: {e}")

def normalize_date(date_value: Any) -> str:
    """Convert various date formats to ISO format (YYYY-MM-DD) for QuickSight"""
    
    if not date_value or date_value in ['', 'None', None]:
        return None
    
    date_str = str(date_value).strip()
    
    if not date_str or date_str.lower() in ['none', 'null', '']:
        return None
    
    try:
        # Common date patterns
        patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-MM-DD or YYYY-M-D
            r'(\d{1,2})/(\d{1,2})/(\d{4})',  # MM/DD/YYYY or M/D/YYYY
            r'(\d{1,2})-(\d{1,2})-(\d{4})',  # MM-DD-YYYY or M-D-YYYY
            r'(\d{4})/(\d{1,2})/(\d{1,2})',  # YYYY/MM/DD or YYYY/M/D
        ]
        
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, date_str)
            if match:
                if i == 0 or i == 3:  # YYYY-MM-DD or YYYY/MM/DD format
                    year, month, day = match.groups()
                else:  # MM/DD/YYYY or MM-DD-YYYY format
                    month, day, year = match.groups()
                
                # Normalize to YYYY-MM-DD
                return f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"
        
        # If no pattern matches, try parsing with datetime
        from datetime import datetime
        parsed_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
        return parsed_date.strftime('%Y-%m-%d')
        
    except Exception as e:
        print(f"Warning: Could not parse date '{date_value}': {e}")
        return None

def calculate_days_between(start_date: str, end_date: str) -> int:
    """Calculate days between two date strings"""
    try:
        start_normalized = normalize_date(start_date)
        end_normalized = normalize_date(end_date)
        
        if not start_normalized or not end_normalized:
            return None
            
        start = datetime.strptime(start_normalized, '%Y-%m-%d')
        end = datetime.strptime(end_normalized, '%Y-%m-%d')
        return (end - start).days
    except:
        return None

def flatten_invoice_record(record: Dict, execution_id: str) -> Dict:
    """Flatten invoice record for QuickSight with proper date formatting"""
    
    invoice_data = record.get('invoice_data', {})
    row_data = record.get('row_data', {})
    state_classification = record.get('state_classification', {})
    
    # Extract and normalize key fields
    amount = invoice_data.get('amount', row_data.get('amount', 0))
    try:
        amount = float(amount) if amount else 0.0
    except (ValueError, TypeError):
        amount = 0.0
    
    date_submitted = normalize_date(invoice_data.get('date_submitted', row_data.get('date_submitted', '')))
    date_paid = normalize_date(invoice_data.get('date_paid', row_data.get('date_paid', '')))
    
    inv_link = invoice_data.get('inv_link', row_data.get('inv_link', ''))
    description = invoice_data.get('description', row_data.get('description', ''))
    
    # Create detail summary for tooltips
    details_parts = []
    if amount > 0:
        details_parts.append(f"Amount: ${amount:,.2f}")
    if date_submitted:
        details_parts.append(f"Submitted: {date_submitted}")
    if date_paid:
        details_parts.append(f"Paid: {date_paid}")
    if description:
        details_parts.append(f"Description: {description[:50]}...")
    
    details_summary = " | ".join(details_parts) if details_parts else "No details available"
    
    # Calculate payment timing
    days_to_payment = calculate_days_between(date_submitted, date_paid) if date_submitted and date_paid else None
    
    record_id = f"{record.get('batch_id', 'unknown')}_{execution_id}_{hash(str(row_data))}"
    
    return {
        'execution_id': execution_id,
        'batch_id': record.get('batch_id'),
        'data_type': 'invoice',
        'classification': record.get('classification'),
        'confidence': float(record.get('confidence', 0)),
        'inv_from': state_classification.get('inv_from', ''),
        'inv_status': state_classification.get('inv_status', ''),
        'sec_classification': record.get('sec_classification', ''),
        'processed_at': record.get('processed_at', ''),
        
        # Core invoice fields with proper types
        'inv_link': str(inv_link),
        'inv_paid_link': str(invoice_data.get('inv_paid_link', row_data.get('inv_paid_link', ''))),
        'amount': amount,  # Numeric field
        'date_submitted': date_submitted,  # ISO date format
        'date_paid': date_paid,  # ISO date format
        'description': str(description),
        
        # Enhanced fields for tooltips
        'details_summary': details_summary,
        'record_id': record_id,
        'amount_formatted': f"${amount:,.2f}",
        'status_detail': f"{state_classification.get('inv_from', 'Unknown')} - {state_classification.get('inv_status', 'Unknown')}",
        'link_preview': inv_link[:50] + "..." if len(str(inv_link)) > 50 else str(inv_link),
        'has_payment': date_paid is not None,  # Boolean field
        'days_to_payment': days_to_payment,  # Numeric field for analysis
        
        # Date analysis fields
        'submitted_year': int(date_submitted[:4]) if date_submitted else None,
        'submitted_month': int(date_submitted[5:7]) if date_submitted else None,
        'paid_year': int(date_paid[:4]) if date_paid else None,
        'paid_month': int(date_paid[5:7]) if date_paid else None,
    }

def flatten_job_record(record: Dict, execution_id: str) -> Dict:
    """Flatten job record for QuickSight with proper date formatting"""
    
    job_data = record.get('job_data', {})
    row_data = record.get('row_data', {})
    state_classification = record.get('state_classification', {})
    
    # Extract and normalize key fields
    job_id = str(job_data.get('job_id', row_data.get('job_id', '')))
    client = str(job_data.get('client', row_data.get('client', '')))
    subtask = str(job_data.get('subtask', row_data.get('subtask', '')))
    
    # Normalize date fields
    completion_date = normalize_date(job_data.get('completion_date', row_data.get('completion_date', '')))
    teacher_pay_dt = normalize_date(job_data.get('teacher_pay_dt', row_data.get('teacher_pay_dt', '')))
    acd_pay_dt = normalize_date(job_data.get('ACD_pay_dt', row_data.get('ACD_pay_dt', '')))
    
    worker_inv_link = str(job_data.get('worker_inv_link', row_data.get('worker_inv_link', '')))
    
    # Create detail summary for tooltips
    details_parts = []
    if job_id:
        details_parts.append(f"Job ID: {job_id}")
    if client:
        details_parts.append(f"Client: {client}")
    if subtask:
        details_parts.append(f"Subtask: {subtask}")
    if completion_date:
        details_parts.append(f"Completed: {completion_date}")
    
    details_summary = " | ".join(details_parts) if details_parts else "No details available"
    
    # Create status summary
    inv_wk_status = state_classification.get('inv_wk', '')
    inv_co_status = state_classification.get('inv_co', '')
    job_status = state_classification.get('job_status', '')
    
    status_summary = f"Worker: {inv_wk_status}, Company: {inv_co_status}, Job: {job_status}"
    
    record_id = f"{record.get('batch_id', 'unknown')}_{execution_id}_{hash(str(row_data))}"
    
    return {
        'execution_id': execution_id,
        'batch_id': record.get('batch_id'),
        'data_type': 'jobs',
        'classification': record.get('classification'),
        'confidence': float(record.get('confidence', 0)),
        'inv_wk': inv_wk_status,
        'inv_co': inv_co_status,
        'job_status': job_status,
        'sec_classification': record.get('sec_classification', ''),
        'processed_at': record.get('processed_at', ''),
        
        # Core job fields with proper types
        'job_id': job_id,
        'client': client,
        'subtask': subtask,
        'worker_inv_link': worker_inv_link,
        'teacher_pay_dt': teacher_pay_dt,  # ISO date format
        'ACD_inv_link': str(job_data.get('ACD_inv_link', row_data.get('ACD_inv_link', ''))),
        'ACD_pay_dt': acd_pay_dt,  # ISO date format
        'completion_date': completion_date,  # ISO date format
        'status': str(job_data.get('status', row_data.get('status', ''))),
        
        # Enhanced fields for tooltips
        'details_summary': details_summary,
        'record_id': record_id,
        'status_summary': status_summary,
        'client_job': f"{client} - {job_id}" if client and job_id else (client or job_id or "Unknown"),
        'worker_link_preview': worker_inv_link[:50] + "..." if len(worker_inv_link) > 50 else worker_inv_link,
        'is_completed': completion_date is not None,  # Boolean field
        'is_billable': subtask.lower() != 'unbillable' if subtask else True,  # Boolean field
        
        # Date analysis fields
        'completion_year': int(completion_date[:4]) if completion_date else None,
        'completion_month': int(completion_date[5:7]) if completion_date else None,
        'teacher_pay_year': int(teacher_pay_dt[:4]) if teacher_pay_dt else None,
        'teacher_pay_month': int(teacher_pay_dt[5:7]) if teacher_pay_dt else None,
    }

def calculate_days_between(start_date: str, end_date: str) -> int:
    """Calculate days between two date strings"""
    try:
        start_normalized = normalize_date(start_date)
        end_normalized = normalize_date(end_date)
        
        if not start_normalized or not end_normalized:
            return None
            
        start = datetime.strptime(start_normalized, '%Y-%m-%d')
        end = datetime.strptime(end_normalized, '%Y-%m-%d')
        return (end - start).days
    except:
        return None

def flatten_default_record(record: Dict, execution_id: str) -> Dict:
    """Flatten default/unclassified record for QuickSight"""
    
    row_data = record.get('row_data', {})
    
    return {
        'execution_id': execution_id,
        'batch_id': record.get('batch_id'),
        'data_type': 'default',
        'classification': record.get('classification'),
        'confidence': record.get('confidence', 0),
        'sec_classification': record.get('sec_classification', ''),
        'processed_at': record.get('processed_at', ''),
        
        # Default fields - extract common patterns
        'field_count': len(row_data),
        'non_empty_fields': sum(1 for v in row_data.values() if v not in [None, '', 0]),
        'has_links': any('link' in str(k).lower() for k in row_data.keys()),
        'has_dates': any('date' in str(k).lower() for k in row_data.keys()),
        'sample_data': json.dumps(dict(list(row_data.items())[:3]), default=str)  # First 3 fields
    }

def create_summary_dataset(invoice_data: List, job_data: List, default_data: List, execution_id: str) -> List[Dict]:
    """Create summary metrics for executive dashboard"""
    
    summary_records = []
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Overall summary
    summary_records.append({
        'execution_id': execution_id,
        'metric_category': 'overall',
        'metric_name': 'total_records',
        'metric_value': len(invoice_data) + len(job_data) + len(default_data),
        'data_type': 'all',
        'timestamp': timestamp
    })
    
    # Invoice summaries
    if invoice_data:
        inv_by_sec_class = {}
        for record in invoice_data:
            sec_class = record.get('sec_classification', 'unknown')
            inv_by_sec_class[sec_class] = inv_by_sec_class.get(sec_class, 0) + 1
        
        for sec_class, count in inv_by_sec_class.items():
            summary_records.append({
                'execution_id': execution_id,
                'metric_category': 'invoice_sec_classification',
                'metric_name': sec_class,
                'metric_value': count,
                'data_type': 'invoice',
                'timestamp': timestamp
            })
    
    # Job summaries
    if job_data:
        job_by_sec_class = {}
        for record in job_data:
            sec_class = record.get('sec_classification', 'unknown')
            job_by_sec_class[sec_class] = job_by_sec_class.get(sec_class, 0) + 1
        
        for sec_class, count in job_by_sec_class.items():
            summary_records.append({
                'execution_id': execution_id,
                'metric_category': 'job_sec_classification',
                'metric_name': sec_class,
                'metric_value': count,
                'data_type': 'jobs',
                'timestamp': timestamp
            })
    
    return summary_records

def save_dataset_to_s3(s3_client, bucket: str, key: str, data: List[Dict]):
    """Save dataset to S3"""
    
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, default=str),
            ContentType='application/json'
        )
    except Exception as e:
        print(f"Error saving dataset to s3://{bucket}/{key}: {e}")
        raise

# For local testing
if __name__ == "__main__":
    test_event = {
        "execution_id": "test-execution-123",
        "total_batches_processed": 5
    }
    
    class MockContext:
        aws_request_id = "test-request-123"
    
    result = lambda_handler(test_event, MockContext())
    print("QuickSight Data Prep Result:")
    print(json.dumps(result, indent=2, default=str))