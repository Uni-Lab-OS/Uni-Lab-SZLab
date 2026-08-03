"""SZLab Warehouse Site 到 PLC/机器人参数的部署映射。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Iterable

from szlab_poly_studio.devices.szlab_poly_plc.device import (
    POWDER_CONTAINER_SENSORS,
    S2_TIP_SENSORS,
    S3_UNUSED_BEAKER_SENSORS,
    S3_UNUSED_SAMPLE_VIAL_SENSORS,
    S10_LIQUID_REAGENT_SENSORS,
    S11_USED_BEAKER_SENSORS,
    S11_USED_SAMPLE_VIAL_SENSORS,
)

# Deployment-owned copies intentionally live outside the robot package so the
# Site resolver remains importable before the robot device/gateway is built.
S04_SENSOR_BY_POSITION = {
    1: "传感器状态_上位机[2].NO[10]",
    2: "传感器状态_上位机[2].NO[11]",
    3: "传感器状态_上位机[2].NO[12]",
    4: "传感器状态_上位机[2].NO[13]",
    5: "传感器状态_上位机[2].NO[14]",
    6: "传感器状态_上位机[2].NO[15]",
}
S05_MATERIAL_SENSOR = "传感器状态_上位机[3].NO[0]"
S06_MATERIAL_SENSOR = "传感器状态_上位机[3].NO[1]"
S072_SENSOR_BY_POSITION = {
    1: "传感器状态_上位机[3].NO[14]",
    2: "传感器状态_上位机[3].NO[15]",
}

S1_INVENTORY_ONLY_SITE_LABELS = (
    "L1C1",
    "L1C2",
    "L1C3",
    "L2C1",
    "L2C2",
    "L2C3",
)

_SITE_OWNER_ALIASES = {
    # Storage warehouses.
    "s02": "s2_tip_warehouse",
    "s2": "s2_tip_warehouse",
    "s2_tip_warehouse": "s2_tip_warehouse",
    "szlab_poly_s2_tip_placeholder_warehouse": "s2_tip_warehouse",
    "tip 头架子": "s2_tip_warehouse",
    "s03": "s3_unused_beaker",
    "s3": "s3_unused_beaker",
    "s3_unused_beaker": "s3_unused_beaker",
    "szlab_poly_s3_unused_beaker_warehouse": "s3_unused_beaker",
    "烧杯堆栈2": "s3_unused_beaker",
    "s071": "powder_container_warehouse",
    "powder_container_warehouse": "powder_container_warehouse",
    "szlab_poly_powder_container_placeholder_warehouse": "powder_container_warehouse",
    "固体粉桶堆栈": "powder_container_warehouse",
    "s10": "s10_liquid_reagent",
    "s10_liquid_reagent": "s10_liquid_reagent",
    "szlab_poly_s10_liquid_reagent_placeholder_warehouse": "s10_liquid_reagent",
    "试剂瓶堆栈": "s10_liquid_reagent",
    "s11": "s11_used_beaker",
    "s11_used_beaker": "s11_used_beaker",
    "szlab_poly_s11_used_beaker_warehouse": "s11_used_beaker",
    "烧杯堆栈1": "s11_used_beaker",
    # Device-owned lightweight warehouses.
    "s04": "s04_process_warehouse",
    "s4": "s04_process_warehouse",
    "s04_process_warehouse": "s04_process_warehouse",
    "szlab_s04_process_warehouse": "s04_process_warehouse",
    "szlab_s04processcarrier": "s04_process_warehouse",
    "s04磁搅工位仓": "s04_process_warehouse",
    "s05": "s05_process_warehouse",
    "s5": "s05_process_warehouse",
    "s05_process_warehouse": "s05_process_warehouse",
    "szlab_s05_process_warehouse": "s05_process_warehouse",
    "szlab_s05processcarrier": "s05_process_warehouse",
    "s05拍照工位仓": "s05_process_warehouse",
    "s06": "s06_process_warehouse",
    "s6": "s06_process_warehouse",
    "s06_process_warehouse": "s06_process_warehouse",
    "szlab_s06_process_warehouse": "s06_process_warehouse",
    "szlab_s06processcarrier": "s06_process_warehouse",
    "s06加液工位仓": "s06_process_warehouse",
    "s07": "s07_process_warehouse",
    "s7": "s07_process_warehouse",
    "s07_process_warehouse": "s07_process_warehouse",
    "szlab_s07_process_warehouse": "s07_process_warehouse",
    "szlab_s07processcarrier": "s07_process_warehouse",
    "s07固体加料转盘仓": "s07_process_warehouse",
}


@dataclass(frozen=True)
class SiteControlBinding:
    """一个物理 Site 的部署侧观测和机器人位置参数。"""

    warehouse_instance_id: str
    station: str
    site_label: str
    sensor_key: str
    controller_position: int
    presence_variable: str
    product_type: int | None = None
    robot_action_ready: bool = True
    blocked_reason: str = ""


def resolve_s2_site(position: int | str) -> SiteControlBinding:
    layer, column, number = _resolve_grid_position(
        position,
        layers=3,
        columns=2,
        label_pattern=r"T(?P<layer>\d+)(?P<column>\d+)",
        station="S02",
    )
    return SiteControlBinding(
        warehouse_instance_id="s2_tip_warehouse",
        station="S02",
        site_label=f"T{layer}{column}",
        sensor_key=str(number),
        controller_position=number,
        presence_variable=S2_TIP_SENSORS[str(number)],
    )


def resolve_s3_site(product_type: int, position: int | str) -> SiteControlBinding:
    return _resolve_container_stack_site(product_type, position, used=False)


def resolve_s071_site(position: int | str) -> SiteControlBinding:
    layer, column, number = _resolve_grid_position(
        position,
        layers=2,
        columns=3,
        label_pattern=r"L(?P<layer>\d+)C(?P<column>\d+)",
        station="S071",
    )
    sensor_key = f"{layer}-{column}"
    return SiteControlBinding(
        warehouse_instance_id="powder_container_warehouse",
        station="S071",
        site_label=f"L{layer}C{column}",
        sensor_key=sensor_key,
        controller_position=number,
        presence_variable=POWDER_CONTAINER_SENSORS[sensor_key],
    )


def resolve_s10_site(position: int | str) -> SiteControlBinding:
    row, column, number = _resolve_grid_position(
        position,
        layers=4,
        columns=5,
        label_pattern=r"R(?P<layer>\d+)C(?P<column>\d+)",
        station="S10",
    )
    sensor_key = f"{row}-{column}"
    return SiteControlBinding(
        warehouse_instance_id="s10_liquid_reagent",
        station="S10",
        site_label=f"R{row}C{column}",
        sensor_key=sensor_key,
        controller_position=number,
        presence_variable=S10_LIQUID_REAGENT_SENSORS[sensor_key],
    )


def resolve_s11_site(product_type: int, position: int | str) -> SiteControlBinding:
    return _resolve_container_stack_site(product_type, position, used=True)


def resolve_s04_site(position: int | str) -> SiteControlBinding:
    value = str(position).strip().upper()
    if value.startswith("S04") and value[3:].isdigit():
        value = value[3:]
    number = _single_axis_position(value, count=6, station="S04")
    return SiteControlBinding(
        warehouse_instance_id="s04_process_warehouse",
        station="S04",
        site_label=f"S04{number}",
        sensor_key=str(number),
        controller_position=number,
        presence_variable=S04_SENSOR_BY_POSITION[number],
        product_type=1,
    )


def resolve_s05_site(position: int | str) -> SiteControlBinding:
    number = _single_process_position(position, station="S05", label="S051")
    return SiteControlBinding(
        warehouse_instance_id="s05_process_warehouse",
        station="S05",
        site_label="S051",
        sensor_key="1",
        controller_position=number,
        presence_variable=S05_MATERIAL_SENSOR,
        product_type=1,
    )


def resolve_s06_site(position: int | str) -> SiteControlBinding:
    number = _single_process_position(position, station="S06", label="S061")
    return SiteControlBinding(
        warehouse_instance_id="s06_process_warehouse",
        station="S06",
        site_label="S061",
        sensor_key="1",
        controller_position=number,
        presence_variable=S06_MATERIAL_SENSOR,
        product_type=1,
    )


def resolve_s07_process_site(position: int | str) -> SiteControlBinding:
    value = str(position).strip().upper()
    if value.startswith("P"):
        value = value[1:]
    number = _single_axis_position(value, count=10, station="S07")
    return SiteControlBinding(
        warehouse_instance_id="s07_process_warehouse",
        # Pxx is the Inventory destination.  The selected carousel position is
        # first presented by S07, then the existing robot program approaches it
        # through the S072 position-1 hand-off point.
        station="S072",
        site_label=f"P{number:02d}",
        sensor_key=f"S07位置{number}二维码",
        controller_position=1,
        presence_variable=S072_SENSOR_BY_POSITION[1],
        product_type=1,
    )


def resolve_s072_site(position: int | str) -> SiteControlBinding:
    value = str(position).strip().upper()
    if value.startswith("S072"):
        value = value[4:]
    number = _single_axis_position(value, count=2, station="S072")
    return SiteControlBinding(
        warehouse_instance_id="s07_process_warehouse",
        station="S072",
        site_label=f"S072{number}",
        sensor_key=str(number),
        controller_position=number,
        presence_variable=S072_SENSOR_BY_POSITION[number],
        product_type=1,
    )


def resolve_robot_site_reference(mount_resource: Any, site: str) -> SiteControlBinding:
    """Resolve ``ResourceSlot parent + local Site`` into a deployment binding.

    ``mount_resource`` is the authoritative parent.  ``site`` remains a local
    label, while low-level commissioning may still use the controller number or
    row-column expression accepted by the selected warehouse.
    """

    owner = _resolve_mount_owner(mount_resource)
    local_site = str(site).strip()
    if not local_site:
        raise ValueError("site 不能为空")

    if owner == "s2_tip_warehouse":
        return resolve_s2_site(local_site)
    if owner == "s3_unused_beaker":
        return resolve_s3_site(_product_type_from_site_label(local_site, station="S03"), local_site)
    if owner == "powder_container_warehouse":
        return resolve_s071_site(local_site)
    if owner == "s10_liquid_reagent":
        return resolve_s10_site(local_site)
    if owner == "s11_used_beaker":
        return resolve_s11_site(_product_type_from_site_label(local_site, station="S11"), local_site)
    if owner == "s04_process_warehouse":
        return resolve_s04_site(local_site)
    if owner == "s05_process_warehouse":
        return resolve_s05_site(local_site)
    if owner == "s06_process_warehouse":
        return resolve_s06_site(local_site)
    if owner == "s07_process_warehouse":
        if local_site.strip().upper().startswith("S072"):
            return resolve_s072_site(local_site)
        return resolve_s07_process_site(local_site)
    raise ValueError(f"未注册机械臂 Site owner: {owner}")


def canonical_site_reference(binding: SiteControlBinding) -> str:
    return f"{binding.warehouse_instance_id}/{binding.site_label}"


def resolve_canonical_site_reference(site: str) -> SiteControlBinding:
    """Resolve the journal/adapter form; workflow callers do not use this."""

    value = str(site).strip()
    if "/" not in value:
        raise ValueError("内部 Site 引用必须是 <warehouse>/<site>")
    owner, local_site = value.split("/", maxsplit=1)
    return resolve_robot_site_reference(owner, local_site)


def iter_robot_site_bindings() -> Iterable[SiteControlBinding]:
    """按 Warehouse Site 顺序返回全部 104 个可控 Site binding。"""

    for position in range(1, 7):
        yield resolve_s2_site(position)
    for position in range(1, 19):
        yield resolve_s3_site(1, position)
        yield resolve_s3_site(3, position)
    for position in range(1, 7):
        yield resolve_s071_site(position)
    for position in range(1, 21):
        yield resolve_s10_site(position)
    for position in range(1, 19):
        yield resolve_s11_site(1, position)
        yield resolve_s11_site(3, position)


def iter_process_site_bindings() -> Iterable[SiteControlBinding]:
    """Return all currently modeled device-owned process Sites."""

    for position in range(1, 7):
        yield resolve_s04_site(position)
    yield resolve_s05_site(1)
    yield resolve_s06_site(1)
    for position in range(1, 11):
        yield resolve_s07_process_site(position)
    for position in range(1, 3):
        yield resolve_s072_site(position)


def _resolve_mount_owner(mount_resource: Any) -> str:
    candidates: list[str] = []
    if isinstance(mount_resource, str):
        candidates.append(mount_resource)
    elif isinstance(mount_resource, Mapping):
        for key in ("id", "name", "class", "category", "model", "resource_template_id"):
            value = mount_resource.get(key)
            if value:
                candidates.append(str(value))
        meta_data = mount_resource.get("meta_data")
        if isinstance(meta_data, Mapping):
            for key in ("source_node_id", "resource_template_id"):
                value = meta_data.get(key)
                if value:
                    candidates.append(str(value))
    else:
        for attribute in ("id", "name", "category", "model", "resource_template_id"):
            value = getattr(mount_resource, attribute, None)
            if value:
                candidates.append(str(value))
        extra = getattr(mount_resource, "extra", None)
        if isinstance(extra, Mapping):
            candidates.extend(str(value) for value in extra.values() if isinstance(value, str))

    for candidate in candidates:
        normalized = candidate.strip().casefold()
        for prefix in ("community.szlab_poly_studio.", "szlab_poly_studio.resources.warehouses."):
            if normalized.startswith(prefix):
                normalized = normalized.removeprefix(prefix)
        owner = _SITE_OWNER_ALIASES.get(normalized)
        if owner is not None:
            return owner
    shown = ", ".join(candidates) or type(mount_resource).__name__
    raise ValueError(f"无法从 ResourceSlot 识别 Site 父 Warehouse: {shown}")


def _single_axis_position(value: int | str, *, count: int, station: str) -> int:
    text = str(value).strip()
    if not text.isdigit() or not 1 <= int(text) <= count:
        raise ValueError(f"{station} 位置必须在 1-{count} 范围内")
    return int(text)


def _single_process_position(value: int | str, *, station: str, label: str) -> int:
    text = str(value).strip().upper()
    if text == label:
        return 1
    return _single_axis_position(text, count=1, station=station)


def _product_type_from_site_label(site_label: str, *, station: str) -> int:
    match = re.fullmatch(r"L\d+(?P<row>[AB])\d+", str(site_label).strip().upper())
    if match is None:
        raise ValueError(f"{station} 标准动作必须使用含 A/B 行的完整 Site 标签")
    return 3 if match.group("row") == "A" else 1


def _resolve_container_stack_site(
    product_type: int,
    position: int | str,
    *,
    used: bool,
) -> SiteControlBinding:
    product_type = int(product_type)
    if product_type == 1:
        row = "B"
        sensors = S11_USED_BEAKER_SENSORS if used else S3_UNUSED_BEAKER_SENSORS
    elif product_type == 3:
        row = "A"
        sensors = S11_USED_SAMPLE_VIAL_SENSORS if used else S3_UNUSED_SAMPLE_VIAL_SENSORS
    else:
        raise ValueError("S03/S11 产品类型必须是 1(500mL烧杯) 或 3(500mL样品瓶)")

    match = re.fullmatch(r"L(?P<layer>\d+)(?P<row>[AB])(?P<column>\d+)", str(position).strip().upper())
    if match is not None:
        if match.group("row") != row:
            raise ValueError(f"产品类型 {product_type} 与 Site {position} 的 A/B 行不一致")
        normalized_position: int | str = f"{match.group('layer')}-{match.group('column')}"
    else:
        normalized_position = position

    layer, column, number = _resolve_grid_position(
        normalized_position,
        layers=3,
        columns=6,
        label_pattern=None,
        station="S11" if used else "S03",
    )
    sensor_key = f"{layer}-{column}"
    return SiteControlBinding(
        warehouse_instance_id="s11_used_beaker" if used else "s3_unused_beaker",
        station="S11" if used else "S03",
        site_label=f"L{layer}{row}{column}",
        sensor_key=sensor_key,
        controller_position=number,
        presence_variable=sensors[sensor_key],
        product_type=product_type,
    )


def _resolve_grid_position(
    position: int | str,
    *,
    layers: int,
    columns: int,
    label_pattern: str | None,
    station: str,
) -> tuple[int, int, int]:
    value = str(position).strip().upper()
    layer: int
    column: int

    if value.isdigit():
        number = int(value)
        if not 1 <= number <= layers * columns:
            raise ValueError(f"{station} 位置必须在 1-{layers * columns} 范围内")
        layer = (number - 1) // columns + 1
        column = (number - 1) % columns + 1
        return layer, column, number

    match = re.fullmatch(r"(?P<layer>\d+)-(?P<column>\d+)", value)
    if match is None and label_pattern is not None:
        match = re.fullmatch(label_pattern, value)
    if match is None:
        raise ValueError(f"{station} 位置格式无效: {position}")

    layer = int(match.group("layer"))
    column = int(match.group("column"))
    if not 1 <= layer <= layers or not 1 <= column <= columns:
        raise ValueError(f"{station} 位置超出 {layers}层×{columns}列范围: {position}")
    return layer, column, (layer - 1) * columns + column
