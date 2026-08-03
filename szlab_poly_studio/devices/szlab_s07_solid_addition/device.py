"""SZLab S07 固体加料工位设备驱动。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any, TypedDict

from pydantic import Field
from unilabos.registry.annotations import AllowedResourceTemplates, JSONValue
from unilabos.registry.decorators import action, device, not_action
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.utils.log import logger

from szlab_poly_studio.common.action_logging import (
    compact_log_value,
    current_action_log_context,
    install_action_logging,
)
from szlab_poly_studio.common.plc_gateway import UnifiedPLCGatewayMixin
from szlab_poly_studio.devices.szlab_s07_solid_addition.sensors import (
    NODE_ALLOW_PROCESS,
    NODE_COARSE_POSITION,
    NODE_COARSE_SHAKE_MAX_SPEED,
    NODE_FINE_POSITION,
    NODE_FINE_SHAKE_MAX_SPEED,
    NODE_HOME,
    NODE_LOAD_POSITION,
    NODE_PARAMS_WRITTEN,
    NODE_PROCESS_COMPLETE,
    NODE_PROCESS_SELECT,
    NODE_TARGET_WEIGHT,
    POSITION_RANGE,
    PROCESS_DOSE_POWDER,
    PROCESS_ROTATE_TO_FEED,
    PROCESS_SCAN_CARTRIDGES,
    iter_s07_powder_param_vars,
    normalize_powder_params,
    s07_powder_param_var,
    s07_qr_code_var,
)
from szlab_poly_studio.resources.materials import beaker_500ml, powder_container

DEFAULT_POWDER_PARAMS_PATH = Path(__file__).resolve().parent / "s07_powder_params.json"


class PowderSitePreparationStatus(TypedDict):
    """粉桶 ResourceSlot 由同名输入端口透传。"""

    success: bool
    message: str
    powder_site: str


class PowderDoseWithMaterialsStatus(TypedDict):
    """两项物料均由同名 ResourceSlot 输入端口透传。"""

    success: bool
    message: str
    commanded_mass_g: float


@device(
    id="szlab_s07_solid_addition",
    display_name="S07 固体加料工位",
    category=["workstation", "szlab"],
    description="苏州实验室 S07 固体加料工位，通过 szlab_poly_plc 转发 PLC 读写",
    model={
        "shape": {
            "format": "unilab.shape/v1",
            "entry": "models/shape.yml",
        },
    },
)
class SZLabS07SolidAdditionDevice(UnifiedPLCGatewayMixin):
    def __init__(
        self,
        plc_device_id: str = "szlab_poly_plc",
        plc_action_timeout: float = 30.0,
        process_timeout: float = 300.0,
        poll_interval: float = 0.2,
        require_station_ready: bool = True,
        plc_gateway: Any = None,
        plc_server_wait_timeout: float = 10.0,
        *args,
        **kwargs,
    ):
        self._configure_plc_gateway(
            plc_device_id=plc_device_id,
            plc_gateway=plc_gateway,
            plc_action_timeout=max(plc_action_timeout, process_timeout),
            plc_server_wait_timeout=plc_server_wait_timeout,
        )
        self.process_timeout = process_timeout
        self.poll_interval = poll_interval
        self.require_station_ready = require_station_ready

    @not_action
    def _read_plc_variable(self, node_name: str) -> Any:
        return self._plc_gateway.read_variable(node_name, use_cache=False)

    @not_action
    def _write_plc_variable(self, node_name: str, value: Any) -> None:
        self._plc_gateway.write_variable(node_name, value)

    @not_action
    def _wait_plc_bool(self, node_name: str, expected: bool, timeout: float, description: str) -> bool:
        context = current_action_log_context()
        logger.info(
            f"[SZLAB-STEP] WAIT {context} description={description} "
            f"variable={node_name} expected={expected!r} timeout={float(timeout):.3f}s"
        )
        waiter = getattr(self._plc_gateway, "wait_variable_equal", None)
        if callable(waiter):
            completed = bool(
                waiter(
                    node_name,
                    expected,
                    timeout=timeout,
                    interval=self.poll_interval,
                )
            )
        else:
            started_at = time.monotonic()
            completed = False
            while time.monotonic() - started_at < timeout:
                if bool(self._read_plc_variable(node_name)) is expected:
                    completed = True
                    break
                time.sleep(self.poll_interval)
        try:
            actual = self._read_plc_variable(node_name)
        except Exception as exc:
            actual = f"<read failed: {type(exc).__name__}: {exc}>"
        log_method = logger.info if completed else logger.error
        state = "WAIT-SUCCESS" if completed else "WAIT-TIMEOUT"
        log_method(
            f"[SZLAB-STEP] {state} {context} description={description} "
            f"variable={node_name} expected={expected!r} "
            f"actual={compact_log_value(actual)} timeout={float(timeout):.3f}s"
        )
        return completed

    @not_action
    def _wait_process_complete(self, expected: int, timeout: float) -> bool:
        context = current_action_log_context()
        logger.info(
            f"[SZLAB-STEP] WAIT {context} description=等待 S07 工艺完成 "
            f"variable={NODE_PROCESS_COMPLETE} expected={expected} "
            f"timeout={float(timeout):.3f}s"
        )
        waiter = getattr(self._plc_gateway, "wait_variable_equal", None)
        if callable(waiter):
            completed = bool(
                waiter(
                    NODE_PROCESS_COMPLETE,
                    expected,
                    timeout=timeout,
                    interval=self.poll_interval,
                )
            )
        else:
            started_at = time.monotonic()
            completed = False
            while time.monotonic() - started_at < timeout:
                if int(self._read_plc_variable(NODE_PROCESS_COMPLETE) or 0) == expected:
                    completed = True
                    break
                time.sleep(self.poll_interval)
        try:
            actual = self._read_plc_variable(NODE_PROCESS_COMPLETE)
        except Exception as exc:
            actual = f"<read failed: {type(exc).__name__}: {exc}>"
        log_method = logger.info if completed else logger.error
        state = "WAIT-SUCCESS" if completed else "WAIT-TIMEOUT"
        log_method(
            f"[SZLAB-STEP] {state} {context} description=等待 S07 工艺完成 "
            f"variable={NODE_PROCESS_COMPLETE} expected={expected} "
            f"actual={compact_log_value(actual)} timeout={float(timeout):.3f}s"
        )
        return completed

    @not_action
    def _reset_unilab_written_params(
        self,
        process_id: int,
        *,
        reset_payload: bool = True,
    ) -> None:
        for node, value in (
            (NODE_PROCESS_SELECT, 0),
            (NODE_PARAMS_WRITTEN, False),
        ):
            self._write_plc_variable(node, value)
        if not reset_payload:
            return
        if process_id == PROCESS_ROTATE_TO_FEED:
            self._write_plc_variable(NODE_LOAD_POSITION, 0)
        elif process_id == PROCESS_DOSE_POWDER:
            for node, value in (
                (NODE_COARSE_POSITION, 0),
                (NODE_FINE_POSITION, 0),
                (NODE_TARGET_WEIGHT, 0.0),
            ):
                self._write_plc_variable(node, value)
            for node, value in iter_s07_powder_param_vars():
                self._write_plc_variable(node, value)

    @not_action
    def _run_s07_process(self, process_id: int, timeout: float) -> dict[str, Any]:
        timeout = self.process_timeout if timeout is None else timeout
        if self.require_station_ready and not self._wait_plc_bool(NODE_HOME, True, timeout, "S07 原点信号"):
            return {"success": False, "message": "等待 S07 原点信号超时"}
        if not self._wait_plc_bool(NODE_ALLOW_PROCESS, True, timeout, "S07 允许加工"):
            return {"success": False, "message": "等待 S07 允许加工超时"}
        self._write_plc_variable(NODE_PROCESS_SELECT, process_id)
        self._write_plc_variable(NODE_PARAMS_WRITTEN, True)
        if not self._wait_process_complete(process_id, timeout):
            self._reset_unilab_written_params(process_id)
            return {"success": False, "message": f"等待 S07 工艺完成超时（期望 {process_id}）"}
        self._reset_unilab_written_params(process_id)
        return {"success": True, "process_type": process_id, "status": {"process_complete": process_id}}

    @not_action
    def _read_qr_codes(self) -> dict[int, list[int]]:
        return {
            position: [int(self._read_plc_variable(s07_qr_code_var(position, index)) or 0) for index in range(30)]
            for position in POSITION_RANGE
        }

    @not_action
    def _write_powder_params(self, kind: str, params: dict[str, Any], shake_node: str) -> None:
        normalized = normalize_powder_params(params)
        field_map = {
            "opening": "开口量",
            "feed_speed": "落粉匀速",
            "rotation_speed": "旋转速度",
            "stop_amount": "提请停止量",
        }
        for key, field in field_map.items():
            for index, value in enumerate(normalized[key]):  # type: ignore[index]
                self._write_plc_variable(s07_powder_param_var(kind, field, index), value)
        self._write_plc_variable(shake_node, normalized["shake_max_speed"])

    @not_action
    def _load_powder_params_from_json(
        self, params_json: str | None, recipe_name: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        path = Path(params_json or DEFAULT_POWDER_PARAMS_PATH)
        data = json.loads(path.read_text(encoding="utf-8"))
        if recipe_name not in data:
            raise ValueError(f"注粉参数 JSON 中未找到 recipe: {recipe_name}")
        recipe = data[recipe_name]
        return dict(recipe.get("coarse_params", {})), dict(recipe.get("fine_params", {}))

    @not_action
    def _merge_powder_params(self, base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(base)
        if override:
            merged.update(override)
        return merged

    @not_action
    def _powder_position_from_site(self, powder_site: str | int) -> int:
        value = str(powder_site).strip().upper()
        if value.startswith("P"):
            value = value[1:]
        if not value.isdigit():
            raise ValueError("powder_site 必须是 P01..P10 或 1..10")
        position = int(value)
        if position not in POSITION_RANGE:
            raise ValueError("powder_site 必须是 P01..P10 或 1..10")
        return position

    @action(description="S07 粉罐扫码盘点")
    def scan_powder_cartridges(self, timeout: float = 300.0) -> dict[str, Any]:
        self._reset_unilab_written_params(PROCESS_SCAN_CARTRIDGES)
        result = self._run_s07_process(PROCESS_SCAN_CARTRIDGES, timeout)
        if result.get("success"):
            result["qr_codes"] = self._read_qr_codes()
        return result

    @action(description="S07 替换粉罐旋转到进料位")
    def rotate_powder_cartridge_to_feed(self, position: int, timeout: float = 300.0) -> dict[str, Any]:
        if position not in POSITION_RANGE:
            return {"success": False, "message": "position 必须在 1-10 范围内"}
        self._reset_unilab_written_params(PROCESS_ROTATE_TO_FEED)
        self._write_plc_variable(NODE_LOAD_POSITION, int(position))
        result = self._run_s07_process(PROCESS_ROTATE_TO_FEED, timeout)
        result["position"] = position
        return result

    @action(description="将指定 S07 转盘 Site 转到已验证的粉桶上下料位")
    def prepare_powder_cartridge_site(
        self,
        powder_cartridge: Annotated[
            ResourceSlot,
            AllowedResourceTemplates(powder_container),
            Field(description="机械臂已从固体粉桶堆栈取出的注粉瓶"),
        ],
        powder_site: str,
        timeout: float = 300.0,
    ) -> PowderSitePreparationStatus:
        try:
            position = self._powder_position_from_site(powder_site)
        except ValueError as exc:
            return {"success": False, "message": str(exc), "powder_site": str(powder_site)}
        result = self.rotate_powder_cartridge_to_feed(position=position, timeout=timeout)
        return {
            "success": bool(result.get("success", False)),
            "message": str(result.get("message", "")),
            "powder_site": f"P{position:02d}",
        }

    @action(description="S07 注粉")
    def dose_powder(
        self,
        coarse_position: int,
        fine_position: int,
        target_weight: float,
        coarse_params: dict[str, JSONValue] | None = None,
        fine_params: dict[str, JSONValue] | None = None,
        timeout: float = 300.0,
        params_json: str | None = None,
        recipe_name: str = "default",
    ) -> dict[str, Any]:
        if coarse_position not in POSITION_RANGE or fine_position not in POSITION_RANGE:
            return {"success": False, "message": "coarse_position/fine_position 必须在 1-10 范围内"}
        json_coarse_params, json_fine_params = self._load_powder_params_from_json(params_json, recipe_name)
        coarse_params = self._merge_powder_params(json_coarse_params, coarse_params)
        fine_params = self._merge_powder_params(json_fine_params, fine_params)
        self._reset_unilab_written_params(PROCESS_DOSE_POWDER, reset_payload=False)
        self._write_plc_variable(NODE_COARSE_POSITION, int(coarse_position))
        self._write_plc_variable(NODE_FINE_POSITION, int(fine_position))
        self._write_plc_variable(NODE_TARGET_WEIGHT, float(target_weight))
        self._write_powder_params("粗注粉", coarse_params, NODE_COARSE_SHAKE_MAX_SPEED)
        self._write_powder_params("精注粉", fine_params, NODE_FINE_SHAKE_MAX_SPEED)
        result = self._run_s07_process(PROCESS_DOSE_POWDER, timeout)
        result["target_weight"] = target_weight
        result["recipe_name"] = recipe_name
        return result

    @action(description="使用已装入 S07 的粉桶向交接位烧杯投粉（物料感知）")
    def dose_powder_with_materials(
        self,
        powder_cartridge: Annotated[
            ResourceSlot,
            AllowedResourceTemplates(powder_container),
            Field(description="已从粉桶堆栈搬入 S07 转盘的注粉瓶"),
        ],
        beaker: Annotated[
            ResourceSlot,
            AllowedResourceTemplates(beaker_500ml),
            Field(description="已由机械臂搬到 S072 的 500 mL 烧杯"),
        ],
        powder_site: str,
        target_mass_g: float,
        recipe_name: str = "default",
        params_json: str | None = None,
        timeout: float = 300.0,
    ) -> PowderDoseWithMaterialsStatus:
        if not 0 < float(target_mass_g) <= 100:
            return {
                "success": False,
                "message": "target_mass_g 必须在 (0, 100] g 范围内",
                "commanded_mass_g": float(target_mass_g),
            }
        try:
            position = self._powder_position_from_site(powder_site)
        except ValueError as exc:
            return {
                "success": False,
                "message": str(exc),
                "commanded_mass_g": float(target_mass_g),
            }
        result = self.dose_powder(
            coarse_position=position,
            fine_position=position,
            target_weight=float(target_mass_g),
            timeout=timeout,
            params_json=params_json,
            recipe_name=recipe_name,
        )
        success = bool(result.get("success", False))
        message = str(result.get("message", ""))
        if success and not message:
            message = "S07 固体称量流程完成；PLC 未提供实测质量"
        return {
            "success": success,
            "message": message,
            "commanded_mass_g": float(target_mass_g),
        }


install_action_logging(SZLabS07SolidAdditionDevice)
