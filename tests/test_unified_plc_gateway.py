from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from szlab_poly_studio.common.plc_gateway import (
    PLCActionGateway,
    PLCVariableTransport,
    UnifiedPLCGatewayMixin,
)
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
from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
    SZLabS07SolidAdditionDevice,
)
from szlab_poly_studio.devices.szlab_s08_cap_station.device import (
    SZLabS08CapStationDevice,
)


class FakeROSNode:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call_device_action(
        self,
        device_id: str,
        action_name: str,
        action_kwargs: dict[str, Any],
        **options: Any,
    ) -> Any:
        self.calls.append(
            {
                "device_id": device_id,
                "action_name": action_name,
                "action_kwargs": action_kwargs,
                "options": options,
            }
        )
        if action_name == "read_variable":
            return 42
        if action_name == "get_variables":
            return {"A": {"success": True, "value": 42}}
        if action_name == "get_opc_variable_metadata":
            return ["A", "ns=4;s=上位机通讯|A"]
        if action_name == "check_variable_accessible":
            return [True, "ns=4;s=上位机通讯|A"]
        return True


def test_plc_action_gateway_delegates_to_the_single_plc_device() -> None:
    node = FakeROSNode()
    gateway = PLCActionGateway(
        node,
        plc_device_id="szlab_poly_plc",
        command_timeout=12.0,
        server_wait_timeout=3.0,
    )
    assert isinstance(gateway, PLCVariableTransport)

    assert gateway.read_variable("A", use_cache=False) == 42
    assert gateway.write_variable("A", 7) is True
    assert gateway.get_variables(["A"], use_cache=False) == {
        "A": {"success": True, "value": 42}
    }
    assert gateway.get_opc_variable_metadata("A") == (
        "A",
        "ns=4;s=上位机通讯|A",
    )
    assert gateway.check_variable_accessible("A") == (
        True,
        "ns=4;s=上位机通讯|A",
    )

    assert {call["device_id"] for call in node.calls} == {"szlab_poly_plc"}
    assert [call["action_name"] for call in node.calls] == [
        "read_variable",
        "write_variable",
        "get_variables",
        "get_opc_variable_metadata",
        "check_variable_accessible",
    ]
    assert node.calls[0]["action_kwargs"] == {
        "node_name": "A",
        "use_cache": False,
    }


@pytest.mark.parametrize(
    "device_class",
    [
        SzlabMixerRobotDevice,
        SzlabMixerMagneticStirrerDevice,
        SzlabMixerPhotoShottingDevice,
        SzlabMixerPumpDevice,
        SZLabS07SolidAdditionDevice,
        SZLabS08CapStationDevice,
        SzlabMixerPipettingStationDevice,
    ],
)
def test_every_plc_attached_device_uses_the_unified_gateway(
    device_class: type,
) -> None:
    device = device_class(auto_connect=False)

    assert isinstance(device, UnifiedPLCGatewayMixin)
    assert device.plc_device_id == "szlab_poly_plc"
    assert device._plc_gateway is None

    ros_node = FakeROSNode()
    device.post_init(ros_node)

    assert isinstance(device._plc_gateway, PLCActionGateway)
    assert getattr(device, "_client", device._plc_gateway) is device._plc_gateway
    assert ros_node.calls == []


def test_moveit_sim_profile_cannot_use_legacy_plc_read_or_write() -> None:
    class InjectedPLC:
        def __init__(self) -> None:
            self.writes: list[tuple[str, Any]] = []

        def read_variable(self, node_name: str, use_cache: bool = True) -> Any:
            return True

        def write_variable(self, node_name: str, value: Any) -> bool:
            self.writes.append((node_name, value))
            return True

    transport = InjectedPLC()
    device = SzlabMixerRobotDevice(
        plc_gateway=transport,
        standard_execution_backend="moveit_sim",
    )

    with pytest.raises(RuntimeError, match="禁止 legacy PLC 动作"):
        device._write_variable("任务号", 1)
    with pytest.raises(RuntimeError, match="禁止 legacy PLC 动作"):
        device._read_variable("Robot_Home", use_cache=False)
    assert transport.writes == []

    injected_moveit = SzlabMixerRobotDevice(
        plc_gateway=transport,
        standard_execution_adapter=SimpleNamespace(backend_id="szlab.moveit"),
    )
    with pytest.raises(RuntimeError, match="禁止 legacy PLC 动作"):
        injected_moveit._write_variable("任务号", 2)
    assert transport.writes == []
