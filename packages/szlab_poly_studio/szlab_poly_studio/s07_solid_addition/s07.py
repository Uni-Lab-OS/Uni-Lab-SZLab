"""SZLab S07 固体加料工位设备驱动。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from unilabos.registry.decorators import action, device, not_action
from unilabos.utils.log import logger

from szlab_poly_studio.plc_gateway import UnifiedPLCGatewayMixin
from szlab_poly_studio.s07_solid_addition.sensors import (
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

DEFAULT_POWDER_PARAMS_PATH = Path(__file__).resolve().parent / "s07_powder_params.json"


@device(
    id="szlab_s07_solid_addition",
    display_name="S07 固体加料工位",
    category=["workstation", "szlab"],
    description="苏州实验室 S07 固体加料工位，通过 szlab_poly_plc 转发 PLC 读写",
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
        logger.info(f"等待 {description} == {expected}")
        start = time.time()
        while time.time() - start < timeout:
            if bool(self._read_plc_variable(node_name)) is expected:
                return True
            time.sleep(self.poll_interval)
        return False

    @not_action
    def _wait_process_complete(self, expected: int, timeout: float) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if int(self._read_plc_variable(NODE_PROCESS_COMPLETE) or 0) == expected:
                return True
            time.sleep(self.poll_interval)
        return False

    @not_action
    def _reset_unilab_written_params(self) -> None:
        for node, value in (
            (NODE_PROCESS_SELECT, 0),
            (NODE_PARAMS_WRITTEN, False),
            (NODE_LOAD_POSITION, 0),
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
            self._reset_unilab_written_params()
            return {"success": False, "message": f"等待 S07 工艺完成超时（期望 {process_id}）"}
        self._reset_unilab_written_params()
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

    @action(description="S07 粉罐扫码盘点")
    def scan_powder_cartridges(self, timeout: float = 300.0) -> dict[str, Any]:
        self._reset_unilab_written_params()
        result = self._run_s07_process(PROCESS_SCAN_CARTRIDGES, timeout)
        if result.get("success"):
            result["qr_codes"] = self._read_qr_codes()
        return result

    @action(description="S07 替换粉罐旋转到进料位")
    def rotate_powder_cartridge_to_feed(self, position: int, timeout: float = 300.0) -> dict[str, Any]:
        if position not in POSITION_RANGE:
            return {"success": False, "message": "position 必须在 1-10 范围内"}
        self._reset_unilab_written_params()
        self._write_plc_variable(NODE_LOAD_POSITION, int(position))
        result = self._run_s07_process(PROCESS_ROTATE_TO_FEED, timeout)
        result["position"] = position
        return result

    @action(description="S07 注粉")
    def dose_powder(
        self,
        coarse_position: int,
        fine_position: int,
        target_weight: float,
        coarse_params: dict[str, Any] | None = None,
        fine_params: dict[str, Any] | None = None,
        timeout: float = 300.0,
        params_json: str | None = None,
        recipe_name: str = "default",
    ) -> dict[str, Any]:
        if coarse_position not in POSITION_RANGE or fine_position not in POSITION_RANGE:
            return {"success": False, "message": "coarse_position/fine_position 必须在 1-10 范围内"}
        json_coarse_params, json_fine_params = self._load_powder_params_from_json(params_json, recipe_name)
        coarse_params = self._merge_powder_params(json_coarse_params, coarse_params)
        fine_params = self._merge_powder_params(json_fine_params, fine_params)
        self._reset_unilab_written_params()
        self._write_plc_variable(NODE_COARSE_POSITION, int(coarse_position))
        self._write_plc_variable(NODE_FINE_POSITION, int(fine_position))
        self._write_plc_variable(NODE_TARGET_WEIGHT, float(target_weight))
        self._write_powder_params("粗注粉", coarse_params, NODE_COARSE_SHAKE_MAX_SPEED)
        self._write_powder_params("精注粉", fine_params, NODE_FINE_SHAKE_MAX_SPEED)
        result = self._run_s07_process(PROCESS_DOSE_POWDER, timeout)
        result["target_weight"] = target_weight
        result["recipe_name"] = recipe_name
        return result
