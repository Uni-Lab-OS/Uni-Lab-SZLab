from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5

from unilabos.package_manager import PackageAssetResolver, PackageCatalog, WorkspaceSource
from unilabos.package_manager.consumers import (
    register_package_catalog,
)
from unilabos.registry.catalog_consumer import (
    workflow_template_imports_from_registry_snapshot,
)


def _deployment_graphs(repo_root: Path) -> list[Path]:
    return sorted(
        path
        for path in (repo_root / "deployment" / "graphs").glob("szlab-*.json")
        if " copy" not in path.name
    )


def test_single_device_debug_keeps_catalog_discovery_separate_from_graph_selection(
    repo_root: Path,
    package_catalog: PackageCatalog,
    monkeypatch,
) -> None:
    from unilabos.registry.registry import lab_registry

    graph = json.loads((repo_root / "deployment" / "graphs" / "szlab-local-debug.json").read_text(encoding="utf-8"))
    selected = next(node for node in graph["nodes"] if node["id"] == "szlab_poly_plc")

    monkeypatch.setattr(lab_registry, "device_type_registry", {})
    monkeypatch.setattr(lab_registry, "resource_type_registry", {})
    register_package_catalog(lab_registry, package_catalog)

    assert len(package_catalog.definitions.devices) == 9
    assert len(lab_registry.device_type_registry) == 9
    assert selected["class"] in lab_registry.device_type_registry
    assert selected["config"]["auto_connect"] is False
    assert selected["config"]["csv_path"] == "szlab_plc_0730.csv"
    assert selected["config"]["url"] == "opc.tcp://127.0.0.1:50100/"


def test_full_workspace_debug_discovers_graph_workflows_and_assets(
    repo_root: Path,
    package_catalog: PackageCatalog,
) -> None:
    graph = json.loads((repo_root / "deployment" / "graphs" / "szlab-local-debug.json").read_text(encoding="utf-8"))
    resolver = PackageAssetResolver(WorkspaceSource(repo_root), package_catalog)

    assert len(graph["nodes"]) == 129
    assert len(package_catalog.definitions.workflows) == 13
    assert len(package_catalog.assets) == 14
    for asset in package_catalog.assets:
        with resolver.open_binary(asset.logical_path) as stream:
            assert stream.read(1)
    assert all((repo_root / workflow.declaring_file).is_file() for workflow in package_catalog.definitions.workflows)


def test_all_declared_workflows_compile_against_fe_template_catalog(
    repo_root: Path,
    package_catalog: PackageCatalog,
) -> None:
    from unilabos.registry.registry import Registry
    from unilabos.workflow.authoring_engine import WorkflowAuthoringEngine
    from unilabos.workflow.catalog import (
        CatalogAuthority,
        LocalResourceTemplateIdentityIndex,
        TemplateCatalog,
    )
    from unilabos.workflow.store import WorkflowStore

    registry = Registry()
    registry.device_type_registry = {}
    registry.resource_type_registry = {}
    register_package_catalog(registry, package_catalog)
    resource_template_uuids = {}
    material_template_uuids = {}
    for definition in (
        *package_catalog.definitions.devices,
        *package_catalog.definitions.resources,
    ):
        identity = str(uuid5(NAMESPACE_URL, definition.fqid))
        resource_template_uuids[definition.fqid] = identity
        resource_template_uuids[
            f"{definition.module}:{definition.symbol}"
        ] = identity
        if definition.kind == "resource":
            material_template_uuids[
                f"{definition.module}:{definition.symbol}"
            ] = identity
    imports = workflow_template_imports_from_registry_snapshot(
        copy.deepcopy(registry.device_type_registry),
        authority_id="szlab-workspace-test",
        resource_template_identity_resolver=resource_template_uuids.__getitem__,
    )
    authority = CatalogAuthority("szlab-workspace-test", "local")

    with TemporaryDirectory() as temporary:
        store = WorkflowStore(Path(temporary) / "workflow.db")
        try:
            templates = TemplateCatalog(store)
            templates.replace(
                authority,
                imports,
                resource_template_identities=material_template_uuids,
            )
            engine = WorkflowAuthoringEngine(
                catalog=templates,
                authority=authority,
                resource_template_identity_index=LocalResourceTemplateIdentityIndex(
                    store,
                    authority,
                    tuple(material_template_uuids),
                ),
            )
            for workflow in package_catalog.definitions.workflows:
                workflow_uuid = str(workflow.details["workflow_uuid"])
                applied_graph = {
                    "workflow": {
                        "uuid": workflow_uuid,
                        "revision": 1,
                        "name": workflow.id,
                        "description": "",
                        "tags": [],
                        "meta_data": {},
                        "create_time": "2026-08-01T00:00:00Z",
                        "update_time": "2026-08-01T00:00:00Z",
                    },
                    "nodes": [],
                    "edges": [],
                    "node_templates": [],
                    "handle_templates": [],
                }
                result = engine.compile(
                    workflow_uuid=workflow_uuid,
                    workflow_revision=1,
                    python_source=(repo_root / workflow.declaring_file).read_text(encoding="utf-8"),
                    source_uri=str(workflow.details["source_uri"]),
                    applied_graph=applied_graph,
                )
                assert result.valid, (workflow.id, result.diagnostics)
        finally:
            store.close()


def test_graph_selected_material_factories_receive_graph_config(
    repo_root: Path,
    package_catalog: PackageCatalog,
    monkeypatch,
) -> None:
    from unilabos.registry.registry import lab_registry
    from unilabos.resources.graphio import initialize_resource

    monkeypatch.setattr(lab_registry, "device_type_registry", {})
    monkeypatch.setattr(lab_registry, "resource_type_registry", {})
    register_package_catalog(lab_registry, package_catalog)

    selected: dict[str, dict] = {}
    for graph_path in _deployment_graphs(repo_root):
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        for node in payload["nodes"]:
            if node["type"] != "device":
                selected.setdefault(node["class"], node)

    initialized = {class_name: initialize_resource(copy.deepcopy(node)) for class_name, node in selected.items()}

    catalog_resources = {definition.fqid for definition in package_catalog.definitions.resources}
    assert set(initialized) < catalog_resources
    assert catalog_resources - set(initialized) == {
        "community.szlab_poly_studio.szlab_pipette_tip",
        "community.szlab_poly_studio.szlab_poly_s3_unused_sample_vial_warehouse",
        "community.szlab_poly_studio.szlab_poly_s11_used_sample_vial_warehouse",
    }
    deck = initialized["community.szlab_poly_studio.szlab_poly_studio_deck"]
    assert len(deck[0]) == 1
