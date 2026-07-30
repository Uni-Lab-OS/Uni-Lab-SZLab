"""统一的 SZLab PLC 跨设备通信模块。

PLC 工位驱动只依赖本模块提供的读、写、等待接口。生产环境由
``PLCActionGateway`` 通过 ROS 命令通道调用唯一的 ``szlab_poly_plc`` 设备；
测试可以向 ``UnifiedPLCGatewayMixin`` 注入内存适配器。
"""

from __future__ import annotations

from typing import Any


class PLCActionGateway:
    """通过 Uni-Lab-OS 跨设备命令接口复用唯一 PLC 连接。"""

    def __init__(
        self,
        ros_node: Any,
        *,
        plc_device_id: str = "szlab_poly_plc",
        command_timeout: float = 300.0,
        server_wait_timeout: float = 10.0,
    ) -> None:
        self._ros_node = ros_node
        self.plc_device_id = plc_device_id
        self.command_timeout = float(command_timeout)
        self.server_wait_timeout = float(server_wait_timeout)

    def _call(
        self,
        function_name: str,
        function_args: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Any:
        return self._ros_node.call_device_action(
            self.plc_device_id,
            function_name,
            function_args,
            timeout=self.command_timeout if timeout is None else float(timeout),
            server_wait_timeout=self.server_wait_timeout,
        )

    def read_variable(self, node_name: str, use_cache: bool = True) -> Any:
        return self._call(
            "read_variable",
            {"node_name": node_name, "use_cache": use_cache},
        )

    def write_variable(self, node_name: str, value: Any) -> bool:
        result = self._call(
            "write_variable",
            {"node_name": node_name, "value": value},
        )
        return True if result is None else bool(result)

    def read(self, node_name: str, use_cache: bool = True) -> Any:
        return self.read_variable(node_name, use_cache=use_cache)

    def write(self, node_name: str, value: Any) -> None:
        self.write_variable(node_name, value)

    def pulse(
        self,
        node_name: str,
        value: Any = True,
        reset_value: Any = False,
        reset_delay: float = 0.1,
    ) -> None:
        self._call(
            "pulse",
            {
                "node_name": node_name,
                "value": value,
                "reset_value": reset_value,
                "reset_delay": reset_delay,
            },
            timeout=max(self.command_timeout, float(reset_delay) + 5.0),
        )

    def wait_equal(
        self,
        node_name: str,
        expected: Any,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        return bool(
            self._call(
                "wait_equal",
                {
                    "node_name": node_name,
                    "expected": expected,
                    "timeout": timeout,
                    "interval": interval,
                },
                timeout=max(self.command_timeout, float(timeout) + 5.0),
            )
        )

    def wait_variable_equal(
        self,
        node_name: str,
        expected: Any,
        timeout: float = 300.0,
        interval: float = 1.0,
    ) -> bool:
        return bool(
            self._call(
                "wait_variable_equal",
                {
                    "node_name": node_name,
                    "expected": expected,
                    "timeout": timeout,
                    "interval": interval,
                },
                timeout=max(self.command_timeout, float(timeout) + 5.0),
            )
        )

    def wait_variable_true(
        self,
        node_name: str,
        timeout: float = 300.0,
        interval: float = 1.0,
    ) -> bool:
        return bool(
            self._call(
                "wait_variable_true",
                {
                    "node_name": node_name,
                    "timeout": timeout,
                    "interval": interval,
                },
                timeout=max(self.command_timeout, float(timeout) + 5.0),
            )
        )

    def wait_new_cycle_done(
        self,
        node_name: str,
        timeout: float = 300.0,
        interval: float = 0.2,
    ) -> bool:
        return bool(
            self._call(
                "wait_new_cycle_done",
                {
                    "node_name": node_name,
                    "timeout": timeout,
                    "interval": interval,
                },
                timeout=max(self.command_timeout, float(timeout) + 5.0),
            )
        )

    def get_variables(
        self,
        node_names: list[str] | None = None,
        use_cache: bool = False,
    ) -> dict[str, Any]:
        result = self._call(
            "get_variables",
            {"node_names": node_names, "use_cache": use_cache},
        )
        return dict(result or {})

    def get_opc_variable_metadata(
        self,
        node_name: str,
    ) -> tuple[str, str | None]:
        result = self._call(
            "get_opc_variable_metadata",
            {"node_name": node_name},
        )
        if isinstance(result, (list, tuple)) and len(result) == 2:
            return str(result[0]), None if result[1] is None else str(result[1])
        return node_name, None

    def check_variable_accessible(
        self,
        node_name: str,
    ) -> tuple[bool, str | None]:
        result = self._call(
            "check_variable_accessible",
            {"node_name": node_name},
        )
        if isinstance(result, (list, tuple)) and len(result) == 2:
            return bool(result[0]), None if result[1] is None else str(result[1])
        return bool(result), None

    def disconnect(self) -> None:
        """连接由 ``szlab_poly_plc`` 持有，业务设备释放时不关闭它。"""


class UnifiedPLCGatewayMixin:
    """让 PLC 工位统一在 ROS ``post_init`` 阶段连接 PLC 模块。"""

    plc_device_id: str
    plc_action_timeout: float
    plc_server_wait_timeout: float
    _plc_gateway: Any
    _client: Any

    def _configure_plc_gateway(
        self,
        *,
        plc_device_id: str = "szlab_poly_plc",
        plc_gateway: Any = None,
        plc_action_timeout: float = 300.0,
        plc_server_wait_timeout: float = 10.0,
    ) -> None:
        self.plc_device_id = plc_device_id
        self.plc_action_timeout = float(plc_action_timeout)
        self.plc_server_wait_timeout = float(plc_server_wait_timeout)
        self._plc_gateway = plc_gateway
        self._client = plc_gateway

    def set_plc_gateway(self, plc_gateway: Any) -> None:
        self._plc_gateway = plc_gateway
        self._client = plc_gateway

    def post_init(self, ros_node: Any) -> None:
        if self._plc_gateway is None:
            self.set_plc_gateway(
                PLCActionGateway(
                    ros_node,
                    plc_device_id=self.plc_device_id,
                    command_timeout=self.plc_action_timeout,
                    server_wait_timeout=self.plc_server_wait_timeout,
                )
            )
        self._on_plc_gateway_ready()

    def _on_plc_gateway_ready(self) -> None:
        """子类可在统一 PLC adapter 就绪后执行一次初始化。"""
