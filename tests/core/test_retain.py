"""`pskit remove --keep-resources`: which Terraform addresses are kept."""

from __future__ import annotations

from py_serverless_kit.core.retain import kept_addresses, supports

AWS_STATE = [
    "aws_iam_role.fn_api",
    "aws_lambda_function.api",
    "aws_s3_bucket.pskit-artifacts",
    "aws_s3_bucket.b_uploads",
    "aws_s3_bucket_public_access_block.b_uploads",
    "aws_s3_bucket_notification.b_uploads",
    "aws_sqs_queue.q_jobs",
    "aws_sqs_queue.q_jobs-dlq",
    "aws_sns_topic.t_events",
    "aws_sns_topic_subscription.t_events_worker",
    "data.aws_sqs_queue.q_existing",
]


def test_aws_keeps_data_but_not_infrastructure():
    kept = kept_addresses("aws", AWS_STATE)
    assert kept == [
        "aws_s3_bucket.b_uploads",
        "aws_s3_bucket_public_access_block.b_uploads",
        "aws_sqs_queue.q_jobs",
        "aws_sqs_queue.q_jobs-dlq",
        "aws_sns_topic.t_events",
    ]
    assert "aws_s3_bucket.pskit-artifacts" not in kept  # the code-upload bucket goes


def test_azure_keeps_the_containers_of_kept_data():
    state = [
        "azurerm_resource_group.rg",
        "azurerm_storage_account.app",
        "azurerm_storage_queue.q_jobs",
        "azurerm_linux_function_app.app",
        "azurerm_service_plan.plan",
    ]
    kept = kept_addresses("azure", state)
    assert set(kept) == {"azurerm_storage_queue.q_jobs", "azurerm_storage_account.app", "azurerm_resource_group.rg"}
    # Nothing to keep: the parents go too.
    assert kept_addresses("azure", ["azurerm_resource_group.rg", "azurerm_storage_account.app"]) == []


def test_modules_and_indexes_and_unsupported_providers():
    assert kept_addresses("gcp", ['module.x.google_storage_bucket.b_media["a"]', "google_storage_bucket.source"]) == [
        'module.x.google_storage_bucket.b_media["a"]'
    ]
    assert not supports("cloudflare") and kept_addresses("cloudflare", ["cloudflare_workers_script.w"]) == []


def test_deployer_drops_kept_resources_from_state(make_project):
    from py_serverless_kit.core.deployer import Deployer

    project = make_project("""
service: demo
provider: {name: aws}
functions:
  api: {handler: app.handlers.hello, events: [{queue: jobs}]}
""")
    calls = []

    class Runner:
        def init(self):
            calls.append("init")

        def state_list(self):
            return AWS_STATE

        def state_pull(self):
            return {"version": 4, "resources": []}

        def state_rm(self, addresses):
            calls.append(("rm", list(addresses)))

        def destroy(self, auto_approve=True):
            calls.append("destroy")

    (project.work_dir).mkdir(parents=True, exist_ok=True)
    (project.work_dir / "main.tf.json").write_text("{}")
    kept = Deployer(project, echo=lambda *_: None, runner=Runner()).remove(keep_resources=True)
    assert calls[0] == "init" and calls[-1] == "destroy"
    assert calls[1] == ("rm", kept) and "aws_sqs_queue.q_jobs" in kept
    assert (project.work_dir / "kept" / "terraform.tfstate").is_file()  # remembered for `pskit resources delete`

    calls.clear()
    assert Deployer(project, echo=lambda *_: None, runner=Runner()).remove() == []
    assert calls == ["init", "destroy"]


def test_cli_and_studio_pass_the_flag():
    from py_serverless_kit.studio.jobs import build_argv

    assert build_argv("remove", "aws", "dev", {"keep_resources": True})[-1] == "--keep-resources"
    assert "--keep-resources" not in build_argv("remove", "aws", "dev", {})
