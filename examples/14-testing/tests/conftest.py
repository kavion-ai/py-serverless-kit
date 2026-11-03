from pathlib import Path

import pytest

from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project() -> Project:
    return Project.load(cwd=ROOT)


@pytest.fixture
def runner(project) -> LocalRunner:
    # Runs handlers through the real dispatcher: routing, error mapping, CORS,
    # batch results - exactly what happens in the cloud, minus the network.
    return LocalRunner(project, env_file=None)
