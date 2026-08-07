from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
SOURCE_PATH = REPO_ROOT / "szlab_poly_studio" / "workflows" / "beaker_transfer_chain.py"
WORKFLOW_UUID = "0a6b3005-833d-491b-9fd4-fe6545846dab"


def _keyword(call: ast.Call, name: str) -> ast.expr:
    return next(keyword.value for keyword in call.keywords if keyword.arg == name)


def _constant(call: ast.Call, name: str) -> str:
    value = _keyword(call, name)
    assert isinstance(value, ast.Constant) and isinstance(value.value, str)
    return value.value


def _resource_ref(call: ast.Call, name: str) -> str:
    value = _keyword(call, name)
    assert isinstance(value, ast.Call)
    assert isinstance(value.func, ast.Name) and value.func.id == "resource_ref"
    assert len(value.args) == 1 and isinstance(value.args[0], ast.Constant)
    return str(value.args[0].value)


def test_transfer_chain_uses_five_ordered_standard_transfers() -> None:
    """验证同一烧杯经 S0722 按五段固定路径线性转运。

    参数：无。
    返回：无；断言每段的源/目标库位、仓库和目标设备。
    """

    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    workflow = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "s_z_lab_烧杯五工位搬运"
    )
    assignments = [
        statement
        for statement in workflow.body
        if isinstance(statement, ast.Assign)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "s_z_lab_标准物料转运"
    ]

    assert len(assignments) == 5
    assert [(_constant(item.value, "source_site"), _constant(item.value, "target_site")) for item in assignments] == [
        ("L1B1", "S0722"),
        ("S0722", "S061"),
        ("S061", "BEAKER1"),
        ("BEAKER1", "S041"),
        ("S041", "S051"),
    ]
    assert [
        (_resource_ref(item.value, "source_warehouse"), _resource_ref(item.value, "target_warehouse"))
        for item in assignments
    ] == [
        ("s3_unused_beaker", "s07_process_warehouse"),
        ("s07_process_warehouse", "s06_process_warehouse"),
        ("s06_process_warehouse", "szlab_mixer_pipetting_station"),
        ("szlab_mixer_pipetting_station", "s04_process_warehouse"),
        ("s04_process_warehouse", "s05_process_warehouse"),
    ]
    assert [_constant(item.value, "target_device") for item in assignments] == [
        "szlab_s07_solid_addition",
        "szlab_mixer_pump",
        "szlab_mixer_pipetting_station",
        "szlab_mixer_stirrer",
        "szlab_mixer_photoshotting",
    ]

    first_resource = _keyword(assignments[0].value, "resource")
    assert isinstance(first_resource, ast.Name) and first_resource.id == "source_beaker"
    for previous, current in zip(assignments, assignments[1:]):
        previous_target = previous.targets[0]
        resource = _keyword(current.value, "resource")
        assert isinstance(previous_target, ast.Name)
        assert isinstance(resource, ast.Attribute) and resource.attr == "resource"
        assert isinstance(resource.value, ast.Name) and resource.value.id == previous_target.id


def test_transfer_chain_is_registered_with_matching_identity() -> None:
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    workflow = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    decorator = next(
        item
        for item in workflow.decorator_list
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "workflow"
    )
    assert _constant(decorator, "workflow_uuid") == WORKFLOW_UUID

    package_yaml = (REPO_ROOT / "package.yaml").read_text(encoding="utf-8")
    assert f"workflow_uuid: {WORKFLOW_UUID}" in package_yaml
    assert "source: szlab_poly_studio/workflows/beaker_transfer_chain.py" in package_yaml


def test_transfer_chain_source_site_is_graph_independent() -> None:
    """验证烧杯来源由库存权威按挂载点解析，而非绑定某张设备图的库位 UUID。

    参数：无。
    返回：无；断言来源库位为动态解析。
    """

    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    workflow = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "s_z_lab_烧杯五工位搬运"
    )
    source_assignment = next(
        statement
        for statement in workflow.body
        if isinstance(statement, ast.Assign)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "material_source"
    )

    site = _keyword(source_assignment.value, "site")
    assert isinstance(site, ast.Constant) and site.value is None
