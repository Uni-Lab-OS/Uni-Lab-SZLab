#!/usr/bin/env python3
"""独立运行的 SZLab OPC UA 工作流握手仿真器。

用途：

1. ``list``：列出仓库中全部工作流的 PLC/配置先决条件，不连接服务器。
2. ``check``：只读检查远端 OPC UA 中可自动判定的先决条件。
3. ``serve``：写入测试先决条件，并监听 PC→PLC 信号，模拟 PLC 握手。

当前覆盖 ``workflows`` 目录中全部 13 个工作流、23 个唯一动作调用：

- ``szlab_mixer_robot.submit_place_to_s04``（机器人任务号 7）
- ``szlab_mixer_stirrer.run_stirring``
- ``szlab_mixer_robot.submit_pick_from_s04``（机器人任务号 8）
- ``szlab_mixer_photoshotting.take_photo``（当前为只读完成信号）
- ``szlab_mixer_pump.run_solvent_addition``
- ``szlab_mixer_robot.submit_place_to_s06``（机器人任务号 11）
- ``szlab_mixer_robot.submit_pick_from_s06``（机器人任务号 12）
- ``szlab_mixer_robot.submit_place_to_s071``（机器人任务号 13）
- ``szlab_mixer_robot.submit_place_to_s072``（机器人任务号 15）
- ``szlab_mixer_robot.submit_pick_from_s072``（机器人任务号 16）
- ``szlab_s07_solid_addition.scan_powder_cartridges``（S07 工艺 1）
- ``szlab_s07_solid_addition.rotate_powder_cartridge_to_feed``（S07 工艺 2）
- ``szlab_s07_solid_addition.dose_powder``（S07 工艺 3）
- ``szlab_s08_cap_station.process_cap_with_sample_parts``（S08 工艺 1-6）
- ``szlab_mixer_pipetting_station.prepare_liquid_station``
- ``szlab_mixer_pipetting_station.bind_sample_to_station``
- ``szlab_mixer_pipetting_station.add_liquid``（内部工艺 5→7→8→6）
- ``szlab_mixer_pipetting_station.release_station``
- ``szlab_poly_plc.get_stack_status``（只读，无动态握手）
- ``szlab_mixer_robot.pick_beaker_from_s03``（机器人任务号 6）
- ``szlab_mixer_robot.place_beaker_to_s06``（机器人任务号 11）
- ``szlab_mixer_pump.add_solvent_to_beaker``
- ``szlab_mixer_robot.pick_beaker_from_s06``（机器人任务号 12）

建议用 ``--workflow WORKFLOW_ID`` 定向运行单个工作流；选择
``s06_robot_workflow`` 时会让 S06 烧杯传感器从 False 开始，并由任务
11/12 的握手周期切换；选择 ``szlab_s09_pipetting_workflow`` 时会初始化
S09 工位和液体余量，并响应全部内部工艺。原有
``--s06-robot-workflow``、``--s09-pipetting-workflow`` 参数仍作为兼容别名保留。

本文件不依赖 Uni-Lab-OS 进程，也不创建 OPC UA 节点；它只连接由 CSV
创建好的节点。请使用包含 ``python-opcua`` 的 unilab Python 环境运行。
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Protocol

DEFAULT_URL = "opc.tcp://opcua.ideawit.com:4855/xuse_sim"
DEFAULT_NODE_PREFIX = "ns=4;s=上位机通讯|"

ROBOT_HOME = "Robot_Home"
ROBOT_WRITE_ALLOWED = "Robot_任务允许写入"
ROBOT_WRITE_DONE = "Robot_任务写入完成"
ROBOT_TASK_NUMBER = "任务号"
ROBOT_TASK_COMPLETE = "Robot_任务完成"
S04_ROBOT_POSITION = "S04取放料编号"
S03_BEAKER_SENSOR = "传感器状态_上位机[0].NO[6]"

S05_DONE = "S05加工完成"
S05_RESULT = "S05拍照结果"

S06_READY = "S06准备信号"
S06_ALLOW = "S06允许加工"
S06_PROCESS = "S06工艺选择"
S06_PARAMS_WRITTEN = "S06参数写入完成"
S06_DONE = "S06加工完成"
S06_BEAKER_SENSOR = "传感器状态_上位机[3].NO[1]"
S06_STORAGE_BOTTLE_SENSOR = {
    1: "传感器状态_上位机[4].NO[12]",
    2: "传感器状态_上位机[5].NO[1]",
}

S071_ROBOT_POSITION = "S071取放料编号"
S071_SENSOR_BY_SLOT = {
    1: "传感器状态_上位机[3].NO[8]",
    2: "传感器状态_上位机[3].NO[9]",
    3: "传感器状态_上位机[3].NO[10]",
    4: "传感器状态_上位机[3].NO[11]",
    5: "传感器状态_上位机[3].NO[12]",
    6: "传感器状态_上位机[3].NO[13]",
}
S072_SENSOR_BY_POSITION = {
    1: "传感器状态_上位机[3].NO[14]",
    2: "传感器状态_上位机[3].NO[15]",
}

S07_HOME = "S07原点信号"
S07_ALLOW = "S07允许加工"
S07_PROCESS = "S07工艺选择"
S07_PARAMS_WRITTEN = "S07参数写入完成"
S07_DONE = "S07工艺完成"
S07_PROCESS_LABELS = {
    1: "粉罐扫码盘点",
    2: "替换粉罐旋转到进料位",
    3: "注粉",
}

S08_HOME = "S08原点信号"
S08_ALLOW = "S08允许加工"
S08_PROCESS = "S08工艺选择"
S08_PARAMS_WRITTEN = "S08参数写入完成"
S08_DONE = "S08工艺完成"
S08_CAP_STORAGE_SLOT = "S082瓶盖暂存位"
S08_STATION_STATUS = "工站状态[7]"
S08_PROCESS_LABELS = {
    1: "500 mL 样品瓶开盖",
    2: "500 mL 样品瓶关盖",
    3: "250 mL 样品瓶开盖",
    4: "250 mL 样品瓶关盖",
    5: "100 mL 液体瓶开盖",
    6: "100 mL 液体瓶关盖",
}

S09_PROCESS = "S09工艺选择"
S09_PARAMS_WRITTEN = "S09参数写入完成"
S09_DONE = "S09工艺完成"
S09_ALLOW = "S09允许加工"
S09_STATION_STATUS = "工站状态[8]"
S09_PROCESS_LABELS = {
    1: "去安全位1",
    2: "去安全位2",
    3: "去安全位3",
    4: "去安全位4",
    5: "取 TIP",
    6: "放 TIP",
    7: "液体瓶取液",
    8: "烧杯放液",
    9: "测密度抽液",
    10: "测密度排液",
}


def s09_remaining_volume(bottle: int) -> str:
    return f"S09液体瓶{int(bottle)}剩余液量"


def s08_cap_cache(slot: int, index: int) -> str:
    return f"S082_{int(slot)}数据缓存[{int(index)}]"


SUPPORTED_ACTIONS = (
    "szlab_mixer_robot.submit_place_to_s04",
    "szlab_mixer_stirrer.run_stirring",
    "szlab_mixer_robot.submit_pick_from_s04",
    "szlab_mixer_photoshotting.take_photo",
    "szlab_mixer_pump.run_solvent_addition",
    "szlab_mixer_robot.submit_place_to_s06",
    "szlab_mixer_robot.submit_pick_from_s06",
    "szlab_mixer_pipetting_station.prepare_liquid_station",
    "szlab_mixer_pipetting_station.bind_sample_to_station",
    "szlab_mixer_pipetting_station.add_liquid",
    "szlab_mixer_pipetting_station.release_station",
    "szlab_mixer_robot.submit_place_to_s071",
    "szlab_mixer_robot.submit_place_to_s072",
    "szlab_mixer_robot.submit_pick_from_s072",
    "szlab_s07_solid_addition.scan_powder_cartridges",
    "szlab_s07_solid_addition.rotate_powder_cartridge_to_feed",
    "szlab_s07_solid_addition.dose_powder",
    "szlab_s08_cap_station.process_cap_with_sample_parts",
    "szlab_poly_plc.get_stack_status",
    "szlab_mixer_robot.pick_beaker_from_s03",
    "szlab_mixer_robot.place_beaker_to_s06",
    "szlab_mixer_pump.add_solvent_to_beaker",
    "szlab_mixer_robot.pick_beaker_from_s06",
)

# 保留首版握手器导出的动作别名，避免既有测试脚本和外部调用方因扩展
# SUPPORTED_ACTIONS 而被迫按元组下标取值。
S04_PLACE_ACTION = SUPPORTED_ACTIONS[0]
S04_STIR_ACTION = SUPPORTED_ACTIONS[1]
S04_PICK_ACTION = SUPPORTED_ACTIONS[2]
S06_PUMP_ACTION = SUPPORTED_ACTIONS[4]
S06_PLACE_ACTION = SUPPORTED_ACTIONS[5]
S06_PICK_ACTION = SUPPORTED_ACTIONS[6]
S09_ADD_LIQUID_ACTION = SUPPORTED_ACTIONS[9]
S07_SOLID_ACTION_BY_PROCESS = {
    1: SUPPORTED_ACTIONS[14],
    2: SUPPORTED_ACTIONS[15],
    3: SUPPORTED_ACTIONS[16],
}
S08_CAP_ACTION = SUPPORTED_ACTIONS[17]
MATERIAL_S03_PICK_ACTION = SUPPORTED_ACTIONS[19]
MATERIAL_S06_PLACE_ACTION = SUPPORTED_ACTIONS[20]
MATERIAL_S06_ADD_ACTION = SUPPORTED_ACTIONS[21]
MATERIAL_S06_PICK_ACTION = SUPPORTED_ACTIONS[22]

WORKFLOW_IDS = (
    "szlab_magnetic_stirring_workflow",
    "szlab_photoshotting_workflow",
    "szlab_robot_action_workflow",
    "s04_robot_stirring_workflow",
    "s06_robot_workflow",
    "s07_robot_workflow",
    "szlab_s07_solid_addition_workflow",
    "s08_cap_workflow",
    "szlab_s09_pipetting_workflow",
    "szlab_stack_s05_s06_workflow",
    "szlab_mixer_workflow",
    "szlab_mixer_pump_production",
    "szlab_material_s06_workflow",
)

WORKFLOW_COMPONENTS = {
    "szlab_magnetic_stirring_workflow": frozenset({"stirrer"}),
    "szlab_photoshotting_workflow": frozenset({"photo"}),
    "szlab_robot_action_workflow": frozenset({"robot_s04"}),
    "s04_robot_stirring_workflow": frozenset({"robot_s04", "stirrer"}),
    "s06_robot_workflow": frozenset({"robot_s06", "pump"}),
    "s07_robot_workflow": frozenset({"robot_s07"}),
    "szlab_s07_solid_addition_workflow": frozenset({"s07"}),
    "s08_cap_workflow": frozenset({"s08"}),
    "szlab_s09_pipetting_workflow": frozenset({"s09"}),
    "szlab_stack_s05_s06_workflow": frozenset({"photo", "pump"}),
    "szlab_mixer_workflow": frozenset({"pump"}),
    "szlab_mixer_pump_production": frozenset({"pump"}),
    "szlab_material_s06_workflow": frozenset({"robot_s03", "robot_s06", "pump"}),
}
ALL_COMPONENTS = frozenset().union(*WORKFLOW_COMPONENTS.values())

ROBOT_ACTION_BY_TASK = {
    6: MATERIAL_S03_PICK_ACTION,
    7: SUPPORTED_ACTIONS[0],
    8: SUPPORTED_ACTIONS[2],
    11: SUPPORTED_ACTIONS[5],
    12: SUPPORTED_ACTIONS[6],
    13: SUPPORTED_ACTIONS[11],
    15: SUPPORTED_ACTIONS[12],
    16: SUPPORTED_ACTIONS[13],
}

MATERIAL_S06_ACTION_BY_TASK = {
    6: MATERIAL_S03_PICK_ACTION,
    11: MATERIAL_S06_PLACE_ACTION,
    12: MATERIAL_S06_PICK_ACTION,
}


def s04_station(position: int) -> str:
    return f"S04{int(position)}"


def s04_sensor(position: int) -> str:
    position = int(position)
    if position not in range(1, 7):
        raise ValueError("S04 position 必须在 1-6 范围内")
    return f"传感器状态_上位机[2].NO[{position + 9}]"


def s04_allow(position: int) -> str:
    return f"{s04_station(position)}允许加工"


def s04_process(position: int) -> str:
    return f"{s04_station(position)}磁搅工艺选择"


def s04_params_written(position: int) -> str:
    return f"{s04_station(position)}参数写入完成"


def s04_done(position: int) -> str:
    return f"{s04_station(position)}加工完成"


def s071_sensor(slot: int) -> str:
    try:
        return S071_SENSOR_BY_SLOT[int(slot)]
    except KeyError as exc:
        raise ValueError("S071 位置必须在 1-6 范围内") from exc


def s072_sensor(position: int) -> str:
    try:
        return S072_SENSOR_BY_POSITION[int(position)]
    except KeyError as exc:
        raise ValueError("S072 位置必须在 1-2 范围内") from exc


class VariableAdapter(Protocol):
    """状态机所需的最小变量读写 interface。"""

    def read(self, name: str) -> Any: ...

    def write(self, name: str, value: Any) -> None: ...


@dataclass(frozen=True)
class Requirement:
    kind: Literal["opcua", "config", "file", "parameter"]
    subject: str
    expectation: str
    expected: Any = None
    operator: Literal["eq", "in", "gt", "readable", "manual"] = "manual"
    phase: str = "启动前"
    note: str = ""

    def evaluate(self, adapter: VariableAdapter) -> tuple[bool | None, Any]:
        if self.kind != "opcua" or self.operator == "manual":
            return None, None
        try:
            actual = adapter.read(self.subject)
        except Exception as exc:  # noqa: BLE001 - 报告远端单节点错误
            return False, f"{type(exc).__name__}: {exc}"
        if self.operator == "readable":
            return True, actual
        if self.operator == "eq":
            return actual == self.expected, actual
        if self.operator == "in":
            return actual in self.expected, actual
        if self.operator == "gt":
            try:
                return actual > self.expected, actual
            except TypeError:
                return False, actual
        raise ValueError(f"未知检查操作: {self.operator}")


@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    actions: tuple[str, ...]
    requirements: tuple[Requirement, ...]


def _opc_eq(subject: str, expected: Any, *, phase: str = "启动前", note: str = "") -> Requirement:
    return Requirement(
        kind="opcua",
        subject=subject,
        expectation=f"== {expected!r}",
        expected=expected,
        operator="eq",
        phase=phase,
        note=note,
    )


def _opc_in(subject: str, expected: Iterable[Any], *, note: str = "") -> Requirement:
    values = tuple(expected)
    return Requirement(
        kind="opcua",
        subject=subject,
        expectation=f"in {values!r}",
        expected=values,
        operator="in",
        note=note,
    )


def _opc_gt(subject: str, expected: Any, *, note: str = "") -> Requirement:
    return Requirement(
        kind="opcua",
        subject=subject,
        expectation=f"> {expected!r}",
        expected=expected,
        operator="gt",
        note=note,
    )


def _opc_readable(subject: str, *, note: str = "") -> Requirement:
    return Requirement(
        kind="opcua",
        subject=subject,
        expectation="节点存在且可读",
        operator="readable",
        note=note,
    )


def _manual(
    kind: Literal["config", "file", "parameter"],
    subject: str,
    expectation: str,
    *,
    note: str = "",
) -> Requirement:
    return Requirement(
        kind=kind,
        subject=subject,
        expectation=expectation,
        operator="manual",
        note=note,
    )


def _robot_common() -> tuple[Requirement, ...]:
    return (
        _opc_eq(ROBOT_HOME, True),
        _opc_eq(ROBOT_WRITE_ALLOWED, True),
        _opc_eq(ROBOT_TASK_COMPLETE, 0, note="开始新任务前完成码应清零"),
    )


def build_workflow_specs(position: int = 1, pump: int = 1) -> tuple[WorkflowSpec, ...]:
    """返回仓库当前 13 个 Python 工作流的先决条件目录。"""

    position = int(position)
    pump = int(pump)
    if position not in range(1, 7):
        raise ValueError("position 必须在 1-6 范围内")
    if pump not in (1, 2, 3):
        raise ValueError("pump 必须是 1、2 或 3")

    storage_requirements = tuple(
        _opc_eq(S06_STORAGE_BOTTLE_SENSOR[index], True)
        for index in ((1, 2) if pump == 3 else (pump,))
    )
    s06_common = (
        _opc_eq(S06_READY, True),
        _opc_eq(S06_ALLOW, True),
        _opc_eq(S06_DONE, False, note="wait_new_cycle_done 要求从 False 开始新周期"),
        *storage_requirements,
    )
    s04_common = (
        _opc_eq(s04_allow(position), True),
        _opc_eq(s04_done(position), False, note="新一轮磁搅开始前完成信号应清零"),
    )
    return (
        WorkflowSpec(
            "szlab_magnetic_stirring_workflow",
            ("szlab_mixer_stirrer.run_stirring",),
            s04_common,
        ),
        WorkflowSpec(
            "szlab_photoshotting_workflow",
            ("szlab_mixer_photoshotting.take_photo",),
            (
                _opc_eq(S05_DONE, True, note="当前驱动没有拍照启动写入，只等待该信号"),
                _opc_eq(S05_RESULT, 1, note="1=OK，2=NG"),
            ),
        ),
        WorkflowSpec(
            "szlab_robot_action_workflow",
            (
                "szlab_mixer_robot.submit_place_to_s04",
                "szlab_mixer_robot.submit_pick_from_s04",
            ),
            (
                *_robot_common(),
                _opc_eq(s04_sensor(position), False, note="放料前目标位必须为空；握手器放料后会置 True"),
            ),
        ),
        WorkflowSpec(
            "s04_robot_stirring_workflow",
            (
                "szlab_mixer_robot.submit_place_to_s04",
                "szlab_mixer_stirrer.run_stirring",
                "szlab_mixer_robot.submit_pick_from_s04",
            ),
            (
                *_robot_common(),
                _opc_eq(s04_sensor(position), False, note="放料前为空，放料后 True，取料后恢复 False"),
                *s04_common,
            ),
        ),
        WorkflowSpec(
            "s06_robot_workflow",
            (
                "szlab_mixer_robot.submit_place_to_s06",
                "szlab_mixer_pump.run_solvent_addition",
                "szlab_mixer_robot.submit_pick_from_s06",
            ),
            (
                *_robot_common(),
                _opc_eq(S06_BEAKER_SENSOR, False, note="机器人放料前 S06 加液位必须为空"),
                *s06_common,
                _manual("parameter", "skip_level_check", "False 时储液瓶传感器必须在位"),
            ),
        ),
        WorkflowSpec(
            "s07_robot_workflow",
            (
                "szlab_mixer_robot.submit_place_to_s071",
                "szlab_mixer_robot.submit_place_to_s072",
                "szlab_mixer_robot.submit_pick_from_s072",
            ),
            (
                *_robot_common(),
                _opc_eq("传感器状态_上位机[3].NO[8]", False, note="S071 放粉罐目标位初始为空"),
                _opc_eq("传感器状态_上位机[3].NO[14]", False, note="S072 放料目标位初始为空"),
            ),
        ),
        WorkflowSpec(
            "szlab_s07_solid_addition_workflow",
            (
                "szlab_s07_solid_addition.scan_powder_cartridges",
                "szlab_s07_solid_addition.rotate_powder_cartridge_to_feed",
                "szlab_s07_solid_addition.dose_powder",
            ),
            (
                _opc_eq("S07原点信号", True),
                _opc_eq("S07允许加工", True),
                _opc_eq("S07工艺完成", 0, note="每轮开始前完成工艺号应清零"),
                _opc_readable("S07位置1二维码[0]", note="扫码动作还需要全部 10×30 个二维码节点"),
                _manual("file", "s07_powder_params.json", "default recipe 存在且参数长度正确"),
            ),
        ),
        WorkflowSpec(
            "s08_cap_workflow",
            (
                "szlab_s08_cap_station.process_cap_with_sample_parts(open)",
                "szlab_s08_cap_station.process_cap_with_sample_parts(close)",
            ),
            (
                _opc_eq("S08原点信号", True),
                _opc_eq("S08允许加工", True),
                _opc_eq("S08工艺完成", 0, note="每轮完成后还必须响应 PC 复位并再次清零"),
                _opc_eq("S082_1数据缓存[0]", 0, note="开盖前至少一个瓶盖暂存缓存为空"),
                _manual("parameter", "sample_id", "非零，open/close 使用完全相同的 ID"),
                _opc_in("工站状态[7]", (2, 3, 4, 5, 6), note="仅开启工站状态校验时要求"),
            ),
        ),
        WorkflowSpec(
            "szlab_s09_pipetting_workflow",
            (
                "szlab_mixer_pipetting_station.prepare_liquid_station",
                "szlab_mixer_pipetting_station.bind_sample_to_station",
                "szlab_mixer_pipetting_station.add_liquid",
                "szlab_mixer_pipetting_station.release_station",
            ),
            (
                _opc_eq("工站状态[8]", 2, note="prepare_liquid_station 只接受状态 2"),
                _opc_eq("S09工艺完成", 0, note="每个 5/7/8/6 子工艺开始前完成号应清零"),
                _opc_gt(f"S09液体瓶{pump if pump in (1, 2) else 1}剩余液量", 0.0),
                _manual("parameter", "tip_box_index/tip_index", "分别在 1-2、1-96 范围内"),
            ),
        ),
        WorkflowSpec(
            "szlab_stack_s05_s06_workflow",
            (
                "szlab_poly_plc.get_stack_status",
                "szlab_mixer_photoshotting.take_photo",
                "szlab_mixer_pump.run_solvent_addition",
            ),
            (
                _opc_readable("传感器状态_上位机[0].NO[0]", note="堆栈传感器组节点必须可读"),
                _opc_eq(S05_DONE, True),
                _opc_eq(S05_RESULT, 1),
                _opc_eq(S06_BEAKER_SENSOR, True),
                *s06_common,
            ),
        ),
        WorkflowSpec(
            "szlab_mixer_workflow",
            ("szlab_mixer_pump.run_solvent_addition",),
            (
                _opc_eq(S06_BEAKER_SENSOR, True),
                *s06_common,
            ),
        ),
        WorkflowSpec(
            "szlab_mixer_pump_production",
            ("szlab_mixer_pump.run_solvent_addition",),
            (
                _opc_eq(S06_BEAKER_SENSOR, True),
                *s06_common,
            ),
        ),
        WorkflowSpec(
            "szlab_material_s06_workflow",
            (
                MATERIAL_S03_PICK_ACTION,
                MATERIAL_S06_PLACE_ACTION,
                MATERIAL_S06_ADD_ACTION,
                MATERIAL_S06_PICK_ACTION,
            ),
            (
                *_robot_common(),
                _opc_eq(S03_BEAKER_SENSOR, True, note="S03 1-1 取料源位必须有烧杯"),
                _opc_eq(S06_BEAKER_SENSOR, False, note="机器人放料前 S06 加液位必须为空"),
                *s06_common,
                _manual("parameter", "skip_level_check", "False 时储液瓶传感器必须在位"),
            ),
        ),
    )


class OpcUaVariableAdapter:
    """使用直接 NodeId 访问 CSV 已创建变量的生产 adapter。"""

    def __init__(self, url: str, node_prefix: str, username: str = "", password: str = "") -> None:
        self.url = url
        self.node_prefix = node_prefix
        self.username = username
        self.password = password
        self._client = self._new_client()
        self._nodes: dict[str, Any] = {}

    def _new_client(self) -> Any:
        from opcua import Client

        client = Client(self.url, timeout=10)
        if self.username:
            client.set_user(self.username)
            client.set_password(self.password)
        return client

    def connect(self) -> None:
        self._client.connect()

    def disconnect(self) -> None:
        try:
            self._client.disconnect()
        except Exception as exc:
            print(
                f"OPC UA 断开连接时忽略临时错误: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )

    def _reconnect(self) -> None:
        try:
            self._client.disconnect()
        except Exception:
            pass
        self._client = self._new_client()
        self._client.connect()
        self._nodes.clear()

    def _run_io(self, name: str, operation: Any) -> Any:
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                return operation()
            except (TimeoutError, ConnectionError) as exc:
                if attempt >= attempts:
                    raise RuntimeError(
                        f"{name}: OPC UA 通信失败（已重试 {attempts} 次）"
                    ) from exc
                print(
                    f"{name}: OPC UA {type(exc).__name__}，"
                    f"正在重连并重试 ({attempt}/{attempts})",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(1.0)
                self._reconnect()
        raise AssertionError("unreachable")


    def _node(self, name: str) -> Any:
        node = self._nodes.get(name)
        if node is None:
            node = self._client.get_node(f"{self.node_prefix}{name}")
            self._nodes[name] = node
        return node

    def read(self, name: str) -> Any:
        return self._run_io(name, lambda: self._node(name).get_value())

    def write(self, name: str, value: Any) -> None:
        """按远端变量真实 VariantType 写 Value，不改时间戳或状态码。"""

        self._run_io(name, lambda: self._write_once(name, value))

    def _write_once(self, name: str, value: Any) -> None:
        from opcua import ua

        node = self._node(name)
        variant_type = node.get_data_type_as_variant_type()
        data_value = ua.DataValue()
        data_value.Value = ua.Variant(value, variant_type)
        data_value.StatusCode = None
        data_value.SourceTimestamp = None
        data_value.ServerTimestamp = None
        data_value.SourcePicoseconds = None
        data_value.ServerPicoseconds = None

        write_value = ua.WriteValue()
        write_value.NodeId = node.nodeid
        write_value.AttributeId = ua.AttributeIds.Value
        write_value.Value = data_value

        params = ua.WriteParameters()
        params.NodesToWrite = [write_value]
        results = self._client.uaclient.write(params)
        if results and not results[0].is_good():
            raise RuntimeError(f"{name}: {results[0]}")


@dataclass(frozen=True)
class HandshakeEvent:
    action: str
    phase: Literal["accepted", "completed", "reset"]
    detail: dict[str, Any]


@dataclass
class _Cycle:
    phase: Literal["idle", "executing", "await_reset"] = "idle"
    due_at: float = 0.0
    process: int = 0
    position: int = 0
    sensor: str = ""


class WorkflowHandshakeSimulator:
    """覆盖仓库全部工作流动作的独立 PLC 握手状态机。"""

    def __init__(
        self,
        adapter: VariableAdapter,
        *,
        position: int = 1,
        pump: int = 1,
        process_delay: float = 0.5,
        s06_robot_workflow: bool = False,
        s09_pipetting_workflow: bool = False,
        s09_remaining_volume_ml: float = 100.0,
        workflow: str | None = None,
    ) -> None:
        if int(position) not in range(1, 7):
            raise ValueError("position 必须在 1-6 范围内")
        if int(pump) not in (1, 2, 3):
            raise ValueError("pump 必须是 1、2 或 3")
        selected_workflow = workflow or "all"
        if selected_workflow not in ("all", *WORKFLOW_IDS):
            raise ValueError(f"不支持的握手工作流: {selected_workflow}")
        self.adapter = adapter
        self.position = int(position)
        self.pump = int(pump)
        self.process_delay = max(float(process_delay), 0.0)
        self.workflow = selected_workflow
        self.s06_robot_workflow = bool(
            s06_robot_workflow
            or selected_workflow in {"s06_robot_workflow", "szlab_material_s06_workflow"}
        )
        self.s09_pipetting_workflow = bool(
            s09_pipetting_workflow
            or selected_workflow == "szlab_s09_pipetting_workflow"
        )
        self.s09_remaining_volume_ml = float(s09_remaining_volume_ml)
        if self.s09_pipetting_workflow and self.s09_remaining_volume_ml <= 0:
            raise ValueError("S09 初始液体余量必须大于 0 mL")
        self.robot = _Cycle()
        self.stirrer = _Cycle(position=self.position)
        self.pump_cycle = _Cycle(process=self.pump)
        self.s07_cycle = _Cycle()
        self.s08_cycle = _Cycle()
        self.s09_cycle = _Cycle()
        self._s071_loaded_sensor = ""
        self.completed_actions = 0

    @property
    def enabled_components(self) -> frozenset[str]:
        if self.workflow == "all":
            return ALL_COMPONENTS
        return WORKFLOW_COMPONENTS[self.workflow]

    def initialization_values(self) -> dict[str, Any]:
        components = self.enabled_components
        values: dict[str, Any] = {}
        if components & {"robot_s03", "robot_s04", "robot_s06", "robot_s07"}:
            values.update(
                {
                    ROBOT_HOME: True,
                    ROBOT_WRITE_ALLOWED: True,
                    ROBOT_WRITE_DONE: False,
                    ROBOT_TASK_COMPLETE: 0,
                }
            )
        if "robot_s03" in components:
            values[S03_BEAKER_SENSOR] = True
        if "robot_s04" in components:
            values[s04_sensor(self.position)] = False
        if "stirrer" in components:
            values.update(
                {
                    s04_allow(self.position): True,
                    s04_done(self.position): False,
                }
            )
        if "photo" in components:
            values.update({S05_DONE: True, S05_RESULT: 1})
        if "pump" in components:
            values.update(
                {
                    S06_READY: True,
                    S06_ALLOW: True,
                    S06_DONE: False,
                    S06_BEAKER_SENSOR: not self.s06_robot_workflow,
                }
            )
            for index in ((1, 2) if self.pump == 3 else (self.pump,)):
                values[S06_STORAGE_BOTTLE_SENSOR[index]] = True
        if "robot_s07" in components:
            values.update({s071_sensor(1): False, s072_sensor(1): False})
        if "s07" in components:
            values.update({S07_HOME: True, S07_ALLOW: True, S07_DONE: 0})
        if "s08" in components:
            values.update(
                {
                    S08_HOME: True,
                    S08_ALLOW: True,
                    S08_DONE: 0,
                    S08_STATION_STATUS: 2,
                    **{s08_cap_cache(1, index): 0 for index in range(30)},
                }
            )
        if "s09" in components:
            values.update(
                {
                    S09_STATION_STATUS: 2,
                    S09_ALLOW: True,
                    S09_DONE: 0,
                    **{
                        s09_remaining_volume(index): self.s09_remaining_volume_ml
                        for index in range(1, 6)
                    },
                }
            )
        return values

    def cleanup_values(self) -> dict[str, Any]:
        components = self.enabled_components
        values: dict[str, Any] = {}
        if components & {"robot_s03", "robot_s04", "robot_s06", "robot_s07"}:
            values.update(
                {
                    ROBOT_HOME: False,
                    ROBOT_WRITE_ALLOWED: False,
                    ROBOT_TASK_COMPLETE: 0,
                }
            )
        if "robot_s03" in components:
            values[S03_BEAKER_SENSOR] = False
        if "robot_s04" in components:
            values[s04_sensor(self.position)] = False
        if "stirrer" in components:
            values.update(
                {
                    s04_allow(self.position): False,
                    s04_done(self.position): False,
                }
            )
        if "photo" in components:
            values.update({S05_DONE: False, S05_RESULT: 0})
        if "pump" in components:
            values.update(
                {
                    S06_READY: False,
                    S06_ALLOW: False,
                    S06_DONE: False,
                    S06_BEAKER_SENSOR: False,
                }
            )
            for index in ((1, 2) if self.pump == 3 else (self.pump,)):
                values[S06_STORAGE_BOTTLE_SENSOR[index]] = False
        if "robot_s07" in components:
            values.update({s071_sensor(1): False, s072_sensor(1): False})
        if "s07" in components:
            values.update({S07_HOME: False, S07_ALLOW: False, S07_DONE: 0})
        if "s08" in components:
            values.update(
                {
                    S08_HOME: False,
                    S08_ALLOW: False,
                    S08_DONE: 0,
                    S08_STATION_STATUS: 0,
                    **{s08_cap_cache(1, index): 0 for index in range(30)},
                }
            )
        if "s09" in components:
            values.update(
                {
                    S09_STATION_STATUS: 0,
                    S09_ALLOW: False,
                    S09_DONE: 0,
                    **{
                        s09_remaining_volume(index): 0.0
                        for index in range(1, 6)
                    },
                }
            )
        return values

    def initialize(self) -> None:
        for name, value in self.initialization_values().items():
            self.adapter.write(name, value)

    def cleanup(self) -> None:
        for name, value in self.cleanup_values().items():
            self.adapter.write(name, value)

    def check_supported_prerequisites(self) -> list[tuple[str, bool, Any, Any]]:
        result: list[tuple[str, bool, Any, Any]] = []
        for name, expected in self.initialization_values().items():
            try:
                actual = self.adapter.read(name)
                result.append((name, actual == expected, expected, actual))
            except Exception as exc:  # noqa: BLE001
                result.append((name, False, expected, f"{type(exc).__name__}: {exc}"))
        return result

    def step(self, now: float | None = None) -> list[HandshakeEvent]:
        now = time.monotonic() if now is None else float(now)
        components = self.enabled_components
        events: list[HandshakeEvent] = []
        if components & {"robot_s03", "robot_s04", "robot_s06", "robot_s07"}:
            events.extend(self._step_robot(now))
        if "stirrer" in components:
            events.extend(self._step_stirrer(now))
        if "pump" in components:
            events.extend(self._step_pump(now))
        if "s07" in components:
            events.extend(self._step_s07(now))
        if "s08" in components:
            events.extend(self._step_s08(now))
        if "s09" in components:
            events.extend(self._step_s09(now))
        self.completed_actions += sum(event.phase == "completed" for event in events)
        return events

    def all_cycles_idle(self) -> bool:
        """所有已启用握手均已被 Edge 消费并完成复位。"""

        components = self.enabled_components
        cycles = []
        if components & {"robot_s03", "robot_s04", "robot_s06", "robot_s07"}:
            cycles.append(self.robot)
        if "stirrer" in components:
            cycles.append(self.stirrer)
        if "pump" in components:
            cycles.append(self.pump_cycle)
        if "s07" in components:
            cycles.append(self.s07_cycle)
        if "s08" in components:
            cycles.append(self.s08_cycle)
        if "s09" in components:
            cycles.append(self.s09_cycle)
        return all(cycle.phase == "idle" for cycle in cycles)

    def _step_robot(self, now: float) -> list[HandshakeEvent]:
        cycle = self.robot
        events: list[HandshakeEvent] = []
        if cycle.phase == "idle":
            write_done = bool(self.adapter.read(ROBOT_WRITE_DONE))
            task = int(self.adapter.read(ROBOT_TASK_NUMBER) or 0)
            if write_done and task in ROBOT_ACTION_BY_TASK:
                position = 0
                sensor = ""
                if task == 6:
                    sensor = S03_BEAKER_SENSOR
                elif task in (7, 8):
                    position = int(self.adapter.read(S04_ROBOT_POSITION) or 0)
                    if position != self.position:
                        raise RuntimeError(
                            f"机器人 S04 位置不匹配：脚本监听 {self.position}，收到 {position}"
                        )
                    sensor = s04_sensor(position)
                elif task in (11, 12):
                    sensor = S06_BEAKER_SENSOR
                elif task == 13:
                    position = int(self.adapter.read(S071_ROBOT_POSITION) or 0)
                    sensor = s071_sensor(position)
                elif task in (15, 16):
                    # 当前仓库 s07_robot_workflow 固定使用 S072 position=1；
                    # 设备驱动只把产品类型写入 PLC，没有单独写位置变量。
                    position = 1
                    sensor = s072_sensor(position)
                self.adapter.write(ROBOT_WRITE_ALLOWED, False)
                self.adapter.write(ROBOT_HOME, False)
                self.adapter.write(ROBOT_TASK_COMPLETE, 0)
                cycle.phase = "executing"
                cycle.process = task
                cycle.position = position
                cycle.sensor = sensor
                cycle.due_at = now + self.process_delay
                events.append(
                    HandshakeEvent(
                        self._robot_action(task),
                        "accepted",
                        {
                            "task_number": task,
                            **({"position": position} if position else {}),
                            **({"sensor": sensor} if sensor else {}),
                        },
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            occupied = cycle.process in (7, 11, 13, 15)
            if cycle.sensor:
                self.adapter.write(cycle.sensor, occupied)
            rearmed_sensor = ""
            if cycle.process == 13:
                self._s071_loaded_sensor = cycle.sensor
            elif cycle.process == 16 and self._s071_loaded_sensor:
                # s07_robot_workflow 的最后一步取走 S072 产品后，模拟 S071
                # 粉罐已被工站消费/移走，从而无需重启即可开始下一轮放粉罐。
                rearmed_sensor = self._s071_loaded_sensor
                self.adapter.write(rearmed_sensor, False)
                self._s071_loaded_sensor = ""
            self.adapter.write(ROBOT_HOME, True)
            self.adapter.write(ROBOT_TASK_COMPLETE, cycle.process)
            cycle.phase = "await_reset"
            events.append(
                HandshakeEvent(
                    self._robot_action(cycle.process),
                    "completed",
                    {
                        "task_number": cycle.process,
                        "occupied": occupied,
                        **({"position": cycle.position} if cycle.position else {}),
                        **({"sensor": cycle.sensor} if cycle.sensor else {}),
                        **({"rearmed_sensor": rearmed_sensor} if rearmed_sensor else {}),
                    },
                )
            )
        elif cycle.phase == "await_reset":
            write_done = bool(self.adapter.read(ROBOT_WRITE_DONE))
            task = int(self.adapter.read(ROBOT_TASK_NUMBER) or 0)
            # Robot_任务写入完成=False 表示 Edge 已经消费完成码。任务号在
            # SKIP_RESET_AFTER_RUN 等配置下可能保留为上一任务，不能用它
            # 阻塞状态机重装填；下一轮仍以 write_done 的新上升沿触发。
            if not write_done:
                self.adapter.write(ROBOT_TASK_COMPLETE, 0)
                self.adapter.write(ROBOT_WRITE_ALLOWED, True)
                self.adapter.write(ROBOT_HOME, True)
                events.append(
                    HandshakeEvent(
                        self._robot_action(cycle.process),
                        "reset",
                        {
                            "task_number": cycle.process,
                            "observed_task_number": task,
                        },
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
                cycle.position = 0
                cycle.sensor = ""
        return events

    def _robot_action(self, task: int) -> str:
        if self.workflow == "szlab_material_s06_workflow":
            return MATERIAL_S06_ACTION_BY_TASK[task]
        return ROBOT_ACTION_BY_TASK[task]

    def _step_stirrer(self, now: float) -> list[HandshakeEvent]:
        cycle = self.stirrer
        events: list[HandshakeEvent] = []
        params_name = s04_params_written(self.position)
        process_name = s04_process(self.position)
        if cycle.phase == "idle":
            params_written = bool(self.adapter.read(params_name))
            process = int(self.adapter.read(process_name) or 0)
            if params_written and process in (1, 2, 3):
                self.adapter.write(s04_allow(self.position), False)
                self.adapter.write(s04_done(self.position), False)
                cycle.phase = "executing"
                cycle.process = process
                cycle.due_at = now + self.process_delay
                events.append(
                    HandshakeEvent(
                        SUPPORTED_ACTIONS[1],
                        "accepted",
                        {"process": process, "position": self.position},
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            self.adapter.write(s04_done(self.position), True)
            cycle.phase = "await_reset"
            events.append(
                HandshakeEvent(
                    SUPPORTED_ACTIONS[1],
                    "completed",
                    {"process": cycle.process, "position": self.position},
                )
            )
        elif cycle.phase == "await_reset":
            params_written = bool(self.adapter.read(params_name))
            process = int(self.adapter.read(process_name) or 0)
            if not params_written and process == 0:
                self.adapter.write(s04_done(self.position), False)
                self.adapter.write(s04_allow(self.position), True)
                events.append(
                    HandshakeEvent(
                        SUPPORTED_ACTIONS[1],
                        "reset",
                        {"process": cycle.process, "position": self.position},
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
        return events

    def _step_pump(self, now: float) -> list[HandshakeEvent]:
        cycle = self.pump_cycle
        events: list[HandshakeEvent] = []
        if cycle.phase == "idle":
            params_written = bool(self.adapter.read(S06_PARAMS_WRITTEN))
            process = int(self.adapter.read(S06_PROCESS) or 0)
            if params_written and process in (1, 2, 3):
                self.adapter.write(S06_ALLOW, False)
                self.adapter.write(S06_DONE, False)
                cycle.phase = "executing"
                cycle.process = process
                cycle.due_at = now + self.process_delay
                events.append(
                    HandshakeEvent(
                        self._pump_action(),
                        "accepted",
                        {"process": process},
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            self.adapter.write(S06_DONE, True)
            cycle.phase = "await_reset"
            events.append(
                HandshakeEvent(
                    self._pump_action(),
                    "completed",
                    {"process": cycle.process},
                )
            )
        elif cycle.phase == "await_reset":
            params_written = bool(self.adapter.read(S06_PARAMS_WRITTEN))
            process = int(self.adapter.read(S06_PROCESS) or 0)
            # 参数写入标志的下降沿是 PC 已消费完成信号的权威确认。工艺号
            # 允许保留旧值；下一轮仍需 params_written 再次变为 True。
            if not params_written:
                self.adapter.write(S06_DONE, False)
                self.adapter.write(S06_ALLOW, True)
                events.append(
                    HandshakeEvent(
                        self._pump_action(),
                        "reset",
                        {
                            "process": cycle.process,
                            "observed_process": process,
                        },
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
        return events

    def _pump_action(self) -> str:
        if self.workflow == "szlab_material_s06_workflow":
            return MATERIAL_S06_ADD_ACTION
        return S06_PUMP_ACTION

    def _step_s07(self, now: float) -> list[HandshakeEvent]:
        """模拟 S07 扫码、转位和注粉三个工艺的可重复握手。"""

        cycle = self.s07_cycle
        events: list[HandshakeEvent] = []
        process = int(self.adapter.read(S07_PROCESS) or 0)
        params_written = bool(self.adapter.read(S07_PARAMS_WRITTEN))

        if cycle.phase == "idle":
            if params_written and process in S07_PROCESS_LABELS:
                self.adapter.write(S07_ALLOW, False)
                self.adapter.write(S07_DONE, 0)
                cycle.phase = "executing"
                cycle.process = process
                cycle.due_at = now + self.process_delay
                events.append(
                    HandshakeEvent(
                        S07_SOLID_ACTION_BY_PROCESS[process],
                        "accepted",
                        {
                            "process": process,
                            "process_label": S07_PROCESS_LABELS[process],
                        },
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            self.adapter.write(S07_DONE, cycle.process)
            cycle.phase = "await_reset"
            events.append(
                HandshakeEvent(
                    S07_SOLID_ACTION_BY_PROCESS[cycle.process],
                    "completed",
                    {
                        "process": cycle.process,
                        "process_label": S07_PROCESS_LABELS[cycle.process],
                    },
                )
            )
        elif cycle.phase == "await_reset":
            if not params_written and process == 0:
                self.adapter.write(S07_DONE, 0)
                self.adapter.write(S07_ALLOW, True)
                events.append(
                    HandshakeEvent(
                        S07_SOLID_ACTION_BY_PROCESS[cycle.process],
                        "reset",
                        {
                            "process": cycle.process,
                            "process_label": S07_PROCESS_LABELS[cycle.process],
                        },
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
        return events

    def _step_s08(self, now: float) -> list[HandshakeEvent]:
        """模拟 S08 开/关盖工艺，并在 Edge 复位参数后清零完成码。"""

        cycle = self.s08_cycle
        events: list[HandshakeEvent] = []
        process = int(self.adapter.read(S08_PROCESS) or 0)
        params_written = bool(self.adapter.read(S08_PARAMS_WRITTEN))
        cap_storage_slot = int(self.adapter.read(S08_CAP_STORAGE_SLOT) or 0)

        if cycle.phase == "idle":
            if params_written and process in S08_PROCESS_LABELS:
                self.adapter.write(S08_ALLOW, False)
                self.adapter.write(S08_DONE, 0)
                cycle.phase = "executing"
                cycle.process = process
                cycle.position = cap_storage_slot
                cycle.due_at = now + self.process_delay
                events.append(
                    HandshakeEvent(
                        S08_CAP_ACTION,
                        "accepted",
                        {
                            "process": process,
                            "process_label": S08_PROCESS_LABELS[process],
                            "cap_storage_slot": cap_storage_slot,
                        },
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            self.adapter.write(S08_DONE, cycle.process)
            cycle.phase = "await_reset"
            events.append(
                HandshakeEvent(
                    S08_CAP_ACTION,
                    "completed",
                    {
                        "process": cycle.process,
                        "process_label": S08_PROCESS_LABELS[cycle.process],
                        "cap_storage_slot": cycle.position,
                    },
                )
            )
        elif cycle.phase == "await_reset":
            if not params_written and process == 0 and cap_storage_slot == 0:
                self.adapter.write(S08_DONE, 0)
                self.adapter.write(S08_ALLOW, True)
                events.append(
                    HandshakeEvent(
                        S08_CAP_ACTION,
                        "reset",
                        {
                            "process": cycle.process,
                            "process_label": S08_PROCESS_LABELS[cycle.process],
                            "cap_storage_slot": cycle.position,
                        },
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
                cycle.position = 0
        return events

    def _step_s09(self, now: float) -> list[HandshakeEvent]:
        """模拟 S09 单工艺握手；支持 add_liquid 的 5→7→8→6 连续序列。"""

        cycle = self.s09_cycle
        events: list[HandshakeEvent] = []
        process = int(self.adapter.read(S09_PROCESS) or 0)
        params_written = bool(self.adapter.read(S09_PARAMS_WRITTEN))

        if cycle.phase == "idle":
            # S09 参数完成信号仅脉冲约 0.1 秒，网络轮询可能错过。工艺号会
            # 一直保留到 Edge 收到完成码，因此它才是可靠的接单依据。
            if process in S09_PROCESS_LABELS:
                self.adapter.write(S09_ALLOW, False)
                self.adapter.write(S09_DONE, 0)
                cycle.phase = "executing"
                cycle.process = process
                cycle.due_at = now + self.process_delay
                events.append(
                    HandshakeEvent(
                        S09_ADD_LIQUID_ACTION,
                        "accepted",
                        {
                            "process": process,
                            "process_label": S09_PROCESS_LABELS[process],
                            "params_written": params_written,
                        },
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            self.adapter.write(S09_DONE, cycle.process)
            cycle.phase = "await_reset"
            events.append(
                HandshakeEvent(
                    S09_ADD_LIQUID_ACTION,
                    "completed",
                    {
                        "process": cycle.process,
                        "process_label": S09_PROCESS_LABELS[cycle.process],
                    },
                )
            )
        elif cycle.phase == "await_reset":
            # Edge 收到完成码后会清零工艺参数，并可能立即写入下一工艺。
            # 只要观察到工艺号不再等于刚完成的工艺，就可复位完成码；
            # 下一轮/下一工艺仍需一个新的非零工艺号才会被接受。
            if process != cycle.process:
                self.adapter.write(S09_DONE, 0)
                self.adapter.write(S09_ALLOW, True)
                events.append(
                    HandshakeEvent(
                        S09_ADD_LIQUID_ACTION,
                        "reset",
                        {
                            "process": cycle.process,
                            "observed_process": process,
                        },
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
        return events


def _print_catalog(specs: tuple[WorkflowSpec, ...]) -> None:
    print(f"当前工作流数量: {len(specs)}")
    print(f"已支持动作数量: {len(SUPPORTED_ACTIONS)}")
    print()
    for spec in specs:
        print(f"[{spec.workflow_id}]")
        print("  动作:")
        for action in spec.actions:
            supported = " [已支持握手]" if action.split("(")[0] in SUPPORTED_ACTIONS else ""
            print(f"    - {action}{supported}")
        print("  先决条件:")
        for requirement in spec.requirements:
            note = f"；{requirement.note}" if requirement.note else ""
            print(
                f"    - ({requirement.kind}/{requirement.phase}) "
                f"{requirement.subject} {requirement.expectation}{note}"
            )
        print()


def _print_check(specs: tuple[WorkflowSpec, ...], adapter: VariableAdapter) -> bool:
    all_passed = True
    for spec in specs:
        print(f"[{spec.workflow_id}]")
        for requirement in spec.requirements:
            passed, actual = requirement.evaluate(adapter)
            if passed is None:
                marker = "MANUAL"
            elif passed:
                marker = "PASS"
            else:
                marker = "FAIL"
                all_passed = False
            actual_text = "" if passed is None else f"，实际={actual!r}"
            print(
                f"  {marker:6} {requirement.subject} "
                f"{requirement.expectation}{actual_text}"
            )
    return all_passed


def _event_line(event: HandshakeEvent) -> str:
    return json.dumps(
        {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": event.action,
            "phase": event.phase,
            "detail": event.detail,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("list", "check", "serve"),
        default="list",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--node-prefix", default=DEFAULT_NODE_PREFIX)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--position", type=int, default=1, help="S04 位置，1-6")
    parser.add_argument("--pump", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument(
        "--process-delay",
        type=float,
        default=5.0,
        help="确认请求后保持完成信号为 False 的秒数（默认 5 秒，确保 Edge 先读到新周期基线）",
    )
    parser.add_argument(
        "--workflow",
        choices=("all", *WORKFLOW_IDS),
        default="all",
        help="只列出/检查指定工作流；serve 时同时启用该场景所需的特殊初始化",
    )
    parser.add_argument(
        "--s06-robot-workflow",
        action="store_true",
        help="完整模拟 S06 机器人工作流：初始烧杯传感器为 False，并响应机器人任务号 11/12",
    )
    parser.add_argument(
        "--s09-pipetting-workflow",
        action="store_true",
        help="完整模拟 S09 移液工作流：初始化工位/液量，并响应工艺 5、7、8、6",
    )
    parser.add_argument(
        "--s09-remaining-volume-ml",
        type=float,
        default=100.0,
        help="S09 1-5 号液体瓶的初始余量（mL，默认 100）",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=0,
        help="完成指定数量的交互动作后退出；0 表示持续运行",
    )
    parser.add_argument(
        "--keep-state-on-exit",
        action="store_true",
        help="退出时不把仿真器负责的 PLC→PC 信号恢复为安全初始值",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    specs = build_workflow_specs(position=args.position, pump=args.pump)
    if args.workflow != "all":
        specs = tuple(spec for spec in specs if spec.workflow_id == args.workflow)
    if args.command == "list":
        _print_catalog(specs)
        return 0

    adapter = OpcUaVariableAdapter(
        args.url,
        args.node_prefix,
        username=args.username,
        password=args.password,
    )
    print(f"连接 OPC UA: {args.url}")
    adapter.connect()
    print("OPC UA 已连接")
    try:
        if args.command == "check":
            return 0 if _print_check(specs, adapter) else 2

        simulator = WorkflowHandshakeSimulator(
            adapter,
            position=args.position,
            pump=args.pump,
            process_delay=args.process_delay,
            s06_robot_workflow=args.s06_robot_workflow,
            s09_pipetting_workflow=args.s09_pipetting_workflow,
            s09_remaining_volume_ml=args.s09_remaining_volume_ml,
            workflow=args.workflow,
        )
        print(f"写入握手场景 {args.workflow!r} 的仿真先决条件...")
        simulator.initialize()
        checks = simulator.check_supported_prerequisites()
        failed = [item for item in checks if not item[1]]
        for name, passed, expected, actual in checks:
            print(
                f"  {'PASS' if passed else 'FAIL'} {name}: "
                f"expected={expected!r}, actual={actual!r}"
            )
        if failed:
            print("先决条件写入后校验失败，拒绝进入握手循环", file=sys.stderr)
            return 3

        print("握手仿真器已启动；按 Ctrl+C 停止。")
        print("S05 为只读完成信号，已保持 S05加工完成=True、S05拍照结果=1。")
        stop_requested = False

        def _request_stop(_signum: int, _frame: Any) -> None:
            nonlocal stop_requested
            stop_requested = True

        previous_sigint = signal.signal(signal.SIGINT, _request_stop)
        previous_sigterm = signal.signal(signal.SIGTERM, _request_stop)
        try:
            while not stop_requested:
                for event in simulator.step():
                    print(_event_line(event), flush=True)
                if (
                    args.max_actions > 0
                    and simulator.completed_actions >= args.max_actions
                    and simulator.all_cycles_idle()
                ):
                    print(f"已完成 {simulator.completed_actions} 个动作，退出握手循环。")
                    break
                time.sleep(max(args.poll_interval, 0.01))
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)
            if not args.keep_state_on_exit:
                print("恢复仿真器负责的 PLC→PC 信号...")
                simulator.cleanup()
        return 0
    finally:
        adapter.disconnect()
        print("OPC UA 已断开")


if __name__ == "__main__":
    raise SystemExit(main())
