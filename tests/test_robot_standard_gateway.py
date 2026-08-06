from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from szlab_poly_studio.common.site_control_bindings import (
    canonical_site_reference,
    resolve_robot_site_reference,
    resolve_s07_process_site,
    resolve_s071_site,
)
from szlab_poly_studio.devices.szlab_mixer_robot.robot_tasks import (
    ROBOT_HOME_VARIABLE,
    ROBOT_WRITE_ALLOWED_VARIABLE,
)
from szlab_poly_studio.devices.szlab_mixer_robot.standard_gateway import (
    TOOL_PAYLOAD_SENSOR_VARIABLE,
    StandardRobotRequest,
    SZLabStandardRobotGateway,
    _capture_workflow_execution_identity,
    _payload_profile_for_resource,
    _robot_command_from_request,
)
from unilabos.utils.tracing import attach_workflow_execution_identity

SOURCE_SENSOR = resolve_s071_site("L1C1").presence_variable
TARGET_SENSOR = resolve_s07_process_site("P01").presence_variable
NODE_JOB_UUID = "6199359e-c8e4-4a86-b709-1c50fc192ff7"
TASK_UUID = "89326717-9448-47ce-825a-e679d6556c27"


class FakeLegacyRobot:
    def __init__(self) -> None:
        self.dispatch_count = 0
        self.variables = {
            ROBOT_HOME_VARIABLE: True,
            ROBOT_WRITE_ALLOWED_VARIABLE: True,
            TOOL_PAYLOAD_SENSOR_VARIABLE: False,
            SOURCE_SENSOR: True,
            TARGET_SENSOR: False,
        }

    def _read_variable(self, name: str, use_cache: bool = False):
        return self.variables[name]

    def _ensure_sensor_gate(self, sensor: str, expected: bool, message: str) -> None:
        if bool(self.variables[sensor]) is not expected:
            raise RuntimeError(message)

    def _submit_robot_task(self, **kwargs):
        self.dispatch_count += 1
        kwargs["precheck"]()
        is_pick = kwargs["task"] == "pick"
        sensor_key = "source_sensor_variable" if is_pick else "target_sensor_variable"
        sensor = kwargs[sensor_key]
        self.variables[sensor] = not is_pick
        self.variables[TOOL_PAYLOAD_SENSOR_VARIABLE] = is_pick
        return {
            "success": True,
            "message": f"legacy {kwargs['task']} complete",
            "status": "completed",
            sensor_key: sensor,
            "completion_value": 1,
        }

    def _run_s072_place(self, product_type: int = 1, position: int = 1):
        self.dispatch_count += 1
        self.variables[TARGET_SENSOR] = True
        self.variables[TOOL_PAYLOAD_SENSOR_VARIABLE] = False
        return {
            "success": True,
            "message": "legacy place complete",
            "status": "completed",
            "product_type": product_type,
            "position": position,
            "target_sensor_variable": TARGET_SENSOR,
            "completion_value": 1,
        }


def gateway(tmp_path, robot: FakeLegacyRobot, **overrides) -> SZLabStandardRobotGateway:
    config = {
        "journal_path": str(tmp_path / "commands.sqlite3"),
        "program_version": "szlab-mixer-plc@0730",
        "point_set_version": "szlab-mixer-points@0730",
        "payload_profiles": ["powder_container@v1", "beaker_500ml@v1"],
        "actions_enabled": True,
        "permit_asserts_remote_auto": True,
        "permit_asserts_safety_normal": True,
        "execution_identity_provider": lambda: {
            "node_job_uuid": NODE_JOB_UUID,
            "task_uuid": TASK_UUID,
        },
    }
    config.update(overrides)
    return SZLabStandardRobotGateway(robot, **config)


def request(
    *,
    command_id: str = "pick-001",
    sequence: int = 1,
    material_id: str = "powder-001",
) -> StandardRobotRequest:
    return StandardRobotRequest(
        kind="pick",
        command_id=command_id,
        site="powder_container_warehouse/L1C1",
        program_version="szlab-mixer-plc@0730",
        point_set_version="szlab-mixer-points@0730",
        payload_profile="powder_container@v1",
        source_boot_id="scheduler-boot-001",
        monotonic_sequence=sequence,
        material_context={
            "resource": {"uuid": material_id},
            "source_device": "powder-stack",
            "target_device": "s07",
        },
    )


def test_payload_profile_uses_unilabos_resource_class_when_plr_category_is_generic() -> None:
    resource = SimpleNamespace(
        category="container",
        unilabos_extra={
            "unilabos_resource_class": "community.szlab_poly_studio.szlab_beaker_500ml",
        },
    )

    assert _payload_profile_for_resource(resource) == "beaker_500ml@v1"


def test_s09_device_resource_resolves_beaker_site_to_legacy_robot_command() -> None:
    warehouse = {
        "uuid": "b14fa65f-72d5-5698-8268-0a47d06e92e1",
        "name": "S09 移液站",
        "class": "community.szlab_poly_studio.szlab_mixer_pipetting_station",
    }
    binding = resolve_robot_site_reference(warehouse, "BEAKER1")
    command = _robot_command_from_request(
        StandardRobotRequest(
            kind="place",
            command_id="place-s09-beaker",
            site=canonical_site_reference(binding),
            program_version="szlab-mixer-plc@0730",
            point_set_version="szlab-mixer-points@0730",
            payload_profile="beaker_500ml@v1",
            source_boot_id="scheduler-boot-001",
            monotonic_sequence=1,
            material_context={"resource": {"uuid": "beaker-001"}},
        )
    )

    assert binding.station == "S09"
    assert binding.product_type == 3
    assert binding.controller_position == 1
    assert command.legacy_runner_name == "_run_s09_place"
    assert command.legacy_parameters == {"product_type": 3, "position": 1}


def test_s08_device_resource_resolves_reagent_site_to_legacy_robot_command() -> None:
    warehouse = {
        "uuid": "2c7fa65f-72d5-5698-8268-0a47d06e92e1",
        "name": "S08 开关盖",
        "class": "community.szlab_poly_studio.szlab_s08_cap_station",
    }
    binding = resolve_robot_site_reference(warehouse, "S082")
    command = _robot_command_from_request(
        StandardRobotRequest(
            kind="place",
            command_id="place-s08-reagent",
            site=canonical_site_reference(binding),
            program_version="szlab-mixer-plc@0730",
            point_set_version="szlab-mixer-points@0730",
            payload_profile="liquid_reagent_bottle_100ml@v1",
            source_boot_id="scheduler-boot-001",
            monotonic_sequence=1,
            material_context={"resource": {"uuid": "reagent-001"}},
        )
    )

    assert binding.station == "S08"
    assert binding.product_type == 3
    assert binding.controller_position == 2
    assert command.legacy_runner_name == "_run_s08_place"
    assert command.legacy_parameters == {"product_type": 3, "position": 2}


def test_payload_profile_distinguishes_250ml_sample_vial() -> None:
    resource = SimpleNamespace(
        category="sample_vial",
        max_volume=250_000,
        unilabos_extra={
            "unilabos_resource_class": "community.szlab_poly_studio.szlab_sample_vial_250ml",
        },
    )

    assert _payload_profile_for_resource(resource) == "sample_vial_250ml@v1"


def test_s03_sample_row_selects_250ml_plc_product_from_payload() -> None:
    warehouse = {
        "uuid": "4a0b516d-d145-5cdf-9b15-02093b1286d4",
        "id": "s3_unused_beaker",
    }
    binding = resolve_robot_site_reference(warehouse, "L1A1")
    command = _robot_command_from_request(
        StandardRobotRequest(
            kind="pick",
            command_id="pick-s03-sample-vial-250ml",
            site=canonical_site_reference(binding),
            program_version="szlab-mixer-plc@0730",
            point_set_version="szlab-mixer-points@0730",
            payload_profile="sample_vial_250ml@v1",
            source_boot_id="scheduler-boot-001",
            monotonic_sequence=1,
            material_context={"resource": {"uuid": "sample-vial-250ml-001"}},
        )
    )

    assert binding.site_label == "L1A1"
    assert command.legacy_runner_name == "_run_s03_pick"
    assert command.legacy_parameters == {"product_type": 2, "position": "1-1"}


def test_s11_sample_row_selects_250ml_plc_product_from_payload() -> None:
    warehouse = {"id": "s11_used_beaker"}
    binding = resolve_robot_site_reference(warehouse, "L1A1")
    command = _robot_command_from_request(
        StandardRobotRequest(
            kind="place",
            command_id="place-s11-sample-vial-250ml",
            site=canonical_site_reference(binding),
            program_version="szlab-mixer-plc@0730",
            point_set_version="szlab-mixer-points@0730",
            payload_profile="sample_vial_250ml@v1",
            source_boot_id="scheduler-boot-001",
            monotonic_sequence=1,
            material_context={"resource": {"uuid": "sample-vial-250ml-001"}},
        )
    )

    assert binding.site_label == "L1A1"
    assert command.legacy_runner_name == "_run_s11_place"
    assert command.legacy_parameters == {"product_type": 2, "position": "1-1"}


def test_standard_pick_reuses_legacy_plc_handshake_and_is_idempotent(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot)

    first = target.execute(request())
    second = target.execute(request())

    assert first["state"] == "SUCCEEDED"
    assert second == first
    assert robot.dispatch_count == 1


def test_site_action_uses_workflow_node_job_as_command_identity(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot)

    first = target.execute_site(
        kind="pick",
        resource={"uuid": "powder-001", "category": "powder_reagent"},
        warehouse={
            "uuid": "powder-warehouse-001",
            "id": "powder_container_warehouse",
        },
        site="L1C1",
    )
    replay = target.execute_site(
        kind="pick",
        resource={"uuid": "powder-001", "category": "powder_reagent"},
        warehouse={
            "uuid": "powder-warehouse-001",
            "id": "powder_container_warehouse",
        },
        site="L1C1",
    )

    assert first["success"] is True
    assert first["command_id"] == f"workflow-node-job:{NODE_JOB_UUID}"
    assert replay == first
    assert robot.dispatch_count == 1


def test_default_identity_provider_reads_current_os_runtime_context() -> None:
    with attach_workflow_execution_identity(NODE_JOB_UUID, TASK_UUID):
        assert _capture_workflow_execution_identity() == {
            "node_job_uuid": NODE_JOB_UUID,
            "task_uuid": TASK_UUID,
        }


def test_local_debug_enables_guarded_standard_robot_actions() -> None:
    graph_path = (
        Path(__file__).resolve().parents[1]
        / "deployment"
        / "graphs"
        / "szlab-local-debug.json"
    )
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    robot = next(node for node in graph["nodes"] if node["id"] == "szlab_mixer_robot")

    assert robot["config"]["standard_actions_enabled"] is True
    assert robot["config"]["standard_permit_asserts_remote_auto"] is True
    assert robot["config"]["standard_permit_asserts_safety_normal"] is True


def test_site_action_without_workflow_identity_fails_closed(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot, execution_identity_provider=lambda: {})

    result = target.execute_site(
        kind="pick",
        resource={"uuid": "powder-001", "category": "powder_reagent"},
        warehouse={
            "uuid": "powder-warehouse-001",
            "id": "powder_container_warehouse",
        },
        site="L1C1",
    )

    assert result["state"] == "REJECTED"
    assert "WorkflowNodeJob" in result["message"]
    assert "业务侧幂等标识" in result["message"]
    assert robot.dispatch_count == 0


def test_same_command_id_with_another_material_is_rejected(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot)
    assert target.execute(request())["success"] is True

    conflict = target.execute(request(material_id="powder-002"))

    assert conflict["state"] == "REJECTED"
    assert "不同请求" in conflict["message"]
    assert robot.dispatch_count == 1


def test_standard_actions_fail_closed_until_permit_semantics_are_accepted(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot, permit_asserts_remote_auto=False)

    result = target.execute(request())

    assert result["state"] == "REJECTED"
    assert "REMOTE_AUTO" in result["message"]
    assert robot.dispatch_count == 0


def test_unknown_witness_is_not_automatically_redispatched(tmp_path) -> None:
    robot = FakeLegacyRobot()

    def pick_without_tool_witness(**kwargs):
        robot.dispatch_count += 1
        kwargs["precheck"]()
        robot.variables[SOURCE_SENSOR] = False
        return {
            "success": True,
            "status": "completed",
            "source_sensor_variable": SOURCE_SENSOR,
            "completion_value": 1,
        }

    robot._submit_robot_task = pick_without_tool_witness  # type: ignore[method-assign]
    target = gateway(tmp_path, robot)

    first = target.execute(request())
    second = target.execute(request())
    blocked_new = target.execute(request(command_id="pick-002", sequence=2))

    assert first["state"] == "UNKNOWN"
    assert second == first
    assert blocked_new["state"] == "REJECTED"
    assert "未对账 UNKNOWN" in blocked_new["message"]
    assert robot.dispatch_count == 1


def test_reconcile_only_reobserves_unknown_witness(tmp_path) -> None:
    robot = FakeLegacyRobot()

    def pick_with_late_tool_witness(**kwargs):
        robot.dispatch_count += 1
        kwargs["precheck"]()
        robot.variables[SOURCE_SENSOR] = False
        return {
            "success": True,
            "status": "completed",
            "source_sensor_variable": SOURCE_SENSOR,
            "completion_value": 1,
        }

    robot._submit_robot_task = pick_with_late_tool_witness  # type: ignore[method-assign]
    target = gateway(tmp_path, robot)
    assert target.execute(request())["state"] == "UNKNOWN"

    robot.variables[TOOL_PAYLOAD_SENSOR_VARIABLE] = True
    reconciled = target.reconcile("pick-001")

    assert reconciled["state"] == "SUCCEEDED"
    assert robot.dispatch_count == 1


def test_monotonic_sequence_rejects_late_smaller_command(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot)
    assert target.execute(request(sequence=2))["state"] == "SUCCEEDED"
    robot.variables[SOURCE_SENSOR] = True
    robot.variables[TOOL_PAYLOAD_SENSOR_VARIABLE] = False

    stale = target.execute(request(command_id="pick-002", sequence=1))

    assert stale["state"] == "REJECTED"
    assert "未单调递增" in stale["message"]
    assert robot.dispatch_count == 1


def test_pick_then_place_use_distinct_ids_and_increasing_sequence(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot)
    assert target.execute(request())["state"] == "SUCCEEDED"

    placed = target.execute(
        StandardRobotRequest(
            kind="place",
            command_id="place-001",
            site="s07_process_warehouse/P01",
            program_version="szlab-mixer-plc@0730",
            point_set_version="szlab-mixer-points@0730",
            payload_profile="powder_container@v1",
            source_boot_id="scheduler-boot-001",
            monotonic_sequence=2,
            material_context={
                "resource": {"uuid": "powder-001"},
                "target_device": "s07",
            },
        )
    )

    assert placed["state"] == "SUCCEEDED"
    assert robot.dispatch_count == 2
