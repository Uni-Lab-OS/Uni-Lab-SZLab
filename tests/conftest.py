from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT.parent
OS_ROOT = CORE_ROOT / "Uni-Lab-OS"

for path in (OS_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def profiles(repo_root: Path):
    from unilabos.runtime.profile_loader import load_profiles

    return load_profiles(
        [
            repo_root
            / "szlab_poly_studio"
            / "profiles"
            / "default"
            / "package.yaml",
        ]
    )


@pytest.fixture(scope="session")
def decorated_action_catalog(repo_root: Path) -> dict:
    from unilabos.registry.action_catalog import scan_decorated_device_package

    return scan_decorated_device_package(repo_root / "szlab_poly_studio")


@pytest.fixture(scope="session")
def action_catalog(profiles, decorated_action_catalog) -> dict:
    catalog: dict = {}
    for profile in profiles.values():
        overlap = set(catalog) & set(profile.action_catalog)
        assert not overlap, f"duplicate action refs across profiles: {sorted(overlap)}"
        catalog.update(profile.action_catalog)
    overlap = set(catalog) & set(decorated_action_catalog)
    assert not overlap, f"duplicate profile/decorator action refs: {sorted(overlap)}"
    catalog.update(decorated_action_catalog)
    return catalog
