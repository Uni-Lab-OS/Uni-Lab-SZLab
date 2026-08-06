"""S04 磁搅动作前置条件（ActionPrecondition）合同回归。"""

from __future__ import annotations

from unilabos.registry.decorators import get_action_meta

from szlab_poly_studio.devices.szlab_mixer_stirrer.device import (
    SzlabMixerMagneticStirrerDevice,
)


class MemoryGateway:
    def __init__(self, values: dict[str, bool]):
        self.values = values
        self.events: list[tuple[str, str]] = []

    def read_variable(self, name: str, use_cache: bool = False) -> bool:
        del use_cache
        self.events.append(("read", name))
        return self.values[name]


def test_run_stirring_declares_fail_fast_material_presence_contract() -> None:
    metadata = get_action_meta(SzlabMixerMagneticStirrerDevice.run_stirring)
    assert metadata is not None
    assert metadata["preconditions"] == [
        {
            "id": "material_present",
            "parameter": "position",
            "properties": {
                "1": "material_present_position_1",
                "2": "material_present_position_2",
                "3": "material_present_position_3",
                "4": "material_present_position_4",
                "5": "material_present_position_5",
                "6": "material_present_position_6",
            },
            "sensors": {
                "1": "传感器状态_上位机[2].NO[10]",
                "2": "传感器状态_上位机[2].NO[11]",
                "3": "传感器状态_上位机[2].NO[12]",
                "4": "传感器状态_上位机[2].NO[13]",
                "5": "传感器状态_上位机[2].NO[14]",
                "6": "传感器状态_上位机[2].NO[15]",
            },
            "expected": True,
            "policy": "fail_fast",
            "max_age_seconds": 2.0,
            "message": "位置 {position} 无物料，无法开始磁搅",
        }
    ]


def test_material_presence_topics_publish_direct_sensor_observations() -> None:
    gateway = MemoryGateway(
        {
            "传感器状态_上位机[2].NO[10]": False,
            "传感器状态_上位机[2].NO[11]": True,
        }
    )
    device = SzlabMixerMagneticStirrerDevice(plc_gateway=gateway)

    assert device.get_material_present_position_1() is False
    assert device.get_material_present_position_2() is True
    assert gateway.events[-2:] == [
        ("read", "传感器状态_上位机[2].NO[10]"),
        ("read", "传感器状态_上位机[2].NO[11]"),
    ]
