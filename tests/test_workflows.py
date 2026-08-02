from __future__ import annotations

import ast
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import yaml
from unilabos.package_manager import PackageCatalog
from unilabos.package_manager.consumers import register_package_catalog
from unilabos.registry.catalog_consumer import (
    workflow_template_imports_from_registry_snapshot,
)
from unilabos.registry.registry import Registry
from unilabos.workflow.authoring_engine import WorkflowAuthoringEngine
from unilabos.workflow.catalog import CatalogAuthority, TemplateCatalog
from unilabos.workflow.store import WorkflowStore


def _manifest_entries(manifest: dict) -> list[dict]:
    return [*manifest["presets"], *manifest["additional_workflows"]]


def _workflow_by_id(catalog: PackageCatalog) -> dict[str, object]:
    return {workflow.id: workflow for workflow in catalog.definitions.workflows}


def _action_sequence(source: str) -> list[str]:
    tree = ast.parse(source)
    selectors: dict[str, str] = {}
    workflow: ast.FunctionDef | None = None
    for statement in tree.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            value = statement.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "device"
                and len(value.args) == 1
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                selectors[statement.target.id] = value.args[0].value
        elif isinstance(statement, ast.FunctionDef):
            workflow = statement
    assert workflow is not None
    calls = sorted(
        (
            node
            for node in ast.walk(workflow)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in selectors
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    return [f"{selectors[call.func.value.id]}.{call.func.attr}" for call in calls]


def test_migration_manifest_covers_all_committed_inputs(repo_root: Path) -> None:
    migration_root = repo_root / "migration"
    manifest = yaml.safe_load((migration_root / "manifest.yaml").read_text(encoding="utf-8"))
    presets = manifest["presets"]

    assert len(presets) == 11
    assert {item["id"] for item in presets} == {
        path.stem for path in (migration_root / "legacy" / "ui-presets").glob("*.json")
    }
    assert {item["legacy_workflow"] for item in _manifest_entries(manifest) if item.get("legacy_workflow")} == {
        str(path.relative_to(migration_root)) for path in (migration_root / "legacy" / "workflows").glob("*.json")
    }
    assert manifest["capture"]["live_browser_draft_found"] is False

    for entry in _manifest_entries(manifest):
        assert (migration_root / entry["python_source"]).resolve().is_file()
        assert (migration_root / entry.get("legacy_preset", "manifest.yaml")).resolve().is_file()
        if entry.get("legacy_workflow"):
            assert (migration_root / entry["legacy_workflow"]).resolve().is_file()


def test_all_migrated_python_workflows_compile_to_canonical_v2(
    repo_root: Path,
    package_catalog: PackageCatalog,
    action_catalog: dict,
) -> None:
    migration_root = repo_root / "migration"
    manifest = yaml.safe_load((migration_root / "manifest.yaml").read_text(encoding="utf-8"))
    catalog_by_id = _workflow_by_id(package_catalog)
    declared_ids: set[str] = set()

    for entry in _manifest_entries(manifest):
        source_path = (migration_root / entry["python_source"]).resolve()
        workflow = catalog_by_id[entry["workflow_id"]]
        actions = _action_sequence(source_path.read_text(encoding="utf-8"))
        assert actions
        assert all(action in action_catalog for action in actions)
        assert (repo_root / workflow.declaring_file).resolve() == source_path
        declared_ids.add(workflow.id)

    assert declared_ids == set(catalog_by_id)


def test_all_package_workflows_satisfy_authoring_candidate_contract(
    repo_root: Path,
    package_catalog: PackageCatalog,
    tmp_path: Path,
) -> None:
    registry = Registry()
    registry.device_type_registry = {}
    registry.resource_type_registry = {}
    register_package_catalog(registry, package_catalog)

    authority = CatalogAuthority(authority_id="szlab-test", kind="local")
    resource_template_uuids = {
        device.fqid: str(uuid5(NAMESPACE_URL, device.fqid))
        for device in package_catalog.definitions.devices
    }
    imports = workflow_template_imports_from_registry_snapshot(
        registry.device_type_registry,
        authority_id=authority.authority_id,
        resource_template_identity_resolver=resource_template_uuids.__getitem__,
    )

    store = WorkflowStore(tmp_path / "workflow.db")
    try:
        template_catalog = TemplateCatalog(store)
        template_catalog.replace(authority, imports)
        compiler = WorkflowAuthoringEngine(
            catalog=template_catalog,
            authority=authority,
        )
        timestamp = "2026-08-02T00:00:00Z"

        for workflow in package_catalog.definitions.workflows:
            details = dict(workflow.details)
            workflow_uuid = details["workflow_uuid"]
            result = compiler.compile(
                workflow_uuid=workflow_uuid,
                workflow_revision=1,
                python_source=(repo_root / workflow.declaring_file).read_text(
                    encoding="utf-8"
                ),
                source_uri=details["source_uri"],
                applied_graph={
                    "workflow": {
                        "uuid": workflow_uuid,
                        "create_time": timestamp,
                        "update_time": timestamp,
                        "meta_data": {},
                        "name": workflow.displayname,
                        "tags": [],
                        "revision": 1,
                    },
                    "nodes": [],
                    "edges": [],
                    "node_templates": [],
                    "handle_templates": [],
                },
            )

            assert result.valid, (
                workflow.id,
                [diagnostic["code"] for diagnostic in result.diagnostics],
            )
    finally:
        store.close()


def test_legacy_json_action_sequences_are_preserved(
    repo_root: Path,
    action_catalog: dict,
) -> None:
    migration_root = repo_root / "migration"
    manifest = yaml.safe_load((migration_root / "manifest.yaml").read_text(encoding="utf-8"))

    for entry in _manifest_entries(manifest):
        legacy_ref = entry.get("legacy_workflow")
        if not legacy_ref:
            continue
        legacy = json.loads((migration_root / legacy_ref).read_text(encoding="utf-8"))
        expected = [f"{node['device_name']}.{node['name'].removeprefix('auto-')}" for node in legacy["nodes"]]
        if entry["workflow_id"] == "s08_cap_workflow":
            expected = ["szlab_s08_cap_station.process_cap_with_sample_parts" for _ in expected]

        source_path = (migration_root / entry["python_source"]).resolve()
        assert _action_sequence(source_path.read_text(encoding="utf-8")) == expected


def test_e2e_screenshots_cover_every_production_workflow(
    repo_root: Path,
    action_catalog: dict,
) -> None:
    result_path = repo_root / "docs" / "screenshots" / "all-workflows-e2e-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["outcome"] == "passed"
    assert result["total"] == 12
    assert result["packages"] == {"SZLab": 12}
    assert result["browserErrors"] == []
    assert [item["order"] for item in result["workflows"]] == list(range(1, 13))

    compiled_ids: set[str] = set()
    for item in result["workflows"]:
        source_path = repo_root / item["source"]
        screenshot_path = repo_root / "docs" / "screenshots" / item["screenshot"]
        actions = _action_sequence(source_path.read_text(encoding="utf-8"))

        assert source_path.stem == item["source"].rsplit("/", 1)[-1].removesuffix(".py")
        assert len(actions) == item["node_count"]
        assert max(0, len(actions) - 1) == item["edge_count"]
        assert screenshot_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert screenshot_path.stat().st_size > 100_000
        compiled_ids.add(item["workflow_id"])

    assert len(compiled_ids) == 12
