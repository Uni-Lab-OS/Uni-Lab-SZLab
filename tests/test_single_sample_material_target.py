from __future__ import annotations

import ast
from pathlib import Path


def _call_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return names


def _workflow_parameters(source: str, function_name: str) -> set[str]:
    module = ast.parse(source)
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    return {
        argument.arg
        for argument in (*function.args.args, *function.args.kwonlyargs)
    }


def test_single_sample_target_expresses_material_and_transfer_contract(
    repo_root: Path,
) -> None:
    target = (
        repo_root
        / "docs/examples/workflow_authoring/single_sample_atomic_material_target.py"
    )
    source = target.read_text(encoding="utf-8")
    calls = _call_names(source)

    assert calls.count("material_source") == 4
    assert calls.count("material_transfer") == 11
    assert calls.count("parallel") == 2
    assert calls.count("pick") == 1
    assert calls.count("place") == 1
    assert calls.count("transfer_resource") == 1
    assert not any(name.startswith("submit_") for name in calls)
    assert "transfer_id" not in source

    assert {
        "process_cap_with_material",
        "dose_powder_with_two_materials",
        "add_solvent_with_materials",
        "add_liquid_with_materials",
        "stir_beaker",
        "inspect_beaker",
        "pour_beaker_into_vial",
    } < set(calls)


def test_single_sample_target_keeps_deployment_locations_internal(
    repo_root: Path,
) -> None:
    target = (
        repo_root
        / "docs/examples/workflow_authoring/single_sample_atomic_material_target.py"
    )
    source = target.read_text(encoding="utf-8")
    parameters = _workflow_parameters(
        source,
        "single_sample_atomic_material_workflow",
    )

    assert not any(name.endswith("_site") for name in parameters)
    assert {name for name in parameters if name.endswith("_warehouse")} == {
        "s08_warehouse",
        "s09_warehouse",
    }
    for resource_id in (
        "s3_unused_beaker",
        "powder_container_warehouse",
        "s10_liquid_reagent",
        "s04_process_warehouse",
        "s05_process_warehouse",
        "s06_process_warehouse",
        "s07_process_warehouse",
        "s11_used_beaker",
    ):
        assert f'resource_ref("{resource_id}")' in source


def test_production_single_sample_workflow_has_the_same_location_boundary(
    repo_root: Path,
) -> None:
    production = (
        repo_root
        / "szlab_poly_studio/workflows/single_sample_atomic_material.py"
    )
    source = production.read_text(encoding="utf-8")
    calls = _call_names(source)
    parameters = _workflow_parameters(
        source,
        "s_z_lab_单样品全流程_物料感知",
    )

    assert not any(name.endswith("_site") for name in parameters)
    assert calls.count("s_z_lab_标准物料转运") == 11
    assert not any(name.startswith("material_transfer_") for name in calls)
    assert {name for name in parameters if name.endswith("_warehouse")} == {
        "s08_warehouse",
        "s09_warehouse",
    }
    for resource_id in (
        "s3_unused_beaker",
        "powder_container_warehouse",
        "s10_liquid_reagent",
        "s04_process_warehouse",
        "s05_process_warehouse",
        "s06_process_warehouse",
        "s07_process_warehouse",
        "s11_used_beaker",
    ):
        assert f"resource_ref('{resource_id}')" in source


def test_standard_transfer_uses_implicit_material_passthrough(
    repo_root: Path,
) -> None:
    transfer = repo_root / "szlab_poly_studio/workflows/material_transfer.py"
    source = transfer.read_text(encoding="utf-8")
    module = ast.parse(source)
    result = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "SZLab标准物料转运Result"
    )
    result_fields = {
        node.target.id
        for node in result.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }

    assert result_fields == {"site"}
    assert "resource: ResourceSlot" in source
    assert "committed.resource" not in source


def test_single_sample_mapping_covers_all_legacy_actions(repo_root: Path) -> None:
    mapping = (
        repo_root / "docs/SINGLE_SAMPLE_ATOMIC_MATERIAL_REWRITE.md"
    ).read_text(encoding="utf-8")

    for index in range(1, 39):
        assert f"| {index} |" in mapping

    assert "robot.pick" in mapping
    assert "robot.place" in mapping
    assert "host.transfer_resource" in mapping
    assert "MaterialSource" in mapping
    assert "ResourceSlot" in mapping
