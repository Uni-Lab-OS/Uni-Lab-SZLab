from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml
from unilabos.app.scheduler.dispatch import RecordingDispatcher
from unilabos.app.scheduler.models import WorkflowNode, WorkflowSpec
from unilabos.app.scheduler.service import EdgeScheduler

from szlab_poly_studio.devices.szlab_mixer_robot.device import (
    SzlabMixerRobotDevice,
)
from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
    SZLabS07SolidAdditionDevice,
)

WORKFLOW_UUID = "5e7ce142-bf5a-5d30-8666-fdf5374941f1"
WORKFLOW_SOURCE = "szlab_poly_studio/workflows/s07_material_dosing.py"
DEPLOYMENT_BOUND_INPUTS = {
    "powder_source_warehouse",
    "beaker_source_warehouse",
    "solid_addition_warehouse",
    "powder_source_site",
    "powder_target_site",
    "beaker_source_site",
    "beaker_target_site",
}


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _calls(statements: list[ast.stmt]) -> list[str]:
    return [
        _call_name(node)
        for statement in statements
        for node in ast.walk(statement)
        if isinstance(node, ast.Call) and _call_name(node) != "resource_ref"
    ]


def _workflow_function(tree: ast.Module) -> ast.FunctionDef:
    matches = [
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
    assert len(matches) == 1
    return matches[0]


def test_s07_material_dosing_is_published_by_the_package(repo_root: Path) -> None:
    package = yaml.safe_load((repo_root / "package.yaml").read_text(encoding="utf-8"))
    entries = {item["workflow_uuid"]: item["source"] for item in package["workflows"]}

    assert entries[WORKFLOW_UUID] == WORKFLOW_SOURCE
    assert (repo_root / WORKFLOW_SOURCE).is_file()


def test_s07_deployment_warehouses_and_sites_are_not_workflow_inputs(
    repo_root: Path,
) -> None:
    tree = ast.parse((repo_root / WORKFLOW_SOURCE).read_text(encoding="utf-8"))
    workflow = _workflow_function(tree)

    argument_names = {argument.arg for argument in (*workflow.args.args, *workflow.args.kwonlyargs)}
    assert DEPLOYMENT_BOUND_INPUTS.isdisjoint(argument_names)

    rendered_source = ast.unparse(workflow)
    assert "resource_ref('s3_unused_beaker')" in rendered_source
    assert "resource_ref('powder_container_warehouse')" in rendered_source
    assert "resource_ref('s07_process_warehouse')" in rendered_source
    assert "resource_template_uuid" not in rendered_source
    assert "site='L1B1'" in rendered_source
    assert "site='L1C1'" in rendered_source
    assert "site='S0722'" in rendered_source
    assert "site='P01'" in rendered_source
    assert "powder_site='P01'" in rendered_source


def test_s07_material_dosing_has_two_parallel_material_branches_and_one_join(
    repo_root: Path,
) -> None:
    tree = ast.parse((repo_root / WORKFLOW_SOURCE).read_text(encoding="utf-8"))
    workflow = _workflow_function(tree)

    material_sources = [
        node for node in ast.walk(workflow) if isinstance(node, ast.Call) and _call_name(node) == "material_source"
    ]
    assert len(material_sources) == 2

    parallel_blocks = [
        node
        for node in ast.walk(workflow)
        if isinstance(node, ast.With)
        and len(node.items) == 1
        and isinstance(node.items[0].context_expr, ast.Call)
        and _call_name(node.items[0].context_expr) == "parallel"
    ]
    assert len(parallel_blocks) == 1
    branches = parallel_blocks[0].body
    assert len(branches) == 2
    assert all(
        isinstance(branch, ast.With)
        and isinstance(branch.items[0].context_expr, ast.Call)
        and _call_name(branch.items[0].context_expr) == "group"
        for branch in branches
    )

    branch_calls = [_calls(branch.body) for branch in branches if isinstance(branch, ast.With)]
    assert branch_calls == [
        [
            "pick",
            "place",
            "transfer_resource",
        ],
        [
            "pick",
            "prepare_powder_cartridge_site",
            "place",
            "transfer_resource",
        ],
    ]

    dose_calls = [
        node
        for node in ast.walk(workflow)
        if isinstance(node, ast.Call) and _call_name(node) == "dose_powder_with_materials"
    ]
    assert len(dose_calls) == 1
    inputs = {keyword.arg: ast.unparse(keyword.value) for keyword in dose_calls[0].keywords}
    assert inputs["powder_cartridge"] == "committed_powder.resource"
    assert inputs["beaker"] == "committed_beaker.resource"


def test_s07_compiler_normalization_is_a_fixed_point(
    repo_root: Path,
    production_authoring_compiler,
) -> None:
    source = (repo_root / WORKFLOW_SOURCE).read_text(encoding="utf-8")
    applied_graph = {
        "workflow": {
            "uuid": WORKFLOW_UUID,
            "revision": 1,
            "name": "S07 material dosing fixed point",
            "description": "",
            "tags": [],
            "meta_data": {},
            "create_time": "2026-08-03T00:00:00Z",
            "update_time": "2026-08-03T00:00:00Z",
        },
        "nodes": [],
        "edges": [],
        "node_templates": [],
        "handle_templates": [],
    }
    first = production_authoring_compiler.compile(
        workflow_uuid=WORKFLOW_UUID,
        workflow_revision=1,
        python_source=source,
        source_uri=f"package://{WORKFLOW_SOURCE}",
        applied_graph=applied_graph,
    )

    assert first.valid, first.diagnostics
    assert first.graph is not None
    assert first.normalized_python_source is not None
    second = production_authoring_compiler.compile(
        workflow_uuid=WORKFLOW_UUID,
        workflow_revision=1,
        python_source=first.normalized_python_source,
        source_uri=f"package://{WORKFLOW_SOURCE}",
        applied_graph=first.graph,
    )

    assert second.valid, second.diagnostics
    assert second.normalized_python_source == first.normalized_python_source


def test_scheduler_serializes_parallel_actions_on_the_same_robot() -> None:
    dispatcher = RecordingDispatcher()
    scheduler = EdgeScheduler(dispatcher=dispatcher)
    spec = WorkflowSpec(
        workflow_id="s07-parallel-robot-contract",
        nodes=[
            WorkflowNode(
                id="powder-pick",
                device_id="szlab_mixer_robot",
                action_name="pick",
                action_type="goal",
            ),
            WorkflowNode(
                id="beaker-place",
                device_id="szlab_mixer_robot",
                action_name="place",
                action_type="goal",
            ),
        ],
    )

    first = scheduler.submit_workflow(spec)
    assert len(first["dispatched"]) == 1
    assert len(scheduler.snapshot()["inflight_jobs"]) == 1

    second = scheduler.on_job_finished(
        first["dispatched"][0]["job_id"],
        success=True,
    )
    assert len(second["dispatched"]) == 1
    assert len(scheduler.snapshot()["inflight_jobs"]) == 1
    assert {item["node_id"] for item in dispatcher.dispatched} == {
        "powder-pick",
        "beaker-place",
    }


class _SuccessfulRobotGateway:
    def execute_site(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "command_id": "transfer-1:pick",
            "state": "SUCCEEDED",
            "success": True,
            "message": "complete",
            "boot_id": "test-boot",
        }


def test_robot_pick_and_place_return_the_transferred_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    robot = object.__new__(SzlabMixerRobotDevice)
    gateway = _SuccessfulRobotGateway()
    monkeypatch.setattr(robot, "_standard_gateway", lambda: gateway)
    resource = {"uuid": "material-1"}
    warehouse = {"uuid": "warehouse-1"}

    picked = robot.pick(
        resource=resource,
        warehouse=warehouse,
        site="L1C1",
        transfer_id="transfer-1",
    )
    placed = robot.place(
        resource=resource,
        warehouse=warehouse,
        site="P01",
        transfer_id="transfer-1",
    )

    assert picked["resource"] is resource
    assert placed["resource"] is resource


def test_s07_actions_return_both_material_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    station = object.__new__(SZLabS07SolidAdditionDevice)
    monkeypatch.setattr(
        station,
        "rotate_powder_cartridge_to_feed",
        lambda **_kwargs: {"success": True, "message": "ready"},
    )
    monkeypatch.setattr(
        station,
        "dose_powder",
        lambda **_kwargs: {"success": True, "message": "dosed"},
    )
    powder = {"uuid": "powder-1"}
    beaker = {"uuid": "beaker-1"}

    prepared = station.prepare_powder_cartridge_site(
        powder_cartridge=powder,
        powder_site="P01",
    )
    dosed = station.dose_powder_with_materials(
        powder_cartridge=powder,
        beaker=beaker,
        powder_site="P01",
        target_mass_g=1.0,
    )

    assert prepared["powder_cartridge"] is powder
    assert dosed["powder_cartridge"] is powder
    assert dosed["beaker"] is beaker
