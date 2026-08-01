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


def _bare_plc(node: Any) -> plc.SZLabPolyPLCDevice:
    device = object.__new__(plc.SZLabPolyPLCDevice)
    device._io_lock = threading.RLock()
    device._direct_node_id_map = {"A": "ns=4;s=上位机通讯|A"}
    device.use_node = lambda _name: node
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
