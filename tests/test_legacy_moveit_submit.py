"""Legacy submit_* entry points route to MoveIt under moveit_sim."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_mixer_robot.legacy_to_moveit_sites import (
    resolve_legacy_moveit_site,
)
from szlab_poly_studio.devices.szlab_mixer_robot.moveit_execution import (
    SZLabMoveItExecutionAdapter,
)


class _RecordingMoveItClient:
    def __init__(self) -> None:
        self.dispatch_count = 0
        self.writes_attempted = 0
        self.positions = (0.0,) * 7

    def ready(self) -> bool:
        return True

    def wait_until_ready(self, timeout_sec: float = 180.0) -> bool:
        del timeout_sec
        return self.ready()

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


class _InjectedPLC:
    def __init__(self) -> None:
        self.writes: list[tuple[str, Any]] = []
        self.reads: list[str] = []

    def read_variable(self, node_name: str, use_cache: bool = True) -> Any:
        self.reads.append(node_name)
        return True

    def write_variable(self, node_name: str, value: Any) -> bool:
        self.writes.append((node_name, value))
        return True


SITE_TARGETS = {
    "s06_process_warehouse/S061": {
        "pick": [
            [0.1, 0.0, -0.3, 0.6, 0.0, 0.2, 0.0],
            [0.15, 0.0, -0.25, 0.55, 0.0, 0.2, 0.0],
        ],
        "place": [
            [0.15, 0.0, -0.25, 0.55, 0.0, 0.2, 0.0],
            [0.1, 0.0, -0.3, 0.6, 0.0, 0.2, 0.0],
        ],
    },
    "s04_process_warehouse/S041": {
        "place": [
            [0.2, -0.1, -0.3, 0.5, 0.0, 0.2, 0.0],
            [0.25, -0.1, -0.35, 0.55, 0.0, 0.2, 0.0],
        ],
        "pick": [
            [0.25, -0.1, -0.35, 0.55, 0.0, 0.2, 0.0],
            [0.2, -0.1, -0.3, 0.5, 0.0, 0.2, 0.0],
        ],
    },
}

JOINT_NAMES = (
    "arm_base_joint",
    "cr7_joint_1",
    "cr7_joint_2",
    "cr7_joint_3",
    "cr7_joint_4",
    "cr7_joint_5",
    "cr7_joint_6",
)


def _moveit_robot(tmp_path, client: _RecordingMoveItClient) -> SzlabMixerRobotDevice:
    transport = _InjectedPLC()
    adapter = SZLabMoveItExecutionAdapter(
        client,
        site_targets=SITE_TARGETS,
        joint_names=JOINT_NAMES,
        binding_version="moveit-test@v1",
        simulation_only=True,
    )
    device = SzlabMixerRobotDevice(
        plc_gateway=transport,
        standard_execution_backend="moveit_sim",
        standard_execution_adapter=adapter,
        standard_journal_path=str(tmp_path / "robot-commands.sqlite3"),
        standard_program_version="szlab-mixer-moveit-sim@v1",
        standard_point_set_version="szlab-mixer-moveit-sim-demo@v1",
        standard_actions_enabled=True,
        standard_moveit_site_targets=SITE_TARGETS,
    )
    device._plc_transport_for_test = transport  # type: ignore[attr-defined]
    job_uuid = str(uuid4())
    device._standard_gateway_config["execution_identity_provider"] = lambda: {
        "node_job_uuid": job_uuid,
        "task_uuid": str(uuid4()),
    }
    return device


def test_resolve_legacy_moveit_sites_for_demo_stations() -> None:
    s06 = resolve_legacy_moveit_site(station="S06", task="place")
    assert s06.target_site == "s06_process_warehouse/S061"
    assert s06.payload_profile == "beaker_500ml@v1"

    s04 = resolve_legacy_moveit_site(station="S04", task="place", position=1)
    assert s04.target_site == "s04_process_warehouse/S041"

    with pytest.raises(ValueError, match="尚未映射"):
        resolve_legacy_moveit_site(station="S08", task="place")


def test_moveit_submit_place_to_s06_does_not_write_plc(tmp_path) -> None:
    client = _RecordingMoveItClient()
    device = _moveit_robot(tmp_path, client)
    transport: _InjectedPLC = device._plc_transport_for_test  # type: ignore[attr-defined]

    result = device.submit_place_to_s06()

    assert result["success"] is True
    assert result["execution_backend"] == "moveit_sim"
    assert result["target_site"] == "s06_process_warehouse/S061"
    assert result["inventory_commit_allowed"] is False
    assert client.dispatch_count >= 1
    assert transport.writes == []
    assert transport.reads == []


def test_moveit_submit_place_to_s04_uses_position_site(tmp_path) -> None:
    client = _RecordingMoveItClient()
    device = _moveit_robot(tmp_path, client)

    result = device.submit_place_to_s04(position=1, sample_id="demo")

    assert result["success"] is True
    assert result["target_site"] == "s04_process_warehouse/S041"
    assert result["position"] == 1
    assert client.dispatch_count >= 1


def test_moveit_submit_fails_closed_without_site_targets(tmp_path) -> None:
    client = _RecordingMoveItClient()
    transport = _InjectedPLC()
    adapter = SZLabMoveItExecutionAdapter(
        client,
        site_targets={},
        joint_names=JOINT_NAMES,
        binding_version="moveit-test@v1",
        simulation_only=True,
    )
    device = SzlabMixerRobotDevice(
        plc_gateway=transport,
        standard_execution_backend="moveit_sim",
        standard_execution_adapter=adapter,
        standard_journal_path=str(tmp_path / "empty-targets.sqlite3"),
        standard_actions_enabled=True,
    )
    device._standard_gateway_config["execution_identity_provider"] = lambda: {
        "node_job_uuid": str(uuid4()),
        "task_uuid": str(uuid4()),
    }

    result = device.submit_pick_from_s06()

    assert result["success"] is False
    assert "MoveIt" in result["message"] or "点位" in result["message"]
    assert client.dispatch_count == 0
    assert transport.writes == []
