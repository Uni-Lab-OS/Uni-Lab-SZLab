from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from szlab_poly_studio.common.site_control_bindings import (
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
    CommandUnresolvedError,
    SZLabRobotCommandJournal,
    SZLabStandardRobotGateway,
    _payload_profile_for_resource,
)
from szlab_poly_studio.devices.szlab_mixer_robot.execution_backend import (
    MotionSequence,
    RobotCommand,
)
from szlab_poly_studio.devices.szlab_mixer_robot.moveit_execution import (
    SZLabMoveItExecutionAdapter,
)

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


class FakeMoveItClient:
    def __init__(self) -> None:
        self.dispatch_count = 0
        self.positions = (0.0,) * 7

    def ready(self) -> bool:
        return True

    def execute_joint_target(
        self,
        *,
        planning_group,
        joint_names,
        joint_positions,
    ) -> bool:
        assert planning_group == "arm"
        assert len(joint_names) == 7
        self.dispatch_count += 1
        self.positions = tuple(joint_positions)
        return True

    def current_joint_positions(self, joint_names):
        assert len(joint_names) == 7
        return self.positions


def moveit_adapter(client: FakeMoveItClient) -> SZLabMoveItExecutionAdapter:
    return SZLabMoveItExecutionAdapter(
        client,
        site_targets={
            "powder_container_warehouse/L1C1": {
                "pick": [
                    [0.10, 0.00, -0.30, 0.60, 0.00, 0.20, 0.00],
                    [0.15, 0.00, -0.25, 0.55, 0.00, 0.20, 0.00],
                ],
                "place": [
                    [0.15, 0.00, -0.25, 0.55, 0.00, 0.20, 0.00],
                    [0.10, 0.00, -0.30, 0.60, 0.00, 0.20, 0.00],
                ],
            }
        },
        joint_names=(
            "arm_base_joint",
            "eco65_joint_1",
            "eco65_joint_2",
            "eco65_joint_3",
            "eco65_joint_4",
            "eco65_joint_5",
            "eco65_joint_6",
        ),
        binding_version="moveit-test@v1",
        simulation_only=True,
    )


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


def request_for_adapter(adapter, **kwargs) -> StandardRobotRequest:
    return replace(
        request(**kwargs),
        backend_id=adapter.backend_id,
        hardware_profile_ref=adapter.hardware_profile_ref,
        hardware_profile_digest=adapter.hardware_profile_digest,
        execution_environment=adapter.capabilities.execution_environment,
    )


def test_payload_profile_uses_unilabos_resource_class_when_plr_category_is_generic() -> None:
    resource = SimpleNamespace(
        category="container",
        unilabos_extra={
            "unilabos_resource_class": "community.szlab_poly_studio.szlab_beaker_500ml",
        },
    )

    assert _payload_profile_for_resource(resource) == "beaker_500ml@v1"


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
    assert "ACCEPTED/RUNNING/UNKNOWN" in blocked_new["message"]
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


def test_moveit_adapter_uses_same_gateway_without_reading_plc_variables(tmp_path) -> None:
    class NoPLC:
        def _read_variable(self, *args, **kwargs):
            raise AssertionError("MoveIt Adapter 不得读取 PLC 变量")

    client = FakeMoveItClient()
    adapter = moveit_adapter(client)
    target = gateway(
        tmp_path,
        NoPLC(),
        execution_backend=adapter,
    )

    first = target.execute(request_for_adapter(adapter))
    replay = target.execute(request_for_adapter(adapter))

    assert first["state"] == "SUCCEEDED"
    assert replay == first
    assert client.dispatch_count == 2  # two approved segments, dispatched once each


def test_moveit_final_joint_mismatch_remains_unknown_and_is_not_resent(tmp_path) -> None:
    client = FakeMoveItClient()
    adapter = moveit_adapter(client)
    target = gateway(tmp_path, object(), execution_backend=adapter)

    original_current = client.current_joint_positions
    client.current_joint_positions = lambda joint_names: (9.0,) * 7  # type: ignore[method-assign]
    first = target.execute(request_for_adapter(adapter))
    replay = target.execute(request_for_adapter(adapter))
    client.current_joint_positions = original_current  # type: ignore[method-assign]

    assert first["state"] == "UNKNOWN"
    assert replay == first
    assert client.dispatch_count == 2


def test_robot_command_wire_shape_contains_no_site_material_or_transport_fields() -> None:
    command = RobotCommand(
        command_id="cmd-001",
        instruction=MotionSequence(
            planning_group="arm",
            joint_names=("j1", "j2"),
            joint_targets=((0.0, 0.0), (0.1, -0.1)),
        ),
        program_version="moveit-program@v1",
        point_set_version="moveit-points@v1",
        payload_profile="powder_container@v1",
    ).to_dict()
    serialized = str(command).lower()

    for forbidden in (
        "warehouse",
        "material",
        "site",
        "register",
        "presence_variable",
        "legacy_runner",
        "tcp_host",
        "ros_action",
    ):
        assert forbidden not in serialized


def test_observation_exception_becomes_unknown_and_fences_new_motion(tmp_path) -> None:
    client = FakeMoveItClient()
    adapter = moveit_adapter(client)
    adapter.observe = lambda command, receipt: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("observation exploded")
    )
    target = gateway(tmp_path, object(), execution_backend=adapter)

    first = target.execute(request_for_adapter(adapter))
    blocked = target.execute(
        request_for_adapter(adapter, command_id="pick-002", sequence=2)
    )

    assert first["state"] == "UNKNOWN"
    assert "观察/见证失败" in first["message"]
    assert blocked["state"] == "REJECTED"
    assert client.dispatch_count == 2


def test_verifier_exception_becomes_unknown_and_fences_new_motion(tmp_path) -> None:
    client = FakeMoveItClient()
    adapter = moveit_adapter(client)
    adapter.verify = lambda action, execution: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("verification exploded")
    )
    target = gateway(tmp_path, object(), execution_backend=adapter)

    first = target.execute(request_for_adapter(adapter))
    blocked = target.execute(
        request_for_adapter(adapter, command_id="pick-002", sequence=2)
    )

    assert first["state"] == "UNKNOWN"
    assert blocked["state"] == "REJECTED"
    assert client.dispatch_count == 2


def test_moveit_rejects_non_finite_target_and_tolerance() -> None:
    client = FakeMoveItClient()
    try:
        SZLabMoveItExecutionAdapter(
            client,
            site_targets={},
            joint_names=("j1",),
            binding_version="test@v1",
            simulation_only=True,
            final_joint_tolerance=float("nan"),
        )
    except ValueError as exc:
        assert "有限正数" in str(exc)
    else:
        raise AssertionError("NaN tolerance 必须 fail-closed")

    try:
        MotionSequence(
            planning_group="arm",
            joint_names=("j1",),
            joint_targets=((float("inf"),),),
        )
    except ValueError as exc:
        assert "有限数" in str(exc)
    else:
        raise AssertionError("Inf joint target 必须 fail-closed")


def test_accept_checks_unresolved_fence_inside_one_sqlite_transaction(tmp_path) -> None:
    path = tmp_path / "shared.sqlite3"
    first = SZLabRobotCommandJournal(path)
    second = SZLabRobotCommandJournal(path)

    created, _ = first.accept(request(command_id="pick-a", sequence=1), "edge-a")
    assert created is True
    with pytest.raises(CommandUnresolvedError):
        second.accept(request(command_id="pick-b", sequence=2), "edge-b")


def test_simulation_request_contains_fixture_not_production_resource(tmp_path) -> None:
    client = FakeMoveItClient()
    target = gateway(
        tmp_path,
        object(),
        execution_backend=moveit_adapter(client),
    )

    result = target.execute_simulation_site(
        kind="pick",
        target_site="powder_container_warehouse/L1C1",
        payload_profile="powder_container@v1",
        fixture_id="fixture-001",
    )
    record = target.journal.get(result["command_id"])

    assert result["state"] == "SUCCEEDED"
    assert result["inventory_commit_allowed"] is False
    assert record is not None
    assert record.request["material_context"]["simulation_fixture_id"] == "fixture-001"
    assert "resource" not in record.request["material_context"]


def test_completed_command_cannot_replay_across_hardware_profiles(tmp_path) -> None:
    robot = FakeLegacyRobot()
    plc_gateway = gateway(tmp_path, robot)
    assert plc_gateway.execute(request())["state"] == "SUCCEEDED"

    client = FakeMoveItClient()
    adapter = moveit_adapter(client)
    moveit_gateway = gateway(
        tmp_path,
        object(),
        execution_backend=adapter,
    )
    replay = moveit_gateway.execute(request_for_adapter(adapter))

    assert replay["state"] == "REJECTED"
    assert "跨 profile" in replay["message"]
    assert client.dispatch_count == 0
