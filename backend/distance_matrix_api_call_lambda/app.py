import boto3
import json 
import os
from io import BytesIO, StringIO
from datetime import datetime, timedelta
import requests
import csv
import uuid

# Initialize Boto3 clients
events_client = boto3.client('events')
dynamodb_client = boto3.client('dynamodb')

def get_distance_matrix(api_key, origin_list, destination_list, transport_mode):
    url = 'https://maps.googleapis.com/maps/api/distancematrix/json'
    d_d_data = []
    batch_size = 10

    max_size = len(origin_list)//10
    if max_size*10 < len(origin_list):
      max_size += 1

    for i in range(max_size):
        o_list = origin_list[i*10:(i+1)*10]
        d_list = destination_list[i*10:(i+1)*10]
        origins_batch = '|'.join(o_list)
        destinations_batch = '|'.join(d_list)
        print(origins_batch)
        print(destinations_batch)
        params = {
            'origins': origins_batch,
            'destinations': destinations_batch,
            'key': 'API_KEY',
            'mode':0
        }
    
        response = requests.get(url, params=params)
        data = response.json()
        if 'rows' in data:
          for i, row in enumerate(data['rows']):
            d_d_l = [0,0]
            if 'elements' in row:
                for j, element in enumerate(row['elements']):
                  if 'distance' in element.keys() and 'duration' in element.keys() and i == j:
                    distance = element['distance']['value']
                    duration = element['duration']['value']
                    d_d_l = [distance, duration]
                    break
            d_d_data.append(d_d_l)
                  
    return d_d_data
    
def create_csv_from_list(list_of_lists):
    # Create a StringIO object to write CSV data
    csv_buffer = StringIO()
    
    # Create a CSV writer object
    csv_writer = csv.writer(csv_buffer)
    
    # Write rows to CSV file
    for row in list_of_lists:
        csv_writer.writerow(row)
    
    # Return the CSV data as a string
    csv_data = csv_buffer.getvalue()
    csv_buffer.close()
    
    return csv_data

def upload_csv_to_s3(csv_data, bucket_name, file_key):
    s3 = boto3.client('s3')

    # Upload the CSV data to S3
    s3.put_object(Body=csv_data, Bucket=bucket_name, Key=file_key)

def update_dynamodb_item(id, field_to_update, new_value):
    response = dynamodb_client.update_item(
        TableName='Event_Data',
        Key={'id': {'S': id}},
        UpdateExpression=f'SET {field_to_update} = :val',
        ExpressionAttributeValues={':val': {'N': new_value}}
    )
    return response

def delete_event_rule(rule_name):
    # List targets for the rule
    response = events_client.list_targets_by_rule(Rule=rule_name)
    
    # Remove all targets associated with the rule
    for target in response['Targets']:
        events_client.remove_targets(Rule=rule_name, Ids=[target['Id']])
    
    # Delete the EventBridge rule
    events_client.delete_rule(Name=rule_name)
    
def process_csv(csv_text):
    # Create a StringIO object from the CSV text
    csv_file = StringIO(csv_text)
    
    # Create a CSV reader object
    csv_reader = csv.reader(csv_file)
    
    # Read each row of the CSV data
    origin_list = []
    destination_list = []
    for i, row in enumerate(csv_reader):
        if i==0:
          headers = row
        else:
          origin_list.append(row[2])
          destination_list.append(row[3])
    return headers, origin_list, destination_list

def process_csv_reverse(csv_text, data):
    # Create a StringIO object from the CSV text
    csv_file = StringIO(csv_text)
    
    # Create a CSV reader object
    csv_reader = csv.reader(csv_file)
    
    # Read each row of the CSV data
    data_list = []
    for i, row in enumerate(csv_reader):
        if i==0:
            row.extend(['DISTANCE(Meters)', 'DURATION(Seconds)'])
            data_list.append(row)
        else:
            row.extend(data[i-1])
            data_list.append(row)
    return data_list
    
    
def generate_presigned_url(bucket_name, object_key, expiration_time=3600):
    """
    Generate a presigned URL for accessing an S3 object.

    :param bucket_name: The name of the S3 bucket.
    :param object_key: The key of the S3 object.
    :param expiration_time: The expiration time for the presigned URL in seconds (default is 1 hour).
    :return: The presigned URL.
    """
    s3_client = boto3.client('s3')
    presigned_url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket_name, 'Key': object_key},
        ExpiresIn=expiration_time
    )
    return presigned_url

def lambda_handler(event, context):
    # Retrieve ID from the event
    api_key = os.environ.get('api_key')
    id = event['id']
    
    # Retrieve data from DynamoDB based on the ID
    dynamodb_response = dynamodb_client.get_item(
        TableName='Event_Data',
        Key={'id': {'S': id}}
    )
    
    # Extract start_time, end_time, and frequency from DynamoDB response
    item = dynamodb_response.get('Item')
    if not item:
        raise ValueError(f"No data found for ID: {id}")
    
    current_count = int(item['current_trigger_count']['N']) + 1
    total_trigger = int(item['total_trigger_count']['N'])
    update_dynamodb_item(id, "current_trigger_count", str(current_count))
    
    text = item['distance_key_pair']['S']
    transport_mode = item['transport_mode']['S']
    headers, origin_list, destination_list = process_csv(text)
    data = get_distance_matrix(api_key, origin_list, destination_list, transport_mode)
    list_data = process_csv_reverse(text, data)
    csv_data = create_csv_from_list(list_data)
    
    start_datetime_str = item['event_start_time']['S']
    frequency = item['frequency']['N']
    start_date_time = datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M:%S')
    file_time = start_date_time + timedelta(minutes=(current_count-1)*int(frequency))
    file_time = datetime.strftime(file_time, '%Y-%m-%dT%H:%M:%S')
    # AWS S3 configuration
    bucket_name = 'output-bucket-dm'
    directory_path = f'Data/{id}/'  # Specify the directory path here
    file_name = f'{file_time}_generate_{current_count}.xlsx'  # Specify the filename here
    

    # Construct the full key with directory path and filename
    file_key = directory_path + file_name
    upload_csv_to_s3(csv_data, bucket_name, file_key)
    
    s3_url = generate_presigned_url(bucket_name, file_key)
    child_id = str(uuid.uuid4())
    item = {
            'id': child_id,
            'parent_id': id,
            'created_time': file_time,
            'url' : s3_url
        }
    # Store in DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('Distance_Matrix_Data')
    table.put_item(
        Item= item
    )  
  
    if total_trigger == current_count:
        rule_name = f'TriggerAtInterval_{id}'
        delete_event_rule(rule_name)
    else:
        print(f'Current Count : {current_count}')
        print(f'Total Triggers : {total_trigger}')
    
    return {
        'statusCode': 200,
        'body': json.dumps('Table updated successfully.')
    }