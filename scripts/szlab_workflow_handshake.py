#!/usr/bin/env python3
"""独立运行的 SZLab OPC UA 工作流握手仿真器。

用途：

1. ``list``：列出仓库中全部工作流的 PLC/配置先决条件，不连接服务器。
2. ``check``：只读检查远端 OPC UA 中可自动判定的先决条件。
3. ``serve``：写入首批测试先决条件，并监听 PC→PLC 信号，模拟 PLC 握手。

首批覆盖五个工作流动作：

- ``szlab_mixer_robot.submit_place_to_s04``（机器人任务号 7）
- ``szlab_mixer_stirrer.run_stirring``
- ``szlab_mixer_robot.submit_pick_from_s04``（机器人任务号 8）
- ``szlab_mixer_photoshotting.take_photo``（当前为只读完成信号）
- ``szlab_mixer_pump.run_solvent_addition``

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

SUPPORTED_ACTIONS = (
    "szlab_mixer_robot.submit_place_to_s04",
    "szlab_mixer_stirrer.run_stirring",
    "szlab_mixer_robot.submit_pick_from_s04",
    "szlab_mixer_photoshotting.take_photo",
    "szlab_mixer_pump.run_solvent_addition",
)


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


def _manual(kind: Literal["config", "file", "parameter"], subject: str, expectation: str, *, note: str = "") -> Requirement:
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
    """返回仓库当前 12 个 Python 工作流的先决条件目录。"""

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
                _manual("config", "robot_addition_position", "> 0（当前 workflow 的 skip_robot=False）"),
                _manual("config", "robot_stirrer_position", "> 0（当前 workflow 的 skip_robot=False）"),
            ),
        ),
        WorkflowSpec(
            "szlab_mixer_pump_production",
            ("szlab_mixer_pump.run_solvent_addition",),
            (
                _opc_eq(S06_BEAKER_SENSOR, True),
                *s06_common,
                _manual("config", "robot_addition_position", "> 0（当前 workflow 的 skip_robot=False）"),
                _manual("config", "robot_stirrer_position", "> 0（当前 workflow 的 skip_robot=False）"),
            ),
        ),
    )


class OpcUaVariableAdapter:
    """使用直接 NodeId 访问 CSV 已创建变量的生产 adapter。"""

    def __init__(self, url: str, node_prefix: str, username: str = "", password: str = "") -> None:
        from opcua import Client

        self.url = url
        self.node_prefix = node_prefix
        self._client = Client(url)
        if username:
            self._client.set_user(username)
            self._client.set_password(password)
        self._nodes: dict[str, Any] = {}

    def connect(self) -> None:
        self._client.connect()

    def disconnect(self) -> None:
        self._client.disconnect()

    def _node(self, name: str) -> Any:
        node = self._nodes.get(name)
        if node is None:
            node = self._client.get_node(f"{self.node_prefix}{name}")
            self._nodes[name] = node
        return node

    def read(self, name: str) -> Any:
        return self._node(name).get_value()

    def write(self, name: str, value: Any) -> None:
        """按远端变量真实 VariantType 写 Value，不改时间戳或状态码。"""

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


class WorkflowHandshakeSimulator:
    """五个动作的独立 PLC 握手状态机 module。"""

    def __init__(
        self,
        adapter: VariableAdapter,
        *,
        position: int = 1,
        pump: int = 1,
        process_delay: float = 0.5,
    ) -> None:
        if int(position) not in range(1, 7):
            raise ValueError("position 必须在 1-6 范围内")
        if int(pump) not in (1, 2, 3):
            raise ValueError("pump 必须是 1、2 或 3")
        self.adapter = adapter
        self.position = int(position)
        self.pump = int(pump)
        self.process_delay = max(float(process_delay), 0.0)
        self.robot = _Cycle()
        self.stirrer = _Cycle(position=self.position)
        self.pump_cycle = _Cycle(process=self.pump)
        self.completed_actions = 0

    def initialization_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            ROBOT_HOME: True,
            ROBOT_WRITE_ALLOWED: True,
            ROBOT_WRITE_DONE: False,
            ROBOT_TASK_COMPLETE: 0,
            s04_sensor(self.position): False,
            s04_allow(self.position): True,
            s04_done(self.position): False,
            S05_DONE: True,
            S05_RESULT: 1,
            S06_READY: True,
            S06_ALLOW: True,
            S06_DONE: False,
            S06_BEAKER_SENSOR: True,
        }
        for index in ((1, 2) if self.pump == 3 else (self.pump,)):
            values[S06_STORAGE_BOTTLE_SENSOR[index]] = True
        return values

    def cleanup_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            ROBOT_HOME: False,
            ROBOT_WRITE_ALLOWED: False,
            ROBOT_TASK_COMPLETE: 0,
            s04_sensor(self.position): False,
            s04_allow(self.position): False,
            s04_done(self.position): False,
            S05_DONE: False,
            S05_RESULT: 0,
            S06_READY: False,
            S06_ALLOW: False,
            S06_DONE: False,
            S06_BEAKER_SENSOR: False,
        }
        for index in ((1, 2) if self.pump == 3 else (self.pump,)):
            values[S06_STORAGE_BOTTLE_SENSOR[index]] = False
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
        events: list[HandshakeEvent] = []
        events.extend(self._step_robot(now))
        events.extend(self._step_stirrer(now))
        events.extend(self._step_pump(now))
        self.completed_actions += sum(event.phase == "completed" for event in events)
        return events

    def _step_robot(self, now: float) -> list[HandshakeEvent]:
        cycle = self.robot
        events: list[HandshakeEvent] = []
        if cycle.phase == "idle":
            write_done = bool(self.adapter.read(ROBOT_WRITE_DONE))
            task = int(self.adapter.read(ROBOT_TASK_NUMBER) or 0)
            if write_done and task in (7, 8):
                position = int(self.adapter.read(S04_ROBOT_POSITION) or 0)
                if position != self.position:
                    raise RuntimeError(
                        f"机器人 S04 位置不匹配：脚本监听 {self.position}，收到 {position}"
                    )
                self.adapter.write(ROBOT_WRITE_ALLOWED, False)
                self.adapter.write(ROBOT_HOME, False)
                self.adapter.write(ROBOT_TASK_COMPLETE, 0)
                cycle.phase = "executing"
                cycle.process = task
                cycle.position = position
                cycle.due_at = now + self.process_delay
                action = (
                    SUPPORTED_ACTIONS[0]
                    if task == 7
                    else SUPPORTED_ACTIONS[2]
                )
                events.append(
                    HandshakeEvent(
                        action,
                        "accepted",
                        {"task_number": task, "position": position},
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            occupied = cycle.process == 7
            self.adapter.write(s04_sensor(cycle.position), occupied)
            self.adapter.write(ROBOT_HOME, True)
            self.adapter.write(ROBOT_TASK_COMPLETE, cycle.process)
            cycle.phase = "await_reset"
            action = SUPPORTED_ACTIONS[0] if cycle.process == 7 else SUPPORTED_ACTIONS[2]
            events.append(
                HandshakeEvent(
                    action,
                    "completed",
                    {
                        "task_number": cycle.process,
                        "position": cycle.position,
                        "occupied": occupied,
                    },
                )
            )
        elif cycle.phase == "await_reset":
            write_done = bool(self.adapter.read(ROBOT_WRITE_DONE))
            task = int(self.adapter.read(ROBOT_TASK_NUMBER) or 0)
            if not write_done and task == 0:
                self.adapter.write(ROBOT_TASK_COMPLETE, 0)
                self.adapter.write(ROBOT_WRITE_ALLOWED, True)
                events.append(
                    HandshakeEvent(
                        SUPPORTED_ACTIONS[0] if cycle.process == 7 else SUPPORTED_ACTIONS[2],
                        "reset",
                        {"task_number": cycle.process},
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
                cycle.position = 0
        return events

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
                        SUPPORTED_ACTIONS[4],
                        "accepted",
                        {"process": process},
                    )
                )
        elif cycle.phase == "executing" and now >= cycle.due_at:
            self.adapter.write(S06_DONE, True)
            cycle.phase = "await_reset"
            events.append(
                HandshakeEvent(
                    SUPPORTED_ACTIONS[4],
                    "completed",
                    {"process": cycle.process},
                )
            )
        elif cycle.phase == "await_reset":
            params_written = bool(self.adapter.read(S06_PARAMS_WRITTEN))
            process = int(self.adapter.read(S06_PROCESS) or 0)
            if not params_written and process == 0:
                self.adapter.write(S06_DONE, False)
                self.adapter.write(S06_ALLOW, True)
                events.append(
                    HandshakeEvent(
                        SUPPORTED_ACTIONS[4],
                        "reset",
                        {"process": cycle.process},
                    )
                )
                cycle.phase = "idle"
                cycle.process = 0
        return events


def _print_catalog(specs: tuple[WorkflowSpec, ...]) -> None:
    print(f"当前工作流数量: {len(specs)}")
    print(f"首批可交互动作数量: {len(SUPPORTED_ACTIONS)}")
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
    parser.add_argument("--process-delay", type=float, default=0.5)
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
        )
        print("写入首批动作的仿真先决条件...")
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
                if args.max_actions > 0 and simulator.completed_actions >= args.max_actions:
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
