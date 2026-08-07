from __future__ import annotations

import ast
import difflib
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
            and decorator.func.id in {"workflow", "workflow_definition"}
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
            and item.func.id in {"workflow", "workflow_definition"}
        )
        keywords = {keyword.arg for keyword in decorator.keywords}

        assert {"workflow_uuid", "displayname"} <= keywords
        assert keywords <= {"workflow_uuid", "displayname", "description"}
        imports = {
            alias.name
            for node in ast.parse(source).body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        if workflow.returns is None:
            assert "workflow_output" in imports
            terminal = workflow.body[-1]
            assert isinstance(terminal, ast.Return)
            assert isinstance(terminal.value, ast.Call)
            assert isinstance(terminal.value.func, ast.Name)
            assert terminal.value.func.id == "workflow_output"
            assert not terminal.value.args
            assert not terminal.value.keywords
        else:
            assert isinstance(workflow.returns, ast.Name)
            assert "workflow_output" not in imports


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


def test_s07_material_workflow_keeps_two_material_sources_and_parallel_transfers(
    repo_root: Path,
) -> None:
    source = (
        repo_root / "szlab_poly_studio/workflows/s07_material_dosing.py"
    ).read_text(encoding="utf-8")
    workflow = _workflow_function(source)

    material_sources = [
        node
        for node in ast.walk(workflow)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "material_source"
    ]
    assert len(material_sources) == 2
    assert all(
        any(
            keyword.arg == "mount"
            and isinstance(keyword.value, ast.Call)
            and isinstance(keyword.value.func, ast.Name)
            and keyword.value.func.id == "resource_ref"
            for keyword in call.keywords
        )
        for call in material_sources
    )

    parallel_blocks = [
        statement
        for statement in workflow.body
        if isinstance(statement, ast.With)
        and len(statement.items) == 1
        and isinstance(statement.items[0].context_expr, ast.Call)
        and isinstance(statement.items[0].context_expr.func, ast.Name)
        and statement.items[0].context_expr.func.id == "parallel"
    ]
    assert len(parallel_blocks) == 1
    branches = parallel_blocks[0].body
    assert len(branches) == 2
    assert all(
        isinstance(branch, ast.With)
        and len(branch.items) == 1
        and isinstance(branch.items[0].context_expr, ast.Call)
        and isinstance(branch.items[0].context_expr.func, ast.Name)
        and branch.items[0].context_expr.func.id == "group"
        for branch in branches
    )

    selector_ids = {
        "szlab_mixer_robot_device": "szlab_mixer_robot",
        "host_node": "host_node",
    }
    branch_actions = []
    for branch in branches:
        calls = sorted(
            (
                node
                for node in ast.walk(branch)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in selector_ids
            ),
            key=lambda node: (node.lineno, node.col_offset),
        )
        branch_actions.append(
            [
                f"{selector_ids[call.func.value.id]}.{call.func.attr}"
                for call in calls
            ]
        )
    assert branch_actions == [
        [
            "szlab_mixer_robot.pick",
            "szlab_mixer_robot.place",
            "host_node.transfer_resource",
        ],
        [
            "szlab_mixer_robot.pick",
            "szlab_mixer_robot.place",
            "host_node.transfer_resource",
        ],
    ]

    dose = next(
        node
        for node in ast.walk(workflow)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "dose_powder_with_materials"
    )
    dose_inputs = {keyword.arg: ast.unparse(keyword.value) for keyword in dose.keywords}
    assert dose_inputs["powder_cartridge"] == "committed_powder.resource"
    assert dose_inputs["beaker"] == "committed_beaker.resource"
    assert all(argument.arg != "transfer_id" for argument in workflow.args.kwonlyargs)
    assert all(
        keyword.arg != "transfer_id"
        for node in ast.walk(workflow)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
    )


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

        if workflow.id == "s_z_lab_单样品全流程_物料感知":
            assert result.valid is False
            assert {item["code"] for item in result.diagnostics} == {
                "composite_child_unapplied"
            }
            continue

        assert result.valid, (
            workflow.id,
            result.diagnostics,
        )
        if workflow.id == "s07_粉桶与烧杯搬运后固体称量":
            assert result.graph is not None
            assert result.normalized_python_source is not None
            nodes = {node["uuid"]: node for node in result.graph["nodes"]}
            assert {
                node["uuid"]
                for node in nodes.values()
                if node["type"] == "material_source"
            } == {
                "f7969031-098d-52eb-9193-92e41de3f3da",
                "af599d17-1d6c-5f34-a2f1-dc5239d1275d",
            }
            assert nodes[
                "9f67e05d-020a-5e8d-bf86-ae812aac7c01"
            ]["parent_uuid"] == "b6337f56-31f2-55c1-ab9d-f44e1b956e50"
            assert nodes[
                "4058067c-18e2-5b35-90eb-ddf04694c040"
            ]["parent_uuid"] == "115b2549-9202-518c-9aac-0a71de8ba72f"
            dose_predecessors = {
                edge["source_node_uuid"]
                for edge in result.graph["edges"]
                if edge["target_node_uuid"]
                == "58198f7a-eec4-5276-9bc5-5dd5b54c4b06"
            }
            assert {
                "8d8bfc18-03db-5ff3-a681-edf1c15294b7",
                "65fbc7bf-5e17-5a3e-9b15-eab6ebebbf82",
            } <= dose_predecessors
            assert result.normalized_python_source.count("material_source(") == 2
            assert "with parallel():" in result.normalized_python_source


def test_material_transfer_applies_before_single_sample_composite(
    repo_root: Path,
    production_authoring_service,
) -> None:
    package_root = repo_root / "szlab_poly_studio"
    children = (
        ("e7c53119-9fde-5250-9bf5-264f23d157a8", "material_transfer.py"),
    )

    for workflow_uuid, filename in children:
        production_authoring_service.register_editable_source(
            workflow_uuid=workflow_uuid,
            package_id="szlab_poly_studio",
            package_root=package_root,
            relative_path=f"workflows/{filename}",
        )
        aggregate = production_authoring_service.reconcile_registered_source(
            workflow_uuid
        )
        assert aggregate["draft"]["diagnostics"] == []
        assert aggregate["candidate"] is not None
        assert (
            aggregate["draft"]["python_source"]
            == aggregate["candidate"]["normalized_python_source"]
        )
        production_authoring_service.apply_authoring(
            workflow_uuid,
            candidate_hash=aggregate["candidate"]["candidate_hash"],
        )

    parent_uuid = "6d9fb3e2-4dcb-5f23-93b4-74d1b6083393"
    production_authoring_service.register_editable_source(
        workflow_uuid=parent_uuid,
        package_id="szlab_poly_studio",
        package_root=package_root,
        relative_path="workflows/single_sample_atomic_material.py",
    )
    parent = production_authoring_service.reconcile_registered_source(parent_uuid)
    assert parent["draft"]["diagnostics"] == []
    assert parent["candidate"] is not None
    assert (
        parent["draft"]["python_source"]
        == parent["candidate"]["normalized_python_source"]
    ), "".join(
        difflib.unified_diff(
            parent["draft"]["python_source"].splitlines(keepends=True),
            parent["candidate"]["normalized_python_source"].splitlines(
                keepends=True
            ),
            fromfile="draft",
            tofile="normalized",
        )
    )
    applied = production_authoring_service.apply_authoring(
        parent_uuid,
        candidate_hash=parent["candidate"]["candidate_hash"],
    )
    assert applied["apply_result"]["workflow_revision"] == 2


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
