from __future__ import annotations

import ast
import json
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


def _resource_ref_ids(source: str) -> set[str]:
    """提取源码中 ``resource_ref`` 调用的字符串资源身份。"""

    identities: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "resource_ref"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            identities.add(node.args[0].value)
    return identities


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
    assert {
        "s3_unused_beaker",
        "powder_container_warehouse",
        "s10_liquid_reagent",
        "s04_process_warehouse",
        "s05_process_warehouse",
        "s06_process_warehouse",
        "s07_process_warehouse",
        "s11_used_beaker",
    } <= _resource_ref_ids(source)


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
    assert calls.count("material_source") == 8
    assert not any(name.startswith("material_transfer_") for name in calls)
    assert not {name for name in parameters if name.endswith("_warehouse")}
    assert {
        "s2_tip_warehouse",
        "s3_unused_beaker",
        "powder_container_warehouse",
        "s10_liquid_reagent",
        "s04_process_warehouse",
        "s05_process_warehouse",
        "s06_process_warehouse",
        "s07_process_warehouse",
        "szlab_s08_cap_station",
        "szlab_mixer_pipetting_station",
        "s11_used_beaker",
    } <= _resource_ref_ids(source)


def test_production_beaker_source_is_graph_independent_and_starts_at_l1b1(
    repo_root: Path,
) -> None:
    """证明烧杯来源不固化设备图 UUID，首个物理转运仍从 L1B1 取料。

    参数：``repo_root`` 是 SZLab 仓库根目录，用于读取生产工作流源码。
    返回：无；断言失败表示物料来源（MaterialSource）与库位（Site）合同漂移。
    """

    production = (
        repo_root
        / "szlab_poly_studio/workflows/single_sample_atomic_material.py"
    )
    module = ast.parse(production.read_text(encoding="utf-8"))
    workflow = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "s_z_lab_单样品全流程_物料感知"
    )
    assignments = {
        target.id: node.value
        for node in ast.walk(workflow)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    source_call = assignments["source_beaker"]
    transfer_call = assignments["beaker_at_s07"]
    assert isinstance(source_call, ast.Call)
    assert isinstance(transfer_call, ast.Call)

    source_site = next(
        keyword.value for keyword in source_call.keywords if keyword.arg == "site"
    )
    transfer_site = next(
        keyword.value
        for keyword in transfer_call.keywords
        if keyword.arg == "source_site"
    )

    assert ast.literal_eval(source_site) is None
    assert ast.literal_eval(transfer_site) == "L1B1"


def test_plc_sim_graph_provides_single_sample_inventory_and_transfer_sites(
    repo_root: Path,
) -> None:
    """证明 PLC-Sim 图提供单样品工作流引用的全部物料与转运库位。

    参数：``repo_root`` 是 SZLab 仓库根目录，用于读取工作流及 PLC-Sim 图。
    返回：无；断言失败表示运行图不能承载该工作流的物料准入或库位转运。
    """

    production = (
        repo_root
        / "szlab_poly_studio/workflows/single_sample_atomic_material.py"
    )
    module = ast.parse(production.read_text(encoding="utf-8"))
    workflow = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "s_z_lab_单样品全流程_物料感知"
    )
    graph_path = repo_root / "deployment/graphs/szlab-plc-sim-local.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}

    source_mounts: set[str] = set()
    for call in ast.walk(workflow):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "material_source"
        ):
            continue
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        mount_call = keywords["mount"]
        assert isinstance(mount_call, ast.Call)
        source_mounts.add(ast.literal_eval(mount_call.args[0]))

    for mount_id in source_mounts:
        sites = nodes_by_id[mount_id]["config"].get("sites", [])
        assert sites, f"PLC-Sim 物料来源 {mount_id} 缺少库位目录"
        assert any(site.get("occupied_by") for site in sites), (
            f"PLC-Sim 物料来源 {mount_id} 缺少初始物料占用"
        )

    beaker_sites = nodes_by_id["s3_unused_beaker"]["config"]["sites"]
    assert beaker_sites[0]["name"] == "L1B1"
    assert beaker_sites[0]["content_type"] == ["szlab_beaker_500ml"]

    for call in ast.walk(workflow):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "s_z_lab_标准物料转运"
        ):
            continue
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        for side in ("source", "target"):
            warehouse_call = keywords[f"{side}_warehouse"]
            assert isinstance(warehouse_call, ast.Call)
            warehouse_id = ast.literal_eval(warehouse_call.args[0])
            if nodes_by_id[warehouse_id]["type"] != "warehouse":
                continue
            expected_site = ast.literal_eval(keywords[f"{side}_site"])
            configured_sites = {
                site["name"]
                for site in nodes_by_id[warehouse_id]["config"].get("sites", [])
            }
            assert expected_site in configured_sites, (
                f"PLC-Sim 资源 {warehouse_id} 缺少转运库位 {expected_site}"
            )


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


def test_single_sample_root_materials_are_scheduler_allocated(
    repo_root: Path,
) -> None:
    """全部根物料由物料来源（MaterialSource）交给 EdgeScheduler 预分配。"""

    production = (
        repo_root
        / "szlab_poly_studio/workflows/single_sample_atomic_material.py"
    )
    module = ast.parse(production.read_text(encoding="utf-8"))
    result = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef)
        and node.name == "SZLab单样品全流程物料感知Result"
    )
    workflow = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "s_z_lab_单样品全流程_物料感知"
    )
    returned = next(
        node.value
        for node in workflow.body
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
    )
    explicit_fields = {
        node.target.id
        for node in result.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    returned_fields = {
        key.value
        for key in returned.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }

    assert {"reagent_bottle", "tip_box"}.isdisjoint(explicit_fields)
    assert {"reagent_bottle", "tip_box"}.isdisjoint(returned_fields)
    assert {"reagent_bottle", "tip", "tip_box"}.isdisjoint(_workflow_parameters(
        production.read_text(encoding="utf-8"),
        "s_z_lab_单样品全流程_物料感知",
    ))


def test_single_sample_outputs_follow_the_final_material_consumers(
    repo_root: Path,
) -> None:
    """成品瓶与使用后烧杯从最后一个物理消费者输出。"""

    production = (
        repo_root
        / "szlab_poly_studio/workflows/single_sample_atomic_material.py"
    )
    module = ast.parse(production.read_text(encoding="utf-8"))
    workflow = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "s_z_lab_单样品全流程_物料感知"
    )
    returned = next(
        node.value
        for node in workflow.body
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
    )
    values = {
        key.value: value
        for key, value in zip(returned.keys, returned.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }

    product = values["product_vial"]
    used_beaker = values["used_beaker"]
    assert isinstance(product, ast.Attribute)
    assert isinstance(product.value, ast.Name)
    assert (product.value.id, product.attr) == ("product_vial_at_s11", "resource")
    assert isinstance(used_beaker, ast.Attribute)
    assert isinstance(used_beaker.value, ast.Name)
    assert (used_beaker.value.id, used_beaker.attr) == (
        "committed_used_beaker",
        "resource",
    )


def test_s09_warehouse_consumers_are_not_parallel_siblings(repo_root: Path) -> None:
    """S09 两次入仓显式排序，不并发消费同一仓物料。"""

    production = (
        repo_root
        / "szlab_poly_studio/workflows/single_sample_atomic_material.py"
    )
    module = ast.parse(production.read_text(encoding="utf-8"))
    workflow = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "s_z_lab_单样品全流程_物料感知"
    )
    parallel_blocks = [
        node
        for node in ast.walk(workflow)
        if isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "parallel"
            for item in node.items
        )
    ]
    parallel_targets = {
        target.id
        for block in parallel_blocks
        for node in ast.walk(block)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert {"beaker_at_s09", "reagent_at_s09"}.isdisjoint(parallel_targets)


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
