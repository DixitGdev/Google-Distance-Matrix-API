import boto3
import json
from datetime import datetime, timedelta

# Initialize Boto3 clients
events_client = boto3.client('events')
dynamodb_client = boto3.client('dynamodb')
lambda_client = boto3.client('lambda')
def create_event_rule(id, start_time, end_time, frequency):

    # Create the EventBridge rule
    rule_name = f'TriggerAtInterval_{id}'
    response = events_client.put_rule(
        Name=rule_name, 
        ScheduleExpression=f'rate({frequency} minutes)',
        State='ENABLED'
    )

    # Add the Lambda function as a target to the rule
    target_response = events_client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                'Id': id,
                'Arn': 'ARN',
                'Input': json.dumps({'id': id})
            }
        ]
    )
    
    # Lambda invoke permission
    lambda_client.add_permission(
        FunctionName='distance_matrix_api_lambda',
        StatementId=rule_name + '-EventBridge',
        Action='lambda:InvokeFunction',
        Principal='events.amazonaws.com',
        SourceArn=response['RuleArn'],
    )
    return response, target_response

def delete_event_rule(rule_name):
    # List targets for the rule
    response = events_client.list_targets_by_rule(Rule=rule_name)
    
    # Remove all targets associated with the rule
    for target in response['Targets']:
        events_client.remove_targets(Rule=rule_name, Ids=[target['Id']])
    
    # Delete the EventBridge rule
    events_client.delete_rule(Name=rule_name)


def lambda_handler(event, context):
    # Retrieve ID from the event
    id = event['id']
    print(id)
    source_event_rule = f"TriggerBeforeStart_{id}"
    delete_event_rule(source_event_rule)
    
    # Retrieve data from DynamoDB based on the ID
    dynamodb_response = dynamodb_client.get_item(
        TableName='Event_Data',
        Key={'id': {'S': id}}
    )
    
    # Extract start_time, end_time, and frequency from DynamoDB response
    item = dynamodb_response.get('Item')
    if not item:
        raise ValueError(f"No data found for ID: {id}")
    
    start_time = datetime.strptime(item['event_start_time']['S'], '%Y-%m-%dT%H:%M:%S')
    end_time = datetime.strptime(item['event_end_time']['S'], '%Y-%m-%dT%H:%M:%S')
    frequency = int(item['frequency']['N'])
    
    # Create a new EventBridge rule based on the fetched data
    response, target_response = create_event_rule(id, start_time, end_time, frequency)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Event rule created successfully')
    }
