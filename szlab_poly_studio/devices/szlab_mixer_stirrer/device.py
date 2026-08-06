from __future__ import annotations

import os
import time
from typing import Annotated, Any, TypedDict

from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.decorators import action, device, not_action, topic_config
from unilabos.registry.placeholder_type import ResourceSlot

from szlab_poly_studio.common.action_logging import install_action_logging
from szlab_poly_studio.common.action_phase_feedback import (
    publish_action_phase,
    publish_completion_phase,
    wait_with_action_feedback,
)
from szlab_poly_studio.common.plc_gateway import (
    PLCActionGateway,
    UnifiedPLCGatewayMixin,
)
from szlab_poly_studio.devices.szlab_mixer_stirrer.sensors import (
    S04_POSITION_RANGE,
    S04_PROCESS_MODES,
    s04_allow_var,
    s04_done_var,
    s04_duration_var,
    s04_material_sensor_var,
    s04_params_written_var,
    s04_process_var,
    s04_safe_temperature_var,
    s04_speed_var,
    s04_station_prefix,
    s04_status_var,
    s04_temperature_var,
)
from szlab_poly_studio.devices.szlab_poly_plc.device import wait_variable_true
from szlab_poly_studio.resources.materials import beaker_500ml

DEFAULT_OPCUA_URL = os.environ.get(
    "UNILABOS_SZLAB_MIXER_OPCUA_URL",
    "opc.tcp://192.168.1.10:4840/",
)


class StirBeakerStatus(TypedDict):
    success: bool
    message: str
    beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)]


@device(
    id="szlab_mixer_stirrer",
    display_name="SZLab 磁搅",
    category=["heaterstirrer"],
    description="SZLab Poly Studio S04 磁搅工位设备",
    model={
        "format": "xacro",
        "entry": "models/device.xacro",
        "macro": "szlab_mixer_stirrer",
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "models/shape.yml",
        },
    },
)
class SzlabMixerMagneticStirrerDevice(UnifiedPLCGatewayMixin):
    def __init__(
        self,
        url: str = DEFAULT_OPCUA_URL,
        username: str | None = None,
        password: str | None = None,
        csv_path: str | None = "magnetic_stirring/magnetic_stirring_nodes.csv",
        timeout: float = 300.0,
        auto_connect: bool = True,
        plc_device_id: str = "szlab_poly_plc",
        use_plc_gateway: bool = False,
        opcua_node_id_map: dict[str, str] | None = None,
        plc_gateway: Any = None,
        plc_action_timeout: float = 300.0,
        plc_server_wait_timeout: float = 10.0,
        **kwargs,
    ):
        del username, password, csv_path, auto_connect, use_plc_gateway
        del opcua_node_id_map, kwargs
        self.url = url
        self.timeout = timeout
        self._configure_plc_gateway(
            plc_device_id=plc_device_id,
            plc_gateway=plc_gateway,
            plc_action_timeout=plc_action_timeout,
            plc_server_wait_timeout=plc_server_wait_timeout,
        )
        self._status = "Idle"
        self._last_position = 0
        self._last_mode = 0

    @property
    @topic_config()
    def status(self) -> str:
        return self._status

    @topic_config(period=0.5)
    def get_material_present_position_1(self) -> bool:
        return self._material_present(1)

    @topic_config(period=0.5)
    def get_material_present_position_2(self) -> bool:
        return self._material_present(2)

    @topic_config(period=0.5)
    def get_material_present_position_3(self) -> bool:
        return self._material_present(3)

    @topic_config(period=0.5)
    def get_material_present_position_4(self) -> bool:
        return self._material_present(4)

    @topic_config(period=0.5)
    def get_material_present_position_5(self) -> bool:
        return self._material_present(5)

    @topic_config(period=0.5)
    def get_material_present_position_6(self) -> bool:
        return self._material_present(6)

    @not_action
    def _material_present(self, position: int) -> bool:
        return bool(
            self._read_variable(
                s04_material_sensor_var(position),
                use_cache=False,
            )
        )

    @not_action
    def disconnect(self) -> None:
        if self._client is not None:
            self._client.disconnect()

    @not_action
    def get_variables(self, variable_names: list[str], use_cache: bool = False) -> dict[str, dict[str, Any]]:
        if getattr(self, "_plc_gateway", None) is not None:
            values = {}
            for name in variable_names:
                try:
                    values[name] = {"success": True, "value": self._read_variable(name, use_cache=use_cache)}
                except Exception as exc:
                    values[name] = {"success": False, "error": str(exc)}
            return values
        return self._client.get_variables(variable_names, use_cache=use_cache)

    @not_action
    def get_opc_variable_metadata(self, variable_name: str) -> tuple[str, str | None]:
        if self._client is None:
            return variable_name, None
        return self._client.get_opc_variable_metadata(variable_name)

    @not_action
    def _read_variable(self, name: str, use_cache: bool = False) -> Any:
        if getattr(self, "_plc_gateway", None) is not None:
            return self._plc_gateway.read_variable(name, use_cache=use_cache)
        return self._client.read(name)

    @not_action
    def _write_variable(self, name: str, value: Any) -> None:
        if getattr(self, "_plc_gateway", None) is not None:
            self._plc_gateway.write_variable(name, value)
            return
        self._client.write(name, value)

    @not_action
    def _validate_position(self, position: int) -> int:
        position = int(position)
        if position not in S04_POSITION_RANGE:
            raise ValueError("磁搅位置必须在 1-6 范围内")
        return position

    @not_action
    def _validate_mode(self, mode: int) -> int:
        mode = int(mode)
        if mode not in S04_PROCESS_MODES:
            raise ValueError("磁搅工艺选择必须是 1(搅拌)、2(加热)、3(搅拌+加热)")
        return mode

    @not_action
    def _wait_allow_processing(self, position: int) -> bool:
        variable = s04_allow_var(position)
        return self._wait_variable_true(variable)

    @not_action
    def _wait_done(self, position: int) -> bool:
        variable = s04_done_var(position)
        waiter = getattr(self._plc_gateway, "wait_new_cycle_done", None)
        if callable(waiter):
            return waiter(variable, timeout=self.timeout, interval=0.2)
        try:
            current = bool(self._read_variable(variable, use_cache=False))
        except Exception:
            current = False
        if current and not self._wait_variable_equal(variable, False):
            return False
        return self._wait_variable_true(variable)

    @not_action
    def _wait_variable_equal(self, variable: str, expected: Any) -> bool:
        waiter = getattr(self._plc_gateway, "wait_equal", None) if self._plc_gateway is not None else None
        if callable(waiter):
            return waiter(variable, expected, timeout=self.timeout, interval=0.2)
        started_at = time.monotonic()
        while time.monotonic() - started_at <= self.timeout:
            if self._read_variable(variable, use_cache=False) == expected:
                return True
            time.sleep(0.2)
        return False

    @not_action
    def _wait_variable_true(self, variable: str) -> bool:
        waiter = getattr(self._plc_gateway, "wait_variable_true", None) if self._plc_gateway is not None else None
        if callable(waiter):
            return waiter(variable, timeout=self.timeout, interval=1.0)
        reader = self._plc_gateway if self._plc_gateway is not None else self._client
        return wait_variable_true(reader, variable, timeout=self.timeout, interval=1.0)

    @action(
        description="执行 S04 磁搅加工",
        preconditions=[
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
        ],
    )
    def run_stirring(
        self,
        position: int = 1,
        mode: int = 3,
        speed: int = 300,
        temperature: int = 25,
        duration: float = 30.0,
        safe_temperature: int = 80,
        reset: bool = False,
    ) -> dict[str, Any]:
        """
        Args:
            position[磁搅位置]: 磁搅工位编号，范围 1-6。
            mode[工艺选择]: 1=搅拌，2=加热，3=搅拌+加热。
            speed[磁搅速度]: 磁搅速度设置。
            temperature[磁搅温度]: 磁搅温度设置。
            duration[磁搅时间(s)]: 磁搅持续时间，单位秒，写入 PLC 时转换为毫秒。
            safe_temperature[安全温度]: 磁搅安全温度设置。
            reset[恢复初始值]: 为 True 时只恢复本位置 PC->PLC 参数初始值，不启动加工。
        """
        try:
            position = self._validate_position(position)
            mode = self._validate_mode(mode)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

        station = s04_station_prefix(position)
        self._status = "Running"
        if reset:
            return self._reset_pc_to_plc_defaults(position)

        material_sensor = s04_material_sensor_var(position)
        material_ready, material_actual, material_elapsed = wait_with_action_feedback(
            variable=material_sensor,
            expected=True,
            phase="waiting_precondition",
            position=position,
            timeout=float(self.timeout),
            read=lambda: self._read_variable(material_sensor, use_cache=False),
            wait=lambda: self._wait_variable_true(material_sensor),
            poll=isinstance(self._plc_gateway, PLCActionGateway),
            precondition="material_present",
        )
        if not material_ready:
            self._status = "Error"
            publish_action_phase(
                "terminal",
                position,
                "timeout",
                sensor=material_sensor,
                precondition="material_present",
                expected_value=True,
                actual_value=material_actual,
                elapsed_s=round(material_elapsed, 3),
                timeout_s=float(self.timeout),
                remaining_s=0.0,
            )
            return {
                "success": False,
                "status": "rejected",
                "message": f"{station} 等待搅拌位置物料在位超时",
                "data": {"station": station, "sensor_variable": material_sensor},
            }
        if not self._wait_variable_equal(s04_status_var(position), 1):
            self._status = "Error"
            publish_action_phase(
                "terminal",
                position,
                "timeout",
                sensor=s04_status_var(position),
                expected_value=1,
            )
            return {"success": False, "message": f"{station} 空闲状态等待超时", "data": {"station": station}}
        if not self._wait_allow_processing(position):
            self._status = "Error"
            publish_action_phase(
                "terminal",
                position,
                "timeout",
                sensor=s04_allow_var(position),
                expected_value=True,
            )
            return {"success": False, "message": f"{station} 允许加工等待超时", "data": {"station": station}}

        pre_reset_result = self._reset_pc_to_plc_defaults(position, include_params_written=False)
        if not pre_reset_result.get("success", False):
            return pre_reset_result

        duration_ms = int(float(duration) * 1000)
        publish_action_phase("writing_parameters", position, "started")
        try:
            self._write_variable(s04_process_var(position), mode)
            self._write_variable(s04_speed_var(position), int(speed))
            self._write_variable(s04_temperature_var(position), int(temperature))
            self._write_variable(s04_duration_var(position), duration_ms)
            self._write_variable(s04_safe_temperature_var(position), int(safe_temperature))
            self._write_variable(s04_params_written_var(position), True)
        except Exception as exc:
            self._reset_pc_to_plc_defaults(position)
            self._status = "Error"
            publish_action_phase("terminal", position, "failed", error=str(exc))
            return {"success": False, "message": str(exc), "data": {"station": station}}

        publish_action_phase("processing", position, "started", duration_s=float(duration))
        done = False
        wait_error: Exception | None = None
        completion_started_at = time.monotonic()
        publish_completion_phase(
            position=position,
            sensor=s04_done_var(position),
            timeout=float(self.timeout),
            elapsed=0.0,
            outcome="waiting",
            actual=None,
        )
        try:
            done = self._wait_done(position)
        except Exception as exc:
            wait_error = exc
        finally:
            reset_result = self._reset_pc_to_plc_defaults(position)
        completion_elapsed = max(0.0, time.monotonic() - completion_started_at)
        publish_completion_phase(
            position=position,
            sensor=s04_done_var(position),
            timeout=float(self.timeout),
            elapsed=completion_elapsed,
            outcome="satisfied" if done else "timeout",
            actual=True if done else None,
        )
        if wait_error is not None:
            self._status = "Error"
            publish_action_phase("terminal", position, "failed", error=str(wait_error))
            return {"success": False, "message": str(wait_error), "data": {"station": station}}
        if not done:
            self._status = "Error"
            publish_action_phase(
                "terminal",
                position,
                "timeout",
                sensor=s04_done_var(position),
                expected_value=True,
                actual_value=None,
                elapsed_s=round(completion_elapsed, 3),
                timeout_s=float(self.timeout),
                remaining_s=0.0,
            )
            return {"success": False, "message": f"{station} 加工完成等待超时", "data": {"station": station}}
        if not reset_result.get("success", False):
            return reset_result

        if not self._wait_variable_true(material_sensor):
            self._status = "Error"
            publish_action_phase(
                "terminal",
                position,
                "verification_failed",
                sensor=material_sensor,
                expected_value=True,
            )
            return {
                "success": False,
                "status": "verification_failed",
                "message": f"{station} 加工已完成，但搅拌位置物料在位验证失败",
                "data": {"station": station, "sensor_variable": material_sensor},
            }

        self._status = "Idle"
        self._last_position = position
        self._last_mode = mode
        publish_action_phase("terminal", position, "succeeded")
        return {
            "success": True,
            "message": f"{station} 磁搅加工完成，工艺 {S04_PROCESS_MODES[mode]}",
            "data": {
                "station": station,
                "position": position,
                "mode": mode,
                "mode_label": S04_PROCESS_MODES[mode],
                "speed": int(speed),
                "temperature": int(temperature),
                "duration": float(duration),
                "duration_ms": duration_ms,
                "safe_temperature": int(safe_temperature),
                "done_variable": s04_done_var(position),
                "reset": reset_result.get("data", {}),
            },
        }

    @action(description="对 S04 中的烧杯执行磁搅并显式透传物料")
    def stir_beaker(
        self,
        beaker: Annotated[ResourceSlot, AllowedResourceTemplates(beaker_500ml)],
        position: int,
        mode: int = 3,
        speed: int = 300,
        temperature: int = 25,
        duration: float = 30.0,
        safe_temperature: int = 80,
        reset: bool = False,
    ) -> StirBeakerStatus:
        result = self.run_stirring(
            position=position,
            mode=mode,
            speed=speed,
            temperature=temperature,
            duration=duration,
            safe_temperature=safe_temperature,
            reset=reset,
        )
        return {
            "success": bool(result.get("success", False)),
            "message": str(result.get("message", "")),
            "beaker": beaker,
        }

    @not_action
    def _reset_pc_to_plc_defaults(self, position: int, include_params_written: bool = True) -> dict[str, Any]:
        station = s04_station_prefix(position)
        try:
            self._write_variable(s04_process_var(position), 0)
            self._write_variable(s04_speed_var(position), 0)
            self._write_variable(s04_temperature_var(position), 0)
            self._write_variable(s04_duration_var(position), 0)
            self._write_variable(s04_safe_temperature_var(position), 0)
            if include_params_written:
                self._write_variable(s04_params_written_var(position), False)
        except Exception as exc:
            self._status = "Error"
            return {"success": False, "message": str(exc), "data": {"station": station, "reset": True}}
        self._status = "Idle"
        return {
            "success": True,
            "message": f"{station} 磁搅 PC->PLC 参数已恢复初始值",
            "data": {"station": station, "position": position, "reset": True},
        }


install_action_logging(SzlabMixerMagneticStirrerDevice)
