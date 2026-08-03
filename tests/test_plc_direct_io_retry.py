from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Any

from szlab_poly_studio.devices.szlab_poly_plc import device as plc


class FakeReadNode:
    def __init__(self, results: list[tuple[Any, bool] | Exception]) -> None:
        self.results = list(results)
        self.calls = 0

    def read(self) -> tuple[Any, bool]:
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class RecordingClient:
    def __init__(self, probe: Any | None = None) -> None:
        self.probe = probe
        self.connect_calls = 0
        self.disconnect_calls = 0

    def connect(self) -> None:
        self.connect_calls += 1

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def get_node(self, _node_id: Any) -> Any:
        if self.probe is None:
            raise AssertionError("probe node was not configured")
        return self.probe


def _bare_plc(node: Any, client: RecordingClient | None = None) -> plc.SZLabPolyPLCDevice:
    device = object.__new__(plc.SZLabPolyPLCDevice)
    device._io_lock = threading.RLock()
    device._direct_node_id_map = {"A": "ns=4;s=上位机通讯|A"}
    device._variables_to_find = {"A": {}}
    device._node_registry = {"A": node}
    device.use_node = lambda _name: node
    device.client = client or RecordingClient()
    device.reconnect_attempts = 3
    device.reconnect_delay = 0.0
    device._connection_healthy = True
    device._last_connection_check_at = None
    device._last_connection_error = None
    device._reconnect_count = 0
    device.connection_check_interval = 5.0
    device._connection_monitor_enabled = False
    device._connection_check_timer = None
    device.heartbeat_on = False
    device._heartbeat_timer = None
    return device


def test_direct_read_retries_a_transient_node_error(monkeypatch) -> None:
    node = FakeReadNode([(None, True), (42, False)])
    device = _bare_plc(node)
    delays: list[float] = []
    monkeypatch.setattr(plc.time, "sleep", delays.append)

    assert device.read_variable("A", use_cache=False) == 42
    assert node.calls == 2
    assert delays == [plc.OPCUA_DIRECT_IO_RETRY_DELAY]


def test_direct_read_still_fails_after_retry_budget(monkeypatch) -> None:
    node = FakeReadNode([(None, True)] * plc.OPCUA_DIRECT_IO_ATTEMPTS)
    device = _bare_plc(node)
    monkeypatch.setattr(plc.time, "sleep", lambda _delay: None)

    try:
        device.read_variable("A", use_cache=False)
    except RuntimeError as exc:
        assert "已重试 3 次" in str(exc)
    else:
        raise AssertionError("missing direct node must still fail")


def test_direct_read_retries_a_timeout(monkeypatch) -> None:
    node = FakeReadNode([TimeoutError(), (42, False)])
    device = _bare_plc(node)
    delays: list[float] = []
    monkeypatch.setattr(plc.time, "sleep", delays.append)

    assert device.read_variable("A", use_cache=False) == 42
    assert node.calls == 2
    assert delays == [plc.OPCUA_DIRECT_IO_RETRY_DELAY]


def test_direct_read_reconnects_before_retrying_a_dropped_session(monkeypatch: Any) -> None:
    node = FakeReadNode([ConnectionError("socket closed"), (42, False)])
    client = RecordingClient()
    device = _bare_plc(node, client)
    monkeypatch.setattr(plc.time, "sleep", lambda _delay: None)

    assert device.read_variable("A", use_cache=False) == 42
    assert client.disconnect_calls == 1
    assert client.connect_calls == 1


def test_direct_read_reconnects_on_an_invalid_opcua_session(monkeypatch: Any) -> None:
    node = FakeReadNode([RuntimeError("BadSessionIdInvalid"), (42, False)])
    client = RecordingClient()
    device = _bare_plc(node, client)
    monkeypatch.setattr(plc.time, "sleep", lambda _delay: None)

    assert device.read_variable("A", use_cache=False) == 42
    assert client.disconnect_calls == 1
    assert client.connect_calls == 1


def test_direct_write_retries_bad_node_id_unknown(monkeypatch) -> None:
    device = _bare_plc(object())
    calls = 0
    delays: list[float] = []

    def write_value(_node: Any, _value: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("BadNodeIdUnknown")

    device._write_value_only = write_value
    monkeypatch.setattr(plc.time, "sleep", delays.append)

    assert device.write_variable("A", 7) is True
    assert calls == 2
    assert delays == [plc.OPCUA_DIRECT_IO_RETRY_DELAY]


def test_direct_write_retries_a_timeout(monkeypatch) -> None:
    device = _bare_plc(object())
    calls = 0
    delays: list[float] = []

    def write_value(_node: Any, _value: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError

    device._write_value_only = write_value
    monkeypatch.setattr(plc.time, "sleep", delays.append)

    assert device.write_variable("A", 7) is True
    assert calls == 2
    assert delays == [plc.OPCUA_DIRECT_IO_RETRY_DELAY]


def test_direct_write_reconnects_before_retrying_a_dropped_session(monkeypatch: Any) -> None:
    client = RecordingClient()
    device = _bare_plc(object(), client)
    calls = 0

    def write_value(_node: Any, _value: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("transport endpoint is not connected")

    device._write_value_only = write_value
    monkeypatch.setattr(plc.time, "sleep", lambda _delay: None)

    assert device.write_variable("A", 7) is True
    assert calls == 2
    assert client.disconnect_calls == 1
    assert client.connect_calls == 1


def test_direct_write_logs_variable_value_node_id_and_failure_reason(monkeypatch) -> None:
    infos: list[str] = []
    errors: list[str] = []
    monkeypatch.setattr(plc.logger, "info", lambda message: infos.append(str(message)))
    monkeypatch.setattr(plc.logger, "error", lambda message: errors.append(str(message)))

    device = _bare_plc(object())
    device._write_value_only = lambda _node, _value: None
    assert device.write_variable("A", 7)

    def fail_write(_node: Any, _value: Any) -> None:
        raise ValueError("wrong variant type")

    device._write_value_only = fail_write
    try:
        device.write_variable("A", 8)
    except RuntimeError:
        pass
    else:
        raise AssertionError("failed PLC write must raise RuntimeError")

    assert any(
        "[SZLAB-PLC-WRITE] START" in message
        and "variable=A node_id=ns=4;s=上位机通讯|A" in message
        and "value=7" in message
        for message in infos
    )
    assert any("[SZLAB-PLC-WRITE] SUCCESS" in message for message in infos)
    assert any(
        "[SZLAB-PLC-WRITE] FAIL" in message
        and "value=8" in message
        and "ValueError: wrong variant type" in message
        for message in errors
    )


def test_direct_reads_are_serialized_on_the_shared_opcua_client() -> None:
    class ConcurrentNode:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def read(self) -> tuple[int, bool]:
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.01)
            with self.lock:
                self.active -= 1
            return 1, False

    node = ConcurrentNode()
    device = _bare_plc(node)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _index: device.read_variable("A"), range(8)))

    assert results == [1] * 8
    assert node.max_active == 1


def test_active_connection_check_reconnects_and_reprobes(monkeypatch: Any) -> None:
    class Probe:
        def __init__(self) -> None:
            self.calls = 0

        def get_value(self) -> int:
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("server stopped responding")
            return 0

    probe = Probe()
    client = RecordingClient(probe)
    device = _bare_plc(FakeReadNode([]), client)
    monkeypatch.setattr(plc.time, "sleep", lambda _delay: None)

    assert device._check_connection_once() is True
    assert probe.calls == 2
    assert client.disconnect_calls == 1
    assert client.connect_calls == 1
    assert device._connection_healthy is True
    assert device._reconnect_count == 1


def test_connection_check_is_serialized_with_business_io() -> None:
    class SharedTransport:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def call(self, result: Any) -> Any:
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.01)
            with self.lock:
                self.active -= 1
            return result

    class ReadNode:
        def __init__(self, transport: SharedTransport) -> None:
            self.transport = transport

        def read(self) -> tuple[int, bool]:
            return self.transport.call((1, False))

    class Probe:
        def __init__(self, transport: SharedTransport) -> None:
            self.transport = transport

        def get_value(self) -> int:
            return self.transport.call(0)

    transport = SharedTransport()
    device = _bare_plc(ReadNode(transport), RecordingClient(Probe(transport)))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        read_future = executor.submit(device.read_variable, "A")
        check_future = executor.submit(device._check_connection_once)

    assert read_future.result() == 1
    assert check_future.result() is True
    assert transport.max_active == 1


def test_connection_status_action_reports_recovery_state(monkeypatch: Any) -> None:
    device = _bare_plc(FakeReadNode([]))
    device._last_connection_check_at = 123.0
    device._reconnect_count = 2
    monkeypatch.setattr(device, "_check_connection_once", lambda: True)

    assert device.check_opcua_connection() == {
        "success": True,
        "connected": True,
        "last_check_at": 123.0,
        "last_error": None,
        "reconnect_count": 2,
    }


def test_auto_connect_starts_the_connection_monitor(monkeypatch: Any, tmp_path: Any) -> None:
    class FakeClient:
        def __init__(self, _url: str, timeout: float) -> None:
            self.timeout = timeout

    csv_path = tmp_path / "plc.csv"
    csv_path.write_text("变量名\nA\n", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(plc, "Client", FakeClient)
    monkeypatch.setattr(plc.SZLabPolyPLCDevice, "_connect", lambda _self: calls.append("connect"))
    monkeypatch.setattr(
        plc.SZLabPolyPLCDevice,
        "_start_connection_monitor",
        lambda _self: calls.append("monitor"),
    )

    plc.SZLabPolyPLCDevice(url="opc.tcp://127.0.0.1:4840", csv_path=str(csv_path))

    assert calls == ["connect", "monitor"]


def test_connection_monitor_starts_a_daemon_timer(monkeypatch: Any) -> None:
    created: list[Any] = []

    class FakeTimer:
        def __init__(self, interval: float, callback: Any) -> None:
            self.interval = interval
            self.callback = callback
            self.daemon = False
            self.started = False
            created.append(self)

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            pass

    monkeypatch.setattr(plc.threading, "Timer", FakeTimer)
    device = _bare_plc(FakeReadNode([]))

    device._start_connection_monitor()
    device._start_connection_monitor()

    assert device._connection_monitor_enabled is True
    assert len(created) == 1
    assert created[0].interval == 5.0
    assert created[0].callback == device._run_connection_check
    assert created[0].daemon is True
    assert created[0].started is True


def test_disconnect_stops_the_connection_monitor() -> None:
    class FakeTimer:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    client = RecordingClient()
    device = _bare_plc(FakeReadNode([]), client)
    timer = FakeTimer()
    device._connection_monitor_enabled = True
    device._connection_check_timer = timer

    device.disconnect()

    assert timer.cancelled is True
    assert device._connection_monitor_enabled is False
    assert device._connection_check_timer is None
    assert device._connection_healthy is False
    assert client.disconnect_calls == 1
