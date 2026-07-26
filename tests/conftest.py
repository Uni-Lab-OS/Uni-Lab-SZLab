from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO_ROOT.parent
OS_ROOT = CORE_ROOT / "Uni-Lab-OS"
SZLAB_PACKAGE_ROOT = REPO_ROOT / "packages" / "szlab_poly_studio"
AI4C_PACKAGE_ROOT = REPO_ROOT / "packages" / "ai4c_robot"

for path in (OS_ROOT, SZLAB_PACKAGE_ROOT, AI4C_PACKAGE_ROOT):
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
            repo_root / "packages" / "szlab_poly_studio" / "package.yaml",
            repo_root / "packages" / "ai4c_robot" / "package.yaml",
        ]
    )


@pytest.fixture(scope="session")
def action_catalog(profiles) -> dict:
    catalog: dict = {}
    for profile in profiles.values():
        overlap = set(catalog) & set(profile.action_catalog)
        assert not overlap, f"duplicate action refs across profiles: {sorted(overlap)}"
        catalog.update(profile.action_catalog)
    return catalog
