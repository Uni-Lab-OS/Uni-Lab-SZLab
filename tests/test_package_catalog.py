from __future__ import annotations

from pathlib import Path

import yaml
from unilabos.package_manager import WorkspaceSource, compile_package_source
from unilabos.package_manager.consumers import (
    action_catalog_from_package_catalog,
    register_package_catalog,
)
from unilabos.registry.registry import lab_registry


def test_repository_compiles_as_the_szlab_domain_package(repo_root: Path) -> None:
    catalog = compile_package_source(WorkspaceSource(repo_root))

    assert catalog.distribution.name == "szlab-poly-studio"
    assert catalog.import_package == "szlab_poly_studio"
    assert catalog.namespace == "community.szlab_poly_studio"
    assert (repo_root / "package.yaml").is_file()
    assert len(catalog.definitions.devices) == 9
    assert len(catalog.definitions.resources) == 16
    assert len(catalog.definitions.workflows) == 13
    assert sum(len(device.details["actions"]) for device in catalog.definitions.devices) == 78
    assert len(catalog.assets) == 14
    assert all(
        item.fqid.startswith("community.szlab_poly_studio.")
        for collection in (
            catalog.definitions.devices,
            catalog.definitions.resources,
            catalog.definitions.workflows,
        )
        for item in collection
    )
    assert {str(workflow.details["workflow_uuid"]) for workflow in catalog.definitions.workflows} == {
        item["workflow_uuid"]
        for item in yaml.safe_load((repo_root / "package.yaml").read_text(encoding="utf-8"))["workflows"]
    }


def test_catalog_projects_to_registry_without_the_legacy_package_scanner(
    repo_root: Path,
    monkeypatch,
) -> None:
    catalog = compile_package_source(WorkspaceSource(repo_root))
    monkeypatch.setattr(lab_registry, "device_type_registry", {})
    monkeypatch.setattr(lab_registry, "resource_type_registry", {})

    register_package_catalog(lab_registry, catalog)
    action_count = sum(
        len(entry["class"]["action_value_mappings"]) for entry in lab_registry.device_type_registry.values()
    )

    assert len(lab_registry.device_type_registry) == 9
    assert len(lab_registry.resource_type_registry) == 16
    assert action_count == 78
    assert len(action_catalog_from_package_catalog(catalog)) == 78
    assert all(
        definition.startswith("community.szlab_poly_studio.") for definition in lab_registry.device_type_registry
    )
