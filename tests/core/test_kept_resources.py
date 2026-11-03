"""Deleting buckets, queues and topics pskit created: kept ones (remove --keep-resources) and deployed ones."""

from __future__ import annotations

import json
import os
import shutil

import pytest

from py_serverless_kit.core.retain import data_resources, delete_kept, list_kept, save_kept

STATE = {
    "version": 4,
    "terraform_version": "1.9.0",
    "serial": 7,
    "lineage": "abc",
    "resources": [
        {
            "mode": "managed",
            "type": "aws_s3_bucket",
            "name": "b_uploads",
            "provider": 'provider["registry.terraform.io/hashicorp/aws"]',
            "instances": [{"attributes": {"id": "demo-uploads", "bucket": "demo-uploads", "arn": "arn:aws:s3:::demo-uploads"}}],
        },
        {
            "mode": "managed",
            "type": "aws_s3_bucket_public_access_block",
            "name": "b_uploads",
            "instances": [{"attributes": {"id": "demo-uploads"}}],
        },
        {
            "mode": "managed",
            "type": "aws_sqs_queue",
            "name": "q_jobs",
            "instances": [{"attributes": {"id": "https://sqs/q", "name": "demo-jobs", "arn": "arn:aws:sqs:q"}}],
        },
        {"mode": "managed", "type": "aws_lambda_function", "name": "api", "instances": [{"attributes": {"id": "fn"}}]},
        {"mode": "data", "type": "aws_sqs_queue", "name": "q_ext", "instances": [{"attributes": {"id": "x"}}]},
    ],
}


def test_data_resources_lists_buckets_queues_topics():
    found = data_resources("aws", STATE)
    assert [(r["address"], r["kind"], r["name"]) for r in found] == [
        ("aws_s3_bucket.b_uploads", "bucket", "demo-uploads"),
        ("aws_sqs_queue.q_jobs", "queue", "demo-jobs"),
    ]
    assert all(r["status"] == "deployed" for r in found)


def test_save_kept_writes_a_config_free_workspace(tmp_path):
    (tmp_path / "main.tf.json").write_text(
        json.dumps(
            {
                "terraform": {"backend": {"s3": {}}, "required_providers": {"aws": {"source": "hashicorp/aws"}}},
                "provider": {"aws": {"region": "eu-west-1"}},
                "resource": {"aws_s3_bucket": {"b_uploads": {}}},
            }
        )
    )
    folder = save_kept(tmp_path, STATE, ["aws_s3_bucket.b_uploads", "aws_s3_bucket_public_access_block.b_uploads"])
    config = json.loads((folder / "main.tf.json").read_text())
    assert "backend" not in config["terraform"] and "resource" not in config and config["provider"]["aws"]
    kept = list_kept(tmp_path)
    assert [r["address"] for r in kept] == ["aws_s3_bucket.b_uploads"] and kept[0]["status"] == "kept"
    # A second remove adds to the same workspace.
    save_kept(tmp_path, STATE, ["aws_sqs_queue.q_jobs"])
    assert {r["address"] for r in list_kept(tmp_path)} == {"aws_s3_bucket.b_uploads", "aws_sqs_queue.q_jobs"}
    assert json.loads((folder / "terraform.tfstate").read_text())["serial"] == 2


TF = os.environ.get("PSKIT_TERRAFORM_BIN") or shutil.which("terraform") or shutil.which("tofu")


@pytest.mark.skipif(not TF, reason="needs terraform or tofu on PATH")
def test_delete_kept_with_real_terraform(tmp_path):
    """terraform_data needs no provider download or credentials: create, keep, then delete one and all."""
    from py_serverless_kit.terraform.runner import TerraformRunner

    work = tmp_path / "work"
    work.mkdir()
    config = {
        "terraform": {"required_version": ">= 1.5.0"},
        "resource": {"terraform_data": {"b_media": {"input": "a"}, "q_jobs": {"input": "b"}, "fn": {"input": "c"}}},
    }
    (work / "main.tf.json").write_text(json.dumps(config))
    runner = TerraformRunner(work, binary=TF, echo=lambda _m: None)
    runner.init()
    runner.apply()
    state = runner.state_pull()
    keep = ["terraform_data.b_media", "terraform_data.q_jobs"]
    save_kept(work, state, keep)
    runner.state_rm(keep)
    runner.destroy()
    assert runner.state_list() == []
    assert {r["address"] for r in list_kept(work)} == set(keep)

    delete_kept(work, ["terraform_data.b_media"], binary=TF, echo=lambda _m: None)
    assert [r["address"] for r in list_kept(work)] == ["terraform_data.q_jobs"]
    delete_kept(work, None, binary=TF, echo=lambda _m: None)
    assert list_kept(work) == [] and not (work / "kept").exists()
