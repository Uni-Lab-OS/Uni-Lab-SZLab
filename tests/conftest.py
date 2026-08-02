from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT.parent
OS_ROOT = Path(os.environ.get("UNILAB_OS_ROOT", CORE_ROOT / "Uni-Lab-OS"))

for path in (OS_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def package_catalog(repo_root: Path):
    from unilabos.package_manager import WorkspaceSource, compile_package_source

    return compile_package_source(WorkspaceSource(repo_root))


@pytest.fixture(scope="session")
def action_catalog(package_catalog) -> dict:
    from unilabos.package_manager.consumers import (
        action_catalog_from_package_catalog,
    )

    return action_catalog_from_package_catalog(package_catalog)
