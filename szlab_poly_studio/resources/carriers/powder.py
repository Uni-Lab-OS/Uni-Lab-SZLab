"""SZLab 固体粉桶堆栈载架 — 写法对齐 Uni-Lab-OS bioyond bottle_carriers。

外框取自 CAD（装配体9^DXY260502-05-00 粉桶堆栈）：长边 370 沿 Y 竖摆，
占位 100 × 370 × 531。位点为实测：2 行 × 3 列 = 6 个，第一个位点中心
(50, 85, 210)，同行 Δy=100，行间 Δz=310。位点里放注粉瓶（Ø70 × 190，
窄嘴朝下落进层板的 Ø50 挂孔）。
"""

from __future__ import annotations

from typing import Dict, Union

from pylabrobot.resources import ResourceHolder, create_ordered_items_2d
from unilabos.resources.itemized_carrier import BottleCarrier, ResourcePLR

from szlab_poly_studio.resources.materials import powder_container


def SZLab_PowderContainerStackCarrier(
    name: str,
    *,
    fill_placeholders: bool = True,
) -> BottleCarrier:
    """SZLab 固体粉桶堆栈 - 2 层 × 3 列

    参数:
    - name: 载架名称前缀
    - fill_placeholders: 是否在每个位点放入占位注粉瓶

    说明:
    - 载架尺寸 W100 × L370 × H531（长边沿 Y）
    - 首位点中心 (50, 85, 210)，同层 Δy=100，层间 Δz=310
    - 标签 L{层}C{列}
    """

    # 载架尺寸 (mm)
    carrier_size_x = 100.0
    carrier_size_y = 370.0
    carrier_size_z = 531.0

    num_cols = 3
    num_layers = 2
    first_center_x = 50.0
    first_center_y = 85.0
    first_seat_z = 210.0
    col_dy = 100.0
    layer_dz = 310.0

    # 位点按注粉瓶外径取（Ø70 的锥面卡在层板 Ø50 挂孔上）
    bottle_diameter = 70.0

    start_x = first_center_x - bottle_diameter / 2.0
    start_y = first_center_y - bottle_diameter / 2.0

    sites: Dict[Union[int, str], ResourcePLR] = {}
    ordering: list[str] = []

    for layer in range(num_layers):
        layer_sites = create_ordered_items_2d(
            klass=ResourceHolder,
            num_items_x=1,
            num_items_y=num_cols,
            dx=start_x,
            dy=start_y,
            dz=first_seat_z + layer * layer_dz,
            item_dx=0.0,
            item_dy=col_dy,
            size_x=bottle_diameter,
            size_y=bottle_diameter,
            size_z=bottle_diameter,
        )
        # PLR 的字母行从高 y 排起，这里按 y 递增编号，C1 = 首位点
        for col, (_plr_key, holder) in enumerate(
            reversed(list(layer_sites.items()))
        ):
            label = f"L{layer + 1}C{col + 1}"
            holder.name = f"{name}_{label}"
            sites[label] = holder
            ordering.append(label)

    carrier = BottleCarrier(
        name=name,
        size_x=carrier_size_x,
        size_y=carrier_size_y,
        size_z=carrier_size_z,
        sites=sites,
        model="SZLab_PowderContainerStackCarrier",
    )
    carrier.num_items_x = 1
    carrier.num_items_y = num_cols
    carrier.num_items_z = num_layers

    if fill_placeholders:
        for label in ordering:
            carrier[label] = powder_container(name=f"{name}_powder_{label}")

    return carrier
