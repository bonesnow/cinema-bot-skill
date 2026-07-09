import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_one_click_deployment_scripts_are_present_and_executable():
    for relative in (
        "scripts/setup_local_env.sh",
        "scripts/local_qa.sh",
        "scripts/deploy_local.sh",
        "scripts/deploy_vps.sh",
        "scripts/configure_sources.sh",
    ):
        path = ROOT / relative
        assert path.exists(), relative
        assert os.access(path, os.X_OK), relative
