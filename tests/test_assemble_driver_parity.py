from __future__ import annotations

import inspect
from typing import Any

import pytest

from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import (
    SzlabMixerPhotoShottingDevice,
)
from szlab_poly_studio.devices.szlab_mixer_photoshotting.sensors import S05_RESULT
from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import (
    SzlabMixerPipettingStationDevice,
)
from szlab_poly_studio.devices.szlab_mixer_pipetting_station.sensors import (
    S09_PARAM_WRITTEN_VAR,
    S09_PROCESS_DONE_VAR,
    S09_STATION_SENSORS,
    s09_remaining_volume_var,
)
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_mixer_stirrer.device import (
    SzlabMixerMagneticStirrerDevice,
)
from szlab_poly_studio.devices.szlab_poly_plc.device import wait_sensor_conditions
from szlab_poly_studio.devices.szlab_s08_cap_station.device import (
    CAP_CACHE_LENGTH,
    CAP_STORAGE_SLOT_SENSORS,
    SENSOR_CAP_STATION,
    S08ProcessType,
    SZLabS08CapStationDevice,
)

ASSEMBLE_ACTIONS = {
    "szlab_poly_plc": {
        "reconnect",
        "start_heart_beat",
        "stop_heart_beat",
        "check_variable_status",
        "write_variable_action",
        "get_sensor_group_status",
        "get_stack_status",
        "get_sensor_arrays",
        "set_s1_loading_request",
    },
    "szlab_mixer_stirrer": {"run_stirring"},
    "szlab_mixer_photoshotting": {"take_photo"},
    "szlab_mixer_pump": {"transfer_liquid", "run_solvent_addition"},
    "szlab_s07_solid_addition": {
        "scan_powder_cartridges",
        "read_s07_balance",
        "rotate_powder_cartridge_to_feed",
        "dose_powder",
    },
    "szlab_s08_cap_station": {"process_cap"},
    "szlab_mixer_pipetting_station": {
        "check_home_position",
        "read_home_positions",
        "prepare_liquid_station",
        "read_allow_process",
        "bind_sample_to_station",
        "release_station",
        "run_process",
        "add_liquid",
        "add_liquid_to_beaker",
        "run_liquid_workflow",
        "set_liquid_bottle_remaining_volume",
        "initialize_liquid_bottle_remaining_volumes",
        "read_balance",
        "get_pipetting_status",
    },
    "szlab_mixer_robot": {
        "submit_pick_from_s01",
        "submit_place_to_s02",
        "submit_pick_from_s02",
        "submit_place_to_s03",
        "submit_pick_from_s03",
        "submit_place_to_s04",
        "submit_pick_from_s04",
        "submit_place_to_s05",
        "submit_pick_from_s05",
        "submit_place_to_s06",
        "submit_pick_from_s06",
        "submit_place_to_s071",
        "submit_pick_from_s071",
        "submit_pick_from_s071_and_rotate_to_feed",
        "submit_place_to_s072",
        "submit_pick_from_s072",
        "submit_place_to_s08",
        "submit_pick_from_s08",
        "submit_pour_from_s08",
        "submit_place_to_s09",
        "submit_pick_from_s09",
        "submit_place_to_s10",
        "submit_pick_from_s10",
        "submit_place_to_s11",
        "submit_pick_from_s11",
        "last_submitted_task",
    },
}


def test_catalog_keeps_every_assemble_action(package_catalog) -> None:
    devices = {device.id: device for device in package_catalog.definitions.devices}
    for device_id, expected_actions in ASSEMBLE_ACTIONS.items():
        actual_actions = {action["name"] for action in devices[device_id].details["actions"]}
        assert expected_actions <= actual_actions, device_id


def test_assemble_compatible_action_parameters_remain_available() -> None:
    stirrer_params = inspect.signature(SzlabMixerMagneticStirrerDevice.run_stirring).parameters
    assert stirrer_params["position"].default == 1

    cap_params = inspect.signature(SZLabS08CapStationDevice.process_cap).parameters
    assert list(cap_params)[1:4] == ["工艺选择", "样品ID", "瓶盖暂存位"]
    assert cap_params["工艺选择"].default == 5

    pipetting_params = inspect.signature(SzlabMixerPipettingStationDevice.add_liquid).parameters
    assert list(pipetting_params)[1:3] == ["take_tip_box_index", "release_tip_box_index"]
    assert all(f"S09液体瓶{index}剩余液量" in pipetting_params for index in range(1, 6))


class MemoryGateway:
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values = dict(values or {})
        self.events: list[tuple[Any, ...]] = []
        self.writes: list[tuple[str, Any]] = []

    def read_variable(self, name: str, use_cache: bool = False) -> Any:
        del use_cache
        self.events.append(("read", name))
        return self.values.get(name, False)

    def read(self, name: str) -> Any:
        return self.read_variable(name, use_cache=False)

    def write_variable(self, name: str, value: Any) -> bool:
        self.events.append(("write", name, value))
        self.writes.append((name, value))
        self.values[name] = value
        return True

    def write(self, name: str, value: Any) -> None:
        self.write_variable(name, value)

    def wait_equal(self, name: str, expected: Any, timeout: float = 300.0, interval: float = 0.2) -> bool:
        del timeout, interval
        self.events.append(("wait", name, expected))
        return True

    wait_variable_equal = wait_equal

    def wait_variable_true(self, name: str, timeout: float = 300.0, interval: float = 0.2) -> bool:
        return self.wait_equal(name, True, timeout=timeout, interval=interval)

    def wait_new_cycle_done(self, name: str, timeout: float = 300.0, interval: float = 0.2) -> bool:
        del timeout, interval
        self.events.append(("wait_new_cycle_done", name))
        return True

    def wait_sensor_conditions(
        self,
        conditions: dict[str, bool],
        timeout: float = 300.0,
        interval: float = 0.2,
        context: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        del timeout, interval, context
        self.events.append(("wait_sensor_conditions", dict(conditions)))
        return True, dict(conditions)

    def check_variable_accessible(self, name: str) -> tuple[bool, str]:
        return True, name

    def get_opc_variable_metadata(self, name: str) -> tuple[str, str]:
        return name, name


def test_s04_restores_assemble_sensor_gates_and_clears_duration() -> None:
    gateway = MemoryGateway()
    device = SzlabMixerMagneticStirrerDevice(plc_gateway=gateway, timeout=0.01)

    result = device.run_stirring(position=1, duration=2)

    assert result["success"] is True
    assert ("wait", "传感器状态_上位机[2].NO[10]", True) in gateway.events
    assert ("wait", "S041磁搅状态", 1) in gateway.events
    assert ("wait_new_cycle_done", "S041加工完成") in gateway.events
    assert gateway.writes[-3:] == [
        ("磁搅时间设置_上位机[0]", 0),
        ("磁搅安全温度设置_上位机[0]", 0),
        ("S041参数写入完成", False),
    ]


def test_s05_waits_for_material_and_non_unknown_result(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = MemoryGateway({S05_RESULT: 0})
    result_codes = iter([0, 1])
    original_read = gateway.read_variable

    def read_variable(name: str, use_cache: bool = False) -> Any:
        if name == S05_RESULT:
            return next(result_codes)
        return original_read(name, use_cache=use_cache)

    gateway.read_variable = read_variable  # type: ignore[method-assign]
    monkeypatch.setattr("szlab_poly_studio.devices.szlab_mixer_photoshotting.device.time.sleep", lambda _: None)
    device = SzlabMixerPhotoShottingDevice(plc_gateway=gateway, timeout=0.1)

    result = device.take_photo(sample_id="sample")

    assert result["success"] is True
    material_waits = [event for event in gateway.events if event[:2] == ("wait", "传感器状态_上位机[3].NO[0]")]
    assert len(material_waits) == 2
    assert result["data"]["result"] == "OK"


def test_s08_chinese_process_entry_keeps_explicit_cap_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    device = SZLabS08CapStationDevice(plc_gateway=MemoryGateway())
    captured: dict[str, Any] = {}

    def open_cap(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(device, "_open_cap", open_cap)
    result = device.process_cap(工艺选择=5, 样品ID=[1, 2, 3], 瓶盖暂存位=4)

    assert result["success"] is True
    assert captured["process_type"] is S08ProcessType.OPEN_LIQUID_VIAL_100ML
    assert captured["cap_storage_slot"] == 4


def test_s08_open_process_checks_station_and_cap_slot_transition() -> None:
    device = SZLabS08CapStationDevice(plc_gateway=MemoryGateway())

    before, after = device._cap_sensor_conditions(S08ProcessType.OPEN_LIQUID_VIAL_100ML, 4)

    assert before == {SENSOR_CAP_STATION[2]: True, CAP_STORAGE_SLOT_SENSORS[4]: False}
    assert after == {SENSOR_CAP_STATION[2]: True, CAP_STORAGE_SLOT_SENSORS[4]: True}


def test_s08_material_wrappers_namespace_cap_tracking_by_container_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = SZLabS08CapStationDevice(plc_gateway=MemoryGateway())
    calls: list[dict[str, Any]] = []

    def process_cap(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"success": True, "message": "ok"}

    monkeypatch.setattr(device, "process_cap", process_cap)
    container = {"uuid": "container-001"}
    device.process_liquid_reagent_100ml_cap_with_material(
        container=container,
        operation="open",
        sample_id="sample-opc-001",
    )
    device.process_sample_vial_250ml_cap_with_material(
        container=container,
        operation="open",
        sample_id="sample-opc-001",
    )
    device.process_sample_vial_250ml_cap_with_material(
        container=container,
        operation="close",
        sample_id="sample-opc-001",
    )

    reagent_tracking_id = calls[0]["sample_id"]
    sample_vial_open_tracking_id = calls[1]["sample_id"]
    sample_vial_close_tracking_id = calls[2]["sample_id"]
    assert reagent_tracking_id != sample_vial_open_tracking_id
    assert sample_vial_open_tracking_id == sample_vial_close_tracking_id
    assert bytes(reagent_tracking_id).decode() == "R:sample-opc-001"
    assert bytes(sample_vial_open_tracking_id).decode() == "S:sample-opc-001"


def test_s08_namespaced_cap_tracking_stays_within_plc_cache_limit() -> None:
    device = SZLabS08CapStationDevice(plc_gateway=MemoryGateway())

    first = device._cap_tracking_sample_id("样品-" * 20, namespace="S")
    second = device._cap_tracking_sample_id("样品-" * 20, namespace="S")
    reagent = device._cap_tracking_sample_id("样品-" * 20, namespace="R")

    assert first == second
    assert first != reagent
    assert len(first) == CAP_CACHE_LENGTH


def test_s09_holds_parameter_signal_until_done_and_checks_material() -> None:
    gateway = MemoryGateway(
        {
            S09_PROCESS_DONE_VAR: 0,
            s09_remaining_volume_var(1): 100.0,
        }
    )
    device = SzlabMixerPipettingStationDevice(plc_gateway=gateway, timeout=0.01)

    result = device.run_process(
        process=7,
        liquid_bottle_index=1,
        aspirate_volume=10,
        skip_level_check=True,
    )

    assert result["success"] is True
    params_on = gateway.events.index(("write", S09_PARAM_WRITTEN_VAR, True))
    done = gateway.events.index(("wait", S09_PROCESS_DONE_VAR, 7))
    params_off = gateway.events.index(("write", S09_PARAM_WRITTEN_VAR, False))
    assert params_on < done < params_off
    sensor_waits = [event for event in gateway.events if event[0] == "wait_sensor_conditions"]
    assert sensor_waits == [
        ("wait_sensor_conditions", {S09_STATION_SENSORS[1]: True}),
        ("wait_sensor_conditions", {S09_STATION_SENSORS[1]: True}),
    ]


def test_shared_sensor_wait_is_bounded() -> None:
    gateway = MemoryGateway({"sensor": False})

    success, values = wait_sensor_conditions(
        gateway,
        {"sensor": True},
        timeout=0.0,
        interval=0.0,
    )

    assert success is False
    assert values == {"sensor": False}


def test_parallel_s071_action_reports_non_retryable_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = MemoryGateway()
    device = SzlabMixerRobotDevice(plc_gateway=gateway, timeout=0.01)
    monkeypatch.setattr(device, "_wait_sensor_conditions", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr(device, "_run_robot_handshake_precheck", lambda station: {"station": station})
    monkeypatch.setattr(device, "_run_s071_pick", lambda position: {"success": False, "message": "pick failed"})

    class FakeS07:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def _wait_plc_bool(self, *args: Any, **kwargs: Any) -> bool:
            return True

        def rotate_powder_cartridge_to_feed(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"success": True}

    monkeypatch.setattr(
        "szlab_poly_studio.devices.szlab_mixer_robot.robot_S07.SZLabS07SolidAdditionDevice",
        FakeS07,
    )

    result = device.submit_pick_from_s071_and_rotate_to_feed(position="1-1", load_position=2)

    assert result["success"] is False
    assert result["status"] == "partial_failure"
    assert "禁止自动重试" in result["message"]


def test_robot_waits_for_exact_task_and_verifies_post_sensor() -> None:
    gateway = MemoryGateway({"Robot_任务允许写入": True})
    device = SzlabMixerRobotDevice(plc_gateway=gateway, timeout=0.01, poll_interval=0.0)

    result = device.submit_place_to_s04(position=2)

    assert result["success"] is True
    assert ("wait", "Robot_任务完成", 7) in gateway.events
    assert result["sensor_precheck"]["conditions"] == {"传感器状态_上位机[2].NO[11]": False}
    assert result["sensor_postcheck"]["conditions"] == {"传感器状态_上位机[2].NO[11]": True}
