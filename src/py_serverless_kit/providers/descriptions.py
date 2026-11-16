"""What every Terraform resource pskit generates is for, shown before a deploy.

``pskit package`` / ``plan`` / ``deploy`` print :func:`summarize` of ``main.tf.json`` (grouped by kind, with a
description and the pskit.yml setting that removes the optional ones) and save it as ``resources.json`` in the
work directory, which the studio's Deploy page shows. Unknown types (third-party providers, ``terraform.extra``)
get a generic description, so the summary always lists everything Terraform will manage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

RESOURCES_FILE = "resources.json"

# category, display order
CATEGORIES = (
    ("compute", "Functions"),
    ("code", "Code & images"),
    ("api", "HTTP / API"),
    ("triggers", "Triggers & schedules"),
    ("messaging", "Queues & topics"),
    ("storage", "Storage"),
    ("workflows", "Workflows"),
    ("access", "Access & permissions"),
    ("monitoring", "Logs & metrics"),
    ("platform", "Platform"),
    ("other", "Other"),
)

LOGS = "monitoring.logs: false"
METRICS = "monitoring.metrics: false (and logs, on every function)"
IMAGE = "package.type: image"

# type -> (category, description, how to leave it out ("" = always needed))
RESOURCES: Dict[str, Tuple[str, str, str]] = {
    # ---------------------------------------------------------------- AWS
    "aws_lambda_function": ("compute", "Lambda function that runs your handler", ""),
    "aws_lambda_permission": ("access", "lets a trigger (API Gateway, S3, SNS, EventBridge) invoke the function", ""),
    "aws_lambda_event_source_mapping": ("triggers", "polls an SQS queue and invokes the function with its messages", ""),
    "aws_iam_role": ("access", "execution role the functions (or schedules) run as", ""),
    "aws_iam_role_policy": ("access", "inline permissions of a role (your iam statements, bound resources, queues)", ""),
    "aws_iam_role_policy_attachment": ("access", "AWS managed policy on a role (CloudWatch Logs / SQS polling)", ""),
    "aws_apigatewayv2_api": ("api", "API Gateway HTTP API: the public endpoint of your HTTP routes", ""),
    "aws_apigatewayv2_stage": ("api", "the API's $default stage (auto-deploy)", ""),
    "aws_apigatewayv2_route": ("api", "one HTTP route (method + path) of the API", ""),
    "aws_apigatewayv2_integration": ("api", "connects API routes to a Lambda function", ""),
    "aws_apigatewayv2_authorizer": ("api", "JWT / IAM authorizer checking callers of protected routes", ""),
    "aws_scheduler_schedule": ("triggers", "EventBridge Scheduler schedule (rate / cron) invoking a function", ""),
    "aws_sqs_queue": ("messaging", "SQS queue (and dead-letter queue)", ""),
    "aws_sns_topic": ("messaging", "SNS topic", ""),
    "aws_sns_topic_subscription": ("triggers", "subscribes a function to an SNS topic", ""),
    "aws_s3_bucket": ("storage", "S3 bucket (your storage resources, or the private bucket holding the code zip)", ""),
    "aws_s3_bucket_public_access_block": ("storage", "blocks public access to the bucket", ""),
    "aws_s3_bucket_notification": ("triggers", "sends S3 object events to the functions", ""),
    "aws_s3_object": ("code", "the uploaded code zip (artifact.zip)", ""),
    "aws_sfn_state_machine": ("workflows", "Step Functions state machine running a workflow", ""),
    "aws_cloudwatch_log_group": ("monitoring", "CloudWatch log group of a function, with its retention", LOGS),
    "aws_ecr_repository": ("code", "Amazon ECR repository holding the function image", IMAGE),
    "aws_ecr_lifecycle_policy": ("code", "expires old images in the ECR repository (package.image.keep)", IMAGE),
    # ---------------------------------------------------------------- Azure
    "azurerm_resource_group": ("platform", "resource group holding everything of this stage", ""),
    "azurerm_storage_account": ("platform", "storage account the Function App needs (state, queues, blobs)", ""),
    "azurerm_service_plan": ("compute", "App Service plan the Function App runs on (Y1 consumption, EP1 premium...)", ""),
    "azurerm_linux_function_app": ("compute", "Function App hosting every function of the service", ""),
    "azurerm_storage_queue": ("messaging", "Storage queue (and its poison queue)", ""),
    "azurerm_storage_container": ("storage", "blob container", ""),
    "azurerm_servicebus_namespace": ("messaging", "Service Bus namespace for topics", ""),
    "azurerm_servicebus_topic": ("messaging", "Service Bus topic", ""),
    "azurerm_servicebus_subscription": ("triggers", "subscribes a function to a Service Bus topic", ""),
    "azurerm_log_analytics_workspace": ("monitoring", "Log Analytics workspace storing the Function App's logs", METRICS),
    "azurerm_application_insights": ("monitoring", "Application Insights: requests, metrics and traces", METRICS),
    "azurerm_logic_app_workflow": ("workflows", "Logic App running a native workflow", ""),
    "azurerm_logic_app_trigger_http_request": ("workflows", "HTTP trigger that starts the Logic App", ""),
    "azurerm_logic_app_action_custom": ("workflows", "steps of the Logic App", ""),
    "azurerm_container_registry": ("code", "Azure Container Registry holding the Function App image", IMAGE),
    # ---------------------------------------------------------------- GCP
    "google_cloudfunctions2_function": ("compute", "Cloud Run function (2nd gen) running your handler", ""),
    "google_storage_bucket": ("storage", "Cloud Storage bucket (your storage resources, or the code bucket)", ""),
    "google_storage_bucket_object": ("code", "the uploaded source zip", ""),
    "google_service_account": ("access", "service account that schedules, triggers and workflows call with", ""),
    "google_project_iam_member": ("access", "project role for a service account", ""),
    "google_cloud_run_service_iam_member": ("access", "lets the invoker account call a function", ""),
    "google_pubsub_topic": ("messaging", "Pub/Sub topic (queues and topics)", ""),
    "google_pubsub_subscription": ("messaging", "Pub/Sub subscription (dead letters)", ""),
    "google_pubsub_topic_iam_member": ("access", "publish permission on a topic", ""),
    "google_pubsub_subscription_iam_member": ("access", "subscriber permission on a subscription", ""),
    "google_cloud_scheduler_job": ("triggers", "Cloud Scheduler job invoking a function", ""),
    "google_workflows_workflow": ("workflows", "Google Cloud Workflows workflow", ""),
    # ---------------------------------------------------------------- container images (any provider)
    "docker_image": ("code", "image built from the bundle with your local Docker", IMAGE),
    "docker_registry_image": ("code", "pushes the image to the registry", IMAGE),
    # ---------------------------------------------------------------- Alibaba
    "alicloud_fcv3_function": ("compute", "Function Compute 3.0 function", ""),
    "alicloud_fcv3_trigger": ("triggers", "Function Compute trigger (HTTP, timer, OSS, MNS)", ""),
    "alicloud_ram_role": ("access", "RAM role the triggers use", ""),
    "alicloud_ram_role_policy_attachment": ("access", "policy on the RAM role", ""),
    "alicloud_oss_bucket": ("storage", "OSS bucket", ""),
    "alicloud_message_service_topic": ("messaging", "MNS topic", ""),
    # ---------------------------------------------------------------- Tencent
    "tencentcloud_scf_function": ("compute", "SCF function", ""),
    "tencentcloud_scf_trigger_config": ("triggers", "SCF trigger (timer, COS)", ""),
    "tencentcloud_api_gateway_service": ("api", "API Gateway service", ""),
    "tencentcloud_api_gateway_api": ("api", "API Gateway API (one route)", ""),
    "tencentcloud_api_gateway_service_release": ("api", "publishes the API Gateway service", ""),
    "tencentcloud_cos_bucket": ("storage", "COS bucket", ""),
    # ---------------------------------------------------------------- Huawei
    "huaweicloud_fgs_function": ("compute", "FunctionGraph function", ""),
    "huaweicloud_fgs_trigger": ("triggers", "FunctionGraph trigger (timer, OBS, SMN)", ""),
    "huaweicloud_apig_group": ("api", "API Gateway group", ""),
    "huaweicloud_apig_api": ("api", "API Gateway API (one route)", ""),
    "huaweicloud_apig_environment": ("api", "API Gateway environment", ""),
    "huaweicloud_apig_api_publishment": ("api", "publishes an API", ""),
    "huaweicloud_obs_bucket": ("storage", "OBS bucket", ""),
    "huaweicloud_smn_topic": ("messaging", "SMN topic", ""),
    # ---------------------------------------------------------------- IBM / Oracle / Cloudflare / DigitalOcean
    "ibm_code_engine_project": ("platform", "Code Engine project", ""),
    "ibm_code_engine_function": ("compute", "Code Engine function", ""),
    "oci_functions_application": ("compute", "OCI Functions application", ""),
    "oci_functions_function": ("compute", "OCI function (container image)", ""),
    "oci_apigateway_gateway": ("api", "OCI API gateway", ""),
    "oci_apigateway_deployment": ("api", "routes of the API gateway", ""),
    "oci_events_rule": ("triggers", "OCI Events rule invoking a function", ""),
    "oci_objectstorage_bucket": ("storage", "Object Storage bucket", ""),
    "cloudflare_workers_script": ("compute", "Cloudflare Worker running your handler", ""),
    "cloudflare_workers_script_subdomain": ("api", "serves the Worker on workers.dev", ""),
    "cloudflare_workers_route": ("api", "routes a zone path to the Worker", ""),
    "cloudflare_workers_cron_trigger": ("triggers", "Cron Triggers of a Worker", ""),
    "terraform_data": ("platform", "local step run by Terraform (deploy on a host, docker build, doctl)", ""),
}


def describe_type(rtype: str) -> Tuple[str, str, str]:
    known = RESOURCES.get(rtype)
    if known:
        return known
    words = rtype.split("_", 1)
    return "other", f"{words[-1].replace('_', ' ')} ({words[0]} provider)", ""


def summarize(tf: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry per resource type in Terraform JSON ``tf``: category, description, count, names, optional."""
    order = {key: i for i, (key, _label) in enumerate(CATEGORIES)}
    out: List[Dict[str, Any]] = []
    for rtype, bodies in (tf.get("resource") or {}).items():
        if not isinstance(bodies, dict):
            continue
        category, description, optional = describe_type(rtype)
        out.append({
            "type": rtype,
            "category": category,
            "category_label": dict(CATEGORIES)[category],
            "description": description,
            "count": len(bodies),
            "names": sorted(bodies),
            "optional": optional,
        })
    out.sort(key=lambda r: (order[r["category"]], r["type"]))
    return out


def lines(summary: List[Dict[str, Any]], max_names: int = 4) -> List[str]:
    """Readable lines for the terminal (grouped by category)."""
    total = sum(r["count"] for r in summary)
    out = [f"Will create or update {total} resource(s):"]
    current = ""
    for r in summary:
        if r["category_label"] != current:
            current = r["category_label"]
            out.append(f"  {current}")
        names = ", ".join(r["names"][:max_names]) + (", ..." if len(r["names"]) > max_names else "")
        extra = f" [optional: {r['optional']}]" if r["optional"] else ""
        out.append(f"    {r['type']} x{r['count']} - {r['description']} ({names}){extra}")
    return out


def save(work_dir: Path, summary: List[Dict[str, Any]], meta: Dict[str, Any]) -> Path:
    path = work_dir / RESOURCES_FILE
    path.write_bytes((json.dumps({**meta, "resources": summary}, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def load(work_dir: Path) -> Dict[str, Any]:
    try:
        data = json.loads((work_dir / RESOURCES_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
