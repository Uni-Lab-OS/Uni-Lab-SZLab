"""AI4C PLC 与机械臂外部设备包。"""

from typing import TYPE_CHECKING

__all__ = ["AI4CPLCDevice", "AI4CRobotArmDevice"]

if TYPE_CHECKING:
    from ai4c_robot.plc import AI4CPLCDevice
    from ai4c_robot.robot import AI4CRobotArmDevice


def __getattr__(name: str):
    """延迟加载设备类，避免注册表并行导入模块时产生模块锁死锁。"""
    if name == "AI4CPLCDevice":
        from ai4c_robot.plc import AI4CPLCDevice

        return AI4CPLCDevice
    if name == "AI4CRobotArmDevice":
        from ai4c_robot.robot import AI4CRobotArmDevice

        return AI4CRobotArmDevice
    raise AttributeError(name)
