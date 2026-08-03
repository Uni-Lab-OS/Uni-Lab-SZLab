import csv
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from opcua import Client, ua
from unilabos.device_comms.opcua_client.node.uniopcua import NodeType, Variable

try:
    from unilabos.devices.workstation.post_process.post_process import BaseClient, OpcUaNode
except ModuleNotFoundError as exc:
    if exc.name != "pylabrobot":
        raise
    BaseClient = object
    OpcUaNode = None
from unilabos.registry.decorators import action, device, not_action, topic_config
from unilabos.utils.log import logger

from szlab_poly_studio.common.action_logging import (
    compact_log_value,
    current_action_log_context,
    install_action_logging,
)
from szlab_poly_studio.common.stack_status import build_stack_status

DEFAULT_CSV_NAME = "szlab_plc_0730.csv"
OPCUA_DIRECT_IO_ATTEMPTS = 3
OPCUA_DIRECT_IO_RETRY_DELAY = 1.0
OPCUA_CONNECTION_CHECK_INTERVAL = 5.0
OPCUA_RECONNECT_ATTEMPTS = 3
OPCUA_RECONNECT_DELAY = 1.0
PLC_WAIT_PROGRESS_LOG_INTERVAL = 10.0
_UNSET = object()

_RECONNECTABLE_OPCUA_STATUS_NAMES = (
    "BadCommunicationError",
    "BadConnectionClosed",
    "BadConnectionRejected",
    "BadNoCommunication",
    "BadNotConnected",
    "BadRequestInterrupted",
    "BadRequestTimeout",
    "BadSecureChannelClosed",
    "BadSecureChannelIdInvalid",
    "BadSecureChannelTokenUnknown",
    "BadServerNotConnected",
    "BadSessionClosed",
    "BadSessionIdInvalid",
    "BadSessionNotActivated",
    "BadTimeout",
)


def _plc_variable_log_ref(reader: Any, variable_name: str) -> str:
    direct_node_id_map = getattr(reader, "_direct_node_id_map", {})
    node_id = direct_node_id_map.get(variable_name) if isinstance(direct_node_id_map, dict) else None
    if node_id:
        return f"{variable_name} node_id={node_id}"
    return variable_name


def wait_variable_equal(
    reader: Any,
    variable_name: str,
    expected: Any,
    *,
    timeout: float = 300.0,
    interval: float = 1.0,
) -> bool:
    started_at = time.monotonic()
    last_seen: Any = _UNSET
    last_log_at = started_at
    variable_ref = _plc_variable_log_ref(reader, variable_name)
    context = current_action_log_context()
    logger.info(
        f"[SZLAB-PLC-WAIT] START {context} variable={variable_ref} "
        f"expected={compact_log_value(expected)} timeout={float(timeout):.3f}s "
        f"interval={float(interval):.3f}s"
    )
    while True:
        try:
            actual = reader.read_variable(variable_name, use_cache=False)
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            logger.error(
                f"[SZLAB-PLC-WAIT] ERROR {context} variable={variable_ref} "
                f"expected={compact_log_value(expected)} elapsed={elapsed:.3f}s "
                f"cause={type(exc).__name__}: {exc}"
            )
            raise

        now = time.monotonic()
        elapsed = now - started_at
        value_changed = last_seen is _UNSET or actual != last_seen
        progress_due = now - last_log_at >= PLC_WAIT_PROGRESS_LOG_INTERVAL
        if value_changed or progress_due:
            phase = "OBSERVED" if value_changed else "STILL"
            logger.info(
                f"[SZLAB-PLC-WAIT] {phase} {context} variable={variable_ref} "
                f"expected={compact_log_value(expected)} actual={compact_log_value(actual)} "
                f"elapsed={elapsed:.3f}s"
            )
            last_log_at = now
            last_seen = actual

        if actual == expected:
            logger.info(
                f"[SZLAB-PLC-WAIT] SUCCESS {context} variable={variable_ref} "
                f"expected={compact_log_value(expected)} actual={compact_log_value(actual)} "
                f"elapsed={elapsed:.3f}s"
            )
            return True

        if elapsed >= timeout:
            logger.error(
                f"[SZLAB-PLC-WAIT] TIMEOUT {context} variable={variable_ref} "
                f"expected={compact_log_value(expected)} "
                f"last_actual={compact_log_value(actual)} elapsed={elapsed:.3f}s"
            )
            return False
        time.sleep(max(float(interval), 0.0))


def wait_variable_true(
    reader: Any,
    variable_name: str,
    *,
    timeout: float = 300.0,
    interval: float = 1.0,
) -> bool:
    return wait_variable_equal(reader, variable_name, True, timeout=timeout, interval=interval)


S3_UNUSED_BEAKER_SENSORS: Dict[str, str] = {
    "1-1": "传感器状态_上位机[0].NO[6]",
    "1-2": "传感器状态_上位机[0].NO[7]",
    "1-3": "传感器状态_上位机[0].NO[8]",
    "1-4": "传感器状态_上位机[0].NO[9]",
    "1-5": "传感器状态_上位机[0].NO[10]",
    "1-6": "传感器状态_上位机[0].NO[11]",
    "2-1": "传感器状态_上位机[0].NO[12]",
    "2-2": "传感器状态_上位机[0].NO[13]",
    "2-3": "传感器状态_上位机[0].NO[14]",
    "2-4": "传感器状态_上位机[0].NO[15]",
    "2-5": "传感器状态_上位机[1].NO[0]",
    "2-6": "传感器状态_上位机[1].NO[1]",
    "3-1": "传感器状态_上位机[1].NO[2]",
    "3-2": "传感器状态_上位机[1].NO[3]",
    "3-3": "传感器状态_上位机[1].NO[4]",
    "3-4": "传感器状态_上位机[1].NO[5]",
    "3-5": "传感器状态_上位机[1].NO[6]",
    "3-6": "传感器状态_上位机[1].NO[7]",
}

S3_UNUSED_SAMPLE_VIAL_SENSORS: Dict[str, str] = {
    "1-1": "传感器状态_上位机[1].NO[8]",
    "1-2": "传感器状态_上位机[1].NO[9]",
    "1-3": "传感器状态_上位机[1].NO[10]",
    "1-4": "传感器状态_上位机[1].NO[11]",
    "1-5": "传感器状态_上位机[1].NO[12]",
    "1-6": "传感器状态_上位机[1].NO[13]",
    "2-1": "传感器状态_上位机[1].NO[14]",
    "2-2": "传感器状态_上位机[1].NO[15]",
    "2-3": "传感器状态_上位机[2].NO[0]",
    "2-4": "传感器状态_上位机[2].NO[1]",
    "2-5": "传感器状态_上位机[2].NO[2]",
    "2-6": "传感器状态_上位机[2].NO[3]",
    "3-1": "传感器状态_上位机[2].NO[4]",
    "3-2": "传感器状态_上位机[2].NO[5]",
    "3-3": "传感器状态_上位机[2].NO[6]",
    "3-4": "传感器状态_上位机[2].NO[7]",
    "3-5": "传感器状态_上位机[2].NO[8]",
    "3-6": "传感器状态_上位机[2].NO[9]",
}

S11_USED_BEAKER_SENSORS: Dict[str, str] = {
    "1-1": "传感器状态_上位机[6].NO[0]",
    "1-2": "传感器状态_上位机[6].NO[1]",
    "1-3": "传感器状态_上位机[6].NO[2]",
    "1-4": "传感器状态_上位机[6].NO[3]",
    "1-5": "传感器状态_上位机[6].NO[4]",
    "1-6": "传感器状态_上位机[6].NO[5]",
    "2-1": "传感器状态_上位机[6].NO[6]",
    "2-2": "传感器状态_上位机[6].NO[7]",
    "2-3": "传感器状态_上位机[6].NO[8]",
    "2-4": "传感器状态_上位机[6].NO[9]",
    "2-5": "传感器状态_上位机[6].NO[10]",
    "2-6": "传感器状态_上位机[6].NO[11]",
    "3-1": "传感器状态_上位机[6].NO[12]",
    "3-2": "传感器状态_上位机[6].NO[13]",
    "3-3": "传感器状态_上位机[6].NO[14]",
    "3-4": "传感器状态_上位机[6].NO[15]",
    "3-5": "传感器状态_上位机[7].NO[0]",
    "3-6": "传感器状态_上位机[7].NO[1]",
}

S11_USED_SAMPLE_VIAL_SENSORS: Dict[str, str] = {
    "1-1": "传感器状态_上位机[7].NO[2]",
    "1-2": "传感器状态_上位机[7].NO[3]",
    "1-3": "传感器状态_上位机[7].NO[4]",
    "1-4": "传感器状态_上位机[7].NO[5]",
    "1-5": "传感器状态_上位机[7].NO[6]",
    "1-6": "传感器状态_上位机[7].NO[7]",
    "2-1": "传感器状态_上位机[7].NO[8]",
    "2-2": "传感器状态_上位机[7].NO[9]",
    "2-3": "传感器状态_上位机[7].NO[10]",
    "2-4": "传感器状态_上位机[7].NO[11]",
    "2-5": "传感器状态_上位机[7].NO[12]",
    "2-6": "传感器状态_上位机[7].NO[13]",
    "3-1": "传感器状态_上位机[7].NO[14]",
    "3-2": "传感器状态_上位机[7].NO[15]",
    "3-3": "传感器状态_上位机[8].NO[0]",
    "3-4": "传感器状态_上位机[8].NO[1]",
    "3-5": "传感器状态_上位机[8].NO[2]",
    "3-6": "传感器状态_上位机[8].NO[3]",
}

S2_TIP_SENSORS: Dict[str, str] = {str(index): f"传感器状态_上位机[0].NO[{index - 1}]" for index in range(1, 7)}

POWDER_CONTAINER_SENSORS: Dict[str, str] = {
    "1-1": "传感器状态_上位机[3].NO[8]",
    "1-2": "传感器状态_上位机[3].NO[9]",
    "1-3": "传感器状态_上位机[3].NO[10]",
    "2-1": "传感器状态_上位机[3].NO[11]",
    "2-2": "传感器状态_上位机[3].NO[12]",
    "2-3": "传感器状态_上位机[3].NO[13]",
}

S10_LIQUID_REAGENT_SENSORS: Dict[str, str] = {
    "1-1": "传感器状态_上位机[4].NO[12]",
    "1-2": "传感器状态_上位机[4].NO[13]",
    "1-3": "传感器状态_上位机[4].NO[14]",
    "1-4": "传感器状态_上位机[4].NO[15]",
    "1-5": "传感器状态_上位机[5].NO[0]",
    "2-1": "传感器状态_上位机[5].NO[1]",
    "2-2": "传感器状态_上位机[5].NO[2]",
    "2-3": "传感器状态_上位机[5].NO[3]",
    "2-4": "传感器状态_上位机[5].NO[4]",
    "2-5": "传感器状态_上位机[5].NO[5]",
    "3-1": "传感器状态_上位机[5].NO[6]",
    "3-2": "传感器状态_上位机[5].NO[7]",
    "3-3": "传感器状态_上位机[5].NO[8]",
    "3-4": "传感器状态_上位机[5].NO[9]",
    "3-5": "传感器状态_上位机[5].NO[10]",
    "4-1": "传感器状态_上位机[5].NO[11]",
    "4-2": "传感器状态_上位机[5].NO[12]",
    "4-3": "传感器状态_上位机[5].NO[13]",
    "4-4": "传感器状态_上位机[5].NO[14]",
    "4-5": "传感器状态_上位机[5].NO[15]",
}

SENSOR_GROUPS: Dict[str, Dict[str, str]] = {
    "s2_tip": S2_TIP_SENSORS,
    "s3_unused_beaker": S3_UNUSED_BEAKER_SENSORS,
    "s3_unused_sample_vial": S3_UNUSED_SAMPLE_VIAL_SENSORS,
    "s10_liquid_reagent": S10_LIQUID_REAGENT_SENSORS,
    "s11_used_beaker": S11_USED_BEAKER_SENSORS,
    "s11_used_sample_vial": S11_USED_SAMPLE_VIAL_SENSORS,
    "powder_container": POWDER_CONTAINER_SENSORS,
}


def _resolve_csv_path(csv_path: Optional[str]) -> str:
    if csv_path is None:
        csv_path = DEFAULT_CSV_NAME
    if os.path.isabs(csv_path):
        return csv_path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), csv_path)


def load_variable_definitions_from_csv(csv_path: str) -> tuple[List[str], Dict[str, str]]:
    """Load PLC variable names and optional NodeId mappings from CSV."""
    names: List[str] = []
    node_id_map: Dict[str, str] = {}
    seen = set()
    last_error: Optional[UnicodeDecodeError] = None
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "gb18030", "gbk"):
        for delimiter in (",", "\t"):
            try:
                with open(csv_path, newline="", encoding=encoding) as csv_file:
                    reader = csv.DictReader(csv_file, delimiter=delimiter)
                    fieldnames = reader.fieldnames or []
                    if "变量名" not in fieldnames:
                        names.clear()
                        node_id_map.clear()
                        seen.clear()
                        continue
                    node_id_field = next(
                        (field for field in fieldnames if field.strip().lower() in {"node_id", "nodeid"}),
                        None,
                    )
                    for row in reader:
                        name = (row.get("变量名") or "").strip()
                        node_id = (row.get(node_id_field) or "").strip() if node_id_field else ""
                        if node_id_field and not node_id:
                            continue
                        if not name or name in seen:
                            continue
                        seen.add(name)
                        names.append(name)
                        if node_id:
                            node_id_map[name] = node_id
                return names, node_id_map
            except UnicodeDecodeError as exc:
                names.clear()
                node_id_map.clear()
                seen.clear()
                last_error = exc
                break
    if last_error:
        raise last_error
    return names, node_id_map


def load_variable_names_from_csv(csv_path: str) -> List[str]:
    """Load PLC variable names from the CSV column named '变量名'."""
    names, _node_id_map = load_variable_definitions_from_csv(csv_path)
    return names


def _patch_opcua_token_time_drift_check() -> None:
    """兼容 PLC/OPC UA Server 时间严重漂移导致的 security token 超时。"""
    from opcua.common.connection import SecureConnection

    def _check_sym_header_ignore_prev_token_timeout(self: Any, security_header: Any) -> None:
        assert isinstance(
            security_header,
            ua.SymmetricAlgorithmHeader,
        ), "Expected SymAlgHeader, got: {0}".format(security_header)
        if security_header.TokenId != self.security_token.TokenId:
            if security_header.TokenId != self.next_security_token.TokenId:
                if self._allow_prev_token and security_header.TokenId == self.prev_security_token.TokenId:
                    return
                raise ua.UaError(
                    "Invalid security token id {}, expected {} or {}".format(
                        security_header.TokenId,
                        self.security_token.TokenId,
                        self.next_security_token.TokenId,
                    )
                )
            self.revolve_tokens()
            self.security_policy.make_remote_symmetric_key(self.local_nonce, self.remote_nonce)
            self.prev_security_token = ua.ChannelSecurityToken()
        if self.prev_security_token.TokenId != 0:
            self.security_policy.make_remote_symmetric_key(self.local_nonce, self.remote_nonce)
            self.prev_security_token = ua.ChannelSecurityToken()

    SecureConnection._check_sym_header = _check_sym_header_ignore_prev_token_timeout


@device(
    id="szlab_poly_plc",
    display_name="苏州实验室 PLC",
    category=["custom"],
    description="苏州实验室聚合物工作站 PLC/OPC UA 通讯设备，负责变量读写和传感器状态发布",
)
class SZLabPolyPLCDevice(BaseClient):
    def __init__(
        self,
        url: str,
        csv_path: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        heartbeat_node: str = "Heart_Beat",
        auto_connect: bool = True,
        opcua_log_level: str = "WARNING",
        opcua_node_id_map: Optional[Dict[str, str]] = None,
        opcua_node_id_prefix: Optional[str] = None,
        opcua_timeout: float = 10.0,
        connection_check_interval: float = OPCUA_CONNECTION_CHECK_INTERVAL,
        reconnect_attempts: int = OPCUA_RECONNECT_ATTEMPTS,
        reconnect_delay: float = OPCUA_RECONNECT_DELAY,
        ignore_opcua_token_time_drift: bool = False,
        *args,
        **kwargs,
    ):
        if OpcUaNode is None:
            raise ModuleNotFoundError("SZLabPolyPLCDevice 需要可选依赖 pylabrobot，请在 unilab 环境中运行")
        super().__init__()
        self.csv_path = _resolve_csv_path(csv_path)
        self.heartbeat_node = heartbeat_node
        self.heartbeat_on = False
        self._heartbeat_timer: Optional[threading.Timer] = None
        self._sensor_read_warning_names: set[str] = set()
        self._io_lock = threading.RLock()
        self.connection_check_interval = max(float(connection_check_interval), 0.0)
        self.reconnect_attempts = max(int(reconnect_attempts), 1)
        self.reconnect_delay = max(float(reconnect_delay), 0.0)
        self._connection_monitor_enabled = False
        self._connection_check_timer: Optional[threading.Timer] = None
        self._connection_healthy = False
        self._last_connection_check_at: Optional[float] = None
        self._last_connection_error: Optional[str] = None
        self._reconnect_count = 0

        variable_names, csv_node_id_map = load_variable_definitions_from_csv(self.csv_path)
        nodes = [OpcUaNode(name=name, node_type=NodeType.VARIABLE, data_type=None) for name in variable_names]
        prefix_node_id_map = (
            {name: f"{opcua_node_id_prefix}{name}" for name in variable_names} if opcua_node_id_prefix else {}
        )
        self._direct_node_id_map = {
            **prefix_node_id_map,
            **csv_node_id_map,
            **dict(opcua_node_id_map or {}),
        }
        self.register_node_list(nodes)

        logging.getLogger("opcua").setLevel(getattr(logging, opcua_log_level.upper(), logging.WARNING))
        if ignore_opcua_token_time_drift:
            _patch_opcua_token_time_drift_check()
        client = Client(url, timeout=opcua_timeout)
        if username and password:
            client.set_user(username)
            client.set_password(password)
        self._set_client(client)
        if self._direct_node_id_map:
            self._register_direct_node_ids(nodes)
        if auto_connect:
            self._connect()
            self._start_connection_monitor()

    @not_action
    def _connect(self) -> None:
        if not self._direct_node_id_map:
            super()._connect()
            self._mark_connection_healthy()
            return
        logger.info("try to connect client...")
        if not self.client:
            raise ValueError("client is not initialized")
        try:
            self.client.connect()
            self._mark_connection_healthy()
            logger.info("client connected!")
            missing = sorted(set(self._variables_to_find) - set(self._node_registry))
            if missing:
                logger.warning(f"以下节点缺少 NodeId 映射，未执行自动浏览: {', '.join(missing)}")
        except Exception as exc:
            logger.error(f"client connect failed: {exc}")
            raise

    @not_action
    def _mark_connection_healthy(self) -> None:
        self._connection_healthy = True
        self._last_connection_check_at = time.time()
        self._last_connection_error = None

    @not_action
    def _mark_connection_unhealthy(self, exc: BaseException) -> None:
        self._connection_healthy = False
        self._last_connection_check_at = time.time()
        self._last_connection_error = f"{type(exc).__name__}: {exc}"

    @not_action
    def _probe_connection_locked(self) -> Any:
        if not self.client:
            raise ValueError("client is not initialized")
        server_state = self.client.get_node(ua.ObjectIds.Server_ServerStatus_State)
        return server_state.get_value()

    @not_action
    def _disconnect_client_quietly_locked(self) -> None:
        if not self.client:
            return
        try:
            self.client.disconnect()
        except Exception as exc:
            logger.debug(f"重连前关闭旧 OPC UA 会话失败（可忽略）: {type(exc).__name__}: {exc}")

    @not_action
    def _reconnect_locked(self, *, reason: str) -> None:
        if not self.client:
            raise ValueError("client is not initialized")

        last_error: Optional[BaseException] = None
        for attempt in range(1, self.reconnect_attempts + 1):
            if attempt > 1:
                time.sleep(self.reconnect_delay)
            self._disconnect_client_quietly_locked()
            try:
                self._connect()
            except Exception as exc:
                last_error = exc
                self._mark_connection_unhealthy(exc)
                logger.warning(
                    f"OPC UA 重连失败 ({attempt}/{self.reconnect_attempts}) "
                    f"reason={reason}: {type(exc).__name__}: {exc}"
                )
                continue

            self._reconnect_count += 1
            logger.info(
                f"OPC UA 重连成功 attempt={attempt}/{self.reconnect_attempts} "
                f"reason={reason} reconnect_count={self._reconnect_count}"
            )
            return

        raise ConnectionError(
            f"OPC UA 重连失败，已尝试 {self.reconnect_attempts} 次: {last_error}"
        ) from last_error

    @not_action
    def _check_connection_once(self) -> bool:
        with self._io_lock:
            try:
                server_state = self._probe_connection_locked()
            except Exception as exc:
                self._mark_connection_unhealthy(exc)
                logger.warning(
                    f"OPC UA 通信检测失败，准备重连: {type(exc).__name__}: {exc}"
                )
                try:
                    self._reconnect_locked(reason=f"active probe failed: {type(exc).__name__}: {exc}")
                    server_state = self._probe_connection_locked()
                except Exception as reconnect_exc:
                    self._mark_connection_unhealthy(reconnect_exc)
                    logger.error(
                        f"OPC UA 通信恢复失败: {type(reconnect_exc).__name__}: {reconnect_exc}"
                    )
                    return False

            self._mark_connection_healthy()
            logger.debug(f"OPC UA 通信检测正常: server_state={server_state}")
            return True

    @not_action
    def _start_connection_monitor(self) -> None:
        if self.connection_check_interval <= 0 or self._connection_monitor_enabled:
            return
        self._connection_monitor_enabled = True
        self._schedule_connection_check()

    @not_action
    def _stop_connection_monitor(self) -> None:
        self._connection_monitor_enabled = False
        timer = self._connection_check_timer
        self._connection_check_timer = None
        if timer:
            timer.cancel()

    @not_action
    def _schedule_connection_check(self) -> None:
        if not self._connection_monitor_enabled or self.connection_check_interval <= 0:
            return
        timer = threading.Timer(self.connection_check_interval, self._run_connection_check)
        timer.daemon = True
        self._connection_check_timer = timer
        timer.start()

    @not_action
    def _run_connection_check(self) -> None:
        self._connection_check_timer = None
        if not self._connection_monitor_enabled:
            return
        try:
            self._check_connection_once()
        finally:
            if self._connection_monitor_enabled:
                self._schedule_connection_check()

    @not_action
    def _register_direct_node_ids(self, nodes: List[OpcUaNode]) -> None:
        if not self.client:
            raise ValueError("client is not initialized")
        nodes_by_name = {node.name: node for node in nodes}
        for name, node_id in self._direct_node_id_map.items():
            node = nodes_by_name.get(name)
            if node is None:
                continue
            if node.node_type != NodeType.VARIABLE:
                continue
            self._node_registry[name] = Variable(self.client, name, node_id, node.data_type)
            self._variables_to_find.setdefault(
                name,
                {
                    "node_type": node.node_type,
                    "data_type": node.data_type,
                    "node_id": node_id,
                },
            )

    @not_action
    def read_variable(self, node_name: str, use_cache: bool = True) -> Any:
        with self._io_lock:
            return self._read_variable_locked(node_name, use_cache=use_cache)

    @not_action
    def _read_variable_locked(self, node_name: str, use_cache: bool = True) -> Any:
        del use_cache  # BaseClient reads directly from the OPC UA node.
        started_at = time.monotonic()
        context = current_action_log_context()
        variable_ref = _plc_variable_log_ref(self, node_name)
        is_direct = node_name in self._direct_node_id_map
        attempts = OPCUA_DIRECT_IO_ATTEMPTS if is_direct else 1
        for attempt in range(1, attempts + 1):
            try:
                node = self.use_node(node_name)
                value, error = node.read()
            except Exception as exc:
                is_retryable = is_direct and self._is_retryable_direct_io_error(exc)
                if is_retryable and attempt < attempts:
                    logger.warning(
                        f"读取 PLC 变量遇到临时通信错误，准备重连后重试 "
                        f"({attempt}/{attempts}): {node_name}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    self._mark_connection_unhealthy(exc)
                    try:
                        self._reconnect_locked(
                            reason=f"read {node_name} failed: {type(exc).__name__}: {exc}"
                        )
                    except Exception as reconnect_exc:
                        logger.warning(
                            f"读取 PLC 变量前重连未成功，保留 I/O 重试: {node_name}: "
                            f"{type(reconnect_exc).__name__}: {reconnect_exc}"
                        )
                    time.sleep(OPCUA_DIRECT_IO_RETRY_DELAY)
                    continue
                if is_retryable:
                    self._mark_connection_unhealthy(exc)
                elapsed = time.monotonic() - started_at
                logger.error(
                    f"[SZLAB-PLC-READ] FAIL {context} variable={variable_ref} "
                    f"attempt={attempt}/{attempts} elapsed={elapsed:.3f}s "
                    f"cause={type(exc).__name__}: {exc}"
                )
                raise RuntimeError(
                    f"读取 PLC 变量失败: {node_name}: {exc}"
                ) from exc
            if not error:
                self._mark_connection_healthy()
                logger.debug(
                    f"[SZLAB-PLC-READ] SUCCESS {context} variable={variable_ref} "
                    f"value={compact_log_value(value)} attempt={attempt}/{attempts} "
                    f"elapsed={time.monotonic() - started_at:.3f}s"
                )
                return value
            if attempt < attempts:
                logger.warning(
                    f"读取 PLC 变量暂时失败，准备重试 "
                    f"({attempt}/{attempts}): {node_name}"
                )
                time.sleep(OPCUA_DIRECT_IO_RETRY_DELAY)
        elapsed = time.monotonic() - started_at
        if is_direct:
            direct_node_id = self._direct_node_id_map[node_name]
            logger.error(
                f"[SZLAB-PLC-READ] FAIL {context} variable={variable_ref} "
                f"attempts={attempts} elapsed={elapsed:.3f}s "
                f"cause=direct read returned an error"
            )
            raise RuntimeError(
                f"读取 PLC 变量失败: {node_name}: 直连读取未成功: "
                f"{direct_node_id}（已重试 {attempts} 次）"
            )
        logger.error(
            f"[SZLAB-PLC-READ] FAIL {context} variable={variable_ref} "
            f"attempts={attempts} elapsed={elapsed:.3f}s "
            f"cause=read returned an error"
        )
        raise RuntimeError(f"读取 PLC 变量失败: {node_name}")

    @not_action
    def write_variable(self, node_name: str, value: Any) -> bool:
        with self._io_lock:
            return self._write_variable_locked(node_name, value)

    @not_action
    def _write_variable_locked(self, node_name: str, value: Any) -> bool:
        started_at = time.monotonic()
        context = current_action_log_context()
        variable_ref = _plc_variable_log_ref(self, node_name)
        is_direct = node_name in self._direct_node_id_map
        attempts = OPCUA_DIRECT_IO_ATTEMPTS if is_direct else 1
        log_method = logger.debug if node_name == getattr(self, "heartbeat_node", None) else logger.info
        log_method(
            f"[SZLAB-PLC-WRITE] START {context} variable={variable_ref} "
            f"value={compact_log_value(value)} attempts={attempts}"
        )
        for attempt in range(1, attempts + 1):
            try:
                node = self.use_node(node_name)
                self._write_value_only(node, value)
                self._mark_connection_healthy()
                log_method(
                    f"[SZLAB-PLC-WRITE] SUCCESS {context} variable={variable_ref} "
                    f"value={compact_log_value(value)} attempt={attempt}/{attempts} "
                    f"elapsed={time.monotonic() - started_at:.3f}s"
                )
                return True
            except Exception as exc:
                is_bad_node_id = self._is_bad_node_id_unknown(exc)
                is_retryable = (
                    is_direct and self._is_retryable_direct_io_error(exc)
                )
                if is_retryable and attempt < attempts:
                    logger.warning(
                        f"写入 PLC 变量遇到临时通信错误，准备重连后重试 "
                        f"({attempt}/{attempts}): {node_name}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    self._mark_connection_unhealthy(exc)
                    try:
                        self._reconnect_locked(
                            reason=f"write {node_name} failed: {type(exc).__name__}: {exc}"
                        )
                    except Exception as reconnect_exc:
                        logger.warning(
                            f"写入 PLC 变量前重连未成功，保留 I/O 重试: {node_name}: "
                            f"{type(reconnect_exc).__name__}: {reconnect_exc}"
                        )
                    time.sleep(OPCUA_DIRECT_IO_RETRY_DELAY)
                    continue
                if is_retryable:
                    self._mark_connection_unhealthy(exc)
                elapsed = time.monotonic() - started_at
                if not is_bad_node_id or not is_retryable:
                    logger.error(
                        f"[SZLAB-PLC-WRITE] FAIL {context} variable={variable_ref} "
                        f"value={compact_log_value(value)} attempt={attempt}/{attempts} "
                        f"elapsed={elapsed:.3f}s cause={type(exc).__name__}: {exc}"
                    )
                    raise RuntimeError(
                        f"写入 PLC 变量失败: {node_name}: {exc}"
                        f"{'（已重试 ' + str(attempts) + ' 次）' if is_retryable else ''}"
                    ) from exc
                direct_node_id = self._direct_node_id_map.get(node_name)
                direct_node_detail = f": {direct_node_id}" if direct_node_id else ""
                logger.error(
                    f"[SZLAB-PLC-WRITE] FAIL {context} variable={variable_ref} "
                    f"value={compact_log_value(value)} attempts={attempts} "
                    f"elapsed={elapsed:.3f}s cause=BadNodeIdUnknown"
                )
                raise RuntimeError(
                    f"写入 PLC 变量失败: {node_name}: 直连 NodeId 无效"
                    f"{direct_node_detail}（已重试 {attempts} 次）"
                ) from exc
        raise AssertionError("unreachable")

    @not_action
    def _is_bad_node_id_unknown(self, exc: Exception) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if "BadNodeIdUnknown" in str(current):
                return True
            current = current.__cause__ or current.__context__
        return False

    @not_action
    def _is_retryable_direct_io_error(self, exc: Exception) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if isinstance(current, (TimeoutError, ConnectionError, OSError)):
                return True
            error_text = f"{type(current).__name__}: {current}"
            if "BadNodeIdUnknown" in error_text:
                return True
            if any(status_name in error_text for status_name in _RECONNECTABLE_OPCUA_STATUS_NAMES):
                return True
            current = current.__cause__ or current.__context__
        return False

    @not_action
    def _write_value_only(self, node: Any, value: Any) -> None:
        opc_node = node._get_node()
        variant_type = opc_node.get_data_type_as_variant_type()
        data_value = ua.DataValue()
        data_value.Value = ua.Variant(value, variant_type)
        data_value.StatusCode = None
        data_value.SourceTimestamp = None
        data_value.ServerTimestamp = None
        data_value.SourcePicoseconds = None
        data_value.ServerPicoseconds = None

        write_value = ua.WriteValue()
        write_value.NodeId = opc_node.nodeid
        write_value.AttributeId = ua.AttributeIds.Value
        write_value.Value = data_value

        params = ua.WriteParameters()
        params.NodesToWrite = [write_value]
        results = self.client.uaclient.write(params)
        if results and not results[0].is_good():
            raise RuntimeError(str(results[0]))

    @not_action
    def disconnect(self) -> None:
        self._stop_connection_monitor()
        self.heartbeat_on = False
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None
        with self._io_lock:
            try:
                if self.client:
                    self.client.disconnect()
            finally:
                self._connection_healthy = False

    @not_action
    def read(self, node_name: str, use_cache: bool = True) -> Any:
        return self.read_variable(node_name, use_cache=use_cache)

    @not_action
    def write(self, node_name: str, value: Any) -> None:
        self.write_variable(node_name, value)

    @not_action
    def pulse(
        self,
        node_name: str,
        value: Any = True,
        reset_value: Any = False,
        reset_delay: float = 0.1,
    ) -> None:
        self.write(node_name, value)
        time.sleep(reset_delay)
        self.write(node_name, reset_value)

    @not_action
    def wait_equal(
        self,
        node_name: str,
        expected: Any,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        return self.wait_variable_equal(node_name, expected, timeout=timeout, interval=interval)

    @not_action
    def wait_variable_equal(
        self,
        node_name: str,
        expected: Any,
        timeout: float = 300.0,
        interval: float = 1.0,
    ) -> bool:
        return wait_variable_equal(self, node_name, expected, timeout=timeout, interval=interval)

    @not_action
    def wait_variable_true(
        self,
        node_name: str,
        timeout: float = 300.0,
        interval: float = 1.0,
    ) -> bool:
        return wait_variable_true(self, node_name, timeout=timeout, interval=interval)

    @not_action
    def wait_new_cycle_done(
        self,
        node_name: str,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        started_at = time.monotonic()
        context = current_action_log_context()
        variable_ref = _plc_variable_log_ref(self, node_name)
        initial_value = self.read(node_name)
        logger.info(
            f"[SZLAB-PLC-WAIT] NEW-CYCLE START {context} variable={variable_ref} "
            f"initial={compact_log_value(initial_value)} timeout={float(timeout):.3f}s"
        )
        if bool(initial_value):
            logger.info(
                f"[SZLAB-PLC-WAIT] NEW-CYCLE STALE-DONE {context} variable={variable_ref} "
                f"reason=完成信号启动时已为真，先等待 PLC 复位为 False"
            )
            if not self.wait_equal(node_name, False, timeout=timeout, interval=interval):
                logger.error(
                    f"[SZLAB-PLC-WAIT] NEW-CYCLE TIMEOUT {context} variable={variable_ref} "
                    f"phase=wait_reset_false elapsed={time.monotonic() - started_at:.3f}s"
                )
                return False
        elapsed = time.monotonic() - started_at
        remaining = max(timeout - elapsed, 0.0)
        logger.info(
            f"[SZLAB-PLC-WAIT] NEW-CYCLE WAIT-DONE {context} variable={variable_ref} "
            f"expected=True remaining={remaining:.3f}s"
        )
        completed = self.wait_equal(node_name, True, timeout=remaining, interval=interval)
        if completed:
            logger.info(
                f"[SZLAB-PLC-WAIT] NEW-CYCLE SUCCESS {context} variable={variable_ref} "
                f"elapsed={time.monotonic() - started_at:.3f}s"
            )
        else:
            logger.error(
                f"[SZLAB-PLC-WAIT] NEW-CYCLE TIMEOUT {context} variable={variable_ref} "
                f"phase=wait_done_true elapsed={time.monotonic() - started_at:.3f}s"
            )
        return completed

    @not_action
    def get_opc_variable_metadata(self, node_name: str) -> tuple[str, str | None]:
        try:
            return node_name, self.use_node(node_name).node_id
        except Exception:
            return node_name, None

    @not_action
    def check_variable_accessible(self, node_name: str) -> tuple[bool, str | None]:
        try:
            node = self.use_node(node_name)
            opc_node = node._get_node()
            opc_node.get_data_type_as_variant_type()
            return True, node.node_id
        except Exception as exc:
            return False, str(exc)

    @not_action
    def get_variables(self, node_names: Optional[List[str]] = None, use_cache: bool = False) -> Dict[str, Any]:
        names = node_names or list(self._variables_to_find)
        result: Dict[str, Any] = {}
        for name in names:
            try:
                node = self.use_node(name)
                value = self.read_variable(name, use_cache=use_cache)
                result[name] = {
                    "success": True,
                    "value": value,
                    "node_id": node.node_id,
                }
            except Exception as exc:
                result[name] = {"success": False, "error": str(exc)}
        return result

    @not_action
    def _read_sensor_group(self, sensors: Dict[str, str]) -> Dict[str, Optional[bool]]:
        with self._io_lock:
            result: Dict[str, Optional[bool]] = {}
            for site_key, variable_name in sensors.items():
                try:
                    result[site_key] = bool(self.read_variable(variable_name))
                except Exception as exc:
                    if variable_name not in self._sensor_read_warning_names:
                        logger.warning(f"读取传感器 {variable_name} 失败: {exc}")
                        self._sensor_read_warning_names.add(variable_name)
                    else:
                        logger.debug(f"读取传感器 {variable_name} 失败: {exc}")
                    result[site_key] = None
            return result

    @not_action
    def _read_stack_sensor_groups(
        self, group_names: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Optional[bool]]]:
        with self._io_lock:
            selected_groups = group_names or list(SENSOR_GROUPS)
            return {
                group_name: self._read_sensor_group(sensors)
                for group_name, sensors in SENSOR_GROUPS.items()
                if group_name in selected_groups
            }

    @action(always_free=True, description="启动苏州实验室 PLC 心跳")
    def start_heart_beat(self) -> Dict[str, Any]:
        if self.heartbeat_node not in self._variables_to_find:
            return {
                "success": False,
                "message": f"CSV 中未注册心跳变量 {self.heartbeat_node}",
            }
        if self.heartbeat_on:
            return {"success": True, "message": "心跳已在运行"}
        self.heartbeat_on = True
        self._schedule_heartbeat()
        return {"success": True, "message": "心跳已启动"}

    @action(always_free=True, description="停止苏州实验室 PLC 心跳")
    def stop_heart_beat(self) -> Dict[str, Any]:
        self.heartbeat_on = False
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None
        if self.heartbeat_node in self._variables_to_find:
            try:
                self.write_variable(self.heartbeat_node, False)
            except Exception as exc:
                return {"success": False, "message": str(exc)}
        return {"success": True, "message": "心跳已停止"}

    @not_action
    def _schedule_heartbeat(self) -> None:
        self._heartbeat_timer = threading.Timer(1.0, self._trigger_heart_beat)
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    @not_action
    def _trigger_heart_beat(self) -> None:
        if not self.heartbeat_on:
            return
        try:
            current = bool(self.read_variable(self.heartbeat_node))
            self.write_variable(self.heartbeat_node, not current)
        except Exception as exc:
            logger.warning(f"PLC 心跳写入失败: {exc}")
        if self.heartbeat_on:
            self._schedule_heartbeat()

    @action(always_free=True, description="检测 OPC UA 通信，断线时自动重连")
    def check_opcua_connection(self) -> Dict[str, Any]:
        healthy = self._check_connection_once()
        return {
            "success": healthy,
            "connected": self._connection_healthy,
            "last_check_at": self._last_connection_check_at,
            "last_error": self._last_connection_error,
            "reconnect_count": self._reconnect_count,
        }

    @action(always_free=True, description="读取指定 PLC 变量")
    def check_variable_status(self, variable_name: str) -> Dict[str, Any]:
        try:
            return {
                "success": True,
                "variable_name": variable_name,
                "value": self.read_variable(variable_name),
            }
        except Exception as exc:
            return {
                "success": False,
                "variable_name": variable_name,
                "error": str(exc),
            }

    @not_action
    def write_variable_action(self, variable_name: str, value: Any) -> Dict[str, Any]:
        try:
            self.write_variable(variable_name, value)
            return {"success": True, "variable_name": variable_name, "value": value}
        except Exception as exc:
            return {"success": False, "variable_name": variable_name, "error": str(exc)}

    @action(always_free=True, description="读取指定传感器分组")
    def get_sensor_group_status(self, group_name: str) -> Dict[str, Any]:
        sensors = SENSOR_GROUPS.get(group_name)
        if sensors is None:
            return {
                "success": False,
                "group_name": group_name,
                "available_groups": sorted(SENSOR_GROUPS),
            }
        return {
            "success": True,
            "group_name": group_name,
            "status": self._read_sensor_group(sensors),
        }

    @not_action
    def _build_stack_status(self, group_names: Optional[List[str]] = None) -> Dict[str, Any]:
        return build_stack_status(self._read_stack_sensor_groups(group_names=group_names))

    @action(always_free=True, description="读取前端堆栈 JSON 状态")
    def get_stack_status(self, group_names: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._build_stack_status(group_names=group_names)

    @action(always_free=True, description="写入 S01 上料过渡仓取料编号和入料产品")
    def set_s1_loading_request(self, pick_index: int, product_type: int) -> Dict[str, Any]:
        try:
            self.write_variable("S01取料编号", int(pick_index))
            self.write_variable("S01入料产品", int(product_type))
            return {
                "success": True,
                "pick_index": pick_index,
                "product_type": product_type,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @topic_config(period=1.0)
    def s2_tip_occupied(self) -> Dict[str, Optional[bool]]:
        return self._read_sensor_group(S2_TIP_SENSORS)

    @topic_config(period=1.0)
    def s3_unused_beaker_occupied(self) -> Dict[str, Optional[bool]]:
        return self._read_sensor_group(S3_UNUSED_BEAKER_SENSORS)

    @topic_config(period=1.0)
    def s3_unused_sample_vial_occupied(self) -> Dict[str, Optional[bool]]:
        return self._read_sensor_group(S3_UNUSED_SAMPLE_VIAL_SENSORS)

    @topic_config(period=1.0)
    def s10_liquid_reagent_occupied(self) -> Dict[str, Optional[bool]]:
        return self._read_sensor_group(S10_LIQUID_REAGENT_SENSORS)

    @topic_config(period=1.0)
    def s11_used_beaker_occupied(self) -> Dict[str, Optional[bool]]:
        return self._read_sensor_group(S11_USED_BEAKER_SENSORS)

    @topic_config(period=1.0)
    def s11_used_sample_vial_occupied(self) -> Dict[str, Optional[bool]]:
        return self._read_sensor_group(S11_USED_SAMPLE_VIAL_SENSORS)

    @topic_config(period=1.0)
    def powder_container_occupied(self) -> Dict[str, Optional[bool]]:
        return self._read_sensor_group(POWDER_CONTAINER_SENSORS)

    @topic_config(period=5.0)
    def registered_variable_count(self) -> int:
        return len(self._variables_to_find)

    @topic_config(period=5.0)
    def registered_variables(self) -> List[str]:
        return sorted(self._variables_to_find)

    @topic_config(period=10.0)
    def stack_status(self) -> Dict[str, Any]:
        return self._build_stack_status()


install_action_logging(SZLabPolyPLCDevice)
