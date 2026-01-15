import os
import pandas as pd
import requests
#import gspread
#import smtplib
#from oauth2client.service_account import ServiceAccountCredentials
#from email.mime.text import MIMEText
#from email.mime.multipart import MIMEMultipart

#import base64
#from IPython.display import Image
#import acd_datatool as acd

#verbose = True
#pd.options.display.max_columns = None

#import json

#######################################################
def check_endpoint_status(lama_endpoint):
    """
    check the endpoint,
    example use
    check_endpoint_status("http://localhost:11434")
    """
    
    try:
        response = requests.get(lama_endpoint)
        if response.status_code == 200:
            print("LaMA API is running.")
        else:
            print(f"LaMA API returned status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to LaMA API: {e}")


def parse_pdf_with_lama(pdf_path, lama_endpoint):
    """
    Sends a PDF file to the LaMA 3.1 API for processing and retrieves structured data.
    """
    with open(pdf_path, 'rb') as pdf_file:
        response = requests.post(
            lama_endpoint,
            files={'file': pdf_file}
        )
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Text: {response.text}")
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to process {pdf_path}: {response.text}")



def test_llm(prompt="What is the capital of France?", conect_str="http://localhost:11434/api/generate"):
    # Define the Ollama API endpoint
    OLLAMA_API_URL = conect_str  # Change if hosted elsewhere

    # Define request payload
    payload = {
        "model": "llama3.2",  # Change to your preferred model (e.g., llama2, phi, etc.)
        "prompt": prompt,
        "stream": False  # Set to True if streaming responses are required
    }

    # Send the request
    response = requests.post(OLLAMA_API_URL, json=payload)

    # Check response
    if response.status_code == 200:
        data = response.json()
        print("Response:", data["response"])
    else:
        print(f"Error: {response.status_code}, {response.text}")

def extract_text_locally(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() for page in pdf.pages)
    return text
        
def parse_pdf_with_lama(pdf_path, lama_endpoint):
    """
    Sends a PDF file to the LaMA 3.1 API for processing and retrieves structured data.
    """
    with open(pdf_path, 'rb') as pdf_file:
        response = requests.post(
            lama_endpoint,
            files={'file': pdf_file}
        )
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Text: {response.text}")
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to process {pdf_path}: {response.text}")

def process_pdf_invoices(folder_path, lama_endpoint, method='llama'):
    """
    Processes all PDF invoices in a folder using the LaMA 3.1 API to extract invoice and line-item data.
    ##############################
    method='llama' # parses data with llama 3.1 endpoint
    method='report' # prints existing files 
    method='chk_report' # TODO, make checkilist and check job and invoice sheet for the item 
    """
    invoices_data = []
    jobs_data = []
    
    for file_name in os.listdir(folder_path):
        if file_name.endswith('.pdf'):  # Only process PDF files

            file_path = os.path.join(folder_path, file_name)
            print(f'processing {file_path}')
            if method=='llama':
                print(f'Using {method} method')
                try:
                    #extracted_data = parse_pdf_with_lama(file_path, lama_endpoint)
                    extracted_data = extract_text_locally(file_path)
                    # Extract invoice-level data


                    print(f'I extracted this data from the pdf {extracted_data}')
                    invoice_data = extracted_data.get('invoice', {})
                    invoices_data.append({
                        'Worker': invoice_data.get('worker', 'Unknown'),
                        'Invoice Name': file_name,
                        'Submission Date': invoice_data.get('submission_date', 'Unknown'),
                        'Invoice Total': invoice_data.get('total', 0.0),
                        'File Path': file_path
                    })

                    # Extract job-level data (line items)
                    line_items = extracted_data.get('line_items', [])
                    for item in line_items:
                        jobs_data.append({
                            'Worker': invoice_data.get('worker', 'Unknown'),
                            'Invoice Name': file_name,
                            'Line Item': item.get('description', 'Unknown'),
                            'Units Worked': item.get('units', 0),
                            'Billing Rate': item.get('rate', 0.0),
                            'Line Item Total': item.get('total', 0.0)
                        })
                except Exception as e:
                    print(f"Error processing file {file_name}: {e}")
            elif method=='report':
                print(file_name)
            elif method=='check_report':
                print(file_name)
            else:    
                print('specify a valid method')
    
    invoices_df = pd.DataFrame(invoices_data)
    jobs_df = pd.DataFrame(jobs_data)
    
    return invoices_df, jobs_df