from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml
from unilabos.package_manager import PackageCatalog


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


def _workflow_function(source: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    workflows = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "workflow_definition"
            for decorator in node.decorator_list
        )
    ]
    assert len(workflows) == 1
    return workflows[0]


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
    production_registry,
) -> None:
    migration_root = repo_root / "migration"
    manifest = yaml.safe_load((migration_root / "manifest.yaml").read_text(encoding="utf-8"))
    catalog_by_id = _workflow_by_id(package_catalog)
    declared_ids: set[str] = set()
    host_actions = {
        f"host_node.{name}"
        for name in production_registry.device_type_registry["host_node"]["class"][
            "action_value_mappings"
        ]
    }

    for entry in _manifest_entries(manifest):
        source_path = (migration_root / entry["python_source"]).resolve()
        workflow = catalog_by_id[entry["workflow_id"]]
        actions = _action_sequence(source_path.read_text(encoding="utf-8"))
        assert actions
        assert all(
            action in action_catalog or action in host_actions for action in actions
        )
        assert (repo_root / workflow.declaring_file).resolve() == source_path
        declared_ids.add(workflow.id)

    assert declared_ids == set(catalog_by_id)


def test_package_workflows_use_the_current_decorator_and_return_contract(repo_root: Path) -> None:
    package = yaml.safe_load((repo_root / "package.yaml").read_text(encoding="utf-8"))

    for entry in package["workflows"]:
        source_path = repo_root / entry["source"]
        source = source_path.read_text(encoding="utf-8")
        workflow = _workflow_function(source)
        decorator = next(
            item
            for item in workflow.decorator_list
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "workflow_definition"
        )
        keywords = {keyword.arg for keyword in decorator.keywords}

        assert {"workflow_uuid", "displayname"} <= keywords
        assert keywords <= {"workflow_uuid", "displayname", "description"}
        assert workflow.returns is not None
        assert "workflow_output" not in {
            alias.name
            for node in ast.parse(source).body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }


def test_s06_material_workflow_forms_one_resource_slot_chain(repo_root: Path) -> None:
    source = (repo_root / "szlab_poly_studio/workflows/s06_material.py").read_text(encoding="utf-8")
    workflow = _workflow_function(source)
    calls = _action_sequence(source)

    assert calls == [
        "szlab_mixer_robot.pick_beaker_from_s03",
        "szlab_mixer_robot.place_beaker_to_s06",
        "szlab_mixer_pump.add_solvent_to_beaker",
        "szlab_mixer_robot.pick_beaker_from_s06",
    ]
    assert isinstance(workflow.returns, ast.Name)
    assert workflow.returns.id == "S06MaterialWorkflowResult"
    assert "ResourceSlot" in source
    assert "AllowedResourceTemplates(beaker_500ml)" in source
    assert "beaker=picked.beaker" in source
    assert "beaker=placed.beaker" in source
    assert "beaker=addition.beaker" in source


def test_s06_material_actions_define_the_resource_slot_at_the_action_boundary(
    repo_root: Path,
) -> None:
    action_sources = {
        "pick_beaker_from_s03": repo_root / "szlab_poly_studio/devices/szlab_mixer_robot/device.py",
        "place_beaker_to_s06": repo_root / "szlab_poly_studio/devices/szlab_mixer_robot/device.py",
        "pick_beaker_from_s06": repo_root / "szlab_poly_studio/devices/szlab_mixer_robot/device.py",
        "add_solvent_to_beaker": repo_root / "szlab_poly_studio/devices/szlab_mixer_pump/device.py",
    }

    for action_name, source_path in action_sources.items():
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        action_function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == action_name
        )
        beaker = next(argument for argument in action_function.args.args if argument.arg == "beaker")
        annotation = ast.unparse(beaker.annotation)

        assert "ResourceSlot" in annotation
        assert "AllowedResourceTemplates(beaker_500ml)" in annotation
        assert any(
            (isinstance(decorator, ast.Name) and decorator.id == "action")
            or (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "action"
            )
            for decorator in action_function.decorator_list
        )
        assert isinstance(action_function.returns, ast.Name)


def test_all_package_workflows_satisfy_authoring_candidate_contract(
    repo_root: Path,
    package_catalog: PackageCatalog,
    production_authoring_compiler,
) -> None:
    timestamp = "2026-08-02T00:00:00Z"

    for workflow in package_catalog.definitions.workflows:
        details = dict(workflow.details)
        workflow_uuid = details["workflow_uuid"]
        result = production_authoring_compiler.compile(
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


def test_historical_e2e_screenshot_evidence_remains_valid(
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
