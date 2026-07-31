"""SZLab 试剂瓶堆栈载架 — 写法对齐 Uni-Lab-OS bioyond bottle_carriers。

坐标约定：相对载架左下角 (mm)。
4 行（层）× 每行 5 列 = 20 位；每层仅 1 行 y。
首 slot 圆心 (80, 50, 70)，直径 56；同行 Δx=100，行间 Δz=165。
"""

from __future__ import annotations

from typing import Dict, Union

from pylabrobot.resources import ResourceHolder, create_ordered_items_2d
from unilabos.resources.itemized_carrier import BottleCarrier, ResourcePLR

from szlab_poly_studio.materials import liquid_reagent_bottle_100ml


def SZLab_ReagentBottleStackCarrier(
    name: str,
    *,
    fill_placeholders: bool = True,
) -> BottleCarrier:
    """SZLab 试剂瓶堆栈 - 4 层 × 5 列

    参数:
    - name: 载架名称前缀
    - fill_placeholders: 是否在每个位点放入占位试剂瓶

    说明:
    - 载架尺寸 L560 × W120 × H565
    - 首 slot 圆心 (80, 50, 70)，Ø56
    - create_ordered_items_2d 每层 5×1；标签 R{行}C{列}
    """

    # 载架尺寸 (mm)
    carrier_size_x = 560.0
    carrier_size_y = 120.0
    carrier_size_z = 565.0

    num_cols = 5
    num_layers = 4
    bottle_diameter = 56.0
    first_center_x = 80.0
    first_center_y = 50.0
    first_center_z = 70.0
    col_dx = 100.0
    layer_dz = 165.0

    # 圆心 → holder 左下角
    start_x = first_center_x - bottle_diameter / 2.0
    start_y = first_center_y - bottle_diameter / 2.0

    sites: Dict[Union[int, str], ResourcePLR] = {}
    ordering: list[str] = []

    for layer in range(num_layers):
        layer_sites = create_ordered_items_2d(
            klass=ResourceHolder,
            num_items_x=num_cols,
            num_items_y=1,
            dx=start_x,
            dy=start_y,
            dz=first_center_z + layer * layer_dz,
            item_dx=col_dx,
            item_dy=0.0,
            size_x=bottle_diameter,
            size_y=bottle_diameter,
            size_z=bottle_diameter,
        )
        # 单行：键序 A1..A5（或等价）；按列索引重标为 R{层}C{列}
        for col, (_plr_key, holder) in enumerate(layer_sites.items()):
            label = f"R{layer + 1}C{col + 1}"
            holder.name = f"{name}_{label}"
            sites[label] = holder
            ordering.append(label)

    carrier = BottleCarrier(
        name=name,
        size_x=carrier_size_x,
        size_y=carrier_size_y,
        size_z=carrier_size_z,
        sites=sites,
        model="SZLab_ReagentBottleStackCarrier",
    )
    carrier.num_items_x = num_cols
    carrier.num_items_y = 1
    carrier.num_items_z = num_layers

    if fill_placeholders:
        for label in ordering:
            layer_ch = label[1]
            col_ch = label[3:]
            carrier[label] = liquid_reagent_bottle_100ml(
                name=f"{name}_reagent_R{layer_ch}C{col_ch}"
            )

    return carrier
