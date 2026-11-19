"""terraform apply is retried after errors that only mean the cloud was not consistent yet (terraform/transient.py)."""

import pytest

from py_serverless_kit.core import partial
from py_serverless_kit.core.deployer import Deployer, DeployError
from py_serverless_kit.terraform import transient
from py_serverless_kit.terraform.runner import TerraformError, TerraformRunner

YML = """
service: part
provider:
  name: azure
  options:
    subscription_id: 00000000-0000-0000-0000-000000000000
functions:
  api:
    handler: app.handlers.hello
    events:
      - http: GET /hello
"""

SA_ID = "/subscriptions/0000/resourceGroups/part-dev-rg/providers/Microsoft.Storage/storageAccounts/partdevab12cd34"
AI_ID = "/subscriptions/0000/resourceGroups/part-dev-rg/providers/Microsoft.Insights/components/part-dev-ai"

# Real azurerm output: the storage account was created, listKeys 0.2 s later answered 404.
LIST_KEYS_404 = """
azurerm_storage_account.app: Creation complete after 25s
Error: encoding Storage Account (Subscription: "0000"
Storage Account Name: "partdevab12cd34"): listing Keys for Storage Account (Subscription: "0000"
Storage Account Name: "partdevab12cd34"): unexpected status 404 (404 Not Found) with error: ResourceNotFound: The Resource 'Microsoft.Storage/storageAccounts/partdevab12cd34' under resource group 'part-dev-rg' was not found.
  with azurerm_storage_account.app,
  on main.tf.json line 59, in resource.azurerm_storage_account.app:
  59:       }
"""

ROOT_ABSENT = """
Error: Provider produced inconsistent result after apply
When applying changes to azurerm_application_insights.ai, provider
"provider[\\"registry.terraform.io/hashicorp/azurerm\\"]" produced an
unexpected new value: Root object was present, but now absent.
This is a bug in the provider, which should be reported in the provider's own
issue tracker.
"""

AI_EXISTS = """
Error: a resource with the ID "AI_ID" already exists - to be managed via Terraform this resource needs to be imported into the State. Please see the resource documentation for "azurerm_application_insights" for more information
  with azurerm_application_insights.ai,
  on main.tf.json line 101, in resource.azurerm_application_insights.ai:
 101:       }
""".replace("AI_ID", AI_ID)

SA_EXISTS = AI_EXISTS.replace(AI_ID, SA_ID).replace("azurerm_application_insights.ai", "azurerm_storage_account.app")

QUOTA = """
Error: creating App Service Plan: unexpected status 401 (401 Unauthorized) with response: Operation cannot be completed without additional quota.
  with azurerm_service_plan.plan,
  on main.tf.json line 80, in resource.azurerm_service_plan.plan:
  80:       }
"""

DATA_404 = """
Error: retrieving Resource Group "missing-rg": unexpected status 404 (404 Not Found) with error: ResourceGroupNotFound
  with data.azurerm_resource_group.existing,
  on main.tf.json line 10, in data.azurerm_resource_group.existing:
  10:       }
"""


class SequenceRunner(TerraformRunner):
    """apply fails with each output of ``failures`` in turn, then succeeds."""

    def __init__(self, work_dir, failures):
        super().__init__(work_dir)
        self.failures = list(failures)
        self.applies = 0
        self.calls = []

    def init(self, upgrade=False, reconfigure=False):
        pass

    def apply(self, plan_file=None, auto_approve=True, targets=None):
        self.applies += 1
        if self.failures:
            raise TerraformError("`apply` failed with exit code 1", output=self.failures.pop(0))
        return ""

    def untaint(self, address):
        self.calls.append(("untaint", address))

    def import_resource(self, address, resource_id):
        self.calls.append(("import", address, resource_id))

    def output(self):
        return {"pskit": {"functions": {"api": {"id": "part-dev-api"}}, "workflows": {}, "endpoint": "https://x"}}


def deployer(project, failures, keep_going=True):
    runner = SequenceRunner(project.work_dir, failures)
    d = Deployer(project, echo=lambda _m: None, runner=runner, keep_going=keep_going)
    d.retry_delays = (0, 0)
    return d, runner


# --------------------------------------------------------------------------- classification
def test_list_keys_404_right_after_create_is_untainted():
    fix = transient.recovery(partial.parse_errors(LIST_KEYS_404), set())
    assert fix is not None
    assert fix.untaint == ["azurerm_storage_account.app"] and fix.imports == []


def test_root_object_absent_is_transient_without_untaint():
    seen = set()
    fix = transient.recovery(partial.parse_errors(ROOT_ABSENT), seen)
    assert fix is not None and fix.untaint == [] and seen == {"azurerm_application_insights.ai"}


def test_already_exists_is_imported_only_after_a_transient_failure_of_the_same_address():
    assert transient.recovery(partial.parse_errors(AI_EXISTS), set()) is None  # never adopt an unknown resource
    fix = transient.recovery(partial.parse_errors(AI_EXISTS), {"azurerm_application_insights.ai"})
    assert fix is not None and fix.imports == [("azurerm_application_insights.ai", AI_ID)]


@pytest.mark.parametrize("output", [QUOTA, DATA_404, LIST_KEYS_404 + QUOTA, "", "Error: something else\n"])
def test_real_errors_are_not_retried(output):
    assert transient.recovery(partial.parse_errors(output), set()) is None


# --------------------------------------------------------------------------- deploy
def test_deploy_retries_after_a_404_on_a_new_resource(make_project):
    d, runner = deployer(make_project(YML), [LIST_KEYS_404])
    record = d.deploy(skip_deps=True)
    assert runner.applies == 2
    assert runner.calls == [("untaint", "azurerm_storage_account.app")]
    assert record["status"] == "deployed" and not d.not_deployed


def test_deploy_imports_what_it_created_but_did_not_record(make_project):
    # Same apply: App Insights read back absent, the storage account 404; then both "already exist".
    d, runner = deployer(make_project(YML), [ROOT_ABSENT + LIST_KEYS_404, AI_EXISTS + SA_EXISTS])
    d.deploy(skip_deps=True)
    assert runner.applies == 3
    assert ("import", "azurerm_application_insights.ai", AI_ID) in runner.calls
    assert ("import", "azurerm_storage_account.app", SA_ID) in runner.calls


def test_deploy_gives_up_after_the_last_retry(make_project):
    d, runner = deployer(make_project(YML), [LIST_KEYS_404] * 5)
    with pytest.raises(DeployError):
        d.deploy(skip_deps=True)
    assert runner.applies == 3  # first apply + 2 retries


def test_real_error_fails_at_once(make_project):
    d, runner = deployer(make_project(YML), [QUOTA], keep_going=False)
    with pytest.raises(TerraformError):
        d.deploy(skip_deps=True)
    assert runner.applies == 1 and runner.calls == []
