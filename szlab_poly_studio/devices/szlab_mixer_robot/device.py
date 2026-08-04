from __future__ import annotations

import os
import threading
import time
from typing import Annotated, Any, Literal, TypedDict

from pydantic import Field
from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.decorators import action, device, not_action
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.utils.log import logger

from szlab_poly_studio.common.action_logging import (
    compact_log_value,
    current_action_log_context,
    install_action_logging,
)
from szlab_poly_studio.common.plc_gateway import UnifiedPLCGatewayMixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S01 import SzlabRobotS01Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S02 import SzlabRobotS02Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S03 import SzlabRobotS03Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S04 import SzlabRobotS04Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S05 import SzlabRobotS05Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S06 import SzlabRobotS06Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S07 import SzlabRobotS07Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S08 import SzlabRobotS08Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S09 import SzlabRobotS09Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S10 import SzlabRobotS10Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_S11 import SzlabRobotS11Mixin
from szlab_poly_studio.devices.szlab_mixer_robot.robot_tasks import (
    ROBOT_HOME_VARIABLE,
    ROBOT_TASK_COMPLETE_VARIABLE,
    ROBOT_TASK_NUMBER_VARIABLE,
    ROBOT_WRITE_ALLOWED_VARIABLE,
    ROBOT_WRITE_DONE_VARIABLE,
)
from szlab_poly_studio.devices.szlab_mixer_robot.standard_gateway import SZLabStandardRobotGateway
from szlab_poly_studio.resources.materials import beaker_500ml, sample_vial_250ml

_UNSET = object()


class StandardRobotActionStatus(TypedDict):
    """A1 command status shared by transfer and query actions."""

    command_id: str
    state: Literal[
        "ACCEPTED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
        "UNKNOWN",
        "REJECTED",
    ]
    success: bool
    message: str
    boot_id: str


class StandardRobotTransferStatus(TypedDict):
    """Successful or failed physical transfer with explicit material passthrough."""

    command_id: str
    state: Literal[
        "ACCEPTED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
        "UNKNOWN",
        "REJECTED",
    ]
    success: bool
    message: str
    boot_id: str
    resource: ResourceSlot


class BeakerRobotTransferStatus(TypedDict):
    command_id: str
    state: Literal[
        "ACCEPTED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
        "UNKNOWN",
        "REJECTED",
    ]
    success: bool
    message: str
    boot_id: str
    beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)]


class BeakerActionStatus(TypedDict):
    success: bool
    message: str


class PourBeakerIntoVialStatus(TypedDict):
    success: bool
    message: str
    beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)]
    sample_vial: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(sample_vial_250ml),
    ]


@device(
    id="szlab_mixer_robot",
    display_name="SZLab Mixer 机器人任务",
    category=["robotic_arm"],
    description="SZLab Mixer 机器人任务设备，负责向 PLC 下发 S01-S11 取放料任务号",
    model={
        "format": "xacro",
        "entry": "models/device.xacro",
        "macro": "szlab_mixer_robot",
        # 交点=导轨左端；FE 默认按底面中心补半占位，需跳过。
        "model_origin": "bottom_left",
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "models/shape.yml",
        },
    },
)
class SzlabMixerRobotDevice(
    UnifiedPLCGatewayMixin,
    SzlabRobotS01Mixin,
    SzlabRobotS02Mixin,
    SzlabRobotS03Mixin,
    SzlabRobotS04Mixin,
    SzlabRobotS05Mixin,
    SzlabRobotS06Mixin,
    SzlabRobotS07Mixin,
    SzlabRobotS08Mixin,
    SzlabRobotS09Mixin,
    SzlabRobotS10Mixin,
    SzlabRobotS11Mixin,
):
    def __init__(
        self,
        plc_device_id: str = "szlab_poly_plc",
        timeout: float = 300.0,
        write_allowed_timeout: float = 5.0,
        poll_interval: float = 1.0,
        write_done_hold_seconds: float = 0.0,
        write_readback_timeout: float = 3.0,
        plc_gateway: Any = None,
        plc_action_timeout: float = 300.0,
        plc_server_wait_timeout: float = 10.0,
        standard_actions_enabled: bool = False,
        standard_journal_path: str = "runtime/szlab_robot_commands.sqlite3",
        standard_program_version: str = "szlab-mixer-plc@0730",
        standard_point_set_version: str = "szlab-mixer-points@0730",
        standard_payload_profiles: list[str] | None = None,
        standard_motion_permit_variable: str = ROBOT_WRITE_ALLOWED_VARIABLE,
        standard_permit_asserts_remote_auto: bool = False,
        standard_permit_asserts_safety_normal: bool = False,
        standard_tool_payload_sensor_variable: str = "传感器状态_上位机[3].NO[6]",
        *args,
        **kwargs,
    ):
        self.timeout = float(timeout)
        self.write_allowed_timeout = float(write_allowed_timeout)
        self.poll_interval = float(poll_interval)
        self.write_done_hold_seconds = float(write_done_hold_seconds)
        self.write_readback_timeout = float(write_readback_timeout)
        self._configure_plc_gateway(
            plc_device_id=plc_device_id,
            plc_gateway=plc_gateway,
            plc_action_timeout=plc_action_timeout,
            plc_server_wait_timeout=plc_server_wait_timeout,
        )
        self._last_task: dict[str, Any] = {}
        self._standard_gateway_config = {
            "journal_path": standard_journal_path,
            "program_version": standard_program_version,
            "point_set_version": standard_point_set_version,
            "payload_profiles": standard_payload_profiles
            or [
                "beaker_500ml@v1",
                "tip_box@v1",
                "powder_container@v1",
                "sample_vial_250ml@v1",
                "sample_vial_500ml@v1",
                "liquid_reagent_bottle_100ml@v1",
                "pipette_tip@v1",
            ],
            "actions_enabled": standard_actions_enabled,
            "permit_asserts_remote_auto": standard_permit_asserts_remote_auto,
            "permit_asserts_safety_normal": standard_permit_asserts_safety_normal,
            "motion_permit_variable": standard_motion_permit_variable,
            "tool_payload_sensor_variable": standard_tool_payload_sensor_variable,
        }
        self._standard_gateway_instance: SZLabStandardRobotGateway | None = None
        self._standard_gateway_lock = threading.Lock()

    @not_action
    def _standard_gateway(self) -> SZLabStandardRobotGateway:
        if self._standard_gateway_instance is None:
            with self._standard_gateway_lock:
                if self._standard_gateway_instance is None:
                    self._standard_gateway_instance = SZLabStandardRobotGateway(
                        self,
                        **self._standard_gateway_config,
                    )
        return self._standard_gateway_instance

    @not_action
    def _write_variable(self, name: str, value: Any) -> None:
        if self._plc_gateway is None:
            raise RuntimeError("机器人任务需要注入 szlab_poly_plc 网关")
        self._plc_gateway.write_variable(name, value)

    @not_action
    def _read_variable(self, name: str, use_cache: bool = False) -> Any:
        if self._plc_gateway is None:
            raise RuntimeError("机器人任务需要注入 szlab_poly_plc 网关")
        return self._plc_gateway.read_variable(name, use_cache=use_cache)

    @not_action
    def _wait_variable_equal(
        self,
        name: str,
        expected: Any,
        timeout: float,
        interval: float | None = None,
    ) -> bool:
        waiter = getattr(self._plc_gateway, "wait_variable_equal", None) if self._plc_gateway is not None else None
        if callable(waiter):
            return bool(waiter(name, expected, timeout=timeout, interval=interval or self.poll_interval))

        started_at = time.time()
        poll_interval = self.poll_interval if interval is None else interval
        while time.time() - started_at <= timeout:
            if self._read_variable(name, use_cache=False) == expected:
                return True
            time.sleep(poll_interval)
        return False

    @not_action
    def _wait_variable_truthy(self, name: str, timeout: float, interval: float | None = None) -> tuple[bool, Any]:
        started_at = time.monotonic()
        poll_interval = self.poll_interval if interval is None else interval
        last_value: Any = _UNSET
        last_log_at = started_at
        context = current_action_log_context()
        logger.info(
            f"[SZLAB-STEP] WAIT {context} description=等待机器人握手非零 "
            f"variable={name} expected=truthy timeout={float(timeout):.3f}s "
            f"interval={float(poll_interval):.3f}s"
        )
        while time.monotonic() - started_at <= timeout:
            try:
                value = self._read_variable(name, use_cache=False)
            except Exception as exc:
                elapsed = time.monotonic() - started_at
                logger.error(
                    f"[SZLAB-STEP] WAIT-ERROR {context} variable={name} "
                    f"expected=truthy elapsed={elapsed:.3f}s "
                    f"cause={type(exc).__name__}: {exc}"
                )
                raise
            now = time.monotonic()
            if last_value is _UNSET or value != last_value or now - last_log_at >= 10.0:
                logger.info(
                    f"[SZLAB-STEP] WAIT-OBSERVED {context} variable={name} "
                    f"expected=truthy actual={compact_log_value(value)} "
                    f"elapsed={now - started_at:.3f}s"
                )
                last_value = value
                last_log_at = now
            if bool(value):
                logger.info(
                    f"[SZLAB-STEP] WAIT-SUCCESS {context} variable={name} "
                    f"expected=truthy actual={compact_log_value(value)} "
                    f"elapsed={now - started_at:.3f}s"
                )
                return True, value
            time.sleep(poll_interval)
        logger.error(
            f"[SZLAB-STEP] WAIT-TIMEOUT {context} variable={name} "
            f"expected=truthy last_actual={compact_log_value(last_value)} "
            f"elapsed={time.monotonic() - started_at:.3f}s"
        )
        return False, last_value

    @not_action
    def _ensure_sensor_gate(self, sensor_variable: str, expected: bool, message: str) -> dict[str, Any] | None:
        if os.environ.get("SKIP_SENSOR_PRECHECK") == "1":
            return None
        if not sensor_variable:
            return {"success": False, "message": "缺少精确传感器变量，不能执行机器人取放料动作"}
        if self._should_skip_robot_precheck_variable(sensor_variable):
            return None
        actual = bool(self._read_variable(sensor_variable, use_cache=False))
        logger.info(
            f"[SZLAB-STEP] CHECK {current_action_log_context()} "
            f"description=机器人动作传感器前置检查 variable={sensor_variable} "
            f"expected={expected!r} actual={actual!r}"
        )
        if actual == expected:
            return None
        return {
            "success": False,
            "message": message,
            "sensor_variable": sensor_variable,
            "expected": expected,
            "actual": actual,
        }

    @not_action
    def _slot_number(self, position: str | int) -> int:
        if isinstance(position, int):
            return position
        row_text, col_text = str(position).split("-", maxsplit=1)
        row = int(row_text)
        col = int(col_text)
        if row < 1 or col < 1:
            raise ValueError(f"位置编号必须从 1 开始: {position}")
        return (row - 1) * 6 + col

    @not_action
    def _should_skip_robot_precheck_variable(self, variable_name: str) -> bool:
        raw_variables = os.environ.get("SKIP_ROBOT_PRECHECK_VARIABLES", "")
        skipped_variables = {item.strip() for item in raw_variables.replace(";", ",").split(",") if item.strip()}
        return variable_name in skipped_variables

    @not_action
    def _run_robot_handshake_precheck(self, target_station: str) -> dict[str, Any]:
        if os.environ.get("SKIP_ROBOT_HANDSHAKE_CHECK") == "1":
            return {
                "target_station": target_station,
                "skipped": True,
                "message": "已跳过 Robot_Home 和 Robot_任务允许写入前置检查",
            }

        status: dict[str, Any] = {
            "target_station": target_station,
            ROBOT_HOME_VARIABLE: None,
            ROBOT_WRITE_ALLOWED_VARIABLE: None,
        }
        if self._should_skip_robot_precheck_variable(ROBOT_HOME_VARIABLE):
            status[ROBOT_HOME_VARIABLE] = "skipped"
        else:
            home_value = bool(self._read_variable(ROBOT_HOME_VARIABLE, use_cache=False))
            status[ROBOT_HOME_VARIABLE] = home_value
            if not home_value:
                raise RuntimeError("Robot_Home 未确认，不能提交机器人任务")

        allowed, allowed_value = self._wait_variable_truthy(
            ROBOT_WRITE_ALLOWED_VARIABLE,
            timeout=self.write_allowed_timeout,
            interval=self.poll_interval,
        )
        status[ROBOT_WRITE_ALLOWED_VARIABLE] = allowed_value
        if not allowed:
            raise RuntimeError(f"等待 {ROBOT_WRITE_ALLOWED_VARIABLE} 为 True 超时")
        return status

    @not_action
    def _wait_robot_task_complete(self) -> tuple[bool, str, Any]:
        if os.environ.get("SKIP_ROBOT_HANDSHAKE_CHECK") == "1":
            return True, "已跳过 Robot_任务完成等待", None
        success, value = self._wait_variable_truthy(
            ROBOT_TASK_COMPLETE_VARIABLE,
            timeout=self.timeout,
            interval=self.poll_interval,
        )
        if success:
            return True, f"{ROBOT_TASK_COMPLETE_VARIABLE} 已非 0", value
        return False, f"等待 {ROBOT_TASK_COMPLETE_VARIABLE} 非 0 超时", value

    @not_action
    def _reset_pc_to_plc_variables(self, reset_variables: dict[str, Any]) -> dict[str, Any]:
        reset_writes: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, value in reset_variables.items():
            try:
                self._write_variable(name, value)
                reset_writes[name] = value
            except Exception as exc:
                errors[name] = str(exc)
        return {
            "success": not errors,
            "written_variables": reset_writes,
            "errors": errors,
        }

    @not_action
    def _ensure_written_variables_nonzero(self, written_variables: dict[str, Any]) -> dict[str, Any]:
        names = [name for name in written_variables if name != ROBOT_WRITE_DONE_VARIABLE]
        started_at = time.time()
        readback: dict[str, Any] = {name: None for name in names}
        zero_variables: dict[str, Any] = dict(readback)
        while True:
            zero_variables = {}
            for name in names:
                value = self._read_variable(name, use_cache=False)
                readback[name] = value
                if not bool(value):
                    zero_variables[name] = value
            if not zero_variables:
                return readback
            if time.time() - started_at >= self.write_readback_timeout:
                break
            time.sleep(min(self.poll_interval, 0.2))
        if zero_variables:
            raise RuntimeError(f"机器人任务参数未写入成功，仍为 0: {zero_variables}")
        return readback

    @not_action
    def _submit_robot_task(
        self,
        task: str,
        station: str,
        task_number: int,
        variables: dict[str, Any] | None = None,
        reset_variables: dict[str, Any] | None = None,
        precheck=None,
        **data: Any,
    ) -> dict[str, Any]:
        reset_variables = reset_variables or {ROBOT_TASK_NUMBER_VARIABLE: 0}
        if precheck is not None:
            precheck_result = precheck()
            if precheck_result is not None:
                self._last_task = {**precheck_result, "status": "rejected"}
                return precheck_result

        try:
            handshake_precheck = self._run_robot_handshake_precheck(station)
        except Exception as exc:
            message = str(exc)
            self._last_task = {
                "task": task,
                "station": station,
                "task_number": int(task_number),
                "status": "rejected",
                "handshake_message": message,
                **data,
            }
            return {"success": False, "message": message, **self._last_task}

        written_variables: dict[str, Any] = {}
        try:
            for name, value in (variables or {}).items():
                int_value = int(value)
                self._write_variable(name, int_value)
                written_variables[name] = int_value
            self._write_variable(ROBOT_TASK_NUMBER_VARIABLE, int(task_number))
            written_variables[ROBOT_TASK_NUMBER_VARIABLE] = int(task_number)
            self._write_variable(ROBOT_WRITE_DONE_VARIABLE, False)
            written_variables[ROBOT_WRITE_DONE_VARIABLE] = False
            write_readback = self._ensure_written_variables_nonzero(written_variables)
            self._write_variable(ROBOT_WRITE_DONE_VARIABLE, True)
            written_variables[ROBOT_WRITE_DONE_VARIABLE] = True
            if self.write_done_hold_seconds > 0:
                time.sleep(self.write_done_hold_seconds)
        except Exception as exc:
            rollback_variables = {
                ROBOT_WRITE_DONE_VARIABLE: False,
                **{name: reset_variables[name] for name in written_variables if name in reset_variables},
            }
            reset_result = self._reset_pc_to_plc_variables(rollback_variables)
            self._last_task = {
                "task": task,
                "station": station,
                "task_number": int(task_number),
                "status": "write_failed",
                "written_variables": written_variables,
                "handshake_precheck": handshake_precheck,
                "reset": reset_result,
                **data,
            }
            return {"success": False, "message": str(exc), **self._last_task}

        complete_success, complete_message, complete_value = self._wait_robot_task_complete()
        if os.environ.get("SKIP_RESET_AFTER_RUN") == "1":
            try:
                self._write_variable(ROBOT_WRITE_DONE_VARIABLE, False)
            except Exception:
                pass
            reset_result = {
                "success": True,
                "written_variables": {ROBOT_WRITE_DONE_VARIABLE: False},
                "errors": {},
                "skipped": True,
                "message": "已跳过任务完成后的参数复位，仅复位 Robot_任务写入完成",
            }
        else:
            reset_result = self._reset_pc_to_plc_variables({ROBOT_WRITE_DONE_VARIABLE: False, **reset_variables})
        status = "completed" if complete_success and reset_result["success"] else "failed"

        self._last_task = {
            "task": task,
            "station": station,
            "task_number": int(task_number),
            "status": status,
            "written_variables": written_variables,
            "write_readback": write_readback,
            "completion_variable": ROBOT_TASK_COMPLETE_VARIABLE,
            "completion_value": complete_value,
            "completion_message": complete_message,
            "handshake_precheck": handshake_precheck,
            "reset": reset_result,
            **data,
        }
        if not complete_success:
            return {
                "success": False,
                "message": complete_message,
                **self._last_task,
            }
        if not reset_result["success"]:
            return {
                "success": False,
                "message": "机器人任务已完成，但 PC->PLC 变量复位失败",
                **self._last_task,
            }
        return {
            "success": True,
            "message": f"机器人任务已完成: {station} {task}",
            **self._last_task,
        }

    @action(
        description="标准物理取料：父 Warehouse + 局部 Site 寻址；不修改 OS 物料归属"
    )
    def pick(
        self,
        resource: ResourceSlot,
        warehouse: ResourceSlot,
        site: str,
    ) -> StandardRobotTransferStatus:
        result = self._standard_gateway().execute_site(
            kind="pick",
            resource=resource,
            warehouse=warehouse,
            site=site,
        )
        return {**result, "resource": resource}

    @action(
        description=(
            "标准物理放料：父 Warehouse + 局部 Site 寻址；成功后调用 "
            "host.transfer_resource(resource, target_device, warehouse, site) 记账"
        )
    )
    def place(
        self,
        resource: ResourceSlot,
        warehouse: ResourceSlot,
        site: str,
    ) -> StandardRobotTransferStatus:
        result = self._standard_gateway().execute_site(
            kind="place",
            resource=resource,
            warehouse=warehouse,
            site=site,
        )
        return {**result, "resource": resource}

    @action(description="标准物理取 500 mL 烧杯；保留精确 ResourceSlot 模板约束")
    def pick_beaker(
        self,
        beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)],
        warehouse: ResourceSlot,
        site: str,
    ) -> BeakerRobotTransferStatus:
        result = self._standard_gateway().execute_site(
            kind="pick",
            resource=beaker,
            warehouse=warehouse,
            site=site,
        )
        return {**result, "beaker": beaker}

    @action(always_free=True, description="查询标准机械臂命令；不会重新下发运动")
    def get_command(self, command_id: str) -> StandardRobotActionStatus:
        return self._standard_gateway().get_command(command_id)

    @action(always_free=True, description="按 PLC 与物料传感器见证对账；不会重新下发运动")
    def reconcile(self, command_id: str) -> StandardRobotActionStatus:
        return self._standard_gateway().reconcile(command_id)

    @action(description="从 S03 取出 500 mL 烧杯（旧工作流兼容入口）")
    def pick_beaker_from_s03(
        self,
        beaker: Annotated[
            ResourceSlot,
            AllowedResourceTemplates(beaker_500ml),
            Field(description="当前位于 S03 的 500 mL 烧杯"),
        ],
        product_type: int = 1,
        position: str = "1-1",
    ) -> BeakerActionStatus:
        result = self._run_s03_pick(product_type=product_type, position=position)
        return {"success": bool(result.get("success")), "message": str(result.get("message", ""))}

    @action(description="将 500 mL 烧杯放入 S06（旧工作流兼容入口）")
    def place_beaker_to_s06(
        self,
        beaker: Annotated[
            ResourceSlot,
            AllowedResourceTemplates(beaker_500ml),
            Field(description="待放入 S06 的 500 mL 烧杯"),
        ],
    ) -> BeakerActionStatus:
        result = self._run_s06_place()
        return {"success": bool(result.get("success")), "message": str(result.get("message", ""))}

    @action(description="从 S06 取回 500 mL 烧杯（旧工作流兼容入口）")
    def pick_beaker_from_s06(
        self,
        beaker: Annotated[
            ResourceSlot,
            AllowedResourceTemplates(beaker_500ml),
            Field(description="当前位于 S06 的 500 mL 烧杯"),
        ],
    ) -> BeakerActionStatus:
        result = self._run_s06_pick()
        return {"success": bool(result.get("success")), "message": str(result.get("message", ""))}

    @action(description="S01 取料")
    def submit_pick_from_s01(
        self,
        product_type: int = 1,
        position: int = 1,
    ) -> dict[str, Any]:
        try:
            return self._run_s01_pick(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S01", "position": position}

    @action(description="S02 放 TIP")
    def submit_place_to_s02(self, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s02_place(position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S02", "position": position}

    @action(description="S02 取 TIP")
    def submit_pick_from_s02(self, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s02_pick(position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S02", "position": position}

    @action(description="S03 放容器")
    def submit_place_to_s03(self, product_type: int = 1, position: str = "1-1") -> dict[str, Any]:
        try:
            return self._run_s03_place(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S03", "position": position}

    @action(description="S03 取容器")
    def submit_pick_from_s03(self, product_type: int = 1, position: str = "1-1") -> dict[str, Any]:
        try:
            return self._run_s03_pick(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S03", "position": position}

    @action(description="S04 放料")
    def submit_place_to_s04(self, position: int = 1, sample_id: str = "") -> dict[str, Any]:
        try:
            return self._run_s04_place(position=position, sample_id=sample_id)
        except Exception as exc:
            return {
                "success": False,
                "message": str(exc),
                "task": "place",
                "station": "S04",
                "position": position,
                "sample_id": sample_id,
            }

    @action(description="S04 取料")
    def submit_pick_from_s04(self, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s04_pick(position=position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S04", "position": position}

    @action(description="S05 放料")
    def submit_place_to_s05(self, sample_id: str = "") -> dict[str, Any]:
        try:
            return self._run_s05_place(sample_id=sample_id)
        except Exception as exc:
            return {
                "success": False,
                "message": str(exc),
                "task": "place",
                "station": "S05",
                "sample_id": sample_id,
            }

    @action(description="S05 取料")
    def submit_pick_from_s05(self, sample_id: str = "") -> dict[str, Any]:
        try:
            return self._run_s05_pick(sample_id=sample_id)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S05", "sample_id": sample_id}

    @action(description="S06 放料")
    def submit_place_to_s06(self) -> dict[str, Any]:
        try:
            return self._run_s06_place()
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S06"}

    @action(description="S06 取料")
    def submit_pick_from_s06(self) -> dict[str, Any]:
        try:
            return self._run_s06_pick()
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S06"}

    @action(description="S071 放粉罐")
    def submit_place_to_s071(self, position: str = "1-1") -> dict[str, Any]:
        try:
            return self._run_s071_place(position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S071", "position": position}

    @action(description="S071 取粉罐")
    def submit_pick_from_s071(self, position: str = "1-1") -> dict[str, Any]:
        try:
            return self._run_s071_pick(position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S071", "position": position}

    @action(description="S072 放料")
    def submit_place_to_s072(self, product_type: int = 1, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s072_place(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S072", "position": position}

    @action(description="S072 取料")
    def submit_pick_from_s072(self, product_type: int = 1, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s072_pick(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S072", "position": position}

    @action(description="S08 放瓶")
    def submit_place_to_s08(
        self,
        product_type: int = 1,
        position: int = 1,
    ) -> dict[str, Any]:
        try:
            return self._run_s08_place(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S08", "position": position}

    @action(description="S08 取瓶")
    def submit_pick_from_s08(
        self,
        product_type: int = 1,
        position: int = 1,
    ) -> dict[str, Any]:
        try:
            return self._run_s08_pick(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S08", "position": position}

    @action(description="S08 倒料")
    def submit_pour_from_s08(self, product_type: int = 1) -> dict[str, Any]:
        try:
            return self._run_s08_pour(product_type)
        except Exception as exc:
            return {
                "success": False,
                "message": str(exc),
                "task": "pour",
                "station": "S08",
                "product_type": product_type,
            }

    @action(description="将机械臂持有的 500 mL 烧杯倒入 S08 的 250 mL 样品瓶")
    def pour_beaker_into_vial(
        self,
        beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)],
        sample_vial: Annotated[
            ResourceSlot,
            AllowedResourceTemplates(sample_vial_250ml),
        ],
        sample_vial_site: str,
    ) -> PourBeakerIntoVialStatus:
        if str(sample_vial_site).strip().upper() != "S081":
            return {
                "success": False,
                "message": "250 mL 样品瓶倒料位必须是 S081",
                "beaker": beaker,
                "sample_vial": sample_vial,
            }
        result = self.submit_pour_from_s08(product_type=1)
        return {
            "success": bool(result.get("success", False)),
            "message": str(result.get("message", "")),
            "beaker": beaker,
            "sample_vial": sample_vial,
        }

    @action(description="S09 放料")
    def submit_place_to_s09(self, product_type: int = 1, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s09_place(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S09", "position": position}

    @action(description="S09 取料")
    def submit_pick_from_s09(self, product_type: int = 1, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s09_pick(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S09", "position": position}

    @action(description="S10 放试剂瓶")
    def submit_place_to_s10(self, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s10_place(position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S10", "position": position}

    @action(description="S10 取试剂瓶")
    def submit_pick_from_s10(self, position: int = 1) -> dict[str, Any]:
        try:
            return self._run_s10_pick(position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S10", "position": position}

    @action(description="S11 放成品")
    def submit_place_to_s11(self, product_type: int = 1, position: str = "1-1") -> dict[str, Any]:
        try:
            return self._run_s11_place(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "place", "station": "S11", "position": position}

    @action(description="S11 取成品")
    def submit_pick_from_s11(self, product_type: int = 1, position: str = "1-1") -> dict[str, Any]:
        try:
            return self._run_s11_pick(product_type, position)
        except Exception as exc:
            return {"success": False, "message": str(exc), "task": "pick", "station": "S11", "position": position}

    @action(description="读取最近一次机器人任务提交记录")
    def last_submitted_task(self) -> dict[str, Any]:
        return {"success": True, "task": self._last_task}


install_action_logging(SzlabMixerRobotDevice)
