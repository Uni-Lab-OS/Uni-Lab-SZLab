from __future__ import annotations

import inspect
from typing import Any

import pytest
from unilabos.registry.decorators import action

from szlab_poly_studio.common import action_logging
from szlab_poly_studio.common.action_logging import install_action_logging
from szlab_poly_studio.common.plc_gateway import PLCActionGateway
from szlab_poly_studio.devices.s1_workstation.device import S1Workstation
from szlab_poly_studio.devices.szlab_mixer_photoshotting.device import (
    SzlabMixerPhotoShottingDevice,
)
from szlab_poly_studio.devices.szlab_mixer_pipetting_station.device import (
    SzlabMixerPipettingStationDevice,
)
from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_robot.device import SzlabMixerRobotDevice
from szlab_poly_studio.devices.szlab_mixer_stirrer.device import (
    SzlabMixerMagneticStirrerDevice,
)
from szlab_poly_studio.devices.szlab_poly_plc.device import SZLabPolyPLCDevice, wait_variable_equal
from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
    SZLabS07SolidAdditionDevice,
)
from szlab_poly_studio.devices.szlab_s08_cap_station.device import (
    SZLabS08CapStationDevice,
)


class _ObservableDevice:
    @action(description="测试成功动作")
    def succeed(self, value: int, password: str = "") -> dict[str, Any]:
        return {"success": True, "message": f"value={value}", "password": password}

    @action(description="测试失败动作")
    def reject(self, reason: str) -> dict[str, Any]:
        return {"success": False, "message": reason, "status": "rejected"}

    @action(description="测试异常动作")
    def crash(self) -> dict[str, Any]:
        raise TimeoutError("PLC response timeout")


install_action_logging(_ObservableDevice)


def test_every_szlab_action_is_wrapped_for_observability() -> None:
    device_classes = [
        SZLabPolyPLCDevice,
        SzlabMixerRobotDevice,
        SzlabMixerPumpDevice,
        SZLabS07SolidAdditionDevice,
        SZLabS08CapStationDevice,
        SzlabMixerPipettingStationDevice,
        SzlabMixerPhotoShottingDevice,
        SzlabMixerMagneticStirrerDevice,
        S1Workstation,
    ]
    actions = [
        value
        for device_class in device_classes
        for value in device_class.__dict__.values()
        if callable(value) and hasattr(value, "_action_registry_meta")
    ]

    assert len(actions) == 91
    assert all(getattr(value, "__szlab_action_traced__", False) for value in actions)


def _capture_logs(monkeypatch: pytest.MonkeyPatch, logger: Any) -> tuple[list[str], list[str], list[str]]:
    infos: list[str] = []
    errors: list[str] = []
    debugs: list[str] = []
    monkeypatch.setattr(logger, "info", lambda message: infos.append(str(message)))
    monkeypatch.setattr(logger, "error", lambda message: errors.append(str(message)))
    monkeypatch.setattr(logger, "debug", lambda message: debugs.append(str(message)))
    return infos, errors, debugs


def test_action_logging_reports_start_success_failure_and_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infos, errors, _debugs = _capture_logs(monkeypatch, action_logging.logger)
    device = _ObservableDevice()

    assert device.succeed(7, password="do-not-log")["success"] is True
    assert device.reject("station not ready")["success"] is False

    assert any("[SZLAB-ACTION] START" in message and "value" in message for message in infos)
    assert any("[SZLAB-ACTION] SUCCESS" in message and "value=7" in message for message in infos)
    assert any(
        "[SZLAB-ACTION] FAIL" in message and "station not ready" in message
        for message in errors
    )
    assert all("do-not-log" not in message for message in [*infos, *errors])
    assert any("'password': '***'" in message for message in infos)


def test_action_logging_reports_exception_and_preserves_action_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _infos, errors, _debugs = _capture_logs(monkeypatch, action_logging.logger)

    with pytest.raises(TimeoutError, match="PLC response timeout"):
        _ObservableDevice().crash()

    assert any(
        "[SZLAB-ACTION] FAIL" in message
        and "TimeoutError: PLC response timeout" in message
        for message in errors
    )
    assert hasattr(_ObservableDevice.succeed, "_action_registry_meta")
    assert list(inspect.signature(_ObservableDevice.succeed).parameters) == [
        "self",
        "value",
        "password",
    ]


class _SequenceReader:
    def __init__(self, values: list[Any]) -> None:
        self.values = list(values)
        self.index = 0

    def read_variable(self, variable_name: str, use_cache: bool = False) -> Any:
        del variable_name, use_cache
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        if isinstance(value, Exception):
            raise value
        return value


def test_wait_logging_reports_observed_values_success_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import szlab_poly_studio.devices.szlab_poly_plc.device as plc_module

    infos, errors, _debugs = _capture_logs(monkeypatch, plc_module.logger)

    assert wait_variable_equal(
        _SequenceReader([False, False, True]),
        "S06加工完成",
        True,
        timeout=1.0,
        interval=0.0,
    )
    assert not wait_variable_equal(
        _SequenceReader([False]),
        "S06加工完成",
        True,
        timeout=0.0,
        interval=0.0,
    )

    assert any("[SZLAB-PLC-WAIT] START" in message for message in infos)
    assert any(
        "[SZLAB-PLC-WAIT] OBSERVED" in message and "actual=False" in message
        for message in infos
    )
    assert any("[SZLAB-PLC-WAIT] SUCCESS" in message for message in infos)
    assert any(
        "[SZLAB-PLC-WAIT] TIMEOUT" in message and "last_actual=False" in message
        for message in errors
    )


class _FakeRosNode:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def call_device_action(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        if self.error is not None:
            raise self.error
        return True


def test_plc_gateway_logs_operation_arguments_and_failure_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import szlab_poly_studio.common.plc_gateway as gateway_module

    infos, errors, _debugs = _capture_logs(monkeypatch, gateway_module.logger)
    gateway = PLCActionGateway(_FakeRosNode())
    assert gateway.write_variable("S06工艺选择", 1)

    failing_gateway = PLCActionGateway(_FakeRosNode(TimeoutError("downstream timeout")))
    with pytest.raises(TimeoutError, match="downstream timeout"):
        failing_gateway.write_variable("S06参数写入完成", True)

    assert any(
        "[SZLAB-PLC-CALL] START" in message
        and "write_variable" in message
        and "S06工艺选择" in message
        for message in infos
    )
    assert any(
        "[SZLAB-PLC-CALL] FAIL" in message
        and "TimeoutError: downstream timeout" in message
        and "S06参数写入完成" in message
        for message in errors
    )
