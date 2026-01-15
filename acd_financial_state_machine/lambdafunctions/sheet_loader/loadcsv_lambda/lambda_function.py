"""google sheet loader – loads data from google sheet to a data frame

Environment variables expected:
  GOOGLE_CREDS_SECRET – Secrets Manager ARN with { ...}
  
The secret may also include the host/port; adjust as needed.
"""
import os
import json
import boto3
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from io import StringIO

# Import your custom package
import acd_datatool as acd

# Global credentials dict for fallback (move to environment/secrets in production)
# creds_dict = {
#     "type": "service_account",
#     "private_key_id": "<your key id here>",
#     "private_key": "-----BEGIN PRIVATE KEY-----\n<your key here>\n-----END PRIVATE KEY-----\n",
#     "client_email": "financial-tracking-feb24@financetrack-acd.iam.gserviceaccount.com",
#     "client_id": "115822200334952612535"
# }

def save_dataframes_to_s3(dataframes, bucket_name, execution_id):
    """Save DataFrames to S3 and return their keys for Step Function passing"""
    s3_client = boto3.client('s3')
    s3_keys = {}
    
    for table_name, df in dataframes.items():
        if not df.empty:
            # Convert DataFrame to CSV string
            csv_buffer = StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_content = csv_buffer.getvalue()
            
            # Create S3 key with execution ID for uniqueness
            s3_key = f"raw/step-functions-data/{execution_id}/{table_name}.csv"
            
            # Upload to S3
            s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=csv_content.encode('utf-8'),
                ContentType='text/csv'
            )
            
            s3_keys[table_name] = {
                'bucket': bucket_name,
                'key': s3_key,
                'row_count': len(df),
                'columns': df.columns.tolist()
            }
            print(f"Saved {table_name} to s3://{bucket_name}/{s3_key}")
        else:
            s3_keys[table_name] = {
                'bucket': bucket_name,
                'key': None,
                'row_count': 0,
                'columns': [],
                'error': 'Empty DataFrame'
            }
    
    return s3_keys

def load_dataframes_from_s3(s3_keys):
    """Load DataFrames from S3 keys (for use in downstream Lambda)"""
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

def get_google_credentials():
    """Get Google credentials from either Secrets Manager or hardcoded dict"""
    try:
        # Try to get from Secrets Manager first
        secret_name = os.environ.get('GOOGLE_CREDS_SECRET')
        if secret_name:
            client_secrets = boto3.client('secretsmanager')
            response = client_secrets.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Could not get credentials from Secrets Manager: {e}")
    
    # Fallback to hardcoded credentials
    return creds_dict

def load_table_from_sheet(client, sheet_url, worksheet_name, cell_range=None):
    """Load a specific table from a Google Sheet worksheet"""
    try:
        sheet = client.open_by_url(sheet_url)
        worksheet = sheet.worksheet(worksheet_name)
        
        if cell_range:
            # Get data from specific range (e.g., "A1:AG1000")
            data = worksheet.get(cell_range)
            if data:
                # Convert to list of dicts using first row as headers
                headers = data[0]
                rows = data[1:]
                records = []
                for row in rows:
                    # Pad row with empty strings if shorter than headers
                    padded_row = row + [''] * (len(headers) - len(row))
                    record = dict(zip(headers, padded_row))
                    records.append(record)
                return pd.DataFrame(records)
        else:
            # Get all records if no range specified
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
    except Exception as e:
        print(f"Error loading table from {worksheet_name}: {e}")
        return pd.DataFrame()

def lambda_handler(event, context):
    """
    Lambda handler to load data from Google Sheets tables
    
    Expected event structure:
    {
        "sheet_url": "https://docs.google.com/spreadsheets/d/...",
        "tables": [
            {
                "name": "jobs_tbl",
                "worksheet": "jobs_tbl", 
                "range": "A1:AG1000"
            },
            {
                "name": "inv_tbl",
                "worksheet": "inv_tbl",
                "range": "A1:AD1000"
            }
        ],
        "processing_options": {
            "combine_tables": false,
            "return_data": true
        }
    }

    ## expected secret structure in Secrets Manager:

    creds_dict ={
          "type": "service_account",
          "private_key_id": "<yourkeyid>",
          "private_key": "-----BEGIN PRIVATE KEY-----\n<yourkey>\n-----END PRIVATE KEY-----\n",
          "client_email": "financial-tracking-feb24@financetrack-acd.iam.gserviceaccount.com",
          "client_id": "<client id>"}
    """
    
    try:
        # 1. Get credentials and set up Google Sheets connection
        creds_dict = get_google_credentials()  # Use the function instead of hardcoded creds

        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        # 2. Get configuration from event
        sheet_url = event.get('sheet_url', 'https://docs.google.com/spreadsheets/d/1QEgmIzrVF7pJzzpYyacGHpW5VF0T7dTSu5te3rq2UlI/edit')
        
        # Step Function configuration
        s3_bucket = event.get('s3_bucket', os.environ.get('DATA_BUCKET', 'your-step-functions-bucket'))
        execution_id = event.get('execution_id', context.aws_request_id if context else 'local-test')
        save_to_s3 = event.get('save_to_s3', True)  # Enable S3 saving for Step Functions
        
        # 3. Load tables based on event configuration
        tables = event.get('tables', [])
        if not tables:
            # Default configuration for your specific use case
            tables = [
                {
                    "name": "jobs_tbl",
                    "worksheet": "jobs_tbl", 
                    "range": "A1:AG1000"
                },
                {
                    "name": "inv_tbl",
                    "worksheet": "inv_tbl",
                    "range": "A1:AD1000"
                }
            ]
        
        results = {}
        dataframes = {}  # Store actual DataFrames separately
        total_rows = 0
        
        # 4. Load each table
        for table_config in tables:
            table_name = table_config.get('name')
            worksheet_name = table_config.get('worksheet')
            cell_range = table_config.get('range')
            
            print(f"Loading table: {table_name} from worksheet: {worksheet_name}")
            
            df = load_table_from_sheet(client, sheet_url, worksheet_name, cell_range)
            
            if not df.empty:
                # 5. Process the data using acd_datatool functions if available
                try:
                    # Example processing - customize as needed
                    # df = acd.some_processing_function(df)
                    pass
                except Exception as e:
                    print(f"Processing error for {table_name}: {e}")
                
                # Store the actual DataFrame
                dataframes[table_name] = df
                
                results[table_name] = {
                    'row_count': len(df),
                    'columns': df.columns.tolist(),
                    'sample_data': df.head(3).to_dict(orient='records') if len(df) > 0 else []
                }
                
                # Optionally include full data
                processing_options = event.get('processing_options', {})
                if processing_options.get('return_data', False):
                    results[table_name]['data'] = df.to_dict(orient='records')
                
                total_rows += len(df)
                print(f"Successfully loaded {table_name}: {len(df)} rows")
            else:
                results[table_name] = {
                    'error': f'No data found in {worksheet_name}',
                    'row_count': 0,
                    'columns': []
                }
                dataframes[table_name] = pd.DataFrame()  # Empty DataFrame for failed loads
        
        # 6. Save DataFrames to S3 for Step Functions (if enabled)
        s3_keys = {}
        if save_to_s3 and dataframes:
            try:
                s3_keys = save_dataframes_to_s3(dataframes, s3_bucket, execution_id)
                print(f"Saved {len(s3_keys)} tables to S3 bucket: {s3_bucket}")
            except Exception as e:
                print(f"Error saving to S3: {e}")
        
        # 7. Return results with S3 keys for Step Functions
        response_body = {
            'message': 'Successfully processed tables',
            'total_tables': len(tables),
            'total_rows': total_rows,
            'tables': results,
            's3_data': s3_keys,  # S3 keys for Step Functions
            'execution_id': execution_id
        }
        
        return {
            'statusCode': 200,
            'dataframes': dataframes,  # For local testing
            's3_keys': s3_keys,       # For Step Functions
            'body': json.dumps(response_body, default=str)
        }
        
    except Exception as e:
        print(f"Lambda execution error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Failed to process Google Sheets data'
            })
        }

# to Test the function locally
if __name__ == "__main__":

  # Mock context object for local testing
  class MockContext:
      def __init__(self):
          self.aws_request_id = "test-request-id-12345"
          self.log_group_name = "/aws/lambda/sheet-loader"
          self.log_stream_name = "2025/08/06/[$LATEST]abcdef123456"
          self.function_name = "sheet-loader"
          self.function_version = "$LATEST"
          self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:sheet-loader"
          self.memory_limit_in_mb = 512
          
      def get_remaining_time_in_millis(self):
          return 30000  # 30 seconds remaining
  
# Test event with your actual Google Sheet ID
  event = {
      "sheet_url": "https://docs.google.com/spreadsheets/d/1QEgmIzrVF7pJzzpYyacGHpW5VF0T7dTSu5te3rq2UlI/edit",
      "tables": [
          {
              "name": "jobs_tbl",
              "worksheet": "jobs_tbl", 
              "range": "A1:AG1000"
          },
          {
              "name": "inv_tbl",
              "worksheet": "inv_tbl",
              "range": "A1:AD1000"
          }
      ],
      "processing_options": {
          "combine_tables": False,
          "return_data": True
      }
  }

  # Create mock context
  context = MockContext()
  
  # set required environment variables for local testing
  os.environ['GOOGLE_CREDS_SECRET'] = 'arn:aws:secretsmanager:us-east-1:923029763609:secret:acd_google_sheets-DW4V6T'
  os.environ['DATA_BUCKET'] = 'acd-finance-pipeline'

  # Test the function
  try:
      result = lambda_handler(event, context)
      print("Lambda execution successful!")
      print(f"Status Code: {result['statusCode']}")
      #print(f"Response: {result['body']}")
      
      # Access the DataFrames
      if 'dataframes' in result:
          dataframes = result['dataframes']
          
          # Get individual DataFrames
          jobs_df = dataframes.get('jobs_tbl', pd.DataFrame())
          inv_df = dataframes.get('inv_tbl', pd.DataFrame())
          
          print(f"\n--- JOBS TABLE DATAFRAME ---")
          print(f"Shape: {jobs_df.shape}")
          
          print(f"\n--- INVOICES TABLE DATAFRAME ---")
          print(f"Shape: {inv_df.shape}")
              
          # Example: You can now work with the DataFrames
          # jobs_df.to_csv('jobs_data.csv', index=False)
          # inv_df.to_csv('invoices_data.csv', index=False)
          
  except Exception as e:
      print(f"Lambda execution failed: {e}")