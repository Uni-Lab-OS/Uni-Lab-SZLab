#!/usr/bin/env python3
"""Deterministic local OPC UA endpoint for SZLab workflow E2E runs."""

from __future__ import annotations

import argparse
import csv
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opcua import Server, ua

DEFAULT_CSV = (
    Path(__file__).resolve().parents[1]
    / "szlab_poly_studio/devices/szlab_poly_plc/szlab_plc_0730.csv"
)
DEFAULT_ENDPOINT = "opc.tcp://127.0.0.1:50100/"


@dataclass(frozen=True)
class VariableDefinition:
    name: str
    value: Any
    variant_type: ua.VariantType


def _variant_definition(name: str, data_type: str, initial_value: str) -> VariableDefinition | None:
    normalized_type = data_type.strip().upper()
    if (
        not normalized_type
        or normalized_type.startswith("ST_")
        or ("[" in normalized_type and not normalized_type.startswith("STRING"))
    ):
        return None

    raw_initial = initial_value.strip()
    if normalized_type == "BOOL":
        value = raw_initial.upper() in {"1", "ON", "TRUE"}
        variant_type = ua.VariantType.Boolean
    elif normalized_type == "SINT":
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.SByte
    elif normalized_type in {"USINT", "BYTE"}:
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.Byte
    elif normalized_type == "INT":
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.Int16
    elif normalized_type in {"UINT", "WORD"}:
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.UInt16
    elif normalized_type in {"DINT", "TIME"}:
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.Int32
    elif normalized_type in {"UDINT", "DWORD"}:
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.UInt32
    elif normalized_type == "LINT":
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.Int64
    elif normalized_type in {"ULINT", "LWORD"}:
        value = int(raw_initial or 0)
        variant_type = ua.VariantType.UInt64
    elif normalized_type == "REAL":
        value = float(raw_initial or 0.0)
        variant_type = ua.VariantType.Float
    elif normalized_type == "LREAL":
        value = float(raw_initial or 0.0)
        variant_type = ua.VariantType.Double
    elif normalized_type.startswith("STRING"):
        value = raw_initial
        variant_type = ua.VariantType.String
    else:
        return None
    return VariableDefinition(name=name, value=value, variant_type=variant_type)


def load_variable_definitions(csv_path: Path) -> list[VariableDefinition]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "gb18030", "gbk"):
        for delimiter in (",", "\t"):
            try:
                with csv_path.open(newline="", encoding=encoding) as csv_file:
                    reader = csv.DictReader(csv_file, delimiter=delimiter)
                    if not {"变量名", "数据类型"}.issubset(reader.fieldnames or []):
                        continue
                    definitions: list[VariableDefinition] = []
                    seen: set[str] = set()
                    for row in reader:
                        name = (row.get("变量名") or "").strip()
                        if not name or name in seen:
                            continue
                        definition = _variant_definition(
                            name,
                            row.get("数据类型") or "",
                            row.get("初始值") or "",
                        )
                        if definition is None:
                            continue
                        seen.add(name)
                        definitions.append(definition)
                    return definitions
            except UnicodeDecodeError as exc:
                last_error = exc
                break
    if last_error is not None:
        raise last_error
    raise ValueError(f"CSV 缺少变量名/数据类型列: {csv_path}")


def build_server(endpoint: str, definitions: list[VariableDefinition]) -> Server:
    server = Server()
    server.set_endpoint(endpoint)
    server.set_server_name("SZLab deterministic local PLC")
    server.register_namespace("urn:unilab:debug:dummy-2")
    server.register_namespace("urn:unilab:debug:dummy-3")
    namespace = server.register_namespace("urn:unilab:szlab:plc")
    if namespace != 4:
        raise RuntimeError(f"expected namespace index 4, got {namespace}")

    folder = server.get_objects_node().add_folder(
        ua.NodeId("上位机通讯", namespace),
        ua.QualifiedName("上位机通讯", namespace),
    )
    for definition in definitions:
        variable = folder.add_variable(
            ua.NodeId(f"上位机通讯|{definition.name}", namespace),
            ua.QualifiedName(definition.name, namespace),
            definition.value,
            definition.variant_type,
        )
        variable.set_writable()
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    definitions = load_variable_definitions(args.csv.resolve())
    server = build_server(args.endpoint, definitions)
    stopped = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    server.start()
    print(
        f"SZLAB_LOCAL_OPCUA_READY endpoint={args.endpoint} ns=4 "
        f"variables={len(definitions)} csv={args.csv.resolve()}",
        flush=True,
    )
    try:
        while not stopped:
            time.sleep(0.2)
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
