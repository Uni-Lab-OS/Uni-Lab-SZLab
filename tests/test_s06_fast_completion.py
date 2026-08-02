from __future__ import annotations

from typing import Any

from szlab_poly_studio.devices.szlab_mixer_pump.device import SzlabMixerPumpDevice
from szlab_poly_studio.devices.szlab_mixer_pump.sensors import (
    S06_DONE_VAR,
    S06_PARAM_WRITTEN_VAR,
)


class FastCompletionGateway:
    """模拟参数写入后、Edge 开始等待前已经完成的快速 PLC/仿真器。"""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {S06_DONE_VAR: False}
        self.waits: list[tuple[str, Any]] = []

    def check_variable_accessible(self, name: str) -> tuple[bool, str]:
        return True, f"ns=4;s=上位机通讯|{name}"

    def write(self, name: str, value: Any) -> None:
        self.values[name] = value
        if name == S06_PARAM_WRITTEN_VAR and value is True:
            # 握手器在跨设备 wait 调用注册前就完成本轮动作。
            self.values[S06_DONE_VAR] = True
        elif name == S06_PARAM_WRITTEN_VAR and value is False:
            self.values[S06_DONE_VAR] = False

    def read(self, name: str) -> Any:
        return self.values.get(name, False)

    def wait_variable_equal(
        self,
        name: str,
        expected: Any,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        del timeout, interval
        self.waits.append((name, expected))
        return self.read(name) == expected

    def wait_new_cycle_done(
        self,
        name: str,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        del timeout, interval
        # 旧实现会把已经到达的本轮 True 当作残留信号并等待 False，形成死锁。
        return not bool(self.read(name))


def test_s06_accepts_completion_that_arrives_before_wait_registration() -> None:
    gateway = FastCompletionGateway()
    device = SzlabMixerPumpDevice(opcua_client=gateway, timeout=1.0)

    result = device._execute_s06_addition(1, 8, require_allow=False)

    assert result["success"] is True
    assert gateway.waits == [
        (S06_DONE_VAR, False),
        (S06_DONE_VAR, True),
    ]
