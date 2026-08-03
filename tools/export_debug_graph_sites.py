#!/usr/bin/env python3
"""Export SZLab debug graph sizes/sites from the station layout spec.

Coordinate convention (unless noted otherwise): distances are measured from
the owner's bottom-left corner. Deck size uses 宽→X / 长→Y.

Layout source: field measurements for tip rack, beaker stacks, reagent stack;
《理论交点测距结果.xlsx》(dX/dY/dZ 相对台面左下角) + 对应 CAD STL 包围盒 for
the powder stack and the S07/S08/S09 stations.
"""

from __future__ import annotations

import argparse
import importlib.resources as resources
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import yaml

from szlab_poly_studio.resources.carriers.beaker import SZLab_BeakerStackCarrier
from szlab_poly_studio.resources.carriers.powder import SZLab_PowderContainerStackCarrier
from szlab_poly_studio.resources.carriers.reagent import SZLab_ReagentBottleStackCarrier
from szlab_poly_studio.resources.carriers.tip_box_loader import SZLab_TipBoxLoaderCarrier
from szlab_poly_studio.resources.materials import (
    beaker_500ml,
    liquid_reagent_bottle_100ml,
    pipette_tip,
    powder_container,
    sample_vial_250ml,
    sample_vial_500ml,
    tip_box,
)

# 工站：宽 3634 (X) × 长 1674 (Y)
DECK_SIZE = {"size_x": 3634.0, "size_y": 1674.0, "size_z": 0.0}
S1_WORKSTATION_HEIGHT_MM = 10.0
DECK_LOCAL_Z_MM = S1_WORKSTATION_HEIGHT_MM + 10.0

# Tip 头架子（相对工站左下角）
# 尺寸与层板高度取自 CAD：DXY260502-02-00 tip 头堆栈 / 02.02-00 TIP 盒组件。
TIP_RACK = {
    "node_id": "s2_tip_warehouse",
    "position": {"x": 3065.0, "y": 250.0, "z": 0.0},
    # 外框 310 × 140 × 558；层板顶面 120 / 320 / 520
    "size": {"size_x": 310.0, "size_y": 140.0, "size_z": 558.0},
    # 6 slots = 3 层 × 每层 2 个；层间高度差 200，同层 x 差 120
    "first_slot": {"x": 52.0, "y": 6.0, "z": 120.0},
    # TIP 盒组件的实际占位：X 86 × Y 128 × Z 136
    "slot_size": {"width": 86.0, "height": 128.0, "depth": 136.0},
    "rows": 3,
    "cols": 2,
    "row_dz": 200.0,
    "col_dx": 120.0,
}

# TIP 盒组件内部：孔板顶面 113，枪头 4 列（X）× 6 行（Y），间距 18，Ø14.7
TIP_BOX = {
    "cols": 4,
    "rows": 6,
    "pitch": 18.0,
    "first_tip": {"x": 16.2, "y": 21.4},
    "tip_diameter": 14.7,
    "plate_z": 113.0,
}

# 烧杯堆栈 ×2：两个规格相同（3 层 × 6 列 × 2 行）
# A 行 = 500mL 样品瓶，B 行 = 烧杯
BEAKER_STACKS = [
    {
        "node_id": "s11_used_beaker",
        "name": "烧杯堆栈1",
        "position": {"x": 2538.5, "y": 1394.0, "z": 0.0},
    },
    {
        "node_id": "s3_unused_beaker",
        "name": "烧杯堆栈2",
        "position": {"x": 2235.0, "y": 190.0, "z": 0.0},
    },
]

# 试剂瓶堆栈（S10）：几何由 SZLab_ReagentBottleStackCarrier 定义
REAGENT_STACK = {
    "node_id": "s10_liquid_reagent",
    "name": "试剂瓶堆栈",
    "position": {"x": 1928.5, "y": 1404.0, "z": 0.0},
}

# S1 上料过渡仓（tip 盒上料工装）：几何由 SZLab_TipBoxLoaderCarrier 定义。
# 相对 CAD 转了 90°（长边 442 沿 Y）。按总装图，它站在台面右端、
# 深度方向居中：y = (1674 - 442) / 2，右侧面与台面右边缘齐平。
TIP_BOX_LOADER = {
    "node_id": "s1_loading_buffer",
    "name": "S1 上料过渡仓",
    "position": {"x": 3434.0, "y": 616.0, "z": 0.0},
}

# 固体粉桶堆栈：几何由 SZLab_PowderContainerStackCarrier 定义
# 位置取自《理论交点测距结果》「固体粉桶仓占位」dX=80 dY=786.5 dZ=0
POWDER_STACK = {
    "node_id": "powder_container_warehouse",
    "name": "固体粉桶堆栈",
    "position": {"x": 80.0, "y": 786.5, "z": 0.0},
}

# 工站设备：位置来自《理论交点测距结果》，表里记录的交点即零件占位的左下角
# (x/y) 与底面高度 (z)。带 category 的设备占位尺寸从设备/资源自己的
# models/shape.yml 读取，几何细节（转盘、龙门、层板……）也只写在对应模型资产里；没有外形声明
# 的设备仍在这里写死 STL 包围盒。
STATION_PARTS = [
    {
        "node_id": "szlab_s07_solid_addition",
        "name": "S07 固体加料",
        # 表里 z=50 落在底板外沿倒角上，机器实际是靠 4 个地脚站在台面上
        "position": {"x": 50.0, "y": 30.0, "z": 0.0},
        "category": "carousel_feeder",
        "model": "注粉装置-20260508 市购件.STL",
        "note": (
            "模型 Y 朝上，占位取实体包围盒 503(宽)×770(深)×654.5(高)，"
            "台面上转 90° 摆放（长边沿 X），让开 y=625.5 的机械臂导轨；"
            "940.4 高里含一根伸出 300 的横杆，不算占位"
        ),
    },
    {
        "node_id": "szlab_s08_cap_station",
        "name": "S08 开关盖",
        "position": {"x": 204.5, "y": 1454.0, "z": 0.0},
        "size": {"size_x": 810.0, "size_y": 147.0, "size_z": 349.0},
        "model": "装配体11^DXY260502-06.04-00 拧盖模组/base_link.STL",
    },
    {
        "node_id": "szlab_mixer_pipetting_station",
        "name": "S09 移液站",
        "position": {"x": 1084.0, "y": 1164.0, "z": 0.0},
        "size": {"size_x": 800.0, "size_y": 470.0, "size_z": 650.0},
        "model": "merged: plate+pipetting+tip+reagent platforms",
        "note": (
            "底板 800×470×12；origin=bottom_left=底板左下角；"
            "相对 deck LL (1084,1164)；"
            "tip/reagent 相对底板 (105,98,12)/(93,0,12) mm；"
            "天平开合护罩中心相对底板 (408.5,223.5,12) mm"
        ),
    },
    {
        "node_id": "szlab_mixer_pump",
        "name": "S06 注射泵",
        "position": {"x": 812.5, "y": 183.0, "z": 0.0},
        "category": "gantry_pump",
        "model": "装配体6^DXY260502-08-00 溶剂加样/base_link.STL",
        "note": "LL=(812.5,183)；STL 原点=交点、距底边119.5mm（Rz180）",
    },
    {
        "node_id": "szlab_mixer_stirrer",
        "name": "S04 磁搅",
        "position": {"x": 1480.0, "y": 80.0, "z": 0.0},
        "category": "stirrer_rack",
        "model": "DXY260502-09-00 磁搅模块/base_link.STL",
        "note": "敞口柜前面朝 -Y，六个搅拌台位对应 S041..S046",
    },
    {
        "node_id": "szlab_mixer_photoshotting",
        "name": "S05 拍照检测",
        "position": {"x": 1105.0, "y": 84.0, "z": 0.0},
        "category": "vision_cell",
        "model": "装配体1^DXY260502-10-00 视觉检测模块/base_link.STL",
        "note": (
            "占位 340×329；中心距+Y边128→相对LL (170,201)；"
            "中心(1275,285)→LL=(1105,84)；model.position Y=+36.5mm；侧臂不计占位"
        ),
    },
]

# 机械臂：表里没给 3D 模型，但测的边属于 B17H_L50_S2700 行走轴，
# 记录点 z=208.15 即导轨顶面。臂体沿导轨可移动，画在哪由外形声明决定。
RAIL_ROBOT = {
    "node_id": "szlab_mixer_robot",
    "name": "SZLab 机械臂",
    "position": {"x": 306.85, "y": 625.5, "z": 0.0},
    "category": "rail_robot",
    "note": (
        "《理论交点测距结果》: 交点=导轨左端顶面 z=208.15; "
        "rail = B17H_L50_S2700 行走轴 (行程 2700); "
        "臂体尺寸仍为占位包络，位置沿导轨可变"
    ),
}

# 这些前缀下的数值键是 CAD 特征，现在归设备/资源自己的模型资产管。老图里还留着
# 它们（含 wall_* 这类早就改名的），导出时按前缀清掉，只清数值——设备自己的
# plc_device_id / url / auto_connect 不受影响。
LEGACY_SHAPE_KEY_PREFIXES = (
    "arm_",
    "base_plate_",
    "beam_",
    "camera_",
    "carriage_",
    "column_",
    "deck_",
    "frame_",
    "gantry_",
    "gear_",
    "hopper_",
    "hub_",
    "leg_",
    "lens_",
    "level_",
    "mount_plate_",
    "module_",
    "motor_",
    "needle_",
    "panel_",
    "plate_",
    "seat_",
    "shaft_",
    "shelf_",
    "station_",
    "top_plate_",
    "turntable_",
    "unit_",
    "wall_",
)

MATERIAL_FACTORIES: dict[str, Any] = {
    "szlab_beaker_500ml": beaker_500ml,
    "szlab_sample_vial_250ml": sample_vial_250ml,
    "szlab_sample_vial_500ml": sample_vial_500ml,
    "szlab_liquid_reagent_bottle_100ml": liquid_reagent_bottle_100ml,
    "szlab_powder_container": powder_container,
    "szlab_pipette_tip": pipette_tip,
    "szlab_tip_box": tip_box,
}

MATERIAL_DISPLAY: dict[str, str] = {
    "szlab_beaker_500ml": "烧杯 500 mL",
    "szlab_sample_vial_500ml": "样品瓶 500 mL",
    "szlab_liquid_reagent_bottle_100ml": "试剂瓶 100 mL",
    "szlab_powder_container": "注粉瓶",
    "szlab_tip_box": "TIP 盒",
}

# 样品瓶位点已并入烧杯堆栈的 A 行（3 层 × 6 列 = 18，正好对应 PLC 的样品瓶
# 传感器组），独立的样品瓶仓连同仓里那个 250 mL 调试瓶一起从图里删掉。
DROPPED_NODES = (
    "s3_unused_vial",
    "s11_used_vial",
    "debug_sample_vial_250ml",
)

# 保留既有调试物料 id，避免 e2e/文档里的引用失效
RESERVED_OCCUPANTS: dict[tuple[str, str], str] = {
    ("s3_unused_beaker", "L1B1"): "debug_beaker_500ml",
    ("s10_liquid_reagent", "R1C1"): "debug_reagent_bottle_100ml",
    ("powder_container_warehouse", "L1C1"): "debug_powder_container",
}

# s1_workstation 与 deck 同足迹：deck 作为其子节点。
# deck 高度 0；局部 z = workstation 高度，铺在台面上方便 3D 显示。
DEVICE_SIZES: dict[str, dict[str, float]] = {
    "szlab_poly_plc": {"size_x": 200.0, "size_y": 120.0, "size_z": 80.0},
    "s1_workstation": {
        "size_x": DECK_SIZE["size_x"],
        "size_y": DECK_SIZE["size_y"],
        "size_z": S1_WORKSTATION_HEIGHT_MM,
    },
}


def _shape_envelopes() -> dict[str, dict[str, float]]:
    """按 category 取包内外形声明的 envelope，当设备占位尺寸。

    每个尺寸只写在归属设备或资源的 ``models/shape.yml``：模型图元与包络天然一起迁移。
    """

    package_root = Path(str(resources.files("szlab_poly_studio")))
    envelopes: dict[str, dict[str, float]] = {}
    for shape_path in package_root.glob("**/models/shape.yml"):
        payload = yaml.safe_load(shape_path.read_text(encoding="utf-8")) or {}
        shape = payload.get("shape") or {}
        envelope = shape.get("envelope")
        if not envelope:
            continue
        size = {
            "size_x": float(envelope[0]),
            "size_y": float(envelope[1]),
            "size_z": float(envelope[2]),
        }
        for rule in shape.get("applies_to") or []:
            category = rule.get("category")
            if category:
                envelopes[str(category)] = size
    return envelopes


def _clean_shape_config(node: dict[str, Any]) -> dict[str, Any]:
    """清掉老图里残留的 CAD 数值键，返回该节点的 config。"""

    cfg: dict[str, Any] = node.setdefault("config", {})
    for key in [
        key
        for key, value in cfg.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and key.startswith(LEGACY_SHAPE_KEY_PREFIXES)
    ]:
        del cfg[key]
    return cfg


def _site(
    *,
    label: str,
    x: float,
    y: float,
    z: float,
    width: float,
    height: float,
    depth: float,
    content_types: list[str],
    occupied_by: str | None = None,
) -> dict[str, Any]:
    site: dict[str, Any] = {
        "label": label,
        "name": label,
        "position": {"x": x, "y": y, "z": z},
        "size": {"width": width, "height": height, "depth": depth},
        "content_type": content_types,
        "visible": True,
    }
    if occupied_by:
        site["occupied_by"] = occupied_by
    return site


def _tip_rack_sites() -> list[dict[str, Any]]:
    """3 层 × 2 个 TIP 盒工位（相对 tip 架左下角）。"""

    first = TIP_RACK["first_slot"]
    slot_size = TIP_RACK["slot_size"]
    return [
        _site(
            label=f"T{row + 1}{col + 1}",
            x=first["x"] + col * TIP_RACK["col_dx"],
            y=first["y"],
            z=first["z"] + row * TIP_RACK["row_dz"],
            width=slot_size["width"],
            height=slot_size["height"],
            depth=slot_size["depth"],
            content_types=["szlab_tip_box"],
        )
        for row in range(TIP_RACK["rows"])
        for col in range(TIP_RACK["cols"])
    ]


def _tip_box_sites(slot_label: str, *, rotated: bool = False) -> list[dict[str, Any]]:
    """TIP 盒内 4 列 × 6 行枪头孔（相对 TIP 盒左下角）。

    ``rotated`` 给盒子转 90° 摆放的工位用（S1 上料过渡仓），孔阵随盒体一起转。
    """

    diameter = TIP_BOX["tip_diameter"]
    cols, rows = TIP_BOX["cols"], TIP_BOX["rows"]
    first_x, first_y = TIP_BOX["first_tip"]["x"], TIP_BOX["first_tip"]["y"]
    if rotated:
        cols, rows = rows, cols
        first_x, first_y = first_y, first_x
    return [
        _site(
            label=f"{slot_label}-tip-{row + 1}{col + 1:02d}",
            x=first_x + col * TIP_BOX["pitch"] - diameter / 2.0,
            y=first_y + row * TIP_BOX["pitch"] - diameter / 2.0,
            z=TIP_BOX["plate_z"],
            width=diameter,
            height=diameter,
            depth=23.0,
            content_types=["szlab_pipette_tip"],
        )
        for row in range(rows)
        for col in range(cols)
    ]


def _carrier_sites(
    carrier,
    *,
    content_types: list[str],
) -> list[dict[str, Any]]:
    """从 BottleCarrier._ordering 导出 config.sites。"""

    sites: list[dict[str, Any]] = []
    for label, holder in carrier._ordering.items():
        loc = holder.location
        sites.append(
            _site(
                label=label,
                x=float(loc.x),
                y=float(loc.y),
                z=float(loc.z),
                width=float(holder.get_size_x()),
                height=float(holder.get_size_y()),
                depth=float(holder.get_size_z()),
                content_types=list(content_types),
            )
        )
    return sites


def _beaker_stack_sites(carrier) -> list[dict[str, Any]]:
    """从 SZLab_BeakerStackCarrier 导出 config.sites（A=样品瓶 / B=烧杯）。"""

    sites: list[dict[str, Any]] = []
    for label, holder in carrier._ordering.items():
        loc = holder.location
        row_ch = label[2]  # A=500mL样品瓶, B=烧杯
        if row_ch == "A":
            content_types = ["szlab_sample_vial_500ml"]
        else:
            content_types = ["szlab_beaker_500ml"]
        sites.append(
            _site(
                label=label,
                x=float(loc.x),
                y=float(loc.y),
                z=float(loc.z),
                width=float(holder.get_size_x()),
                height=float(holder.get_size_y()),
                depth=float(holder.get_size_z()),
                content_types=content_types,
            )
        )
    return sites


def _drop_nodes(out: dict[str, Any], dropped: tuple[str, ...]) -> None:
    """删除节点：清掉 children / links 里的引用，原有子节点退回未放置。"""

    out["nodes"] = [n for n in out["nodes"] if str(n["id"]) not in dropped]
    for node in out["nodes"]:
        children = node.get("children")
        if children:
            node["children"] = [c for c in children if c not in dropped]
        if str(node.get("parent")) in dropped:
            node["parent"] = None
    links = out.get("links")
    if links:
        out["links"] = [
            link for link in links if str(link.get("source")) not in dropped and str(link.get("target")) not in dropped
        ]


def _apply_layout(graph: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(graph)
    _drop_nodes(out, DROPPED_NODES)
    nodes_by_id = {str(n["id"]): n for n in out["nodes"]}

    deck = nodes_by_id["szlab_poly_deck"]
    deck.setdefault("config", {}).update(DECK_SIZE)
    deck["parent"] = "s1_workstation"
    deck["position"] = {"x": 0.0, "y": 0.0, "z": DECK_LOCAL_Z_MM}

    s1 = nodes_by_id.get("s1_workstation")
    if s1 is not None:
        s1["parent"] = None
        s1["position"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        s1.setdefault("config", {}).update(DEVICE_SIZES["s1_workstation"])
        s1_children = list(s1.get("children") or [])
        if "szlab_poly_deck" not in s1_children:
            s1_children.insert(0, "szlab_poly_deck")
        s1["children"] = s1_children

    # Tip rack
    tip = nodes_by_id[TIP_RACK["node_id"]]
    tip["name"] = "Tip 头架子"
    tip["position"] = dict(TIP_RACK["position"])
    tip["parent"] = "szlab_poly_deck"
    tip_cfg = tip.setdefault("config", {})
    tip_cfg.update(TIP_RACK["size"])
    tip_cfg["sites"] = _tip_rack_sites()
    # category 决定 2.5D 外形：敞口层架
    tip_cfg["category"] = "tip_stack"
    tip_cfg["num_items_x"] = TIP_RACK["cols"]
    tip_cfg["num_items_y"] = 1
    tip_cfg["num_items_z"] = TIP_RACK["rows"]
    tip_cfg["layout_note"] = (
        "origin=bottom-left; CAD DXY260502-02-00; frame 310x140x558; "
        "3 shelves (z=120/320/520) x 2 tip-box slots (86x128x136); "
        "tips live in the tip box (4 cols x 6 rows, pitch 18)"
    )

    # Beaker stacks — 两个规格相同，共用 s3 烧杯堆栈类型（同一 3D mesh）
    for stack in BEAKER_STACKS:
        carrier = SZLab_BeakerStackCarrier(stack["name"], fill_placeholders=False)
        node = nodes_by_id[stack["node_id"]]
        node["name"] = stack["name"]
        node["position"] = dict(stack["position"])
        node["parent"] = "szlab_poly_deck"
        node["class"] = "szlab_poly_beaker_warehouse"
        cfg = node.setdefault("config", {})
        cfg["size_x"] = float(carrier.get_size_x())
        cfg["size_y"] = float(carrier.get_size_y())
        cfg["size_z"] = float(carrier.get_size_z())
        cfg["sites"] = _beaker_stack_sites(carrier)
        # category 决定 2.5D 外形：敞口层架（背板/侧板/每层层板，前面开放）
        cfg["category"] = "beaker_stack"
        cfg["num_items_x"] = int(carrier.num_items_x)
        cfg["num_items_y"] = int(carrier.num_items_y)
        cfg["num_items_z"] = int(carrier.num_items_z)
        cfg["layout_note"] = (
            "origin=bottom-left; SZLab_BeakerStackCarrier 3x6x2; "
            "L{layer}A{col}=sample_vial_500ml(+50,+50), "
            "L{layer}B{col}=beaker_500ml(+50,+150); "
            "class=szlab_poly_beaker_warehouse (S3/S11 shared)"
        )

    # Reagent bottle stack — SZLab_ReagentBottleStackCarrier
    reagent_carrier = SZLab_ReagentBottleStackCarrier(REAGENT_STACK["name"], fill_placeholders=False)
    reagent_node = nodes_by_id[REAGENT_STACK["node_id"]]
    reagent_node["name"] = REAGENT_STACK["name"]
    reagent_node["position"] = dict(REAGENT_STACK["position"])
    reagent_node["parent"] = "szlab_poly_deck"
    reagent_cfg = reagent_node.setdefault("config", {})
    reagent_cfg["size_x"] = float(reagent_carrier.get_size_x())
    reagent_cfg["size_y"] = float(reagent_carrier.get_size_y())
    reagent_cfg["size_z"] = float(reagent_carrier.get_size_z())
    reagent_cfg["sites"] = _carrier_sites(
        reagent_carrier,
        content_types=["szlab_liquid_reagent_bottle_100ml"],
    )
    # 同烧杯堆栈：敞口层架外形
    reagent_cfg["category"] = "reagent_stack"
    reagent_cfg["num_items_x"] = int(reagent_carrier.num_items_x)
    reagent_cfg["num_items_y"] = int(reagent_carrier.num_items_y)
    reagent_cfg["num_items_z"] = int(reagent_carrier.num_items_z)
    reagent_cfg["layout_note"] = (
        "origin=bottom-left; SZLab_ReagentBottleStackCarrier; 4x5 slots, first center (80,50,70) Ø56, dx=100, dz=165"
    )

    # Powder container stack — SZLab_PowderContainerStackCarrier
    powder_carrier = SZLab_PowderContainerStackCarrier(POWDER_STACK["name"], fill_placeholders=False)
    powder_node = nodes_by_id[POWDER_STACK["node_id"]]
    powder_node["name"] = POWDER_STACK["name"]
    powder_node["position"] = dict(POWDER_STACK["position"])
    powder_node["parent"] = "szlab_poly_deck"
    powder_cfg = powder_node.setdefault("config", {})
    powder_cfg["size_x"] = float(powder_carrier.get_size_x())
    powder_cfg["size_y"] = float(powder_carrier.get_size_y())
    powder_cfg["size_z"] = float(powder_carrier.get_size_z())
    powder_cfg["sites"] = _carrier_sites(
        powder_carrier,
        content_types=["szlab_powder_container"],
    )
    # 同其他堆栈：敞口层架外形
    powder_cfg["category"] = "powder_stack"
    powder_cfg["num_items_x"] = int(powder_carrier.num_items_x)
    powder_cfg["num_items_y"] = int(powder_carrier.num_items_y)
    powder_cfg["num_items_z"] = int(powder_carrier.num_items_z)
    powder_cfg["layout_note"] = (
        "origin=bottom-left; CAD DXY260502-05-00; frame 100x370x531 (长边沿Y); "
        "2 层 × 3 位，首位点中心 (50, 85, 210)，Δy=100，Δz=310; "
        "位点物料=注粉瓶 Ø70x190 (注粉瓶-20260508.STL)"
    )

    # S1 上料过渡仓 — SZLab_TipBoxLoaderCarrier
    loader_carrier = SZLab_TipBoxLoaderCarrier(TIP_BOX_LOADER["name"], fill_placeholders=False)
    loader_node = nodes_by_id[TIP_BOX_LOADER["node_id"]]
    loader_node["name"] = TIP_BOX_LOADER["name"]
    loader_node["position"] = dict(TIP_BOX_LOADER["position"])
    loader_node["parent"] = "szlab_poly_deck"
    loader_cfg = loader_node.setdefault("config", {})
    loader_cfg["size_x"] = float(loader_carrier.get_size_x())
    loader_cfg["size_y"] = float(loader_carrier.get_size_y())
    loader_cfg["size_z"] = float(loader_carrier.get_size_z())
    loader_cfg["sites"] = _carrier_sites(
        loader_carrier,
        content_types=["szlab_tip_box"],
    )
    # 同 tip 头架子：敞口层架外形
    loader_cfg["category"] = "tip_stack"
    loader_cfg["num_items_x"] = int(loader_carrier.num_items_x)
    loader_cfg["num_items_y"] = int(loader_carrier.num_items_y)
    loader_cfg["num_items_z"] = int(loader_carrier.num_items_z)
    loader_cfg["layout_note"] = (
        "origin=bottom-left; CAD DXY260502-13.03-00 tip盒上料工装 "
        "(本体 441.9x200x402.8); 台面上转 90°，占位 200x442x403; "
        "2 层托板 z=70/260，每层 3 个 TIP 盒（转 90° 后 128x86x136），"
        "盒位中心 x=70, y=101/221/341"
    )

    # 表格实测落位的工站设备
    envelopes = _shape_envelopes()
    for part in STATION_PARTS:
        node = nodes_by_id[part["node_id"]]
        node["position"] = dict(part["position"])
        cfg = _clean_shape_config(node)
        category = part.get("category")
        if category:
            cfg["category"] = category
            cfg.update(envelopes[str(category)])
        else:
            cfg.update(part["size"])
        note = "《理论交点测距结果》: 交点=占位左下角(x/y)+底面(z)"
        if part["model"]:
            note = f"{note}; size=bbox of {part['model']}"
        if part.get("note"):
            note = f"{note}; {part['note']}"
        cfg["layout_note"] = note

    robot = nodes_by_id[RAIL_ROBOT["node_id"]]
    robot["position"] = dict(RAIL_ROBOT["position"])
    robot_cfg = _clean_shape_config(robot)
    robot_cfg["category"] = RAIL_ROBOT["category"]
    robot_cfg.update(envelopes[str(RAIL_ROBOT["category"])])
    robot_cfg["layout_note"] = RAIL_ROBOT["note"]

    # Ensure deck children include updated warehouses
    children = list(deck.get("children") or [])
    for node_id in (
        TIP_RACK["node_id"],
        TIP_BOX_LOADER["node_id"],
        *(s["node_id"] for s in BEAKER_STACKS),
        REAGENT_STACK["node_id"],
        POWDER_STACK["node_id"],
    ):
        if node_id not in children:
            children.append(node_id)
    deck["children"] = children

    # Material container sizes from Python factories
    for node in out["nodes"]:
        factory = MATERIAL_FACTORIES.get(str(node.get("class") or ""))
        if factory is None:
            continue
        resource = factory(name=str(node.get("name") or node["id"]))
        cfg = node.setdefault("config", {})
        cfg["size_x"] = float(resource.get_size_x())
        cfg["size_y"] = float(resource.get_size_y())
        cfg["size_z"] = float(resource.get_size_z())
        # category 决定 2.5D 的外形（瓶 / 烧杯）
        cfg["category"] = str(resource.category)

    for node in out["nodes"]:
        if str(node.get("type") or "") != "device":
            continue
        sizes = DEVICE_SIZES.get(str(node.get("id") or ""))
        if sizes:
            node.setdefault("config", {}).update(sizes)

    # 各堆栈的每个位点都摆上对应物料实例
    for node_id in (
        *(s["node_id"] for s in BEAKER_STACKS),
        REAGENT_STACK["node_id"],
        POWDER_STACK["node_id"],
    ):
        _fill_stack_slots(out, nodes_by_id, node_id)

    # Tip 架的 6 个工位放入 TIP 盒组件，枪头孔挂在 TIP 盒自己身上
    _fill_stack_slots(out, nodes_by_id, TIP_RACK["node_id"], inner_sites=_tip_box_sites)

    # S1 上料过渡仓同样是 6 个 TIP 盒，只是整台工装转了 90°
    _fill_stack_slots(
        out,
        nodes_by_id,
        TIP_BOX_LOADER["node_id"],
        inner_sites=lambda label: _tip_box_sites(label, rotated=True),
        rotate_contents=True,
    )

    return out


def _fill_stack_slots(
    out: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    node_id: str,
    inner_sites: Callable[[str], list[dict[str, Any]]] | None = None,
    rotate_contents: bool = False,
) -> int:
    """给堆栈的每个位点生成/复用一个物料节点，并写回 occupied_by。

    ``inner_sites`` 用于物料自身还带位点的场景（如 TIP 盒里的枪头孔）。
    ``rotate_contents`` 用于物料在该工位转 90° 摆放，占位的 X/Y 互换。
    """

    node = nodes_by_id[node_id]
    children = list(node.get("children") or [])
    filled = 0

    for site in node["config"]["sites"]:
        label = str(site["label"])
        content = (site.get("content_type") or [None])[0]
        factory = MATERIAL_FACTORIES.get(str(content))
        if factory is None:
            continue

        material_id = RESERVED_OCCUPANTS.get((node_id, label), f"{node_id}__{label}")
        display = MATERIAL_DISPLAY.get(str(content), str(content))
        resource = factory(name=material_id)

        material = nodes_by_id.get(material_id)
        if material is None:
            material = {"id": material_id, "children": [], "data": {}}
            out["nodes"].append(material)
            nodes_by_id[material_id] = material

        material["name"] = f"{node['name']} {label} {display}"
        material["type"] = "container"
        material["class"] = str(content)
        material["parent"] = node_id
        material["position"] = dict(site["position"])
        size_x = float(resource.get_size_x())
        size_y = float(resource.get_size_y())
        if rotate_contents:
            size_x, size_y = size_y, size_x
        material["config"] = {
            "size_x": size_x,
            "size_y": size_y,
            "size_z": float(resource.get_size_z()),
            "category": str(resource.category),
        }
        if inner_sites is not None:
            material["config"]["sites"] = inner_sites(label)
        site["occupied_by"] = material_id
        if material_id not in children:
            children.append(material_id)
        # 迁移时清理旧父节点的引用
        for other in out["nodes"]:
            if other["id"] == node_id:
                continue
            other_children = other.get("children") or []
            if material_id in other_children:
                other["children"] = [child for child in other_children if child != material_id]
        filled += 1

    node["children"] = children
    return filled


def _record_sites(node: dict[str, Any]) -> list[dict[str, Any]]:
    sites = (node.get("config") or {}).get("sites")
    return sites if isinstance(sites, list) else []


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    default_graph = repo / "deployment" / "graphs" / "szlab-local-debug.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=default_graph)
    parser.add_argument("--output", type=Path, default=default_graph)
    args = parser.parse_args()

    graph = json.loads(args.input.read_text(encoding="utf-8"))
    enriched = _apply_layout(graph)
    args.output.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    tip_count = next(len(n["config"]["sites"]) for n in enriched["nodes"] if n["id"] == TIP_RACK["node_id"])
    loader_count = next(len(n["config"]["sites"]) for n in enriched["nodes"] if n["id"] == TIP_BOX_LOADER["node_id"])
    beaker_counts = {
        s["node_id"]: next(len(n["config"]["sites"]) for n in enriched["nodes"] if n["id"] == s["node_id"])
        for s in BEAKER_STACKS
    }
    reagent_count = next(len(n["config"]["sites"]) for n in enriched["nodes"] if n["id"] == REAGENT_STACK["node_id"])
    powder_count = next(len(n["config"]["sites"]) for n in enriched["nodes"] if n["id"] == POWDER_STACK["node_id"])
    placed: dict[str, int] = {}
    tip_spots = 0
    for node in enriched["nodes"]:
        klass = str(node.get("class") or "")
        if klass in MATERIAL_DISPLAY:
            placed[klass] = placed.get(klass, 0) + 1
        if klass == "szlab_tip_box":
            tip_spots += len(_record_sites(node))

    print(
        f"Wrote {args.output}\n"
        f"  deck={DECK_SIZE}\n"
        f"  tip_slots={tip_count} loader_slots={loader_count} "
        f"tip_spots_in_boxes={tip_spots}\n"
        f"  beaker_sites={beaker_counts}\n"
        f"  reagent_sites={reagent_count} powder_sites={powder_count}\n"
        f"  stations={{"
        + ", ".join(f"{p['node_id']}@{p['position']['x']},{p['position']['y']}" for p in (*STATION_PARTS, RAIL_ROBOT))
        + "}\n"
        f"  placed_materials={placed}"
    )


if __name__ == "__main__":
    main()
