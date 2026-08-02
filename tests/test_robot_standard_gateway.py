from __future__ import annotations

from szlab_poly_studio.devices.szlab_mixer_robot.robot_tasks import (
    ROBOT_HOME_VARIABLE,
    ROBOT_WRITE_ALLOWED_VARIABLE,
)
from szlab_poly_studio.devices.szlab_mixer_robot.standard_gateway import (
    TOOL_PAYLOAD_SENSOR_VARIABLE,
    StandardRobotRequest,
    SZLabStandardRobotGateway,
)

SOURCE_SENSOR = "source-present"
TARGET_SENSOR = "target-present"


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

    def _run_pick_from_s071(self, position: str = "1-1"):
        self.dispatch_count += 1
        self.variables[SOURCE_SENSOR] = False
        self.variables[TOOL_PAYLOAD_SENSOR_VARIABLE] = True
        return {
            "success": True,
            "message": "legacy pick complete",
            "status": "completed",
            "position": position,
            "source_sensor_variable": SOURCE_SENSOR,
            "completion_value": 1,
        }

    def _run_place_to_s072(self, product_type: int = 1, position: int = 1):
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
        skill_id="pick_from_s071",
        program_version="szlab-mixer-plc@0730",
        point_set_version="szlab-mixer-points@0730",
        payload_profile="powder_container@v1",
        source_boot_id="scheduler-boot-001",
        monotonic_sequence=sequence,
        parameters={"position": "1-1"},
        material_context={
            "resource": {"uuid": material_id},
            "source_device": "powder-stack",
            "target_device": "s07",
        },
    )


def test_standard_pick_reuses_legacy_plc_handshake_and_is_idempotent(tmp_path) -> None:
    robot = FakeLegacyRobot()
    target = gateway(tmp_path, robot)

    first = target.execute(request())
    second = target.execute(request())

    assert first["state"] == "SUCCEEDED"
    assert second == first
    assert robot.dispatch_count == 1


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

    def pick_without_tool_witness(position: str = "1-1"):
        robot.dispatch_count += 1
        robot.variables[SOURCE_SENSOR] = False
        return {
            "success": True,
            "status": "completed",
            "source_sensor_variable": SOURCE_SENSOR,
            "completion_value": 1,
        }

    robot._run_pick_from_s071 = pick_without_tool_witness  # type: ignore[method-assign]
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

    def pick_with_late_tool_witness(position: str = "1-1"):
        robot.dispatch_count += 1
        robot.variables[SOURCE_SENSOR] = False
        return {
            "success": True,
            "status": "completed",
            "position": position,
            "source_sensor_variable": SOURCE_SENSOR,
            "completion_value": 1,
        }

    robot._run_pick_from_s071 = pick_with_late_tool_witness  # type: ignore[method-assign]
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
            skill_id="place_to_s072",
            program_version="szlab-mixer-plc@0730",
            point_set_version="szlab-mixer-points@0730",
            payload_profile="powder_container@v1",
            source_boot_id="scheduler-boot-001",
            monotonic_sequence=2,
            parameters={"product_type": 1, "position": 1},
            material_context={
                "resource": {"uuid": "powder-001"},
                "target_device": "s07",
            },
        )
    )

    assert placed["state"] == "SUCCEEDED"
    assert robot.dispatch_count == 2
