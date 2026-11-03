"""BEFORE: a typical AWS-only Lambda codebase (do not deploy with pskit).

Everything AWS-specific is mixed into the business logic: API Gateway event
parsing, statusCode/body dicts, SQS record loops, boto3 Step Functions calls.
"""

import base64
import json
import os

import boto3

sfn = boto3.client("stepfunctions")


def create_order_handler(event, context):
    # API Gateway REST (payload v1) parsing
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    try:
        order = json.loads(body)
    except ValueError:
        return {"statusCode": 400, "body": json.dumps({"error": "invalid json"})}
    if not order.get("items"):
        return {"statusCode": 400, "body": json.dumps({"error": "items required"})}

    # Start the Step Functions workflow directly
    execution = sfn.start_execution(
        stateMachineArn=os.environ["ORDER_STATE_MACHINE_ARN"],
        input=json.dumps(order),
    )
    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"execution": execution["executionArn"]}),
    }


def get_order_handler(event, context):
    order_id = (event.get("pathParameters") or {}).get("id")
    if not order_id:
        return {"statusCode": 404, "body": json.dumps({"error": "not found"})}
    return {"statusCode": 200, "body": json.dumps({"id": order_id, "status": "unknown"})}


def email_worker_handler(event, context):
    # SQS batch with partial failure reporting
    failures = []
    for record in event["Records"]:
        try:
            message = json.loads(record["body"])
            print("sending email to", message["to"])
        except Exception:
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


# Step Functions task Lambdas receive the raw state as the event.
def validate_task(event, context):
    if sum(i["qty"] for i in event["items"]) <= 0:
        raise ValueError("empty order")
    return {**event, "valid": True}


def charge_task(event, context):
    return {**event, "charged": True}
